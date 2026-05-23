# Chapter 29: Container Design

Containers are the backbone of data structure reuse in C++. The standard library provides `vector`, `deque`, `list`, `map`, `set`, `unordered_map`, and their variants, each optimized for a different access pattern. But no library can anticipate every requirement. Domain-specific data structures — ring buffers, interval maps, sparse sets, priority queues with custom update semantics — demand custom containers.

Designing a container in C++ is different from designing one in Java, Python, or C#. The language's value semantics, manual memory management, and template-based polymorphism impose a specific set of constraints: allocator awareness, iterator compatibility with standard algorithms, exception safety guarantees, and correct move/copy semantics. A container that does not handle these correctly will silently produce undefined behavior when used with standard library components.

This chapter covers four aspects of container design that distinguish a production-quality container from a quick script. The first — Custom Allocator Integration — shows how to make your container work with custom memory resources, including stateful allocators and `std::pmr`. The second — Iterator Design and Traits — explains how to write iterators that interoperate with the standard library's algorithm and range infrastructure. The third — Emplace vs Insert Semantics — examines the distinction between constructing elements in place and inserting already-constructed values, and the exception‑safety implications of each. The fourth — Type-Erased Containers — explores containers that store heterogeneous types through the type-erasure idiom, and the trade-offs involved.

---

## Custom Allocator Integration

The C++ standard library containers are **allocator-aware**: they accept an allocator type as a template parameter and use it for all memory management. This design lets users replace the default `std::allocator` with custom allocators that pool memory, use shared memory, or provide alignment guarantees. If you write a custom container, making it allocator-aware ensures it composes with the same allocator infrastructure that standard containers use.

### Allocator Requirements

An allocator in C++ is a class that satisfies the **Allocator** named requirement. At minimum, it must provide:

```cpp
template <typename T>
class Allocator {
public:
    using value_type = T;

    Allocator() = default;

    template <typename U>
    Allocator(const Allocator<U>&);  // rebinding constructor

    T* allocate(std::size_t n);           // allocate storage for n T's
    void deallocate(T* p, std::size_t n); // deallocate storage

    // Since C++17 (optional but expected):
    // template <typename... Args>
    // void construct(T* p, Args&&... args);
    // void destroy(T* p);
};
```

The rebinding constructor is what makes allocators generic: a `vector<T>` uses `allocator<T>`, but it internally needs to allocate memory for a raw buffer (conceptually `allocator<byte>`). The rebinding constructor `Allocator(const Allocator<U>&)` lets the container obtain an allocator for a different type from its own allocator. The standard library provides `std::allocator_traits` as a uniform interface, so your container should never call allocator methods directly — it should go through `allocator_traits`.

### Using allocator_traits Instead of Direct Calls

`std::allocator_traits<Alloc>` normalizes the allocator interface. It provides default implementations for optional allocator methods (like `construct` and `destroy`) so that your container works with minimal allocators that only provide `allocate` and `deallocate`:

```cpp
template <typename T, typename Alloc = std::allocator<T>>
class RingBuffer {
    using traits = std::allocator_traits<Alloc>;
    using pointer = typename traits::pointer;

    Alloc alloc_;       // the allocator instance
    pointer data_ = nullptr;
    size_t capacity_ = 0;
    size_t head_ = 0;
    size_t size_ = 0;

public:
    explicit RingBuffer(const Alloc& alloc = {})
        : alloc_(alloc) {}

    void reserve(size_t n) {
        if (n <= capacity_) return;
        auto new_data = traits::allocate(alloc_, n);
        for (size_t i = 0; i < size_; ++i) {
            traits::construct(alloc_, new_data + i, std::move(data_[(head_ + i) % capacity_]));
            traits::destroy(alloc_, data_ + (head_ + i) % capacity_);
        }
        if (data_) {
            traits::deallocate(alloc_, data_, capacity_);
        }
        data_ = new_data;
        capacity_ = n;
        head_ = 0;
    }

    void push_back(const T& value) {
        if (size_ == capacity_) {
            reserve(capacity_ * 2 + 1);
        }
        size_t pos = (head_ + size_) % capacity_;
        // Use traits::construct for in-place construction.
        traits::construct(alloc_, data_ + pos, value);
        ++size_;
    }

    ~RingBuffer() {
        // Destroy all elements.
        for (size_t i = 0; i < size_; ++i) {
            traits::destroy(alloc_, data_ + (head_ + i) % capacity_);
        }
        if (data_) {
            traits::deallocate(alloc_, data_, capacity_);
        }
    }
};
```

Using `allocator_traits::construct` instead of placement new is important because it respects allocators that have a custom `construct` method (e.g., `std::scoped_allocator_adaptor`), and it falls back to placement new if the allocator does not provide one. Similarly, `traits::destroy` calls the destructor through the allocator, which matters for allocators that track object lifetimes.

### Stateful vs. Stateless Allocators

An allocator is **stateless** if all instances of the same allocator type are interchangeable — copying one produces a functionally identical allocator. `std::allocator<T>` is stateless. A **stateful** allocator carries per-instance state, such as a pointer to a memory pool or arena:

