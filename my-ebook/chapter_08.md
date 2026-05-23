# Chapter 8: Type Erasure

Type erasure is a powerful technique that allows you to store and operate on values of different types through a uniform interface, while erasing the specific type information at compile time. This pattern enables runtime polymorphism without the overhead of virtual functions, flexible container design, and APIs that accept heterogeneous types. Understanding type erasure helps you design libraries that are both flexible and efficient.

This chapter explores four aspects of type erasure: the fundamental concept of erasing type information for polymorphism, how `std::function` implements type erasure for callable objects, the `std::any` type for holding arbitrary values, and type lists for compile-time polymorphic patterns.

## Type Erasure for Polymorphism

Type erasure is a design pattern where you hide the specific type of an object while preserving its functionality through a generic interface. Unlike inheritance-based polymorphism (using virtual functions), type erasure achieves polymorphism without requiring objects to share a common base class at compile time. Instead, type information is stored at runtime, typically through type-erased wrappers and function pointers.

### The Problem Type Erasure Solves

Traditional polymorphism requires a common interface:

```cpp
class Shape {
public:
    virtual void draw() const = 0;
    virtual ~Shape() = default;
};

class Circle : public Shape {
    void draw() const override { /* ... */ }
};

class Square : public Shape {
    void draw() const override { /* ... */ }
};

void renderAll(const std::vector<std::unique_ptr<Shape>>& shapes) {
    for (const auto& shape : shapes) {
        shape->draw();
    }
}
```

This works well but requires all types to inherit from `Shape`. You cannot store fundamentally different types—like a function object, a lambda, and a class instance—in the same container without a common base.

Type erasure removes this requirement:

```cpp
class AnyDrawable {
public:
    template<typename T>
    AnyDrawable(T value) : wrapper_(std::make_unique<Model<T>>(std::move(value))) {}

    void draw() const { wrapper_->draw(); }

private:
    struct Concept {
        virtual ~Concept() = default;
        virtual void draw() const = 0;
    };

    template<typename T>
    struct Model : Concept {
        Model(T value) : value_(std::move(value)) {}
        void draw() const override { value_.draw(); }
        T value_;
    };

    std::unique_ptr<Concept> wrapper_;
};
```

Now `AnyDrawable` can wrap any type that has a `draw()` method—no inheritance required. The type is erased, and the common interface is preserved.

### How Type Erasure Works

Type erasure typically involves four components:

**The handle type**: The public interface that users interact with. In the example above, this is `AnyDrawable`.

**The concept**: The abstract interface defining what operations must be supported. Here, that's the `Concept` class with its `draw()` method.

**The model**: A template that implements the concept for a specific type. `Model<T>` implements `Concept` by delegating to the stored `T`.

**The storage**: Where the actual value is stored. Here, `Model<T>` contains a `T` value.

The key insight is that `Concept` defines the interface at compile time, but `Model<T>` captures the actual type at runtime. When you call `draw()`, the call goes through the virtual function in `Concept`, which dispatches to the appropriate `Model<T>::draw()`.

### A More Complete Example

Let's build a more sophisticated type-erased container:

```cpp
template<typename Signature>
class FunctionWrapper;

template<typename R, typename... Args>
class FunctionWrapper<R(Args...)> {
public:
    FunctionWrapper() = default;

    template<typename F>
    FunctionWrapper(F&& f) : wrapper_(std::make_unique<Model<std::decay_t<F>>>(std::forward<F>(f))) {}

    R operator()(Args... args) const {
        return wrapper_->invoke(std::forward<Args>(args)...);
    }

    explicit operator bool() const { return wrapper_ != nullptr; }

private:
    struct Concept {
        virtual ~Concept() = default;
        virtual std::unique_ptr<Concept> clone() const = 0;
        virtual R invoke(Args...) const = 0;
    };

    template<typename F>
    struct Model : Concept {
        Model(F f) : value_(std::move(f)) {}
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(value_);
        }
        R invoke(Args... args) const override {
            return value_(std::forward<Args>(args)...);
        }
        mutable F value_;
    };

    std::unique_ptr<Concept> wrapper_;
};
```

This `FunctionWrapper` can store any callable with the matching signature—functions, lambdas, functors, or function objects. The type of the callable is erased, but the call semantics are preserved.

### Type Erasure vs Virtual Functions

Type erasure and inheritance-based polymorphism both enable runtime polymorphism, but they differ in important ways:

**Type requirements**: Inheritance requires a common base class; type erasure works with any type satisfying the concept.

**Size**: A type-erased wrapper typically contains a pointer to the concept and potentially stores the value inline or on the heap. Virtual dispatch adds a vtable pointer per object.

**Performance**: Virtual dispatch has call overhead and prevents certain optimizations. Type erasure can be more efficient in some cases (no vtable, potentially inlined calls) but slower in others (heap allocation for the model).

**Flexibility**: Type erasure is more flexible—you can add new types without modifying existing code, and types don't need to share any inheritance relationship.

