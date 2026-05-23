# Chapter 7: Buffer and Memory Management

Buffers are contiguous memory regions used to store sequences of data elements. They're fundamental to I/O operations, network communication, image processing, and many other performance-critical tasks. Understanding buffer management idioms helps you write efficient, safe code that minimizes unnecessary copies and allocation overhead.

This chapter explores idioms for buffer management, covering stack-based buffers with the Small Buffer Optimization, direct construction with placement new, and memory pool patterns for high-performance scenarios.

## Buffer Management Idioms

Buffers in C++ serve as the foundation for handling sequential data efficiently. The way you manage buffers—how you allocate, size, and pass them—significantly impacts performance and safety. Understanding the idioms for buffer management helps you choose the right approach for each situation.

### Stack-Based vs Heap-Based Buffers

The most fundamental choice is whether to store the buffer on the stack or the heap. Stack buffers offer excellent cache locality and automatic lifetime management, but they're limited by stack size and can't survive function returns. Heap buffers offer flexibility but require explicit management.

A common pattern combines both approaches:

```cpp
class Buffer {
public:
    static constexpr size_t kInlineCapacity = 256;

    Buffer() : size_(0), data_(inlineBuffer_) {}

    Buffer(size_t capacity) : size_(0), data_(nullptr) {
        if (capacity > kInlineCapacity) {
            heapBuffer_ = std::make_unique<char[]>(capacity);
            data_ = heapBuffer_.get();
        } else {
            data_ = inlineBuffer_;
        }
        capacity_ = capacity;
    }

    ~Buffer() {
        if (heapBuffer_) {
            heapBuffer_.reset();
        }
    }

    char* data() { return data_; }
    const char* data() const { return data_; }
    size_t size() const { return size_; }
    size_t capacity() const { return capacity_; }

    void setSize(size_t s) { size_ = std::min(s, capacity_); }

private:
    size_t capacity_ = kInlineCapacity;
    size_t size_ = 0;
    char inlineBuffer_[kInlineCapacity];
    std::unique_ptr<char[]> heapBuffer_;
    char* data_;
};
```

This pattern uses a small inline buffer for common cases while dynamically allocating only when needed. The key insight is that most data is small—the inline buffer handles typical workloads without allocation, and heap allocation kicks in only for large data. This is the Small Buffer Optimization (SBO), explored in detail later in this chapter.

### Buffer Sizing Strategies

How you determine buffer size affects both memory usage and correctness. Several idiomatic approaches exist:

Fixed sizing works for known bounds:

```cpp
class PacketHeader {
    static constexpr size_t kMaxHeaderSize = 64;
    char buffer_[kMaxHeaderSize];
    size_t actualSize_ = 0;
};
```

Maximum bounds ensure safety but may waste memory. When actual sizes vary significantly, consider more sophisticated approaches.

Fit-to-content sizing computes required size dynamically:

```cpp
class DynamicBuffer {
public:
    template<typename... Args>
    void write(Args&&... args) {
        size_t needed = calculateSize(std::forward<Args>(args)...);
        ensureCapacity(size_ + needed);
        serialize(std::forward<Args>(args)...);
    }

private:
    void ensureCapacity(size_t required) {
        if (required > capacity_) {
            reallocate(required * 2);  // Grow exponentially
        }
    }
};
```

The exponential growth strategy (doubling capacity) ensures amortized O(1) append operations. This is the same strategy used by `std::vector`.

Minimum-safe sizing with overflow detection:

```cpp
class SafeBuffer {
public:
    bool write(const void* data, size_t size) {
        if (size_ + size > capacity_) {
            return false;  // Would overflow
        }
        std::memcpy(buffer_.get() + size_, data, size);
        size_ += size;
        return true;
    }
};
```

This pattern prevents buffer overflows by checking before writing—a defensive approach essential for security-sensitive code.

### Buffer Ownership and Lifetime

Who owns the buffer determines how it's managed. Three primary models exist:

Exclusive ownership transfers responsibility entirely:

```cpp
class OwningBuffer {
    std::vector<char> buffer_;
public:
    std::vector<char> release() {
        return std::move(buffer_);
    }
};
```

The buffer is destroyed when the owner is destroyed. Transferring ownership moves the buffer.

Borrowed buffers reference externally-owned memory:

```cpp
class BufferView {
    char* data_;
    size_t size_;
public:
    BufferView(char* data, size_t size) : data_(data), size_(size) {}

    char* data() { return data_; }
    size_t size() const { return size_; }
};
```

The view doesn't own the buffer—it merely provides access. The original owner must ensure the buffer outlives all views.

Shared ownership through reference counting:

```cpp
using SharedBuffer = std::shared_ptr<std::vector<char>>;

void processBuffer(SharedBuffer buffer) {
    // buffer may be shared
}
```

When multiple components need to hold and extend a buffer, shared ownership prevents premature destruction.

### Zero-Copy Buffer Passing

Avoiding copies improves performance significantly. The key is distinguishing between passing ownership, borrowing, and sharing:

Passing by reference (borrowing) avoids copies:

```cpp
void processBuffer(const std::vector<char>& buffer) {
    // Read-only access, no copy
}
```

The buffer is borrowed, not copied. This works for read access but can't modify the caller's buffer if the parameter isn't mutable.

Passing by pointer enables mutation:

```cpp
void fillBuffer(std::vector<char>* buffer) {
    buffer->resize(buffer->size() + 100);
}
```

The caller provides a pointer, and the function can modify the buffer. This pattern enables functions that grow or modify buffers.

Move semantics transfer ownership without copying:

```cpp
std::vector<char> createBuffer() {
    std::vector<char> buffer(1000);
    // ... fill buffer ...
    return buffer;  // Move, not copy (RVO may eliminate even the move)
}

void consumeBuffer(std::vector<char> buffer) {
    // Takes ownership
}

consumeBuffer(createBuffer());  // Efficient transfer
```

When returning large buffers or passing to functions that need ownership, move semantics transfer the data without copying.

For subregions, buffer views provide efficient access:

```cpp
class BufferView {
public:
    BufferView(std::vector<char>& buffer, size_t offset, size_t size)
        : data_(buffer.data() + offset), size_(size) {}

    const char* data() const { return data_; }
    size_t size() const { return size_; }

private:
    const char* data_;
    size_t size_;
};

void parseHeader(const BufferView& view) {
    // Access header portion without copying
}
```

The view provides access to a portion of a buffer without copying. This is essential for protocols, file formats, and parsers that work with specific regions.

### Buffer Alignment Considerations