```cpp
class Arena {
    char* buffer_;
    size_t size_;
    size_t offset_ = 0;
public:
    Arena(char* buffer, size_t size) : buffer_(buffer), size_(size) {}
    // Not copyable — each arena is unique.
    Arena(const Arena&) = delete;
    Arena& operator=(const Arena&) = delete;

    void* alloc(size_t size, size_t alignment) {
        size_t space = size_ - offset_;
        void* ptr = buffer_ + offset_;
        if (std::align(alignment, size, ptr, space)) {
            offset_ = (static_cast<char*>(ptr) + size) - buffer_;
            return ptr;
        }
        return nullptr;
    }
};

template <typename T>
class ArenaAllocator {
    Arena* arena_;
public:
    using value_type = T;

    explicit ArenaAllocator(Arena& arena) : arena_(&arena) {}

    template <typename U>
    ArenaAllocator(const ArenaAllocator<U>& other)
        : arena_(other.arena_) {}

    T* allocate(std::size_t n) {
        // Bump-allocate from the arena.
        return static_cast<T*>(arena_->alloc(n * sizeof(T), alignof(T)));
    }

    void deallocate(T*, std::size_t) {
        // Arena allocators typically do not support individual deallocation.
        // The entire arena is freed at once.
    }

private:
    template <typename U> friend class ArenaAllocator;
};
```

Stateful allocators introduce a subtlety: when a container is copied, should the copy use the same allocator as the original, or should it use a default-constructed allocator? The standard library defines three **propagation policies** that an allocator can advertise through nested type aliases:

```cpp
template <typename T>
class MyAllocator {
public:
    using value_type = T;

    // Propagate on copy assignment.
    using propagate_on_container_copy_assignment = std::true_type;
    // Propagate on move assignment.
    using propagate_on_container_move_assignment = std::true_type;
    // Propagate on swap.
    using propagate_on_container_swap = std::true_type;

    // ...
};
```

- `propagate_on_container_copy_assignment::value` — if `true`, the allocator is copied during container copy-assignment; if `false`, the container keeps its original allocator and the elements are copy-assigned element by element.
- `propagate_on_container_move_assignment` — if `true`, the allocator is moved during container move-assignment; if `false`, the allocator stays and elements are moved element by element.
- `propagate_on_container_swap` — if `true`, allocators are swapped during container swap; if `false`, swapping containers with unequal allocators is undefined behavior.

The default for all three is `std::false_type`. You should set them to `true` for stateless allocators (it does not matter) and to the appropriate value for stateful allocators depending on your usage. For an arena allocator, you almost certainly want `propagate_on_container_copy_assignment` to be `false` — copying a container should not move it to a different arena.

### The Scoped Allocator Pattern

When a container holds elements that are themselves allocator-aware (like a `vector` of `strings`), a subtle question arises: which allocator should the nested elements use? The **scoped allocator** pattern says: the container passes its own allocator to the elements' constructors. This ensures that all memory for the entire tree of objects comes from the same source.

`std::scoped_allocator_adaptor` (in `<scoped_allocator>`) implements this pattern. If your custom container holds allocator-aware types with the same allocator type, you can use `std::scoped_allocator_adaptor<OuterAlloc>` as the allocator for the outer container. The adaptor automatically passes itself (or a rebound copy) to inner elements during construction.

For a custom container to support scoped allocators, it must propagate the allocator to elements when it constructs them. This happens automatically if you use `allocator_traits::construct(alloc_, ptr, args...)`, because `scoped_allocator_adaptor`'s `construct` overload will forward the allocator to the element's constructor.

### Polymorphic Allocators (std::pmr)

C++17 introduced `std::pmr::polymorphic_allocator`, which wraps a runtime-polymorphic `std::pmr::memory_resource` pointer. Unlike template-based allocators (which are compile-time parameters), polymorphic allocators let you change the memory resource at runtime without changing the container's type:

```cpp
#include <memory_resource>

std::array<std::byte, 1024> buffer;
std::pmr::monotonic_buffer_resource pool(buffer.data(), buffer.size());

std::pmr::vector<int> vec(&pool);  // Uses the monotonic buffer.
vec.push_back(42);                 // Allocated from the buffer.
```

If your custom container supports the standard allocator interface, it already works with `std::pmr::polymorphic_allocator` — just provide an alias for convenience:

```cpp
namespace pmr {
    template <typename T>
    using RingBuffer = RingBuffer<T, std::pmr::polymorphic_allocator<T>>;
}
```

The key implication of polymorphic allocators is that the container type no longer encodes the allocator. `pmr::vector<int>` is the same type whether it uses a monotonic buffer resource, a pool resource, or the default `new_delete_resource`. This simplifies interfaces — functions can accept `pmr::vector<int>` without template parameters — at the cost of a virtual call per allocation.

### Allocator-Aware Container Checklist

When making a custom container allocator-aware, the standard library's container requirements (Table 80 of the C++ standard) specify what must be supported:

1. **A template parameter** `Alloc` with default `std::allocator<T>`.
2. **A member type** `allocator_type` equal to `Alloc`.
3. **A constructor** `Container(const Alloc&)` that creates an empty container with the given allocator.
4. **A constructor** `Container(const Container& other)` that copies elements using `traits::select_on_container_copy_construction(other.alloc_)`.
5. **Copy assignment** that respects `propagate_on_container_copy_assignment`.
6. **Move assignment** that respects `propagate_on_container_move_assignment`.
7. **`swap`** that respects `propagate_on_container_swap`.
8. **`get_allocator()`** returning a copy of the allocator.

This checklist is what makes a container "allocator-aware" rather than merely "allocator-accepting." The difference matters because standard algorithms and adaptors (like `std::back_inserter` or range adaptors) may rely on these properties.