**Safety**: Virtual functions provide type safety at compile time (you can't accidentally call an unimplemented method if the interface is correct). Type erasure requires careful design to maintain safety.

### Erasure with Value Storage

When the stored type is small, you can avoid heap allocation by storing the value directly:

```cpp
template<typename Signature, size_t MaxSize = 32>
class InlineFunction;

template<typename R, typename... Args, size_t MaxSize>
class InlineFunction<R(Args...), MaxSize> {
public:
    template<typename F>
    InlineFunction(F&& f) {
        static_assert(sizeof(F) <= MaxSize, "Type too large for inline storage");
        static_assert(alignof(F) <= alignof(Concept), "Type alignment too large");
        new (storage_.data()) Model<F>(std::forward<F>(f));
        hasValue_ = true;
    }

    ~InlineFunction() {
        if (hasValue_) {
            model()->~Concept();
        }
    }

    R operator()(Args... args) const {
        return model()->invoke(std::forward<Args>(args)...);
    }

private:
    Concept* model() { return reinterpret_cast<Concept*>(storage_.data()); }
    const Concept* model() const { return reinterpret_cast<const Concept*>(storage_.data()); }

    struct Concept {
        virtual ~Concept() = default;
        virtual R invoke(Args...) const = 0;
    };

    template<typename F>
    struct Model : Concept {
        Model(F f) : value_(std::move(f)) {}
        R invoke(Args... args) const override {
            return value_(std::forward<Args>(args)...);
        }
        F value_;
    };

    alignas(Concept) std::array<char, MaxSize> storage_;
    bool hasValue_ = false;
};
```

This stores the model inline when it fits within the buffer, falling back to heap allocation for larger types. The standard library uses this technique in `std::function` (the small buffer optimization applies to small callables).

### Erasure with Function Pointers

For very simple cases, you can use function pointers directly:

```cpp
class SimpleCallable {
public:
    using FuncPtr = void(*)(void*);

    template<typename F>
    SimpleCallable(F f) : func_([](void* self) {
        auto* self2 = static_cast<Model<F>*>(self);
        self2->value_();
    }), data_(new Model<F>(std::move(f))) {}

    void operator()() const {
        func_(data_.get());
    }

private:
    struct Concept {
        virtual ~Concept() = default;
    };

    template<typename F>
    struct Model : Concept {
        F value_;
    };

    FuncPtr func_;
    std::unique_ptr<Concept> data_;
};
```

This uses a thin vtable with just a function pointer, avoiding the overhead of a full virtual dispatch. It's less flexible than the earlier approaches but extremely lightweight.

### Type Erasure and Move Semantics

Type-erased containers need careful handling of move semantics:

```cpp
template<typename T>
class ErasureWrapper {
public:
    template<typename U>
    ErasureWrapper(U&& value) : wrapper_(std::make_unique<Model<std::decay_t<U>>>(
        std::forward<U>(value))) {}

    ErasureWrapper(ErasureWrapper&& other) noexcept
        : wrapper_(std::move(other.wrapper_)) {}

    ErasureWrapper& operator=(ErasureWrapper&& other) noexcept {
        wrapper_ = std::move(other.wrapper_);
        return *this;
    }

private:
    struct Concept {
        virtual ~Concept() = default;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    template<typename T>
    struct Model : Concept {
        Model(T value) : value_(std::move(value)) {}
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(value_);
        }
        T value_;
    };

    std::unique_ptr<Concept> wrapper_;
};
```

The clone function enables copying type-erased wrappers by asking each model to copy itself. Move operations can simply transfer the underlying pointer when possible.

### Concept Validation

Type erasure loses compile-time type checking, so you must ensure the wrapped type satisfies the concept. Several approaches help:

**Static assertion in constructor**: Use `static_assert` with a type trait:

```cpp
template<typename T>
concept Drawable = requires(T t) { t.draw(); };

template<typename T>
Eraser(Drawable auto value) { ... }
```

**SFINAE**: Disable the constructor for invalid types:

```cpp
template<typename T, typename = std::enable_if_t<...>>
Eraser(T value) { ... }
```

**Concept-based constructor**: C++20 concepts enable elegant constraints:

```cpp
template<Drawable T>
Eraser(T value) { ... }
```

Without such checks, errors manifest at the point of use rather than the point of construction, making debugging harder.

### Performance Considerations

Type erasure has performance characteristics worth understanding:

**Heap allocation**: By default, each wrapped type requires heap allocation for the model. The small buffer optimization mitigates this for small types.

**Indirection**: Calling through type erasure adds at least one level of indirection. For hot paths, this matters.

**Inlining**: The compiler can inline through type erasure in some cases, but it depends on the implementation and optimization level.

**Cache behavior**: Inline storage improves cache locality. Heap-allocated models may cause cache misses.

If performance is critical, measure the impact and consider alternatives—perhaps the type set is small enough for inheritance-based polymorphism, or perhaps you need a hand-optimized implementation.

### Summary

Type erasure enables runtime polymorphism without inheritance, allowing you to store and operate on heterogeneous types through a common interface. The pattern involves a handle type, a concept (abstract interface), models (type-specific implementations), and storage. Type erasure trades compile-time type safety for runtime flexibility. It suits scenarios where types share behavior but not a common base, when you need to decouple interfaces from implementations, or when you want to erase type information for API flexibility.

The implementations shown here form the foundation for `std::function`, `std::any`, and similar standard library facilities. Understanding the mechanics helps you build custom type-erased wrappers and appreciate how the standard library achieves its flexibility.

---

## std::function Implementation Patterns

`std::function` is the standard library's type-erased wrapper for callable objects. It can store any callable—a function pointer, lambda, functor, or member function—with a matching signature. Understanding how `std::function` works internally helps you use it effectively and implement similar functionality in your own code.

### The std::function Interface

`std::function` provides a uniform interface for callable objects:

```cpp
#include <functional>

std::function<int(int, int)> func = [](int a, int b) { return a + b; };
int result = func(1, 2);  // Returns 3

func = std::plus<int>();  // Can be reassigned to different callable types
result = func(1, 2);  // Still returns 3 (plus semantics)

auto bound = std::bind(std::plus<int>(), std::placeholders::_1, 10);
func = bound;
result = func(5);  // Returns 15
```

The key feature is that `func` can hold fundamentally different types—lambdas, function objects, bound functions—but presents a uniform call interface. This is type erasure applied to callables.

### Small Buffer Optimization in std::function

`std::function` uses the small buffer optimization (SBO) to avoid heap allocation for small callables:

```cpp
// Simplified view of typical std::function implementation
template<typename Signature>
class function;

template<typename R, typename... Args>
class function<R(Args...)> {
    static constexpr size_t kSmallBufferSize = 64;  // Often 48-64 bytes

    alignas(void*) char buffer_[kSmallBufferSize];
    // Plus some state: isSmall_, hasValue_, etc.

    // If callable fits in buffer: store inline
    // Otherwise: allocate on heap
};
```

The standard doesn't mandate the buffer size—it's implementation-defined. Typical implementations use 48-64 bytes, which accommodates many lambdas and small functors without heap allocation.

The implementation uses placement new to construct the callable in the buffer:

```cpp
template<typename F>
void setCallable(F&& f) {
    if (sizeof(F) <= kSmallBufferSize && alignof(F) <= kSmallBufferSize) {
        // Store inline using placement new
        new (buffer_) CallableModel<F>(std::forward<F>(f));
        isSmall_ = true;
    } else {
        // Store on heap
        callable_ = new CallableModel<F>(std::forward<F>(f));
        isSmall_ = false;
    }
    hasValue_ = true;
}
```

This is why passing small lambdas to `std::function` is often zero-cost—the callable lives within the `std::function` object itself.

### The Invocation Mechanism

When you call a `std::function`, it delegates to the stored callable through a virtual dispatch:

```cpp
R operator()(Args... args) const {
    if (!hasValue_) {
        throw std::bad_function_call();
    }
    return invokeImpl(args...);
}

virtual R invokeImpl(Args... args) const = 0;

// Concrete implementation:
R ConcreteModel<F>::invokeImpl(Args... args) const {
    return callable_(std::forward<Args>(args)...);
}
```

The virtual function enables runtime polymorphism—you don't know at compile time what type of callable is stored, but the call works through the virtual dispatch.

### std::function and Type Erasure

`std::function` implements type erasure for callables specifically. The concept is "callable with signature R(Args...)":

```cpp
template<typename Signature>
class function;

// Specialization for specific signature
template<typename R, typename... Args>
class function<R(Args...)> {
    // Concept: anything that can be called with Args... and returns R
    // Model: wraps the actual callable type
};
```

The concept is defined by what's callable—not by inheritance. A lambda is callable, a function pointer is callable, a class with `operator()` is callable. `std::function` accepts all of these because the concept is based on syntax (callable) rather than type hierarchy.

This is a key distinction from inheritance-based approaches:

```cpp
// Inheritance-based: requires common base
class CallableBase {
public:
    virtual int operator()(int) = 0;
    virtual ~CallableBase() = default;
};

class MyCallable : public CallableBase {
    int operator()(int x) override { return x * 2; }
};

// Type erasure: any callable works
std::function<int(int)> func = MyCallable{};
func = [](int x) { return x * 2; };
func = &doubleValue;
```

### Storage Strategies

Different implementations use different storage strategies:

**Inline buffer**: Store small callables inline, larger ones on heap. This is the most common approach.

```cpp
union Storage {
    void* heapPointer;
    char inlineBuffer[64];
} storage_;
```

**Discriminated union**: Use a tagged union to track which representation is active.

```cpp
enum class StorageKind { Empty, Inline, Heap };
StorageKind kind_;

union {
    InlineCallable inline_;
    std::unique_ptr<HeapCallable> heap_;
};
```

**External storage**: Some implementations always allocate, storing a pointer to external memory. This is simpler but slower for small callables.

### Copy and Move Semantics

`std::function` must support copying and moving, which is tricky because the callable type is erased:

```cpp
// Copy constructor implementation
function(const function& other) {
    if (other.hasValue_) {
        if (other.isSmall_) {
            // Clone inline
            other.cloneTo(buffer_);
            isSmall_ = true;
        } else {
            // Clone heap
            callable_ = other.callable_->clone();
            isSmall_ = false;
        }
        hasValue_ = true;
    }
}
```

The clone function is defined by the model:

```cpp
template<typename F>
struct CallableModel : Concept {
    F callable;

    std::unique_ptr<Concept> clone() const override {
        return std::make_unique<CallableModel>(callable);
    }

    R invoke(Args... args) const override {
        return callable(std::forward<Args>(args)...);
    }
};
```

Move semantics are similar but transfer ownership rather than clone:

```cpp
function(function&& other) noexcept {
    if (other.hasValue_) {
        if (other.isSmall_) {
            // Move the inline buffer
            other.moveTo(buffer_);
            isSmall_ = true;
        } else {
            // Transfer heap pointer
            callable_ = other.callable_;
            other.callable_ = nullptr;
            isSmall_ = false;
        }
        hasValue_ = other.hasValue_;
    }
}
```

### Handling Different Callable Types

`std::function` must handle several callable categories:

**Free functions**: Can be stored as function pointers, no state required.

```cpp
int (*fn)(int, int) = [](int a, int b) { return a + b; };
// Can convert to function pointer
std::function<int(int, int)> f = fn;
```

**Lambdas**: Each unique lambda has a distinct type. Stored in the model.

```cpp
auto lambda = [](int x) { return x * 2; };
std::function<int(int)> f = lambda;  // lambda's type is unique
```

**Functors**: Classes with `operator()`. Stored like lambdas.

```cpp
struct Adder {
    int operator()(int a, int b) const { return a + b; }
};
std::function<int(int, int)> f = Adder{};
```

**Member functions**: Require a pointer to an object:

```cpp
struct Counter {
    int count = 0;
    int operator()() { return ++count; }
};

Counter c;
std::function<int()> f = std::ref(c);  // std::ref creates a function object
// Or with std::bind:
using namespace std::placeholders;
std::function<int()> f = std::bind(&Counter::operator(), &c);
```

**Stateless lambdas**: Can be converted to function pointers when they capture nothing:

```cpp
auto f = [](int x) { return x * 2; };
// Can convert to function pointer
int (*fn)(int) = f;  // Only for capture-free lambdas
```

### Implementation Reference: callable_wrapper

Some implementations use a `callable_wrapper` pattern:

```cpp
class function<R(Args...)> {
private:
    struct Concept {
        virtual ~Concept() = default;
        virtual R invoke(Args...) = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };

    template<typename F>
    struct Model : Concept {
        F callable;
        R invoke(Args... args) override {
            return callable(std::forward<Args>(args)...);
        }
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model>(callable);
        }
    };

    std::unique_ptr<Concept> callable_;
};
```

This structure mirrors what we built earlier in the type erasure examples. The standard library implementation is more complex (handling SBO, allocator support, etc.) but follows the same pattern.

### Performance Characteristics

`std::function` has specific performance properties:

**Construction overhead**: Creating a `std::function` from a lambda involves allocating (if large) or copy/move (if small). For small inline callables, this is very fast.

**Call overhead**: Each call goes through at least one virtual dispatch. This is typically 1-2 nanoseconds overhead—negligible for most applications but measurable in tight loops.

**Memory footprint**: Even empty `std::function` objects are relatively large (typically 64+ bytes). Don't use `std::function` in inner loops or in types that you instantiate many times.

**Cache behavior**: Inline storage keeps small callables cache-friendly. Heap-allocated callables may cause cache misses.

### Custom Function Implementation

You can implement your own type-erased function to understand the pattern better:

```cpp
template<typename Signature>
class my_function;

template<typename R, typename... Args>
class my_function<R(Args...)> {
public:
    my_function() = default;

    template<typename F>
    my_function(F f) {
        if constexpr (sizeof(F) <= kInlineSize) {
            model_ = std::make_unique<Model<F>>(std::move(f));
        } else {
            // Fall back to heap for large callables
            model_ = std::make_unique<HeapModel<F>>(std::move(f));
        }
    }

    R operator()(Args... args) const {
        return model_->invoke(std::forward<Args>(args)...);
    }

    explicit operator bool() const { return model_ != nullptr; }

private:
    static constexpr size_t kInlineSize = 48;

    struct Concept {
        virtual ~Concept() = default;
        virtual R invoke(Args...) = 0;
    };

    template<typename F>
    struct Model : Concept {
        F callable;
        Model(F f) : callable(std::move(f)) {}
        R invoke(Args... args) override {
            return callable(std::forward<Args>(args)...);
        }
    };

    template<typename F>
    struct HeapModel : Concept {
        std::unique_ptr<F> callable;
        HeapModel(F f) : callable(std::make_unique<F>(std::move(f))) {}
        R invoke(Args... args) override {
            return (*callable)(std::forward<Args>(args)...);
        }
    };

    std::unique_ptr<Concept> model_;
};
```

This simplified implementation demonstrates the core ideas without the complexity of SBO, allocator support, and exception handling.

### When to Use std::function

`std::function` is appropriate in these scenarios:

- **Callbacks**: Storing callbacks that come from various sources (lambdas, function pointers, bound functions)
- **Event systems**: Generic event handlers that accept any callable
- **API flexibility**: Functions that need to accept different callable types
- **Delaying binding**: Separating the time a callable is created from when it's invoked

Avoid `std::function` when:
- **Performance is critical**: In hot loops, the virtual call overhead may matter
- **Type information matters**: You need compile-time type specificity
- **You know the exact type**: If there's only one callable type, use it directly
- **Many small objects**: `std::function` is relatively large

### Summary

`std::function` implements type erasure for callable objects through a concept/model pattern with small buffer optimization. It stores any callable type through a uniform interface, using virtual dispatch for calls. The implementation must handle copy/move semantics, different callable categories, and performance trade-offs between inline storage and heap allocation. Understanding these patterns helps you use `std::function` effectively and implement similar functionality in your own code.

The techniques shown here generalize beyond callables—the same pattern applies to any type erasure scenario.

---

## std::any and Type Erasure

`std::any` is the most general form of type erasure in the standard library. Unlike `std::function` which restricts stored types to those matching a specific signature, `std::any` can store values of any type. This makes it useful for scenarios where you need to store heterogeneous values but don't know their types at compile time—particularly in generic containers, plugin systems, or dynamic type handling.

### The std::any Interface

`std::any` provides a type-erased container:

```cpp
#include <any>

std::any value = 42;  // Store an int
value = std::string("hello");  // Now store a string
value = std::vector<int>{1, 2, 3};  // Now store a vector

// Extract the value - must know the type
int i = std::any_cast<int>(value);  // Throws std::bad_any_cast if wrong type

// Safe extraction with pointer
int* pi = std::any_cast<int>(&value);  // Returns nullptr if wrong type
```

`std::any` is essentially a type-erased box that can hold any value. You must know the type when retrieving—if you ask for the wrong type, you get an exception or null pointer.

### How std::any Works

`std::any` implements type erasure by storing a small buffer for small types and allocating on heap for large ones:

```cpp
// Simplified std::any implementation
class any {
public:
    static constexpr size_t kSmallBufferSize = sizeof(void*) * 2;  // Typically 16 bytes

    any() : holder_(nullptr) {}

    template<typename T>
    any(T value) {
        if (sizeof(T) <= kSmallBufferSize) {
            // Store inline using type-erased wrapper
            holder_ = new SmallHolder<T>(std::move(value));
        } else {
            // Heap allocate
            holder_ = new LargeHolder<T>(std::move(value));
        }
    }

    ~any() { delete holder_; }

    template<typename T>
    T* any_cast() noexcept {
        if (auto* h = dynamic_cast<Holder<T>*>(holder_)) {
            return &h->value();
        }
        return nullptr;
    }

private:
    struct Holder {
        virtual ~Holder() = default;
        virtual const std::type_info& type() const = 0;
    };

    template<typename T>
    struct SmallHolder : Holder {
        alignas(T) unsigned char buffer[sizeof(T)];
        SmallHolder(T v) { new (buffer) T(std::move(v)); }
        T& value() { return *reinterpret_cast<T*>(buffer); }
        const std::type_info& type() const override { return typeid(T); }
    };

    template<typename T>
    struct LargeHolder : Holder {
        std::unique_ptr<T> value;
        LargeHolder(T v) : value(std::make_unique<T>(std::move(v))) {}
        T* valuePtr() { return value.get(); }
        const std::type_info& type() const override { return typeid(T); }
    };

    Holder* holder_;
};
```

The key insight is that `any_cast<T>` uses `dynamic_cast` to check if the holder is of the correct type. This works because all `Holder<T>` derive from the same base, enabling runtime type identification.

### Type Information with std::any

`std::any` maintains type information at runtime:

```cpp
std::any value = 42;

// Query the type
if (value.type() == typeid(int)) {
    int i = std::any_cast<int>(value);
}

// type() returns std::type_info
std::cout << value.type().name() << std::endl;  // Prints "int"
```

The `type()` method returns `std::type_info`, enabling runtime type queries. This is how `std::any_cast` determines if the cast is valid.

### std::any_cast Mechanics

`std::any_cast` has two forms:

```cpp
// Value extraction - throws on mismatch
template<typename T>
T any_cast(any& a) {
    T* ptr = any_cast<T>(&a);
    if (!ptr) {
        throw std::bad_any_cast();
    }
    return *ptr;
}

// Pointer extraction - returns nullptr on mismatch
template<typename T>
T* any_cast(any* a) {
    if (!a) return nullptr;
    return a->type() == typeid(T) ? /* get pointer to value */ : nullptr;
}
```

The pointer version is useful when you're not sure of the type:

```cpp
void processAny(const std::any& value) {
    if (auto* i = std::any_cast<int>(&value)) {
        std::cout << "Integer: " << *i << std::endl;
    } else if (auto* s = std::any_cast<std::string>(&value)) {
        std::cout << "String: " << *s << std::endl;
    } else {
        std::cout << "Unknown type" << std::endl;
    }
}
```

### Small Object Optimization in std::any

Like `std::function`, `std::any` typically uses SBO for small types:

```cpp
// Typical implementation has inline storage
class any {
    // Usually 16-32 bytes depending on implementation
    alignas(void*) char buffer_[32];
    // Plus state to track if value is set, small vs large, etc.
};
```

Types that fit in the buffer are stored inline—no heap allocation. Larger types use heap allocation. The threshold varies by implementation but is typically 16-32 bytes.

This means storing small types in `std::any` can be very efficient:

```cpp
std::any small = 42;  // Inline storage - no allocation
std::any medium = std::array<int, 8>{};  // Might allocate depending on size
std::any large = std::vector<int>(1000);  // Always heap allocated
```

### std::any with Custom Types

`std::any` works with any copyable type:

```cpp
struct MyData {
    int id;
    std::string name;
    std::vector<double> values;
};

std::any config = MyData{1, "test", {1.0, 2.0, 3.0}};

// Later...
MyData& data = std::any_cast<MyData&>(config);  // Reference version
data.name = "updated";
```

The stored type must be copyable (or movable). Move-only types work but can't be copied out of the `any`.

### Move Semantics with std::any

`std::any` supports move semantics:

```cpp
std::any moveSource() {
    std::any a = std::string("temporary");
    return a;  // Move into return value
}

void consume(std::any value) {
    // value was moved in
    auto s = std::any_cast<std::string>(std::move(value));
    std::cout << s << std::endl;
}
```

Moving an `std::any` is efficient—inline values are moved (copied for small types), heap-allocated values have ownership transferred.

### Type Erasure Comparison: std::function vs std::any

The two differ in their constraints:

**std::function<R(Args...)>**:
- Only stores callables with a specific signature
- Can invoke the callable with type-safe arguments
- Knows the call signature at compile time

**std::any**:
- Stores any type
- No built-in operations on the stored value
- Must know type to extract value

```cpp
// std::function constrains what's stored
std::function<int(int, int)> add = [](int a, int b) { return a + b; };
int result = add(1, 2);  // Type-safe call

// std::any accepts anything
std::any anything = [](int a, int b) { return a + b; };
// But you can't call it directly - must know the type
auto fn = std::any_cast<std::function<int(int, int)>>(anything);
result = fn(1, 2);
```

### Custom Type-Erased Container

You can implement your own `std::any`-like container for specialized needs:

```cpp
template<typename... Types>
class variant_any {
public:
    template<typename T>
    variant_any(T value) {
        static_assert((std::is_same_v<T, Types> || ...), "Invalid type");
        // Store using index to track which type
        if constexpr (sizeof(T) <= kInlineSize) {
            new (storage_.data()) T(std::move(value));
            index_ = typeIndex<T>;
        } else {
            heap_ = std::make_unique<T>(std::move(value));
            index_ = typeIndex<T>;
        }
    }

    template<typename T>
    T* any_cast() noexcept {
        if (index_ == typeIndex<T>) {
            if constexpr (sizeof(T) <= kInlineSize) {
                return reinterpret_cast<T*>(storage_.data());
            } else {
                return static_cast<std::unique_ptr<T>&>(heap_).get();
            }
        }
        return nullptr;
    }

private:
    static constexpr size_t kInlineSize = 32;
    size_t index_ = std::numeric_limits<size_t>::max();
    std::array<char, kInlineSize> storage_;
    std::unique_ptr<void> heap_;
};
```

This variant restricts to specific types while still erasing them—combining safety with flexibility.

### Performance Considerations

`std::any` has specific performance characteristics:

**Storage**: Inline for small types (typically 16-32 bytes), heap for larger types. This is transparent to users.

**Access**: `std::any_cast` requires type checking and potentially casting. The cost is typically small but measurable in tight loops.

**Memory**: An empty `std::any` still contains the buffer (32 bytes typical) and state. It also stores type information.

**Copying**: Copying a `std::any` requires copying the stored value, which may allocate if the type is large.

### When to Use std::any

`std::any` is appropriate when:

- **Heterogeneous storage**: You need to store values of unknown or varied types
- **Plugin systems**: Load modules that expose unknown types
- **Generic containers**: Create containers that hold any type
- **Type-agnostic APIs**: APIs that receive arbitrary data

Avoid `std::any` when:

- **Known types**: If you know the possible types at compile time, use `std::variant`
- **Performance is critical**: The type checking and indirection have overhead
- **Type safety is needed**: You want compile-time guarantees about what's stored
- **Operations are needed**: You need to do more than just store and retrieve

### std::any vs Alternatives

Consider alternatives for specific use cases:

**std::variant**: When you know the possible types at compile time:

```cpp
std::variant<int, std::string, double> v = 42;
std::visit([](auto& val) { std::cout << val; }, v);  // Type-safe visitation
```

**std::function**: When you need to store callables with a specific signature:

```cpp
std::function<void(int)> callback = [](int) { };
```

**Custom solutions**: When you need specific semantics beyond what standard containers provide.

### Summary

`std::any` provides the most general form of type erasure—storing values of any type while enabling type-safe retrieval. It uses small buffer optimization for small types, maintains runtime type information via `std::type_info`, and supports move semantics. The key operation is `std::any_cast` which validates the type at runtime.

`std::any` suits scenarios where types aren't known at compile time, while `std::variant` is better when types are known. Understanding this distinction helps you choose the right tool and implement similar functionality when needed.

---

## Type Lists and Compile-Time Polymorphism

Type lists are a compile-time technique for representing and manipulating collections of types. Unlike runtime containers that hold values, type lists hold types—allowing you to write template metaprograms that operate on types at compile time. This enables static polymorphism, type-based code generation, and compile-time computation over type collections.

### What Are Type Lists

A type list is a template that encodes a list of types:

```cpp
// Basic type list structure
template<typename... Types>
struct TypeList {};

using MyTypes = TypeList<int, double, std::string, char>;
```

The `TypeList` itself is just a marker—it holds the types as template parameters. The real power comes from operations on type lists that compute at compile time.

This is different from runtime polymorphism. Instead of erasing types at runtime (like `std::any`), type lists keep all type information available at compile time, enabling the compiler to generate optimal code.

### Basic Type List Implementation

A complete type list implementation provides operations:

```cpp
template<typename... Types>
struct TypeList {
    using head = /* first type */;
    using tail = /* remaining types */;
    static constexpr size_t size = /* number of types */;
};

// Specialization for empty list
template<>
struct TypeList<> {
    static constexpr size_t size = 0;
};
```

The classic implementation uses recursive template specialization:

```cpp
// Type list node - holds one type and links to rest
template<typename Head, typename Tail>
struct TypeListNode {
    using head = Head;
    using tail = Tail;
};

// Convenience alias for building lists
template<typename H, typename... T>
using TypeList = TypeListNode<H, TypeListNode<T, TypeListNode<NullType, NullType>>>;

// Empty marker
struct NullType {};
```

This creates a linked list of types at compile time. You can then write template metaprograms that traverse this list.

### Type List Operations

Several operations are commonly needed:

```cpp
// Length of type list
template<typename List>
struct Length {
    static constexpr size_t value = 1 + Length<typename List::tail>::value;
};

template<>
struct Length<NullType> {
    static constexpr size_t value = 0;
};

// TypeAt - get type at index
template<typename List, size_t Index>
struct TypeAt {
    using type = typename TypeAt<typename List::tail, Index - 1>::type;
};

template<typename List>
struct TypeAt<List, 0> {
    using type = typename List::head;
};

// Append - add type to end
template<typename List, typename Type>
struct Append;

template<typename Type>
struct Append<NullType, Type> {
    using type = TypeListNode<Type, NullType>;
};

template<typename Head, typename Tail, typename Type>
struct Append<TypeListNode<Head, Tail>, Type> {
    using type = TypeListNode<Head, typename Append<Tail, Type>::type>;
};

// Find - find index of type
template<typename List, typename Type>
struct IndexOf;

template<typename Type>
struct IndexOf<NullType, Type> {
    static constexpr size_t value = -1;
};

template<typename Head, typename Tail, typename Type>
struct IndexOf<TypeListNode<Head, Tail>, Type> {
    static constexpr size_t value =
        std::is_same_v<Head, Type> ? 0 : IndexOf<Tail, Type>::value + 1;
};
```

These operations work entirely at compile time—the compiler evaluates them when instantiating templates.

### Type List with Variadic Templates

C++11 variadic templates simplify type lists significantly:

```cpp
template<typename... Types>
struct TypeList {
    static constexpr size_t size = sizeof...(Types);

    template<size_t Index>
    using At = typename std::tuple_element<Index, std::tuple<Types...>>::type;

    template<typename T>
    static constexpr size_t index = []() {
        size_t result = 0;
        size_t i = 0;
        ((std::is_same_v<Types, T> ? (result = i, true) : (i++, false)), ...);
        return result;
    }();
};

// Alternative using fold expression for index
template<typename List, typename T>
struct IndexOf;

template<typename... Types, typename T>
struct IndexOf<TypeList<Types...>, T> {
private:
    template<size_t... Is>
    static constexpr size_t helper(std::index_sequence<Is...>) {
        return ((std::is_same_v<std::tuple_element_t<Is, std::tuple<Types...>, T> ? Is : 0) + ...);
    }
public:
    static constexpr size_t value = helper(std::index_sequence_for<Types...>{});
};
```

Modern C++ (C++17+) makes type lists much simpler to work with.

### Compile-Time Iteration

You can iterate over type lists at compile time using template specialization:

```cpp
// Apply operation to each type in list
template<typename List, template<typename> class Op>
struct ForEach;

template<template<typename> class Op>
struct ForEach<NullType, Op> {};

template<typename Head, typename Tail, template<typename> class Op>
struct ForEach<TypeListNode<Head, Tail>, Op> {
    using type = Op<Head>;
    using next = ForEach<Tail, Op>;
};

// Example: print all types (conceptually - can't actually print at compile time)
// but you can generate code for each type

template<typename T>
struct PrintType {
    static void print() {
        std::cout << typeid(T).name() << std::endl;
    }
};

using MyList = TypeList<int, double, std::string>;
using Result = ForEach<MyList, PrintType>;  // Applies PrintType to each
```

A more practical use is generating code for each type:

```cpp
// Generate serialization code for each type
template<typename T>
struct Serializer {
    static void serialize(std::ostream& os, const T& value) {
        os << value;  // Default just uses operator<<
    }
};

template<typename... Types>
struct SerializeAll {
    template<typename T>
    void operator()(std::ostream& os, const T& value) const {
        Serializer<T>::serialize(os, value);
    }
};
```

### Type List as Compile-Time Dispatch

Type lists enable compile-time dispatch—choosing behavior based on type membership:

```cpp
// Check if type is in list
template<typename List, typename T>
struct Contains;

template<typename T>
struct Contains<NullType, T> : std::false_type {};

template<typename Head, typename Tail, typename T>
struct Contains<TypeListNode<Head, Tail>, T>
    : std::bool_constant<std::is_same_v<Head, T> || Contains<Tail, T>::value> {};

// Modern C++17 version
template<typename T, typename... Types>
constexpr bool contains = (std::is_same_v<T, Types> || ...);

// Use for compile-time dispatch
template<typename T>
auto process(T value) {
    if constexpr (contains<T, int, double, float>) {
        return numericProcess(value);
    } else if constexpr (contains<T, std::string, const char*>) {
        return stringProcess(value);
    } else {
        return genericProcess(value);
    }
}
```

This approach lets you handle different categories of types without runtime type checking.

### Visitor Pattern with Type Lists

The visitor pattern can be implemented using type lists for compile-time dispatch:

```cpp
template<typename... Types>
class Visitor {
public:
    virtual ~Visitor() = default;
    virtual void visit(Types&...) = 0;  // Actually multiple overloads
};

// Alternative: generate visit overloads for each type
template<typename Visitor, typename... Types>
struct VisitorImpl;

// Base case: no more types
template<typename Visitor>
struct VisitorImpl<Visitor> {
    static void accept(Visitor&, typename std::tuple<Types...>&) {}
};

// Recursive: generate visit for head type
template<typename Visitor, typename Head, typename... Tail>
struct VisitorImpl<Visitor, Head, Tail...> {
    static void accept(Visitor& v, std::tuple<Types...>& t) {
        v.visit(std::get<Head>(t));
        VisitorImpl<Visitor, Tail...>::accept(v, t);
    }
};

// Apply visitor to all elements
template<typename Visitor, typename... Types>
void applyVisitor(Visitor& v, std::tuple<Types...>& t) {
    VisitorImpl<Visitor, Types...>::accept(v, t);
}
```

This enables compile-time visitor patterns where each type has its own visit method.

### Type List with std::variant

Type lists combine naturally with `std::variant`:

```cpp
template<typename... Types>
using Variant = std::variant<Types...>;

// Visit variant using type list
template<typename Variant, typename Visitor>
auto visitVariant(Visitor&& v, Variant& variant) {
    return std::visit(std::forward<Visitor>(v), variant);
}

// Create variant from type list
template<typename List>
struct VariantFromList;

template<typename... Types>
struct VariantFromList<TypeList<Types...>> {
    using type = std::variant<Types...>;
};

// Use:
using MyVariant = typename VariantFromList<MyList>::type;
MyVariant v = 42;
std::visit([](const auto& x) { std::cout << x; }, v);
```

### Factory Pattern with Type Lists

Type lists enable compile-time factory patterns:

```cpp
// Type list of product types
using ProductTypes = TypeList<WidgetA, WidgetB, WidgetC>;

// Registry mapping ID to type
template<typename Types>
struct TypeRegistry;

template<typename Head, typename... Tail>
struct TypeRegistry<TypeList<Head, Tail>> {
    template<typename Id>
    static std::unique_ptr<BaseProduct> create(Id id) {
        if (id == typeid(Head).hash_code()) {
            return std::make_unique<Head>();
        }
        return TypeRegistry<TypeList<Tail...>>::create(id);
    }
};

template<>
struct TypeRegistry<TypeList<>> {
    template<typename Id>
    static std::unique_ptr<BaseProduct> create(Id) {
        return nullptr;
    }
};
```

This creates a compile-time dispatch chain for creating objects by type ID.

### Type List for Policy-Based Design

Type lists enable sophisticated policy-based design:

```cpp
template<typename... Policies>
class PolicyContainer {
public:
    // Apply each policy
    template<template<typename> class Applier>
    void apply() {
        (Applier<Policies>::apply(*this), ...);
    }

private:
    // Each policy can access private members
    template<typename P>
    friend class PolicyAccessor;
};

// Example: policies for a class
struct ThreadPolicy {
    static void doSomething() { /* threading logic */ }
};

struct ValidationPolicy {
    static void validate() { /* validation logic */ }
};

using MyContainer = PolicyContainer<ThreadPolicy, ValidationPolicy>;
```

This approach enables composable behavior without virtual functions.

### Tuple-like Access to Types

Type lists enable tuple-like generic operations:

```cpp
template<typename List>
struct TupleLike {
    static constexpr size_t size = List::size;

    template<size_t I>
    using Element = typename List::template At<I>;
};

// Example: find the largest type by sizeof
template<typename List>
struct LargestType;

template<>
struct LargestType<NullType> {
    using type = void;
};

template<typename Head, typename... Tail>
struct LargestType<TypeList<Head, Tail...>> {
private:
    using LargestTail = typename LargestType<TypeList<Tail...>>::type;
public:
    using type = std::conditional_t<
        sizeof(Head) >= sizeof(LargestTail),
        Head,
        LargestTail
    >;
};
```

### Type List Performance

Type list operations are entirely compile-time:

**No runtime overhead**: All type list computations happen during compilation. The resulting code has no trace of the type list.

**Compilation time**: Complex type list operations can increase compilation time. Use carefully in heavily-templated code.

**Error messages**: When things go wrong with type lists, error messages can be extremely verbose. Tools like C++20 concepts help by providing clearer constraints.

### Summary

Type lists represent collections of types for compile-time computation. They enable static polymorphism without virtual functions, compile-time dispatch based on type membership, and code generation over heterogeneous type sets. Modern C++ (C++17+) simplifies type lists with variadic templates and fold expressions.

Type lists form the foundation for many advanced patterns: policy-based design, compile-time visitors, generic factories, and variant creation. While they add compile-time complexity, they enable zero-cost abstractions that eliminate runtime overhead.

This chapter explored type erasure techniques—from fundamental concept/model patterns, through standard library implementations like `std::function` and `std::any`, to compile-time type lists. These patterns provide powerful tools for designing flexible, efficient APIs.

---

## Summary

This chapter explored four interconnected techniques for achieving polymorphism in C++. Type erasure for polymorphism demonstrated the fundamental concept/model pattern that underlies all type erasure, showing how to store heterogeneous types through a common interface while erasing specific type information at runtime. The `std::function` implementation patterns revealed how the standard library applies type erasure to callables, using the small buffer optimization to avoid heap allocation for common cases. The `std::any` section showed the most general form of type erasure—storing values of any type while enabling type-safe retrieval through runtime type checking. Finally, type lists and compile-time polymorphism demonstrated the complementary compile-time approach, where type collections are processed during compilation to generate optimized code.

These techniques form a spectrum from fully dynamic to fully static polymorphism. Type erasure trades some compile-time type safety for runtime flexibility—useful when types aren't known at compile time or when APIs must accept heterogeneous inputs. Type lists preserve compile-time type information, enabling optimizations that static languages are famous for while sacrificing some flexibility.

The key insight is that these patterns are not mutually exclusive. Production code often combines them: `std::function` uses type erasure internally, `std::variant` combines type lists with runtime dispatch, and custom implementations often layer compile-time and runtime techniques. Understanding each approach helps you choose the right tool and compose them effectively.

### Exercises

1. **Type-Erased Container**: Implement a type-erased container that can hold any copyable type and provide a `clone()` method for deep copying.

2. **Custom std::function**: Implement a simplified `std::function` that supports a specific signature with small buffer optimization.

3. **Any-like Wrapper**: Implement a simplified `std::any` that can store and retrieve values of any type.

4. **Type List Operations**: Implement type list operations including `Map` (apply a template to each type), `Filter` (keep types matching a predicate), and `Unique` (remove duplicates).

5. **Compile-Time Dispatch**: Use type lists to implement a compile-time dispatch system that routes function calls based on the type of an argument without runtime checks.

6. **Policy Container**: Design a policy-based class using type lists to compose policies at compile time.