Memory alignment affects performance and correctness. Modern CPUs require proper alignment for efficient access—misaligned access may be slower or cause hardware exceptions on some architectures.

The simplest approach uses standard alignment:

```cpp
alignas(16) char buffer[256];
```

For SIMD operations or custom requirements, explicit alignment matters:

```cpp
template<size_t Alignment>
class AlignedBuffer {
    alignas(Alignment) char data_[1024];
public:
    void* alignedData() { return data_; }
};
```

Cache line alignment prevents false sharing in concurrent code:

```cpp
class alignas(64) CacheLinePadding {
    char padding[64];
};
```

False sharing occurs when threads modify different variables on the same cache line. Padding ensures each variable occupies its own cache line.

### Ring Buffers for Streaming Data

Ring buffers (circular buffers) efficiently handle streaming data where producers and consumers operate at different rates. Instead of shifting data, writes and reads wrap around the buffer:

```cpp
template<typename T>
class RingBuffer {
public:
    explicit RingBuffer(size_t capacity)
        : capacity_(capacity), buffer_(capacity) {}

    bool write(const T& item) {
        if (full()) return false;
        buffer_[writePos_] = item;
        writePos_ = (writePos_ + 1) % capacity_;
        return true;
    }

    bool read(T& item) {
        if (empty()) return false;
        item = buffer_[readPos_];
        readPos_ = (readPos_ + 1) % capacity_;
        return true;
    }

    bool empty() const { return readPos_ == writePos_; }
    bool full() const { return (writePos_ + 1) % capacity_ == readPos_; }
    size_t size() const {
        if (writePos_ >= readPos_) return writePos_ - readPos_;
        return capacity_ - readPos_ + writePos_;
    }

private:
    size_t capacity_;
    std::vector<T> buffer_;
    size_t readPos_ = 0;
    size_t writePos_ = 0;
};
```

Ring buffers are fundamental for I/O pipelines, message queues, and any scenario with continuous data flow. They avoid memory allocation during operation and provide O(1) enqueue and dequeue.

One subtlety: distinguishing full from empty requires either leaving one slot unused (as above) or using a count. Alternative designs use a count or a "valid" flag for each slot.

### Buffer Migration Patterns

Sometimes buffers need to change form during their lifetime—growing, shrinking, or converting between representations:

Grow-in-place when possible:

```cpp
void growInPlace(std::vector<char>& buffer, size_t newCapacity) {
    buffer.reserve(newCapacity);  // May reallocate, preserving contents
}
```

Migrate to new representation:

```cpp
class SmallStringBuffer {
    static constexpr size_t kSmallSize = 32;
    union {
        char small_[kSmallSize];
        std::unique_ptr<char[]> large_;
    };
    bool isLarge_ = false;
    size_t size_ = 0;

public:
    ~SmallStringBuffer() {
        if (isLarge_) large_.reset();
    }

    void ensureLarge(size_t required) {
        if (required > kSmallSize && !isLarge_) {
            auto newBuffer = std::make_unique<char[]>(required);
            std::memcpy(newBuffer.get(), small_, size_);
            large_ = std::move(newBuffer);
            isLarge_ = true;
        }
    }
};
```

This "small string optimization" pattern keeps small data inline while growing to heap allocation only when necessary. It's the same technique used by `std::string` in most standard library implementations.

Buffer migration matters when handling variable-size data, implementing growing collections, or optimizing for common small cases while supporting large cases.

### Summary

Buffer management idioms form the foundation for efficient data handling in C++. The choice between stack and heap buffers depends on lifetime requirements and size constraints. Buffer sizing strategies—fixed, dynamic, or minimum-safe—affect memory usage and correctness. Ownership models determine responsibility: exclusive ownership transfers entirely, borrowed views reference external data, and shared ownership enables reference counting.

Zero-copy passing techniques—borrowing with references, transferring with moves, and viewing subregions—avoid unnecessary copies. Alignment considerations matter for performance and correctness, especially with SIMD and concurrent code. Ring buffers provide efficient streaming semantics without allocation. Buffer migration patterns enable optimization for common small cases while supporting large cases.

These buffer management principles apply throughout the remaining sections in this chapter: the Small Buffer Optimization builds on these concepts, placement new enables custom memory management, and memory pools provide specialized allocation strategies for buffer-intensive applications.

---

## Small Buffer Optimization (SBO)

The Small Buffer Optimization stores small amounts of data inline within the object itself, avoiding heap allocation for common cases. This optimization improves performance by reducing allocation overhead, improving cache locality, and eliminating pointer indirection. Understanding when and how to apply SBO helps you design efficient data structures.

### The Motivation for SBO

Heap allocation, while flexible, carries significant overhead. Each allocation involves finding suitable memory (which can involve searching free lists), potentially splitting blocks, updating metadata, and likely cache misses when accessing the allocated memory. For small objects, this overhead often exceeds the actual data size—the administrative costs dominate the useful work.

Consider a string of 15 characters. A typical `std::string` implementation with SSO (Small String Optimization) stores all 15 characters inline, using only the stack space of the string object itself. Without SSO, each string would heap-allocate, paying the allocation cost even for tiny strings. The difference is dramatic: a simple stack operation versus a potentially blocking memory allocation.

The same principle applies broadly: small vectors, small optional values, small variant types, and small containers all benefit from inline storage. The key is identifying the common case—typically the majority of instances have small data—and optimizing for that case while gracefully supporting larger scenarios.

### SSO Implementation in std::string

The standard library's `std::string` typically implements SSO, though the exact threshold varies by implementation. Understanding how it works clarifies the pattern:

```cpp
// Simplified view of typical std::string implementation
class basic_string {
    struct Rep {
        size_t capacity_;
        size_t size_;
        char data_[16];  // Small buffer inline
    };

    union {
        Rep small_;                    // Inline for small strings
        char* heapData_;               // Pointer for large strings
    };

    static constexpr size_t kSmallThreshold = 15;

    bool isSmall() const {
        return small_.capacity_ <= kSmallThreshold;
    }
};
```

The key insight is the union—either the small buffer is used or the heap pointer, determined by the size of the data. When constructing a small string, the characters are copied into the inline buffer. When the string grows beyond the threshold, heap allocation occurs and data is copied there.

This implementation shows how SSO combines inline storage with dynamic allocation for overflow. The critical design decision is choosing the inline capacity—too small and most strings still allocate; too large and every string object becomes large.

### Custom SBO Container

Implementing your own SBO container reveals the design decisions involved:

```cpp
template<typename T>
class SmallVector {
public:
    static constexpr size_t kInlineCapacity = 8;

    SmallVector() : size_(0), data_(inlineBuffer_) {}

    ~SmallVector() {
        destroyElements();
        if (!isInline()) {
            delete[] heapBuffer_;
        }
    }

    SmallVector(const SmallVector& other) : size_(0), data_(inlineBuffer_) {
        reserve(other.size_);
        for (size_t i = 0; i < other.size_; ++i) {
            new (&data_[i]) T(other.data_[i]);
        }
        size_ = other.size_;
    }

    SmallVector& operator=(const SmallVector& other) {
        if (this != &other) {
            SmallVector tmp(other);
            swap(tmp);
        }
        return *this;
    }

    SmallVector(SmallVector&& other) noexcept : size_(0), data_(inlineBuffer_) {
        if (other.isInline()) {
            for (size_t i = 0; i < other.size_; ++i) {
                new (&data_[i]) T(std::move(other.data_[i]));
            }
            size_ = other.size_;
        } else {
            heapBuffer_ = other.heapBuffer_;
            capacity_ = other.capacity_;
            data_ = heapBuffer_;
            size_ = other.size_;
            other.heapBuffer_ = nullptr;
            other.size_ = 0;
            other.data_ = other.inlineBuffer_;
        }
    }

    SmallVector& operator=(SmallVector&& other) noexcept {
        if (this != &other) {
            destroyElements();
            if (!isInline()) {
                delete[] heapBuffer_;
            }

            if (other.isInline()) {
                for (size_t i = 0; i < other.size_; ++i) {
                    new (&data_[i]) T(std::move(other.data_[i]));
                }
                size_ = other.size_;
                data_ = inlineBuffer_;
            } else {
                heapBuffer_ = other.heapBuffer_;
                capacity_ = other.capacity_;
                data_ = heapBuffer_;
                size_ = other.size_;
                other.heapBuffer_ = nullptr;
            }
            other.size_ = 0;
        }
        return *this;
    }

    void push_back(const T& value) {
        if (size_ == capacity_) {
            grow(size_ + 1);
        }
        new (&data_[size_]) T(value);
        ++size_;
    }

    void push_back(T&& value) {
        if (size_ == capacity_) {
            grow(size_ + 1);
        }
        new (&data_[size_]) T(std::move(value));
        ++size_;
    }

    template<typename... Args>
    T& emplace_back(Args&&... args) {
        if (size_ == capacity_) {
            grow(size_ + 1);
        }
        new (&data_[size_]) T(std::move(args)...);
        return data_[size_++];
    }

    T& operator[](size_t i) { return data_[i]; }
    const T& operator[](size_t i) const { return data_[i]; }

    size_t size() const { return size_; }
    size_t capacity() const { return capacity_; }

    T* data() { return data_; }
    const T* data() const { return data_; }

    void swap(SmallVector& other) noexcept {
        std::swap(size_, other.size_);
        std::swap(capacity_, other.capacity_);
        std::swap(isLarge_, other.isLarge_);

        if (isInline() && other.isInline()) {
            for (size_t i = 0; i < std::min(size_, other.size_); ++i) {
                std::swap(data_[i], other.data_[i]);
            }
        } else {
            std::swap(data_, other.data_);
        }
    }

private:
    bool isInline() const { return isLarge_ == 0; }

    void grow(size_t minCapacity) {
        size_t newCapacity = capacity_ == 0 ? 1 : capacity_ * 2;
        if (newCapacity < minCapacity) newCapacity = minCapacity;

        if (newCapacity <= kInlineCapacity) {
            for (size_t i = 0; i < size_; ++i) {
                new (&inlineBuffer_[i]) T(std::move(data_[i]));
                data_[i].~T();
            }
            data_ = inlineBuffer_;
            capacity_ = kInlineCapacity;
            isLarge_ = 0;
        } else {
            char* newBuffer = new char[newCapacity * sizeof(T)];
            T* newData = reinterpret_cast<T*>(newBuffer);

            for (size_t i = 0; i < size_; ++i) {
                new (&newData[i]) T(std::move(data_[i]));
                data_[i].~T();
            }

            if (!isInline()) {
                delete[] heapBuffer_;
            }

            heapBuffer_ = newBuffer;
            data_ = newData;
            capacity_ = newCapacity;
            isLarge_ = 1;
        }
    }

    void destroyElements() {
        for (size_t i = 0; i < size_; ++i) {
            data_[i].~T();
        }
    }

    size_t size_ = 0;
    size_t capacity_ = kInlineCapacity;
    unsigned char isLarge_ = 0;
    alignas(T) char inlineBuffer_[kInlineCapacity * sizeof(T)];
    char* heapBuffer_ = nullptr;
    T* data_ = nullptr;
};
```

This implementation demonstrates the key SBO patterns. The inline buffer stores data directly when small—here, up to 8 elements. When growing beyond that capacity, heap allocation occurs. The critical complexity is in move assignment, where both objects might be inline or might use the heap, requiring careful handling of each case.

### Union-Based SBO

A more direct approach uses a union to store either the inline data or a heap pointer:

```cpp
template<typename T, size_t N>
class InlineVector {
    static_assert(N > 0, "Inline capacity must be positive");

public:
    InlineVector() : size_(0) {}

    ~InlineVector() {
        destroyElements();
    }

    void push_back(const T& value) {
        if (size_ < N) {
            new (&inline_.data[size_]) T(value);
        } else {
            pushBackLarge(value);
        }
        ++size_;
    }

    T* data() {
        return size_ <= N ? inline_.data : heap_.ptr;
    }

    const T* data() const {
        return size_ <= N ? inline_.data : heap_.ptr;
    }

    size_t size() const { return size_; }

private:
    void destroyElements() {
        for (size_t i = 0; i < size_; ++i) {
            data()[i].~T();
        }
        if (size_ > N) {
            delete[] heap_.ptr;
        }
    }

    void pushBackLarge(const T& value) {
        if (size_ == N) {
            char* newBuffer = new char[sizeof(T) * (N * 2)];
            T* newPtr = reinterpret_cast<T*>(newBuffer);
            for (size_t i = 0; i < size_; ++i) {
                new (&newPtr[i]) T(std::move(inline_.data[i]));
                inline_.data[i].~T();
            }
            heap_.ptr = newPtr;
        }
        new (&heap_.ptr[size_]) T(value);
    }

    size_t size_ = 0;

    union Storage {
        char* ptr;
        T data[N];

        ~Storage() {}
    } inline_;

    struct LargeStorage {
        char* ptr;
        ~LargeStorage() { delete[] ptr; }
    } heap_;
};
```