### Summary of Custom Allocator Integration

- **Use `std::allocator_traits<Alloc>`** for all allocator operations. Never call allocator methods directly.
- **Use `traits::construct` and `traits::destroy`** for element construction and destruction. This supports scoped allocators and custom construction logic.
- **Define propagation policies** (`propagate_on_container_copy_assignment`, `propagate_on_container_move_assignment`, `propagate_on_container_swap`) correctly for stateful allocators.
- **Provide a `pmr` alias** if your container accepts polymorphic allocators, to match the standard library convention.
- **Test with stateful allocators.** A container that works with `std::allocator<T>` may fail with an arena allocator if it assumes allocator equality or default-constructibility.

---

## Iterator Design and Traits

Iterators are the bridge between containers and algorithms. A well-designed iterator makes your container usable with `std::sort`, `std::find`, `std::ranges::views::filter`, and every other algorithm in the standard library. A poorly designed iterator limits the container to handwritten loops and ad-hoc access patterns.

### Iterator Categories

Every iterator belongs to a category that describes what operations it supports. The categories form a hierarchy from most constrained to most powerful:

| Category | Operations | Examples |
|---|---|---|
| `std::input_iterator_tag` | `++it`, `*it` (read-only, single-pass) | Stream iterators |
| `std::output_iterator_tag` | `++it`, `*it = value` (write-only, single-pass) | `std::back_insert_iterator` |
| `std::forward_iterator_tag` | Input + output + multi-pass | `std::forward_list` iterator |
| `std::bidirectional_iterator_tag` | Forward + `--it` | `std::list`, `std::set` iterator |
| `std::random_access_iterator_tag` | Bidirectional + `it + n`, `it - n`, `it[n]`, `<`, `>` | `std::vector`, `std::deque` iterator |
| `std::contiguous_iterator_tag` (C++20) | Random access + elements are contiguous in memory | `std::vector`, `std::array`, `std::string` |

Choose the lowest category that your container can support. If your container is a singly-linked list, provide forward iterators — claiming bidirectional iterators would require the iterator to discover the previous element, which would force O(n) storage or O(n) traversal per decrement. If your container is an array, provide random-access or contiguous iterators — claiming anything less would prevent users from using `std::sort` or pointer arithmetic.

### Defining iterator_traits

`std::iterator_traits` is the mechanism by which algorithms discover an iterator's properties. You can specialize it for your iterator type, or — since C++17 — define the five member types directly in the iterator class:

```cpp
template <typename T>
class RingBufferIterator {
public:
    // Iterator traits (C++17 style: define in the class).
    using iterator_category = std::random_access_iterator_tag;
    using value_type        = T;
    using difference_type   = std::ptrdiff_t;
    using pointer           = T*;
    using reference         = T&;

    // ... iterator operations ...
};

// Or specialize iterator_traits (C++98 compatible):
namespace std {
    template <typename T>
    struct iterator_traits<RingBufferIterator<T>> {
        using iterator_category = typename RingBufferIterator<T>::iterator_category;
        using value_type        = typename RingBufferIterator<T>::value_type;
        using difference_type   = typename RingBufferIterator<T>::difference_type;
        using pointer           = typename RingBufferIterator<T>::pointer;
        using reference         = typename RingBufferIterator<T>::reference;
    };
}
```

The five member types are used by algorithms to declare local variables, deduce return types, and select overloads. For example, `std::distance` computes differently for random-access iterators (return `b - a`) vs. forward iterators (increment until equality). The dispatch is done through the `iterator_category` tag.

### A Complete Iterator Example

Consider a ring buffer that stores elements in a contiguous circular buffer. Its iterator must handle modular arithmetic when advancing past the end of the underlying storage:

```cpp
template <typename T>
class RingBufferIterator {
    T* data_;          // pointer to the start of the underlying buffer
    size_t capacity_;
    size_t pos_;       // current logical position (0 to capacity_ - 1)

public:
    using iterator_category = std::random_access_iterator_tag;
    using value_type        = T;
    using difference_type   = std::ptrdiff_t;
    using pointer           = T*;
    using reference         = T&;

    RingBufferIterator(T* data, size_t capacity, size_t pos)
        : data_(data), capacity_(capacity), pos_(pos) {}

    reference operator*() const {
        return data_[pos_ % capacity_];
    }

    pointer operator->() const {
        return &data_[pos_ % capacity_];
    }

    // Pre-increment.
    RingBufferIterator& operator++() {
        ++pos_;
        return *this;
    }

    // Post-increment.
    RingBufferIterator operator++(int) {
        auto tmp = *this;
        ++*this;
        return tmp;
    }

    // Pre-decrement.
    RingBufferIterator& operator--() {
        --pos_;
        return *this;
    }

    RingBufferIterator operator--(int) {
        auto tmp = *this;
        --*this;
        return tmp;
    }

    // Random access.
    RingBufferIterator& operator+=(difference_type n) {
        pos_ += n;
        return *this;
    }

    RingBufferIterator& operator-=(difference_type n) {
        pos_ -= n;
        return *this;
    }

    reference operator[](difference_type n) const {
        return data_[(pos_ + n) % capacity_];
    }

    // Arithmetic.
    friend RingBufferIterator operator+(RingBufferIterator it, difference_type n) {
        return it += n;
    }

    friend RingBufferIterator operator-(RingBufferIterator it, difference_type n) {
        return it -= n;
    }

    friend difference_type operator-(const RingBufferIterator& a,
                                      const RingBufferIterator& b) {
        return static_cast<difference_type>(a.pos_) -
               static_cast<difference_type>(b.pos_);
    }

    // Comparison.
    friend bool operator==(const RingBufferIterator& a, const RingBufferIterator& b) {
        return a.pos_ == b.pos_;
    }

    friend bool operator!=(const RingBufferIterator& a, const RingBufferIterator& b) {
        return !(a == b);
    }

    friend bool operator<(const RingBufferIterator& a, const RingBufferIterator& b) {
        return a.pos_ < b.pos_;
    }

    friend bool operator>(const RingBufferIterator& a, const RingBufferIterator& b) {
        return b < a;
    }

    friend bool operator<=(const RingBufferIterator& a, const RingBufferIterator& b) {
        return !(b < a);
    }

    friend bool operator>=(const RingBufferIterator& a, const RingBufferIterator& b) {
        return !(a < b);
    }
};
```