The union-based approach is conceptually simpler but requires more careful management. The compiler handles determining which union member is active based on size.

### SSO with Type Erasure

Some implementations use type erasure for more flexible inline storage. Rather than storing the element type directly, they store raw bytes and construct objects into them:

```cpp
template<size_t N>
class InlineBuffer {
public:
    template<typename T>
    T* construct() {
        static_assert(sizeof(T) <= N);
        static_assert(alignof(T) <= alignof(InlineBuffer));
        return new (storage_) T;
    }

    template<typename T, typename... Args>
    T* construct(Args&&... args) {
        static_assert(sizeof(T) <= N);
        return new (storage_) T(std::forward<Args>(args)...);
    }

    template<typename T>
    void destroy() {
        auto* ptr = reinterpret_cast<T*>(storage_);
        ptr->~T();
        std::memset(storage_, 0, N);
    }

    template<typename T>
    T* data() {
        return reinterpret_cast<T*>(storage_);
    }

    template<typename T>
    const T* data() const {
        return reinterpret_cast<const T*>(storage_);
    }

private:
    alignas(double) char storage_[N];
};
```

This pattern enables storing any type up to a certain size within the buffer, but requires compile-time knowledge of the type for correct destruction.

### Performance Characteristics

SBO changes the performance profile significantly. The key metrics to consider:

**Allocation frequency**: Without SBO, every container allocates. With SBO, most containers never allocate—the inline buffer handles typical cases. In a typical application with many small strings, this eliminates thousands of allocations.

**Cache behavior**: Inline data sits in the same cache line as the container metadata. Accessing the data causes no extra cache miss. Heap-allocated data requires at least one additional memory access to fetch the pointer, then another to access the data itself.

**Memory overhead**: The inline buffer adds N * sizeof(T) bytes to every container object, even when unused. For 8-element inline capacity on a vector, that's 64 bytes per empty vector. The trade-off is typically worthwhile when most vectors have fewer than 8 elements.

**Copy semantics**: Copying an inline-only container copies the data directly. Copying an SBO container may need to allocate if the copy exceeds inline capacity. The performance impact depends on copy frequency and typical sizes.

### Trade-offs and Considerations

SBO introduces complexity that must be weighed against benefits. Consider these factors:

**Object size**: Every SBO container is larger than the equivalent heap-only version by the inline buffer size. For small containers this is usually acceptable, but for types that might have millions of instances, the per-instance overhead matters.

**Inline capacity selection**: Too small defeats the optimization (most containers still heap-allocate). Too large wastes memory. Analyze your actual data distribution to find the sweet spot—typically the 90th percentile of sizes.

**Move semantics**: When moving an SBO container that's full, either the data must be moved to the target's heap (expensive) or both containers must share the heap allocation (complexity). Some implementations always heap-allocate on move; others migrate inline data.

**Exception safety**: The SBO code path requires careful handling to maintain exception safety. If construction of an element throws during a grow operation, already-constructed elements must be destroyed.

**Platform considerations**: Some platforms have smaller stack sizes or different heap performance characteristics. Embedded systems may benefit more from aggressive SBO; systems with fast allocators may benefit less.

### std::optional and SBO

`std::optional` applies SBO internally—the contained value is stored inline when it fits:

```cpp
std::optional<int> small;          // Stores int inline (typically 4 bytes overhead)
std::optional<std::vector<int>> large;  // Stores vector inline, even though vector itself heap-allocates
```

This design means `std::optional<T>` typically adds only a few bytes overhead regardless of T's size—a significant improvement over storing a pointer that might allocate.

### std::variant and SBO

`std::variant` combines SBO with a union to store any of several types inline. The largest possible type determines the inline buffer size:

```cpp
std::variant<int, double, std::string> v;
```

If `std::string` uses SSO and fits within the variant's inline buffer, the string can be stored inline. The actual behavior depends on the variant's implementation and the types involved.

### Summary

The Small Buffer Optimization fundamentally improves performance by eliminating heap allocation for small data. The pattern applies broadly—any type that commonly contains small amounts of data benefits. The implementation requires careful handling of copy/move operations, growth logic, and exception safety. The trade-off is increased object size versus reduced allocation frequency and improved cache behavior.

Understanding SBO helps you appreciate why standard library types like `std::string`, `std::optional`, and `std::vector` perform as they do. It also guides you when implementing your own types that might benefit from inline storage.

---

## Placement New for Custom Memory

Placement new constructs objects at specific memory locations rather than allocating new memory. This enables object construction in pre-allocated buffers, memory pools, and custom memory regions. Understanding placement new is essential for custom memory management and performance-critical code.

### How Placement New Works

Regular `new` does two things: allocates memory and constructs an object in that memory. Placement new separates these operations, allowing you to specify where the object should be constructed:

```cpp
#include <new>

void* rawMemory = std::malloc(sizeof(Widget));
Widget* widget = new (rawMemory) Widget(args);
```

The `new (rawMemory)` syntax calls the placement new operator, which simply constructs the object at the provided memory location without allocating. The memory must already be suitably aligned and large enough for the object.

The placement new operator is declared in `<new>`:

```cpp
void* operator new(std::size_t size, void* ptr) noexcept;
```