The iterator stores a raw `pos_` representing the logical position (not the physical index). The physical index is computed in `operator*` as `pos_ % capacity_`, so the iterator naturally wraps around the circular buffer. The `difference_type` subtraction computes `pos_a - pos_b`, which gives the signed distance in logical steps — correct because positions increase monotonically even as the physical location wraps.

The `random_access_iterator_tag` claim is valid because `it + n` is O(1) (simple integer addition) and `it[n]` is O(1) (modular indexing). However, a `contiguous_iterator_tag` is not valid because the elements are not stored contiguously in memory — the buffer wraps around, so element `n` and element `n+1` may not be adjacent in address space.

### Const Iterators and the const/non-const Split

Every container should provide both `iterator` (mutable) and `const_iterator` (non-mutable) types. The standard pattern is to template the iterator on `T` for mutable iterators and on `const T` for const iterators, or to use a base template with a `is_const` parameter:

```cpp
template <typename T>
class RingBuffer {
public:
    using iterator       = RingBufferIterator<T>;
    using const_iterator = RingBufferIterator<const T>;

    iterator begin() { return iterator(data_, capacity_, head_); }
    iterator end()   { return iterator(data_, capacity_, head_ + size_); }

    const_iterator begin() const { return const_iterator(data_, capacity_, head_); }
    const_iterator end() const   { return const_iterator(data_, capacity_, head_ + size_); }

    const_iterator cbegin() const { return begin(); }
    const_iterator cend() const   { return end(); }
};
```

A `const` container should only expose `const_iterator`. Overloading `begin()` on `const` achieves this — when the container is `const`, the `const` overload is selected, returning `const_iterator`. This prevents mutation through the iterator while still allowing read-only traversal.

### Sentinels (C++17 and Beyond)

A sentinel is an alternative to the end iterator. Instead of comparing against a specific iterator value, a sentinel defines an "end condition" — for example, a null-terminated string's end is the null character, not a specific position. C++17 introduced sentinel support in the standard library, and it is especially useful for custom containers with non-trivial end conditions:

```cpp
class NullTerminatedIterator {
    const char* ptr_;
public:
    explicit NullTerminatedIterator(const char* ptr) : ptr_(ptr) {}

    char operator*() const { return *ptr_; }
    NullTerminatedIterator& operator++() { ++ptr_; return *this; }

    bool operator!=(std::default_sentinel_t) const {
        return *ptr_ != '\0';
    }
};
```

For a custom container, you can use sentinels to represent "the end of the valid range" without storing an explicit end position. This is useful for containers like buffers where the end is defined by a count of remaining elements rather than a pointer:

```cpp
template <typename T>
class RingBuffer {
    // ...
    class Sentinel {};

    Iterator begin() { return Iterator(data_, capacity_, head_); }
    Sentinel end() { return {}; }

    bool operator==(const Iterator& it, Sentinel) {
        return it.pos_ == head_ + size_;
    }
    bool operator!=(const Iterator& it, Sentinel) {
        return !(it == Sentinel{});
    }
};
```

The sentinel pattern is most beneficial when storing an explicit end position would be expensive or when the end condition is computed differently from the iterator operations. For most custom containers, a conventional end iterator is simpler.

### Iterator Adaptors

The standard library provides iterator adaptors that transform one iterator type into another:

- `std::reverse_iterator<Iter>` — wraps a bidirectional or random-access iterator, reversing the direction of traversal. Provide `rbegin()` and `rend()` in your container for reverse iteration.
- `std::move_iterator<Iter>` — converts `*it` (which returns `T&`) into `T&&`, enabling move-based algorithms.
- `std::insert_iterator<Container>`, `std::back_insert_iterator<Container>`, `std::front_insert_iterator<Container>` — adaptors that turn assignment into container insertion.

For a custom container, supporting these adaptors requires no additional work beyond providing correct iterators. `std::reverse_iterator` works automatically with any bidirectional or random-access iterator. Move iterators work with any input iterator. The insert adaptors require the container to have appropriate `insert`, `push_back`, or `push_front` methods.

### C++20 Iterator Concepts

C++20 introduced concepts that formalize iterator requirements. Instead of relying on `iterator_category` tags and runtime dispatch, algorithms can now constrain template parameters with concepts:

```cpp
template <std::random_access_iterator Iter>
void sort_and_process(Iter begin, Iter end) {
    std::sort(begin, end);
    // ...
}
```