This operator ignores the `size` parameter (it should match the object's size) and simply returns `ptr`. The compiler then generates code to construct the object at that address.

### Explicit Placement Syntax

The explicit placement syntax is straightforward:

```cpp
char buffer[sizeof(Widget)];
Widget* w = new (buffer) Widget();

// Use w...

w->~Widget();  // Must explicitly destroy
```

After using placement new, you must explicitly call the destructor—the memory won't be automatically freed because it wasn't allocated by `new`.

Multiple objects can be constructed in the same buffer sequentially:

```cpp
alignas(Widget) char buffer[sizeof(Widget) * 10];

Widget* w1 = new (buffer) Widget(1);
Widget* w2 = new (buffer + sizeof(Widget)) Widget(2);

// Destroy in reverse order of construction
w2->~Widget();
w1->~Widget();
```

This pattern is fundamental to memory pools, where a single large allocation is subdivided into many objects.

### Placement New with Custom Alignment

The `std::align_val_t` overload enables aligned construction:

```cpp
void* alignedBuffer = std::aligned_alloc(256, sizeof(Widget) * 10);

Widget* w = new (alignedBuffer, std::align_val_t{256}) Widget();

w->~Widget();
std::free(alignedBuffer);
```

This is essential for SIMD types or hardware requirements. The alignment parameter must match the alignment of the allocated memory.

### Explicit Destructor Calls

When using placement new, you're responsible for destruction:

```cpp
class ResourceHolder {
    char buffer_[1024];
    bool constructed_ = false;

public:
    template<typename T, typename... Args>
    T* construct(Args&&... args) {
        if (constructed_) {
            reinterpret_cast<T*>(buffer_)->~T();
        }
        T* obj = new (buffer_) T(std::forward<Args>(args)...);
        constructed_ = true;
        return obj;
    }

    ~ResourceHolder() {
        if (constructed_) {
            reinterpret_cast<Widget*>(buffer_)->~Widget();
        }
    }
};
```

Forgetting to call the destructor causes resource leaks or undefined behavior if the destructor has important cleanup logic.

### Variadic Placement New

C++11's variadic templates enable perfect forwarding through placement new:

```cpp
template<typename T, typename... Args>
T* constructAt(void* buffer, Args&&... args) {
    return new (buffer) T(std::forward<Args>(args)...);
}

// Usage:
char buffer[256];
auto* obj = constructAt<MyClass>(buffer, arg1, arg2, arg3);
```

This pattern is extensively used in standard library implementations for functions like `std::vector::emplace_back`.

### Allocator-Style Construction

Memory allocators in the standard library use placement new extensively. Understanding this pattern helps when implementing custom allocators:

```cpp
template<typename T>
class PoolAllocator {
public:
    T* allocate(size_t n) {
        if (n != 1) throw std::bad_alloc();
        void* p = pool_.allocate();
        return static_cast<T*>(p);
    }

    void deallocate(T* p, size_t n) {
        if (n != 1) return;
        pool_.deallocate(p);
    }

    template<typename... Args>
    void construct(T* p, Args&&... args) {
        new (p) T(std::forward<Args>(args)...);
    }

    void destroy(T* p) {
        p->~T();
    }

private:
    MemoryPool pool_;
};
```

The allocator's `construct` function uses placement new, while `destroy` calls the destructor. This separation mirrors how `std::allocator` works and enables custom memory management strategies.

### Placement New in Containers

Standard containers use placement new internally. `std::vector::emplace_back` is a prime example:

```cpp
template<typename T, typename Allocator>
void std::vector<T, Allocator>::emplace_back(Args&&... args) {
    if (size_ == capacity_) {
        reallocate();  // Grow the buffer
    }
    allocator_.construct(
        std::addressof(data_[size_]),
        std::forward<Args>(args)...
    );
    ++size_;
}
```

The `allocator.construct` typically uses placement new. This allows elements to be constructed directly in the vector's buffer, avoiding separate allocation and copy.

Understanding this explains why `emplace_back` can be more efficient than `push_back`—it avoids creating a temporary that would then need to be copied or moved into the container.

### Placement New and Exception Safety

Placement new requires careful attention to exception safety. If construction throws, you must handle cleanup:

```cpp
template<typename T, typename... Args>
T* safeConstruct(void* buffer, Args&&... args) {
    T* obj = nullptr;
    try {
        obj = new (buffer) T(std::forward<Args>(args)...);
    } catch (...) {
        // No cleanup needed - buffer wasn't modified on failure
        // The placement new either succeeds completely or
        // leaves the buffer untouched
        throw;
    }
    return obj;
}
```

Placement new has a useful property: if the constructor throws, the already-allocated memory is not considered allocated—the exception propagates without any cleanup required. This differs from regular `new`, where the allocated memory must be freed on failure.

### Reusing Storage with Placement New

Placement new enables reusing memory without deallocation:

```cpp
class ObjectPool {
public:
    template<typename T, typename... Args>
    T* create(Args&&... args) {
        void* slot = findFreeSlot();
        return new (slot) T(std::forward<Args>(args)...);
    }

    template<typename T>
    void destroy(T* obj) {
        obj->~T();
        markSlotFree(obj);
    }

private:
    std::vector<char> storage_;
    std::vector<bool> inUse_;
};
```

This pattern underlies object pools and arena allocators. Memory is pre-allocated once, then objects are constructed and destroyed repeatedly in the same memory without further allocation.

### Placement New for Type Punning

While technically possible, using placement new for type punning is dangerous and often undefined behavior:

```cpp
// DANGEROUS - may be undefined behavior
float squareRootFloat(int x) {
    alignas(float) char buffer[sizeof(float)];
    *reinterpret_cast<int*>(buffer) = x;
    float result = *reinterpret_cast<float*>(buffer);
    return std::sqrt(result);
}
```

Type punning through placement new or reinterpret_cast often violates strict aliasing rules. Instead, use `std::bit_cast` (C++20) for well-defined type conversion:

```cpp
float result = std::bit_cast<float>(x);
return std::sqrt(result);
```

### Stateful Placement New

The default placement new doesn't track state, but you can create custom placement new operators:

```cpp
struct PoolTag {};

void* operator new(std::size_t size, PoolTag, MemoryPool& pool) {
    return pool.allocate(size);
}

void operator delete(void* ptr, PoolTag, MemoryPool& pool) {
    pool.deallocate(ptr);
}

// Usage:
MemoryPool pool;
Widget* w = new (PoolTag{}, pool) Widget();
```

This enables passing additional context (like a memory pool) through the new expression. The matching `operator delete` is called when the object is destroyed.

### Placement New in Embedded Systems

Embedded systems frequently use placement new for fixed-memory scenarios:

```cpp
static constexpr size_t HEAP_SIZE = 4096;
alignas(8) char heapBuffer[HEAP_SIZE];
HeapArena heap(heapBuffer, HEAP_SIZE);

// At runtime, construct objects in fixed memory
Sensor* sensor = new (heap) Sensor(pin, calibration);
```

This approach eliminates dynamic allocation entirely, which is often desirable in real-time systems where allocation timing is unpredictable.

### Placement New and Unions

Placement new is essential for correctly using unions with non-trivial types:

```cpp
union Value {
    int intValue;
    std::string stringValue;

    Value() : intValue(0) {}

    ~Value() {}  // Won't call stringValue destructor

    void setString(std::string_view s) {
        intValue = 0;  // Reset representation
        new (&stringValue) std::string(s);  // Placement construct
    }

    void destroyString() {
        stringValue.~basic_string();
    }
};
```

Without placement new, you cannot properly construct or destroy union members that have non-trivial constructors or destructors. The union itself doesn't know which variant is active—you must track that separately and call the appropriate destructor.

### Placement New vs std::launder

C++17 introduced `std::launder` to handle pointer provenance:

```cpp
struct Trivial { int x; };
alignas(8) unsigned char buffer[sizeof(Trivial)];
Trivial* p = new (buffer) Trivial{42};
Trivial* q = std::launder(&reinterpret_cast<Trivial&>(buffer));
```

`std::launder` is needed when the object representation exists but the object pointer might not be usable due to pointer provenance rules. This arises in scenarios like object reconstruction, const_cast-like operations, and certain type punning patterns.

For typical placement new usage where you construct an object at a fresh memory location, `std::launder` isn't needed—the new object provides a valid pointer.

### Summary

Placement new separates object construction from memory allocation, enabling construction at specific memory locations. This is fundamental to custom allocators, memory pools, and embedded systems programming. The key requirements are managing explicit destructor calls and ensuring proper alignment. Custom placement new operators enable passing additional context through allocation. Placement new combines with standard containers for efficient element construction and enables object pool patterns that avoid repeated allocation overhead.

---

## Memory Pool Patterns

Memory pools pre-allocate large memory blocks and subdivide them for individual allocations. This approach reduces allocation overhead, improves memory locality, and enables deterministic allocation patterns. Memory pools are essential for real-time systems, embedded platforms, and high-performance applications.

### Why Memory Pools Matter

Dynamic allocation via `new` and `delete` carries significant overhead. Each call involves searching free lists, updating metadata, and potentially contacting the OS for more virtual memory. For applications that allocate and deallocate many small objects frequently—such as game engines, network servers, or real-time simulations—this overhead becomes a performance bottleneck.

Memory pools solve this by front-loading the expensive operations. A pool allocates a large block of memory once, then satisfies subsequent allocation requests from that block. Deallocation returns memory to the pool rather than the system. This approach yields several benefits:

**Speed**: Pool allocation is typically O(1) with minimal overhead—often just advancing a pointer. Compare this to general-purpose allocators that may search through free lists.

**Predictability**: Pool allocation time is constant and bounded, making it suitable for real-time systems. General-purpose allocators can have unpredictable latency due to coalescing, fragmentation management, or system calls.

**Memory efficiency**: Pools don't carry per-object overhead beyond what's needed for tracking free slots. They also avoid fragmentation that occurs when allocation patterns create small, unusable gaps in the heap.

**Cache locality**: Objects allocated from the same pool are typically adjacent in memory, improving cache hit rates during iteration.

### Fixed-Size Pool (Free List)

The simplest pool manages fixed-size blocks. Each block is either in use or free, and a free list links the available blocks:

```cpp
template<typename T>
class FixedPool {
public:
    explicit FixedPool(size_t capacity) {
        pool_ = static_cast<char*>(std::aligned_alloc(
            alignof(T), capacity * sizeof(T)));
        freeList_ = nullptr;

        for (size_t i = 0; i < capacity; ++i) {
            void* slot = pool_ + i * sizeof(T);
            *static_cast<void**>(slot) = freeList_;
            freeList_ = slot;
        }
    }

    ~FixedPool() {
        std::free(pool_);
    }

    T* allocate() {
        if (!freeList_) return nullptr;

        void* slot = freeList_;
        freeList_ = *static_cast<void**>(slot);
        return static_cast<T*>(slot);
    }

    void deallocate(T* ptr) {
        *static_cast<void**>(ptr) = freeList_;
        freeList_ = ptr;
    }

    template<typename... Args>
    T* construct(Args&&... args) {
        T* ptr = allocate();
        if (ptr) {
            new (ptr) T(std::forward<Args>(args)...);
        }
        return ptr;
    }

    void destroy(T* ptr) {
        if (ptr) {
            ptr->~T();
            deallocate(ptr);
        }
    }

private:
    void* pool_;
    void* freeList_;
};
```

This implementation uses a simple linked list within the free slots themselves—the first bytes of each free slot store the pointer to the next free slot. When a slot is allocated, it's removed from this list. When deallocated, it becomes the new head of the list.

The key operations are `allocate()` (O(1), just pointer manipulation), `deallocate()` (O(1), same), `construct()` (uses placement new), and `destroy()` (calls destructor then returns to pool).

### Variable-Size Pool (Block List)

For objects of varying sizes, a more complex pool divides memory into blocks of different sizes:

```cpp
class VariablePool {
public:
    VariablePool(size_t poolSize = 64 * 1024)
        : poolSize_(poolSize), used_(0) {
        pool_ = static_cast<char*>(std::aligned_alloc(
            alignof(std::max_align_t), poolSize));
    }

    ~VariablePool() {
        std::free(pool_);
    }

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        size = (size + alignment - 1) & ~(alignment - 1);

        if (used_ + size > poolSize_) {
            return nullptr;
        }

        void* result = pool_ + used_;
        used_ += size;
        return result;
    }

    void reset() {
        used_ = 0;
    }

    size_t used() const { return used_; }
    size_t capacity() const { return poolSize_; }

private:
    size_t poolSize_;
    size_t used_;
    void* pool_;
};
```

This "bump allocator" style pool simply increments a pointer for each allocation. It's extremely fast but only supports reset (freeing all memory at once), not individual deallocation. It's suitable for frames or phases where you allocate many objects and discard them together.

### Slab Allocation

Slab allocation divides memory into fixed-size "slabs," with each slab handling one object size. This combines the efficiency of fixed-size pools with support for multiple sizes:

```cpp
template<size_t BlockSize>
class Slab {
public:
    static constexpr size_t kSlabSize = 4096;
    static constexpr size_t kBlocksPerSlab = kSlabSize / BlockSize;

    Slab* nextSlab = nullptr;

    Slab() : freeHead_(0) {
        for (size_t i = 0; i < kBlocksPerSlab - 1; ++i) {
            *reinterpret_cast<size_t*>(block(i)) = i + 1;
        }
        *reinterpret_cast<size_t*>(block(kBlocksPerSlab - 1)) = kInvalidIndex;
    }

    void* allocate() {
        if (freeHead_ == kInvalidIndex) return nullptr;
        void* result = block(freeHead_);
        freeHead_ = *reinterpret_cast<size_t*>(result);
        return result;
    }

    void deallocate(void* ptr) {
        size_t index = static_cast<char*>(ptr) - reinterpret_cast<char*>(this);
        index /= BlockSize;
        *reinterpret_cast<size_t*>(ptr) = freeHead_;
        freeHead_ = index;
    }

    bool contains(void* ptr) const {
        auto* self = reinterpret_cast<const char*>(this);
        auto* p = static_cast<const char*>(ptr);
        return p >= self && p < self + kSlabSize;
    }

private:
    static constexpr size_t kInvalidIndex = static_cast<size_t>(-1);

    void* block(size_t index) {
        return reinterpret_cast<char*>(this) + sizeof(Slab) + index * BlockSize;
    }

    size_t freeHead_;
};

template<size_t BlockSize, size_t MaxSlabs = 128>
class SlabAllocator {
public:
    SlabAllocator() : slabs_(nullptr) {}

    ~SlabAllocator() {
        for (Slab<BlockSize>* s = slabs_; s;) {
            Slab<BlockSize>* next = s->nextSlab;
            std::free(s);
            s = next;
        }
    }

    void* allocate() {
        for (Slab<BlockSize>* s = slabs_; s; s = s->nextSlab) {
            if (void* ptr = s->allocate()) return ptr;
        }

        if (slabCount_ >= MaxSlabs) return nullptr;

        auto* newSlab = static_cast<Slab<BlockSize>*>(
            std::aligned_alloc(alignof(Slab<BlockSize>), sizeof(Slab<BlockSize>)));
        new (newSlab) Slab<BlockSize>();
        newSlab->nextSlab = slabs_;
        slabs_ = newSlab;
        ++slabCount_;

        return slabs_->allocate();
    }

    void deallocate(void* ptr) {
        for (Slab<BlockSize>* s = slabs_; s; s = s->nextSlab) {
            if (s->contains(ptr)) {
                s->deallocate(ptr);
                return;
            }
        }
    }

private:
    Slab<BlockSize>* slabs_;
    size_t slabCount_ = 0;
};
```

Slab allocation provides excellent performance when you have several distinct object sizes. Each size class has its own set of slabs, eliminating fragmentation within each class.

### Stack-Arena Pool

For temporary allocations with clear lifetime boundaries, a stack-style arena is simpler and more efficient:

```cpp
class StackArena {
public:
    explicit StackArena(size_t size)
        : size_(size), used_(0) {
        buffer_ = static_cast<char*>(std::aligned_alloc(alignof(std::max_align_t), size));
    }

    ~StackArena() {
        std::free(buffer_);
    }

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        size_t offset = reinterpret_cast<uintptr_t>(buffer_) & (alignment - 1);
        offset = (alignment - offset) & (alignment - 1);

        if (used_ + offset + size > size_) {
            return nullptr;
        }

        void* result = buffer_ + used_ + offset;
        used_ += offset + size;
        return result;
    }

    void reset() {
        used_ = 0;
    }

    size_t used() const { return used_; }
    size_t capacity() const { return size_; }

private:
    size_t size_;
    size_t used_;
    char* buffer_;
};

template<typename Arena = StackArena>
class ArenaAllocator {
public:
    explicit ArenaAllocator(Arena* arena) : arena_(arena) {}

    template<typename T>
    T* allocate(size_t n = 1) {
        if (n != 1) return nullptr;
        size_t size = sizeof(T);
        size_t alignment = alignof(T);
        return static_cast<T*>(arena_->allocate(size, alignment));
    }

    template<typename T, typename... Args>
    void construct(T* p, Args&&... args) {
        new (p) T(std::forward<Args>(args)...);
    }

    template<typename T>
    void destroy(T* p) {
        p->~T();
    }

    template<typename T>
    void deallocate(T*, size_t) {}

    Arena* arena() { return arena_; }

private:
    Arena* arena_;
};
```

Arena allocators are particularly useful for parsing, where you build up a tree of objects that all have the same lifetime—destroying the arena destroys them all efficiently.

### Thread-Local Pools

For multithreaded applications, per-thread pools eliminate lock contention:

```cpp
class ThreadLocalPool {
public:
    static ThreadLocalPool& instance() {
        static thread_local ThreadLocalPool pool;
        return pool;
    }

    void* allocate(size_t size) {
        return pool_.allocate(size);
    }

    void deallocate(void* ptr) {
        if (pool_.contains(ptr)) {
            pool_.deallocate(ptr);
        } else {
            std::free(ptr);
        }
    }

private:
    class LocalPool {
    public:
        LocalPool() : memory_(std::aligned_alloc(4096, 64 * 1024)), used_(0) {}

        void* allocate(size_t size) {
            if (used_ + size > 64 * 1024) return nullptr;
            void* ptr = static_cast<char*>(memory_) + used_;
            used_ += size;
            return ptr;
        }

        void deallocate(void*) {
            // Bump allocator - no individual deallocation
        }

        bool contains(void* ptr) {
            auto* p = static_cast<char*>(ptr);
            auto* m = static_cast<char*>(memory_);
            return p >= m && p < m + 64 * 1024;
        }

        void reset() { used_ = 0; }

    private:
        void* memory_;
        size_t used_;
    };

    thread_local LocalPool pool_;
};
```

Each thread has its own pool, so allocations don't require synchronization. This is particularly valuable for server applications handling many concurrent requests.

### Object Pool (Reusing Objects)

Sometimes you want to reuse whole objects rather than just memory:

```cpp
class ObjectPool {
public:
    template<typename T, typename... Args>
    std::shared_ptr<T> create(Args&&... args) {
        if (auto* raw = pool_.allocate()) {
            new (raw) T(std::forward<Args>(args)...);
            return std::shared_ptr<T>(raw, Deleter{this});
        }
        return nullptr;
    }

    void reclaim(T* ptr) {
        ptr->~T();
        pool_.deallocate(ptr);
    }

private:
    class Deleter {
    public:
        explicit Deleter(ObjectPool* pool) : pool_(pool) {}

        void operator()(T* ptr) const {
            pool_->reclaim(ptr);
        }

    private:
        ObjectPool* pool_;
    };

    struct FreeListNode {
        FreeListNode* next;
    };

    static constexpr size_t kCapacity = 1024;
    alignas(T) char storage_[kCapacity * sizeof(T)];
    FreeListNode* freeList_ = nullptr;
};
```

This object pool stores `std::shared_ptr` with a custom deleter that returns objects to the pool rather than destroying them. It's useful when object construction is expensive but objects can be reset and reused.

### Memory Pool with Proper Alignment

Alignment is crucial for correctness and performance:

```cpp
template<typename T, size_t Capacity>
class AlignedPool {
public:
    AlignedPool() {
        static_assert(Capacity > 0, "Capacity must be positive");
        static_assert(alignof(T) <= alignof(AlignedPool), "Invalid alignment");

        freeList_ = nullptr;
        for (size_t i = 0; i < Capacity; ++i) {
            void* slot = &storage_[i];
            *static_cast<void**>(slot) = freeList_;
            freeList_ = slot;
        }
    }

    T* allocate() {
        if (!freeList_) return nullptr;
        void* slot = freeList_;
        freeList_ = *static_cast<void**>(slot);
        return static_cast<T*>(slot);
    }

    void deallocate(T* ptr) {
        *static_cast<void**>(ptr) = freeList_;
        freeList_ = ptr;
    }

    template<typename... Args>
    T* construct(Args&&... args) {
        T* ptr = allocate();
        if (ptr) {
            new (ptr) T(std::forward<Args>(args)...);
        }
        return ptr;
    }

    void destroy(T* ptr) {
        if (ptr) {
            ptr->~T();
            deallocate(ptr);
        }
    }

private:
    alignas(T) char storage_[Capacity * sizeof(T)];
    void* freeList_;
};
```

The `alignas(T)` ensures the storage meets the alignment requirements of type T. Without this, aligned access might fail or perform poorly on some architectures.

### PoolAllocator for Standard Containers

Memory pools integrate with standard containers through allocators:

```cpp
template<typename T, size_t PoolSize = 1024>
class PoolAllocator {
public:
    using value_type = T;
    using pointer = T*;
    using const_pointer = const T*;
    using reference = T&;
    using const_reference = const T&;
    using size_type = std::size_t;
    using difference_type = std::ptrdiff_t;

    template<typename U>
    struct rebind {
        using other = PoolAllocator<U, PoolSize>;
    };

    PoolAllocator() noexcept = default;

    T* allocate(size_type n, const void* = nullptr) {
        if (n != 1) throw std::bad_alloc();
        return static_cast<T*>(pool_.allocate());
    }

    void deallocate(T* p, size_type) {
        pool_.deallocate(p);
    }

    template<typename U, typename... Args>
    void construct(U* p, Args&&... args) {
        new (p) U(std::forward<Args>(args)...);
    }

    template<typename U>
    void destroy(U* p) {
        p->~U();
    }

    bool operator==(const PoolAllocator& other) const { return true; }
    bool operator!=(const PoolAllocator& other) const { return false; }

private:
    static thread_local typename std::aligned_storage<sizeof(T), alignof(T)>::type poolStorage_;
    struct Pool {
        void* allocate() {
            if (head_) {
                void* result = head_;
                head_ = *static_cast<void**>(result);
                return result;
            }
            return nullptr;
        }
        void deallocate(void* ptr) {
            *static_cast<void**>(ptr) = head_;
            head_ = ptr;
        }
        void* head_ = nullptr;
    };
    static Pool& getPool() {
        static Pool p;
        return p;
    }
    Pool& pool_ = getPool();
};

template<typename T, size_t N>
thread_local typename std::aligned_storage<sizeof(T), alignof(T)>::type
    PoolAllocator<T, N>::poolStorage_;

// Usage:
std::vector<Widget, PoolAllocator<Widget, 256>> widgets;
```

This allocator satisfies the `std::allocator` requirements, enabling use with standard containers. The pool is shared across all containers using the same allocator type.

### Pool Performance Characteristics

Memory pools dramatically improve performance in the right scenarios. Consider these characteristics:

**Allocation speed**: Pool allocation is typically 10-100x faster than general `new`. The difference is stark in benchmarks—where general allocation might take hundreds of nanoseconds, pool allocation takes single-digit nanoseconds.

**Deallocation speed**: Similarly fast for pools that return to a free list. Bump allocators don't track individual deallocations at all.

**Memory usage**: Pools eliminate fragmentation since they use fixed-size blocks or contiguous regions. They also avoid the metadata overhead that general allocators store with each allocation.

**Cache behavior**: Objects from the same pool are adjacent, improving cache utilization during iteration. This can provide 2-10x improvements in traversal-heavy code.

The trade-off is flexibility—you can't deallocate arbitrary amounts or grow pools dynamically (without complex implementations). Use pools when allocation patterns are known and repetitive.

### When to Use Memory Pools

Memory pools suit specific scenarios:

**High-frequency allocations**: Game engines allocating thousands of entities per frame, network servers handling requests, parsers building syntax trees—these all benefit from pools.

**Real-time systems**: Systems with strict timing requirements need allocation times that don't vary. Pools provide constant-time allocation.

**Embedded systems**: Limited heap availability and no OS memory management make pools attractive. Pre-allocated pools avoid fragmentation that would be unrecoverable.

**Deterministic behavior**: When you need to know maximum memory usage or allocation time, pools provide the guarantees that general allocators cannot.

Avoid pools when allocation sizes vary wildly, when you need to deallocate while keeping others allocated (except with free-list pools), or when memory is abundant and allocation performance isn't critical.

### Summary

Memory pools pre-allocate memory blocks and subdivide them for individual allocations, dramatically improving performance for repetitive allocation patterns. Fixed-size pools use free lists for O(1) allocate/deallocate. Variable-size bump allocators provide fast allocation with reset-only deallocation. Slab allocation handles multiple object sizes efficiently. Arena allocators support many short-lived objects with single reset. Thread-local pools eliminate contention in concurrent applications. Object pools reuse entire objects rather than just memory. Integration with standard containers happens through custom allocators.

Pools trade flexibility for speed and predictability—they're essential when performance matters and allocation patterns are known. The key is choosing the right pool type for your allocation pattern.

---

## Summary

This chapter explored four idioms for buffer and memory management. Buffer management idioms covered sizing strategies, ownership models, zero-copy passing, alignment, ring buffers, and migration patterns. The Small Buffer Optimization stores small data inline for efficiency. Placement new enables construction at specific memory locations. Memory pools provide high-performance allocation for repetitive allocations.

---

### Exercises

1. **Buffer Design**: Design a buffer class that uses SBO for small sizes but falls back to heap allocation for larger data. Compare performance with `std::vector` and `std::string` for various sizes.

2. **Ring Buffer Implementation**: Implement a lock-free single-producer single-consumer ring buffer. Handle the edge case of distinguishing full from empty states.

3. **Pool Allocator**: Design a memory pool for fixed-size objects. Implement allocation and deallocation with no general heap usage.

4. **Placement New Usage**: Use placement new to construct objects in a pre-allocated buffer, then implement proper destruction without deallocating the underlying memory.

5. **Buffer View Design**: Design a buffer view class that provides read-only access to a subregion of a buffer without copying. Ensure it can't outlive the underlying buffer.