A custom iterator satisfies the appropriate concept automatically if it provides the required operations and member types. The `std::contiguous_iterator` concept additionally requires the iterator to satisfy `std::to_address` (returning a raw pointer to the element), which your iterator can support by specializing `std::pointer_traits` or providing an `operator->` that returns a pointer type.

To make your iterator compatible with C++20 ranges, ensure that:

- It is equality-comparable (`==`, `!=`).
- It is incrementable (`++it`, `it++`).
- It is dereferenceable (`*it`, `it->`).
- It provides the five member types (or they can be deduced via `iterator_traits`).
- For bidirectional iterators: it is decrementable.
- For random-access iterators: it supports `+`, `-`, `+=`, `-=`, `[]`, `<`, `>`, `<=`, `>=`.

If your iterator satisfies these, it will automatically model the correct `std::ranges::XXX_iterator` concept and work with range adaptors, `std::ranges::sort`, and `std::views` pipelines.

### Summary of Iterator Design Principles

- **Choose the correct category** — the lowest category that your container supports. Over-claiming (e.g., random_access when the container is a list) causes algorithms to produce wrong results or infinite loops.
- **Define all five member types** in the iterator class or in `std::iterator_traits`. Without them, algorithms cannot deduce `value_type` or `difference_type`.
- **Provide const overloads** for `begin()` and `end()`. A `const` container should yield `const_iterator`.
- **Provide `rbegin()`/`rend()`** if the iterator is bidirectional or better.
- **Ensure the iterator works with `std::reverse_iterator`**. This usually Just Works if you have bidirectional capability.
- **Test with standard algorithms.** `std::find`, `std::copy`, `std::sort`, and `std::ranges::views::filter` exercise different iterator capabilities and will reveal missing operations.

---

## Emplace vs Insert Semantics

Every container in the standard library provides both `insert` (taking an already-constructed value) and `emplace` (constructing the value in place from forwarded arguments). Understanding the difference between these is essential for correct and efficient container usage, and for designing the interface of a custom container.

### The Conceptual Difference

`insert` takes a value and copies (or moves) it into the container:

```cpp
std::vector<Widget> v;
Widget w(1, 2, 3);
v.insert(v.begin(), w);          // copies w into the vector
v.insert(v.begin(), std::move(w)); // moves w into the vector
```

`emplace` constructs the value directly at the container's storage location, forwarding the constructor arguments:

```cpp
std::vector<Widget> v;
v.emplace(v.begin(), 1, 2, 3);   // constructs Widget in place
```

In the `insert` case, the caller already has a `Widget`. In the `emplace` case, the caller has the ingredients to build a `Widget`. The emplace path avoids a temporary object and a move or copy operation.

### Performance: When Emplace Is a Win

Emplace is most beneficial when the value type is expensive to move or copy, and when the caller does not already have an instance of the type:

```cpp
// Insert: creates a temporary, moves it into the vector.
v.push_back(Widget(a, b, c));

// Emplace: constructs directly in the vector's storage.
v.emplace_back(a, b, c);
```

For `push_back` / `emplace_back`, the difference is one move construction. With cheaply movable types (like `int` or `std::unique_ptr`), the difference is negligible. With expensive types (like `std::array` of large PODs or a `std::string` with a long buffer), the difference can be significant.

In practice, the compiler often elides the temporary in simple cases, especially with C++17's guaranteed copy elision for prvalues. But elision is not guaranteed when the temporary is named or when the move constructor has side effects, so emplace remains the safer choice for hot paths.

### When Emplace Is Not an Optimization

Emplace is not always faster, and in some cases it is observably different from insert. Consider:

```cpp
std::vector<std::unique_ptr<int>> ptrs;
ptrs.emplace_back(new int(42));    // OK: constructs unique_ptr in place
ptrs.push_back(new int(42));       // Error: no implicit conversion to unique_ptr
```

`push_back` requires a `std::unique_ptr<int>` argument. `new int(42)` returns `int*`, which cannot implicitly convert to `unique_ptr`. The `emplace_back` version works because it forwards the raw pointer to `unique_ptr`'s constructor — but if the `emplace_back` fails after allocation (e.g., the vector needs to reallocate and the reallocation throws), the raw pointer is leaked because no `unique_ptr` was ever created. With `push_back`, the `unique_ptr` is created before the container operation, so it is not leaked:

```cpp
// Safe: unique_ptr owns the pointer before the container sees it.
ptrs.push_back(std::unique_ptr<int>(new int(42)));

// Leak-prone: if reallocation throws, the raw pointer is never wrapped.
ptrs.emplace_back(new int(42));
```

The fix is to use `std::make_unique` or to construct the `unique_ptr` explicitly before passing it:

```cpp
ptrs.emplace_back(std::make_unique<int>(42));   // safe
ptrs.push_back(std::make_unique<int>(42));      // also safe
```

Another case where emplace differs from insert is with aggregate types and narrowing conversions:

```cpp
struct Point { int x, y; };

std::vector<Point> points;
points.emplace_back(1.5, 2.7);   // WARNING: narrowing conversions
points.push_back(Point{1, 2});    // explicit, no surprise
```

`emplace_back` implicitly converts `double` to `int`, potentially losing precision. `push_back` with brace initialization requires an explicit cast or triggers a warning. Emplace silences this because it forwards the arguments directly to the constructor — it does not perform the implicit narrowing check that brace initialization does.

### Exception Safety Differences

For `insert`, the value is constructed before the container operation begins. If the container's internal operation (reallocation, node allocation) throws, the value's destructor has already run (for a temporary) or the value is still owned by the caller (for an lvalue). The container state is unchanged.

For `emplace`, the value is constructed during the container operation. If the container needs to reallocate and the reallocation throws, the partially-constructed value at the new storage location may be in an indeterminate state, and the original elements have already been moved from. This is the **basic exception guarantee** — no resources leak, but the container may be in a modified state.

The standard library containers provide the **strong exception guarantee** for `insert` (if the copy constructor does not throw) but only the **basic exception guarantee** for `emplace`. This is documented in the standard for `vector::emplace_back`:

> If an exception is thrown, this function has no effect (strong guarantee) only if `T`'s move constructor does not throw. Otherwise, the basic guarantee.

The emplace operations in `std::map` and `std::unordered_map` have a different consideration: if the insertion fails (key already exists), the emplace-constructed element must be destroyed. This is handled automatically by the container — the constructed element is destroyed if not inserted — but it means that any side effects of the constructor (acquiring a resource, opening a file) are rolled back if the insertion fails.

### Emplace in Associative Containers

Associative containers (`map`, `set`, `unordered_map`, `unordered_set`) have additional emplace variants:

- `try_emplace` (C++17): For `map`, `try_emplace(key, args...)` constructs the value only if the key is not already present. Unlike `emplace`, it does not move from the key if the insertion fails — the key is forwarded only once. This is important for move-only keys:

```cpp
std::map<std::unique_ptr<int>, std::string> m;
auto key = std::make_unique<int>(42);

// emplace: if insertion fails, the key was already moved into the node.
m.emplace(std::move(key), "hello");

// try_emplace: key is not moved if key already exists.
auto [it, inserted] = m.try_emplace(std::move(key), "hello");
```

- `insert_or_assign` (C++17): For `map`, inserts the value if the key is absent, or assigns to the existing value if the key is present. Returns an `std::pair<iterator, bool>` indicating whether insertion occurred.

- **Piecewise construction** in `std::pair`: When constructing a `map` element (which is a `pair<const Key, Value>`), emplace must forward arguments for both the key and the value. Since `pair` has two components, you cannot simply forward all arguments to one constructor. The solution is `std::piecewise_construct`:

```cpp
std::map<std::string, std::vector<int>> m;

// Without piecewise construct: constructs a temporary pair.
m.emplace(std::piecewise_construct,
          std::forward_as_tuple("key"),
          std::forward_as_tuple(10, 20, 30));
```

This constructs the `pair`'s first and second elements in place, avoiding any temporary `pair` or `vector`. For a custom associative container, supporting piecewise construction means accepting `std::piecewise_construct_t` as a tag in your emplace overloads.

### Insert with Hints

For ordered associative containers, `insert` (and `emplace_hint`) accept an iterator hint that suggests where the element should be inserted:

```cpp
std::map<int, std::string> m;
auto it = m.lower_bound(5);
m.emplace_hint(it, 5, "five");  // O(1) if hint is correct, O(log n) otherwise
```

The hint is an iterator to the position just before where the new element should go. If the hint is correct, the insertion is amortized O(1); if wrong, it falls back to O(log n). The hint iterator must be obtained from the same container — using an iterator from a different container is undefined behavior.

For a custom ordered container, providing `emplace_hint` is a design choice. It adds API surface and requires the container's internal structure to support fast insertion at a known position (e.g., by storing the parent node pointer in the iterator). Many custom containers skip this and provide only hint-free insertion, which is acceptable if the use case does not involve bulk insertion with known locality.

### Designing the Interface for a Custom Container

When defining the insertion interface for a custom container, you should typically provide:

```cpp
template <typename... Args>
iterator emplace(const_iterator pos, Args&&... args);

iterator insert(const_iterator pos, const T& value);
iterator insert(const_iterator pos, T&& value);

// Range insertion.
template <typename InputIt>
iterator insert(const_iterator pos, InputIt first, InputIt last);

// Initializer list.
iterator insert(const_iterator pos, std::initializer_list<T> ilist);
```

The emplace overload forwards arguments to the element's constructor. The insert overloads should use `allocator_traits::construct` for the copy/move construction, to respect allocator-awareness.

For associative containers, the interface expands:

```cpp
std::pair<iterator, bool> insert(const T& value);
std::pair<iterator, bool> insert(T&& value);

template <typename... Args>
std::pair<iterator, bool> emplace(Args&&... args);

template <typename... Args>
iterator emplace_hint(const_iterator hint, Args&&... args);

// C++17:
template <typename... Args>
std::pair<iterator, bool> try_emplace(key_type&& k, Args&&... args);
```

The return type `std::pair<iterator, bool>` informs the caller whether the insertion actually happened (the element was not already present) and provides an iterator to the inserted or existing element.

### Summary of Emplace vs Insert

- **Use emplace** when you do not already have a value object and the value type is expensive to move.
- **Use insert** when you already have a value (especially if it is a prvalue that can be elided) or when the arguments require narrowing conversions.
- **Use try_emplace** for move-only keys in associative containers. It avoids moving the key if insertion fails.
- **Beware of leak-prone patterns** with `emplace` and raw pointers. Always wrap resources in RAII types before passing to emplace.
- **Document exception safety.** Emplace typically provides the basic guarantee, not the strong guarantee, when moves can throw.

---

## Type-Erased Containers

The containers discussed so far are homogeneous — every element has the same static type. Type-erased containers store elements whose concrete type is determined at runtime, while presenting a uniform interface to the user. The classic example is `std::any` (a container that holds one value of any type), but the pattern extends to containers of multiple elements where each element may have a different type.

### The Core Pattern: External Polymorphism

Type erasure is a form of external polymorphism. Instead of requiring elements to inherit from a common base, the container stores elements through a uniform interface (a "concept" or "model" pattern):

```cpp
class AnyContainer {
    struct Concept {
        virtual ~Concept() = default;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    template <typename T>
    struct Model : Concept {
        T value;
        explicit Model(T v) : value(std::move(v)) {}
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model<T>>(value);
        }
    };

    std::unique_ptr<Concept> ptr_;

public:
    template <typename T>
    explicit AnyContainer(T value)
        : ptr_(std::make_unique<Model<T>>(std::move(value))) {}

    AnyContainer(const AnyContainer& other)
        : ptr_(other.ptr_ ? other.ptr_->clone() : nullptr) {}

    AnyContainer& operator=(const AnyContainer& other) {
        if (this != &other) {
            ptr_ = other.ptr_ ? other.ptr_->clone() : nullptr;
        }
        return *this;
    }

    template <typename T>
    T* get() {
        auto* model = dynamic_cast<Model<T>*>(ptr_.get());
        return model ? &model->value : nullptr;
    }
};
```

Each element is stored through a pointer to the `Concept` base class. The concrete type information is kept only in the `Model<T>` template — the container sees only the virtual interface. This is the same pattern used by `std::function`, `std::any`, and `std::shared_ptr`'s type-erased deleter.

### Small Buffer Optimization for Type-Erased Containers

The `std::unique_ptr`-based approach allocates every element on the heap. For small types (integers, pointers, small structs), this adds significant overhead. The **small buffer optimization (SBO)** stores small objects in an inline buffer and falls back to heap allocation only for larger types:

```cpp
    SmallAnyContainer(const SmallAnyContainer&) = delete;
    SmallAnyContainer& operator=(const SmallAnyContainer&) = delete;

    SmallAnyContainer(SmallAnyContainer&& other) noexcept : active_(other.active_) {
        other.active_ = nullptr;
    }

    SmallAnyContainer& operator=(SmallAnyContainer&& other) noexcept {
        if (this != &other) {
            if (active_) active_->destroy();
            active_ = other.active_;
            other.active_ = nullptr;
        }
        return *this;
    }
```

The buffer is large enough to hold both the vtable pointer and the value for typical small types (16–64 bytes is common). Types larger than the buffer fall back to heap allocation by storing a `unique_ptr<Concept>` in the buffer. The `std::any` implementation in libstdc++ and libc++ uses precisely this hybrid approach.

The trade-off is layout complexity. The buffer must be aligned correctly for any type that fits, and the `clone` and `destroy` operations dispatch through the vtable. For containers of many elements, the SBO may increase the element size (all elements reserve the buffer, even if only a few use it), which reduces cache density.

### Heterogeneous Containers (Type Erasure per Element)

A single-type container (like `std::any`) holds one value. A heterogeneous container holds many values, each of which may have a different type. The concept/model pattern extends naturally: each element is stored as a `unique_ptr<Concept>`, and the container manages a collection of these:

```cpp
class HeterogeneousVector {
    std::vector<std::unique_ptr<Concept>> elements_;

public:
    template <typename T>
    void push_back(T value) {
        elements_.push_back(
            std::make_unique<Model<T>>(std::move(value)));
    }

    size_t size() const { return elements_.size(); }

    template <typename T>
    T* get(size_t index) {
        auto* model = dynamic_cast<Model<T>*>(elements_[index].get());
        return model ? &model->value : nullptr;
    }
};
```

This is the simplest form. The cost is one heap allocation per element plus a `dynamic_cast` per retrieval. For many use cases (event buses, plugin registries, heterogeneous configuration stores), this overhead is acceptable.

### Type Erasure without Virtual Dispatch

Virtual functions are not the only way to implement type erasure. For smaller types or constrained interfaces, you can use function pointers stored in a table:

```cpp
template <size_t BufferSize = 16>
class FunctionPointerAny {
    struct VTable {
        void (*destroy)(void* obj);
        void (*clone)(void* dst, const void* src);
    };

    template <typename T>
    static VTable make_vtable() {
        return VTable{
            .destroy = [](void* obj) {
                static_cast<T*>(obj)->~T();
            },
            .clone = [](void* dst, const void* src) {
                ::new (dst) T(*static_cast<const T*>(src));
            },
        };
    }

    alignas(std::max_align_t) std::byte storage_[BufferSize];
    const VTable* vtable_ = nullptr;

public:
    template <typename T>
    explicit FunctionPointerAny(T value) {
        static_assert(sizeof(T) <= BufferSize);
        static_assert(alignof(T) <= alignof(std::max_align_t));
        ::new (storage_) T(std::move(value));
        vtable_ = make_vtable<T>();
    }

    FunctionPointerAny(const FunctionPointerAny& other) {
        if (other.vtable_) {
            other.vtable_->clone(storage_, other.storage_);
            vtable_ = other.vtable_;
        }
    }

    ~FunctionPointerAny() {
        if (vtable_) {
            vtable_->destroy(storage_);
        }
    }
};
```

This eliminates the vtable pointer overhead per type (the vtable is a single static object per `T`, shared across all instances) and the virtual dispatch mechanism. The function pointers are called directly. This is the same technique used by `std::function` in most implementations — the vtable is replaced by a pointer to a static table of function pointers generated by the template instantiation.

The advantage is smaller per-object overhead (one function pointer table pointer instead of a virtual table pointer) and potentially better inlining behavior (the function pointers are often devirtualized by the optimizer). The disadvantage is that you must manually implement polymorphic behavior (clone, destroy, move) through the function pointer table — there is no compiler-generated vtable.

### Type-Erased Iterators

For a heterogeneous container to be iterable, the iterator must also be type-erased — it must yield values whose type is not known until iteration time. This is typically done by having the iterator dereference to a type-erased handle:

```cpp
class HeterogeneousIterable {
    struct Concept {
        virtual ~Concept() = default;
    };

    template <typename T>
    struct Model : Concept {
        T value;
    };

    std::vector<std::unique_ptr<Concept>> elements_;

public:
    // Iterator dereferences to a type-erased reference.
    class Iterator {
        std::vector<std::unique_ptr<Concept>>::iterator it_;
    public:
        Concept& operator*() { return **it_; }
    };

    Iterator begin() { return Iterator{elements_.begin()}; }
    Iterator end()   { return Iterator{elements_.end()}; }
};
```

The consumer of the iterator receives a `Concept&` and must use a `dynamic_cast` (or a visitor pattern) to recover the concrete type. This is the fundamental trade-off of heterogeneous containers: iteration is possible, but each element access requires a runtime type check.

### When to Use Type-Erased Containers

Type-erased containers are useful when:

- **Plugin or scripting systems** need to store values of types not known at container compile time.
- **Event buses** carry events of different types in a single queue.
- **Serialization frameworks** process heterogeneous documents (JSON, XML) whose structure is schema-less.
- **Property bags** store configuration values of various types.

They are less useful when:

- **The set of types is fixed and known in advance.** Use `std::variant` instead — it is faster, type-safe, and requires no heap allocation per element.
- **Performance is critical.** Each element access in a type-erased container involves indirection (pointer chase) and a `dynamic_cast` or visitor dispatch.
- **The elements are large and numerous.** The overhead of storing each element through a heap-allocated wrapper becomes significant in both memory and cache behavior.

The decision between type-erased containers and `std::variant` is a classic trade-off: `std::variant` is bounded (you must list all possible types) but fast and safe; type-erased containers are unbounded (any type can be added at runtime) but slower and less type-safe (retrieval requires a cast that can fail at runtime).

### Summary of Type-Erased Containers

- **Use the concept/model pattern** to erase the concrete type behind a uniform virtual interface. This is the idiomatic C++ type-erasure technique.
- **Apply the small buffer optimization** for types that fit in a small inline buffer, avoiding heap allocation overhead.
- **Consider function-pointer-based type erasure** for tighter control over per-object overhead and better devirtualization opportunities.
- **Accept the runtime cost.** Every operation on a type-erased value goes through indirection. Heterogeneous containers are not a zero-cost abstraction — they are a flexibility-for-performance trade-off.
- **Prefer `std::variant` when the type set is fixed.** Variant is the compile-time alternative to runtime type erasure and is almost always faster and safer.

---

### Exercises

1. **Allocator-aware container.** Implement a simple `StaticVector<T, N>` that stores up to N elements in a fixed-size array. Make it allocator-aware by accepting an allocator template parameter. Ensure that construction, destruction, and copy operations go through `std::allocator_traits`. Test with `std::pmr::monotonic_buffer_resource`.

2. **Custom allocator.** Write an arena allocator that allocates from a pre-allocated buffer. Use it as the allocator for your `StaticVector` and for `std::pmr::vector`. Measure the allocation overhead compared to `std::allocator`.

3. **Iterator for a sparse set.** Implement a sparse set container (an array of indices and a parallel array of values, allowing O(1) insertion, deletion, and lookup). Design a bidirectional iterator that skips over "deleted" slots. Which iterator category does it satisfy? Why?

4. **Emplace vs insert benchmark.** Write a benchmark that compares `push_back` vs `emplace_back` for: (a) `std::string` with a long string literal, (b) `std::unique_ptr<int>` initialized with `new`, (c) a small POD struct. Which cases show a significant difference? Which cases are equivalent?

5. **try_emplace for move-only keys.** Given a `std::map<std::unique_ptr<int>, std::string>`, write code that demonstrates the difference between `emplace` and `try_emplace` when the key already exists. Show that `emplace` moves from the key even on failure, while `try_emplace` does not.

6. **Type-erased container with visitor.** Implement a `HeterogeneousVector` that supports a visitor function (`void visit(auto&& visitor)`) that calls the visitor on each element with its concrete type. Use a type-erased `apply` function in the vtable so that the visitor does not need `dynamic_cast`. Compare the performance of the visitor approach vs. `dynamic_cast` per element.

7. **SBO vs heap allocation.** Extend your type-erased container with a small buffer optimization (16 bytes). Benchmark insertion and iteration of small types (int, double) vs. large types (a struct with a 64-byte array). At what size does the heap fallback become faster than the SBO path?

8. **Allocator propagation.** Create a stateful allocator that logs every allocation and deallocation. Attach it to a `std::vector` and verify that copying the vector does or does not propagate the allocator based on `propagate_on_container_copy_assignment`. Then implement the same test for your custom container from exercise 1.
