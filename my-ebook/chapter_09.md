# Chapter 9: CRTP and Static Polymorphism

The Curiously Recurring Template Pattern (CRTP) is a powerful C++ technique that enables static polymorphism—polymorphism resolved at compile time rather than runtime. Unlike virtual function-based polymorphism, CRTP uses template instantiation to achieve polymorphic behavior without the runtime overhead of virtual dispatch. This chapter explores CRTP in depth, showing how it enables zero-cost abstractions, static polymorphism, mixin-based inheritance, and reference counting patterns.

This chapter covers four related techniques: the CRTP pattern itself, using it for static polymorphism without virtual overhead, applying it to mixin-based class composition, and the counted idiom for reference management.

## Curiously Recurring Template Pattern

The Curiously Recurring Template Pattern (CRTP) is an idiom where a class template inherits from a specialization of itself. The name comes from the surprising pattern of a derived class passing itself as a template argument to its base class:

```cpp
template<typename Derived>
class Base {
public:
    void interface() {
        // Call derived class implementation
        static_cast<Derived*>(this)->implementation();
    }
};

class Derived : public Base<Derived> {
public:
    void implementation() {
        std::cout << "Derived implementation\n";
    };
};
```

This pattern enables the base class to call into the derived class without virtual functions—the `static_cast<Derived*>(this)` is resolved at compile time.

### How CRTP Works

The key mechanism is that the base class template knows the derived type at compile time:

```cpp
template<typename Derived>
class Base {
    Derived* self() { return static_cast<Derived*>(this); }
    const Derived* self() const { return static_cast<const Derived*>(this); }

public:
    void doSomething() {
        // Access derived class members directly
        self()->derivedMethod();
    }
};

class Concrete : public Base<Concrete> {
public:
    void derivedMethod() { /* ... */ }
};
```

When `Base<Concrete>` is instantiated, the compiler knows that `Derived` is `Concrete`, so it can generate code that calls `Concrete::derivedMethod` directly—no virtual dispatch needed.

The pattern works because templates are instantiated lazily—when you write `Base<Concrete>`, the base class template is instantiated with `Derived = Concrete`, and inside that instantiation, references to `Derived` are resolved to `Concrete`.

### A Simple Example: Number Operations

A practical use case is creating a hierarchy of types with shared behavior:

```cpp
template<typename T>
class Arithmetic {
public:
    T add(const T& other) const {
        const T* self = static_cast<const T*>(this);
        return T(self->value() + other.value());
    }

    T subtract(const T& other) const {
        const T* self = static_cast<const T*>(this);
        return T(self->value() - other.value());
    }

    T multiply(const T& other) const {
        const T* self = static_cast<const T*>(this);
        return T(self->value() * other.value());
    }
};

class Fraction : public Arithmetic<Fraction> {
public:
    Fraction(int num, int denom) : numerator_(num), denominator_(denom) {}

    int value() const { return numerator_ / denominator_; }

private:
    int numerator_;
    int denominator_;
};

class Matrix : public Arithmetic<Matrix> {
public:
    // Matrix arithmetic implementation
};
```

`Arithmetic<T>` provides arithmetic operations that work with any type `T` that has a `value()` method. The operations are inlined at compile time—there's no runtime polymorphism overhead.

### CRTP for Static Dispatch

The classic CRTP use case is achieving polymorphic behavior without virtual functions:

```cpp
template<typename Derived>
class Shape {
public:
    void draw() const {
        static_cast<const Derived*>(this)->drawImpl();
    }

    double area() const {
        return static_cast<const Derived*>(this)->areaImpl();
    }

private:
    virtual void drawImpl() const = 0;
    virtual double areaImpl() const = 0;
};

class Circle : public Shape<Circle> {
public:
    explicit Circle(double r) : radius_(r) {}

private:
    void drawImpl() const override {
        std::cout << "Drawing circle with radius " << radius_ << "\n";
    }

    double areaImpl() const override {
        return 3.14159 * radius_ * radius_;
    }

    double radius_;
};

class Square : public Shape<Square> {
public:
    explicit Square(double s) : side_(s) {}

private:
    void drawImpl() const override {
        std::cout << "Drawing square with side " << side_ << "\n";
    }

    double areaImpl() const override {
        return side_ * side_;
    }

    double side_;
};
```

This achieves the same effect as traditional inheritance with virtual functions, but the calls are resolved at compile time—each instantiation generates specific code for that type.

### Why Use CRTP Over Virtual Functions

CRTP offers several advantages over virtual functions:

**Zero runtime overhead**: No vtable pointer, no virtual dispatch. Calls are inlined when possible.

**Compile-time binding**: All call targets are known at compile time, enabling optimizations like inlining and dead code elimination.

**No requirement for virtual destructors**: Since there's no runtime polymorphism, you don't need virtual destructors for polymorphic deletion.

**Works with value types**: CRTP works with types that aren't polymorphic in the traditional sense (no base pointers needed).

However, CRTP also has limitations:

**No runtime flexibility**: You can't change the "type" at runtime—there's no dynamic dispatch.

**Code bloat**: Each instantiation generates separate code, potentially increasing binary size.

**Compile-time dependency**: The base must be a template parameter, which affects how you design classes.

### CRTP for Type Discovery

CRTP enables the derived class to discover itself:

```cpp
template<typename Derived>
class SelfAware {
public:
    using Self = Derived;

    static Derived& get() {
        static Derived instance;
        return instance;
    }
};

class Singleton : public SelfAware<Singleton> {
    // Can access Self = Singleton
};
```

This pattern is useful for creating singleton patterns and for metaprogramming where the derived type must know itself.

### CRTP and Covariance

You can implement covariant return types using CRTP:

```cpp
template<typename Derived>
class Cloneable {
public:
    std::unique_ptr<Derived> clone() const {
        return std::make_unique<Derived>(*static_cast<const Derived*>(this));
    }
};

class Widget : public Cloneable<Widget> {
    // clone() returns std::unique_ptr<Widget>
};

class Button : public Cloneable<Button> {
    // clone() returns std::unique_ptr<Button>
};
```

The return type is `std::unique_ptr<Derived>`, which becomes `std::unique_ptr<Widget>` in the `Widget` specialization—no casting needed.

### CRTP for Method Forwarding

CRTP can forward method calls to derived implementations:

```cpp
template<typename Derived>
class Printable {
public:
    std::string toString() const {
        return static_cast<const Derived*>(this)->toStringImpl();
    }

    void print() const {
        std::cout << toString() << "\n";
    }
};

class Person : public Printable<Person> {
public:
    explicit Person(std::string n) : name_(std::move(n)) {}

private:
    std::string toStringImpl() const {
        return "Person: " + name_;
    }

    std::string name_;
};
```

The `Printable` base provides convenience methods (`print`) that use abstract methods (`toStringImpl`) implemented by derived classes.

### CRTP with Multiple Levels

CRTP can be chained through multiple levels:

```cpp
template<typename Derived>
class Base1 {
public:
    void method1() { static_cast<Derived*>(this)->method1Impl(); }
protected:
    virtual void method1Impl() = 0;
};

template<typename Derived>
class Base2 : public Base1<Derived> {
public:
    void method2() { static_cast<Derived*>(this)->method2Impl(); }
protected:
    virtual void method2Impl() = 0;
};

class Concrete : public Base2<Concrete> {
protected:
    void method1Impl() override { std::cout << "method1\n"; }
    void method2Impl() override { std::cout << "method2\n"; }
};
```

This enables composing multiple base classes, each providing their own interface while maintaining the static dispatch chain.

### CRTP vs std::enable_shared_from_this

The standard library's `std::enable_shared_from_this` uses CRTP internally:

```cpp
template<typename T>
class enable_shared_from_this {
public:
    std::shared_ptr<T> shared_from_this() {
        return std::shared_ptr<T>(weak_this_);
    }

protected:
    enable_shared_from_this() : weak_this_(*this) {}
    enable_shared_from_this(const enable_shared_from_this&) : weak_this_(*this) {}
    enable_shared_from_this& operator=(const enable_shared_from_this&) {
        weak_this_ = *this;
        return *this;
    }

private:
    std::weak_ptr<T> weak_this_;
    template<typename> friend class shared_ptr;
};
```

When you inherit from `enable_shared_from_this<MyClass>`, the template parameter is `MyClass`, making this a CRTP pattern. The weak pointer stores the shared state that's set when the object is first owned by a `shared_ptr`.

### CRTP for Interface Delegation

A common pattern uses CRTP to forward interface requirements:

```cpp
template<typename Derived, typename Interface>
class Adapter : public Interface {
public:
    // Forward each method from Interface to Derived
    template<typename Method, Method Interface::*mp>
    struct Forwarder {
        template<typename... Args>
        auto operator()(Args&&... args) const
            -> decltype((static_cast<Derived*>(nullptr)->*mp)(std::forward<Args>(args)...)) {
            return static_cast<Derived*>(this)->*mp(std::forward<Args>(args)...);
        }
    };
};
```

This is complex but enables writing generic adapters that automatically forward interface requirements.

### Static vs Dynamic Polymorphism

The choice between CRTP (static) and virtual functions (dynamic) depends on your requirements:

| Aspect | CRTP (Static) | Virtual (Dynamic) |
|--------|---------------|-------------------|
| Runtime cost | Zero (inlined) | Function pointer call |
| Flexibility | Compile-time | Runtime |
| Binary size | Larger (instantiations) | Smaller (shared vtable) |
| Type changes | None possible | Via base pointers |
| Compile time | Slower (instantiation) | Faster |

Use CRTP when performance is critical and types are known at compile time. Use virtual functions when you need runtime flexibility.

### Summary

The Curiously Recurring Template Pattern enables compile-time polymorphism through template instantiation. A base class template takes the derived class as a parameter, allowing it to call derived class methods without virtual dispatch. This pattern provides zero runtime overhead, better inlining opportunities, and works with value types. Common uses include static interfaces, type discovery, method forwarding, and composing base classes. The key insight is that CRTP trades runtime flexibility for compile-time optimization—useful when types are known and performance matters.

---

## Static Polymorphism without Virtual Overhead

Static polymorphism achieves polymorphic behavior through template instantiation rather than virtual function dispatch. This approach eliminates runtime overhead while maintaining the benefits of polymorphic interfaces. This section explores techniques for implementing static polymorphism, comparing approaches, and understanding when each is appropriate.

### Concept-Based Static Polymorphism

Modern C++ enables clean static polymorphism through concepts:

```cpp
template<typename T>
concept Drawable = requires(T t) {
    t.draw();
};

template<Drawable T>
void render(const T& object) {
    object.draw();  // Resolved at compile time
}

class Circle {
public:
    void draw() const { /* ... */ }
};

class Square {
public:
    void draw() const { /* ... */ */
};
```

The `Drawable` concept specifies what operations a type must support. When `render` is called with a `Circle` or `Square`, the compiler generates specific code for each instantiation—no virtual functions involved.

### Tag Dispatch for Static Dispatch

Tag dispatch provides compile-time selection between implementations:

```cpp
struct Tag {};
struct Tag1 : Tag {};
struct Tag2 : Tag {};

template<typename T>
void processImpl(const T& obj, Tag1) {
    std::cout << "Processing with Tag1\n";
}

template<typename T>
void processImpl(const T& obj, Tag2) {
    std::cout << "Processing with Tag2\n";
}

template<typename T>
void process(const T& obj) {
    using Tag = typename T::tag_type;
    processImpl(obj, Tag{});
}

class TypeA { public: using tag_type = Tag1; };
class TypeB { public: using tag_type = Tag2; };

process(TypeA{});  // Calls processImpl with Tag1
process(TypeB{});  // Calls processImpl with Tag2
```

The tag type embedded in each class determines which implementation is selected at compile time.

### Template Specialization for Type-Specific Behavior

Template specialization enables type-specific implementations:

```cpp
template<typename T>
struct Processor {
    void process(const T& value) {
        std::cout << "Generic: " << value << "\n";
    }
};

template<>
struct Processor<int> {
    void process(int value) {
        std::cout << "Integer: " << value * 2 << "\n";
    }
};

template<>
struct Processor<std::string> {
    void process(const std::string& value) {
        std::cout << "String: " << value.size() << " chars\n";
    }
};

Processor<int> intProcessor;
Processor<std::string> strProcessor;

intProcessor.process(42);
strProcessor.process("hello");
```

Each specialization generates type-specific code, with the compiler selecting the appropriate one based on the template argument.

### Type-Traits-Based Dispatch

Type traits enable conditional compilation:

```cpp
template<typename T>
void serialize(const T& value) {
    if constexpr (std::is_integral_v<T>) {
        serializeInteger(value);
    } else if constexpr (std::is_floating_point_v<T>) {
        serializeFloat(value);
    } else if constexpr (std::is_same_v<T, std::string>) {
        serializeString(value);
    } else {
        serializeGeneric(value);
    }
}
```

The `if constexpr` (C++17) evaluates at compile time, eliminating branches that don't apply to the type. This provides type-specific behavior without virtual dispatch.

### CRTP as Static Polymorphism

CRTP provides one of the most common static polymorphism patterns:

```cpp
template<typename Derived>
class Comparable {
public:
    bool operator<(const Derived& other) const {
        const auto* self = static_cast<const Derived*>(this);
        return self->getValue() < other.getValue();
    }

    bool operator==(const Derived& other) const {
        const auto* self = static_cast<const Derived*>(this);
        return self->getValue() == other.getValue();
    }
};

class Version : public Comparable<Version> {
public:
    explicit Version(int v) : value_(v) {}

    int getValue() const { return value_; }

private:
    int value_;
};

Version v1(1), v2(2);
bool less = v1 < v2;  // Uses Version::getValue()
```

The comparison operators in `Comparable` are instantiated specifically for `Version`, calling `Version::getValue()` directly.

### Static Polymorphism vs Virtual Functions

Understanding when to use each approach:

```cpp
// Virtual function approach - runtime dispatch
class Shape {
public:
    virtual void draw() const = 0;
    virtual ~Shape() = default;
};

class Circle : public Shape {
    void draw() const override;
};

// Static approach - compile-time dispatch
template<typename Shape>
void drawShape(const Shape& s) {
    s.draw();  // Resolved at compile time if draw() is not virtual
}
```

Virtual functions offer runtime flexibility—you can have a `Shape*` that points to any derived type, determined at runtime. Static polymorphism requires knowing the type at compile time, but provides better performance.

### Performance Comparison

The performance characteristics differ significantly:

```cpp
// Virtual dispatch
class VirtualBase {
public:
    virtual int compute(int x) = 0;
    virtual ~VirtualBase() = default;
};

class VirtualDerived : public VirtualBase {
public:
    int compute(int x) override { return x * 2; }
};

// Static dispatch
template<typename T>
int computeStatic(const T& obj, int x) {
    return obj.compute(x);  // Inlined when possible
}
```

In benchmark tests, static dispatch typically shows:
- No function pointer indirection
- Better instruction cache behavior
- More opportunities for compiler optimization
- Potential for complete inlining

The actual difference depends on the compiler, optimization level, and whether the type is known at the call site.

### Mixin-Based Static Polymorphism

Mixins combine multiple behaviors statically:

```cpp
template<typename Base>
class Printable : Base {
public:
    void print() const {
        std::cout << "Printable: ";
        this->printImpl();
    }

protected:
    virtual void printImpl() const = 0;
};

template<typename Base>
class Comparable : Base {
public:
    bool operator<(const Comparable& other) const {
        return this->getValue() < other.getValue();
    }

protected:
    virtual typename Base::ValueType getValue() const = 0;
};

template<typename Value>
class Widget : public Printable<Comparable<Widget<Value>>> {
protected:
    using ValueType = Value;
    void printImpl() const override { std::cout << value_ << "\n"; }
    ValueType getValue() const override { return value_; }

    Value value_;
};
```

The `Widget` inherits from both `Printable` and `Comparable` (which itself inherits from a base), stacking behaviors through CRTP.

### Static Interface Constraints

When designing static polymorphic interfaces, clarity matters:

```cpp
// Explicit requirements
template<typename T>
concept Container = requires(T t) {
    typename T::value_type;
    t.begin();
    t.end();
    t.size();
};

template<Container T>
auto sum(const T& container) {
    typename T::value_type total{};
    for (const auto& elem : container) {
        total += elem;
    }
    return total;
}
```

The `Container` concept clearly specifies what types must provide. This is superior to implicit requirements because errors are caught at the concept level, not deep in the function body.

### Generic Programming with Static Polymorphism

Static polymorphism fits naturally into generic programming:

```cpp
template<typename Container>
auto findMax(const Container& c) {
    auto it = c.begin();
    auto max = *it;
    ++it;
    while (it != c.end()) {
        if (*it > max) max = *it;
        ++it;
    }
    return max;
}
```

This works with any container type that provides iterators with the standard interface—no virtual functions needed. The compiler generates code specifically for each container type.

### When to Use Static Polymorphism

Static polymorphism is appropriate when:

- Performance is critical and runtime dispatch overhead matters
- Types are known at compile time
- You want compile-time error messages for interface violations
- You need to optimize for specific types
- Binary size isn't a concern (multiple instantiations)

Avoid static polymorphism when:

- Types aren't known until runtime
- You need to store heterogeneous types in a container
- You need dynamic casting or type introspection
- Compilation time is a significant concern

### Summary

Static polymorphism achieves polymorphic behavior through templates, concepts, and compile-time dispatch rather than virtual functions. Techniques include concept-based constraints, tag dispatch, template specialization, type-traits-based dispatch, and CRTP. The key advantage is zero runtime overhead—calls are resolved at compile time and can be inlined. The trade-off is reduced flexibility compared to virtual functions. Choose static polymorphism when performance matters and types are known at compile time; use virtual functions when runtime flexibility is needed.

---

## Mixin-Based Inheritance

Mixin-based inheritance is a powerful pattern that enables composing classes from reusable building blocks. A mixin is a class template that accepts a base class as a parameter and extends it with additional functionality. By combining multiple mixins, you can create complex class hierarchies without traditional inheritance chains. This pattern is particularly valuable in C++ for building flexible, modular class designs.

### Understanding Mixins

A mixin is a template that takes a base class and extends it:

```cpp
template<typename Base>
class Printable : public Base {
public:
    void print() const {
        std::cout << "Printing: ";
        Base::print(std::cout);
        std::cout << "\n";
    }
};

class Data {
public:
    void print(std::ostream& os) const { os << data_; }
    void setData(int d) { data_ = d; }
private:
    int data_ = 0;
};

// Compose: Printable adds printing to Data
using PrintableData = Printable<Data>;
```

`Printable<Data>` inherits from `Data` and adds the `print()` method. You can stack multiple mixins to build up functionality.

### Mixins with CRTP

Mixins combine naturally with CRTP for static polymorphism:

```cpp
template<typename Base>
class Comparable : public Base {
public:
    bool operator<(const Comparable& other) const {
        return this->value() < other.value();
    }

    bool operator==(const Comparable& other) const {
        return this->value() == other.value();
    }
};

template<typename Base>
class Serialized : public Base {
public:
    void serialize(std::ostream& os) const {
        os << this->value() << ";";
    }

    void deserialize(std::istream& is) {
        int v;
        is >> v;
        this->setValue(v);
    }
};

template<typename T>
class Widget : public Comparable<Serialized<Widget<T>>> {
public:
    T value() const { return value_; }
    void setValue(T v) { value_ = v; }

private:
    T value_;
};

Widget<int> w;
w.setValue(42);
std::cout << (w < Widget<int>{}) << "\n";  // Comparable functionality
w.serialize(std::cout);  // Serialized functionality
```

The `Widget` inherits from both `Comparable` and `Serialized`, each wrapping the previous level. This creates a stack of behaviors.

### Mixin Template Order

The order of mixins matters—the last applied mixin is the most derived:

```cpp
template<typename Base>
class MixinA {
public:
    void methodA() { std::cout << "A\n"; }
};

template<typename Base>
class MixinB {
public:
    void methodB() { std::cout << "B\n"; }
};

// Different orders produce different class hierarchies
class Type1 : public MixinA<MixinB<Type1>> {};
class Type2 : public MixinB<MixinA<Type2>> {};
```

In `Type1`, `MixinA` is the outer mixin (most derived), so `Type1` has both `methodA()` and `methodB()` (inherited from `MixinB`). The order determines which mixin's interface is most accessible.

### Adding State Through Mixins

Mixins can add member variables:

```cpp
template<typename Base>
class Timestamped : public Base {
public:
    using timestamp_type = std::chrono::system_clock::time_point;

    timestamp_type timestamp() const { return timestamp_; }
    void setTimestamp(timestamp_type t) { timestamp_ = t; }

    void update() { timestamp_ = std::chrono::system_clock::now(); }

private:
    timestamp_type timestamp_ = std::chrono::system_clock::now();
};

template<typename Base>
class Identified : public Base {
public:
    void setId(int id) { id_ = id; }
    int id() const { return id_; }

private:
    int id_ = 0;
};

class Event : public Identified<Timestamped<Event>> {};
```

`Event` has both identification and timestamp functionality, composed from the two mixins.

### Mixins with Template Parameters

Mixins can accept parameters beyond just the base class:

```cpp
template<typename Base, typename Tag = void>
class Tagged : public Base {
public:
    const Tag& tag() const { return tag_; }
    void setTag(const Tag& t) { tag_ = t; }

private:
    Tag tag_;
};

template<typename Base, size_t MaxSize>
class Bounded : public Base {
public:
    void addElement(typename Base::value_type e) {
        if (elements_.size() >= MaxSize) {
            throw std::runtime_error("Capacity exceeded");
        }
        Base::addElement(e);
    }

private:
    std::vector<typename Base::value_type> elements_;
};
```

These mixins add additional configuration through template parameters.

### Mixin for Policy-Based Design

Mixins implement policy-based design patterns:

```cpp
template<typename Base, typename ThreadPolicy = SingleThreaded>
class ThreadSafe : public Base, public ThreadPolicy {
public:
    void modify() {
        Lock lock(this->mutex());
        Base::modify();
    }

    typename Base::value_type read() {
        Lock lock(this->mutex());
        return Base::read();
    }
};

struct SingleThreaded {
    struct Lock {
        Lock(void*) {}
    };
    void* mutex() { return nullptr; }
};

struct MultiThreaded {
    std::mutex mutex_;
    void* mutex() { return &mutex_; }
    struct Lock {
        explicit Lock(std::mutex* m) : lock(*m) {}
        std::lock_guard<std::mutex> lock;
    };
};
```

The `ThreadSafe` mixin adds thread safety to any base class, with the `ThreadPolicy` determining the locking strategy.

### Curiously Recurring Mixins

The combination of mixins and CRTP is particularly powerful:

```cpp
template<typename Derived>
class Addable {
public:
    Derived& add(const Derived& other) {
        Derived& self = static_cast<Derived&>(*this);
        self.setValue(self.getValue() + other.getValue());
        return self;
    }

    Derived& operator+=(const Derived& other) {
        return add(other);
    }
};

template<typename Derived>
class Multiplicable {
public:
    Derived& multiply(const Derived& other) {
        Derived& self = static_cast<Derived&>(*this);
        self.setValue(self.getValue() * other.getValue());
        return self;
    }

    Derived& operator*=(const Derived& other) {
        return multiply(other);
    }
};

template<typename T>
class Number : public Addable<Multiplicable<Number<T>>> {
public:
    Number(T v = T{}) : value_(v) {}

    T getValue() const { return value_; }
    void setValue(T v) { value_ = v; }

private:
    T value_;
};

Number<int> a(5), b(3);
a += b;  // Addable
a *= b;  // Multiplicable
```

Each mixin operates on the final derived type, enabling combined functionality.

### Virtual Inheritance with Mixins

When mixing multiple base classes, virtual inheritance may be needed:

```cpp
template<typename Base>
class Logging : virtual public Base {
public:
    void logOperation() {
        std::cout << "Operation on " << typeid(*this).name() << "\n";
    }
};

template<typename Base>
class Validation : virtual public Base {
public:
    bool validate() const { return true; }
};

template<typename Base>
class Persistence : virtual public Base {
public:
    void save() { /* ... */ }
    void load() { /* ... */ }
};

// Diamond inheritance avoided through virtual inheritance
class Entity : public Logging<Validation<Persistence<Entity>>> {};
```

Virtual inheritance ensures a single instance of common base classes. This pattern becomes important as mixin hierarchies grow complex.

### Mixin Conflicts and Solutions

When mixins provide overlapping functionality, conflicts arise:

```cpp
template<typename Base>
class MixinA {
public:
    void process() { std::cout << "A::process\n"; }
};

template<typename Base>
class MixinB {
public:
    void process() { std::cout << "B::process\n"; }
};

// Ambiguous: which process()?
class Conflict : public MixinA<Conflict>, public MixinB<Conflict> {};

// Solution 1: Rename methods
template<typename Base>
class MixinARenamed {
public:
    void processA() { std::cout << "A::process\n"; }
};

// Solution 2: Use using declarations
class Resolved : public MixinA<Resolved>, public MixinB<Resolved> {
public:
    using MixinA<Resolved>::process;
    using MixinB<Resolved>::process;
    // Or explicitly resolve:
    void process() { MixinA<Resolved>::process(); }
};
```

Careful naming and explicit resolution manage conflicts.

### Building Complex Types with Mixins

Mixins excel at building complex types from simple parts:

```cpp
// Base functionality
template<typename T>
class Comparable {
public:
    bool operator<(const T& o) const { return static_cast<const T*>(this)->get() < o.get(); }
};

template<typename T>
class Hashable {
public:
    size_t hash() const { return std::hash<typename T::value_type>{}(static_cast<const T*>(this)->get()); }
};

template<typename T>
class Printable {
public:
    void print(std::ostream& os) const { os << static_cast<const T*>(this)->get(); }
};

// Composite type
template<typename T>
class SmartValue : public Comparable<SmartValue<T>>,
                   public Hashable<SmartValue<T>>,
                   public Printable<SmartValue<T>> {
public:
    using value_type = T;
    const T& get() const { return value_; }
    void set(const T& v) { value_ = v; }

private:
    T value_;
};

SmartValue<int> sv(42);
std::cout << sv.hash() << "\n";
sv.print(std::cout);
```

Each mixin adds a capability. The final class has all capabilities without explicit implementation.

### Mixins vs Traditional Inheritance

Mixins offer advantages over traditional inheritance:

| Aspect | Traditional | Mixins |
|--------|-------------|--------|
| Composition | Single inheritance limited | Multiple, stackable |
| Flexibility | At runtime | At compile time |
| State | Single path | Independent paths |
| Conflicts | Resolved by overriding | Must manage explicitly |

Mixins compose at compile time, enabling more flexible class building. Traditional inheritance defines a fixed hierarchy at compile time.

### Summary

Mixin-based inheritance enables composing classes from reusable template-based building blocks. A mixin extends a base class with additional functionality, and multiple mixins can be combined in a stack. Mixins work well with CRTP for static polymorphism and can add state, behavior, and template parameters. Policy-based design, virtual inheritance for complex hierarchies, and conflict management are important considerations. Mixins trade some complexity for significant flexibility in class composition.

---

## Counted Idiom

The Counted Idiom (also known as Reference Counted Idiom or Counted Pointer) provides a way to implement shared ownership of objects with minimal overhead. Unlike `std::shared_ptr`, which stores the control block separately from the object, the Counted Idiom stores the reference count within the object itself. This approach is common in COM (Component Object Model), resource management frameworks, and performance-critical code where the overhead of separate control blocks is unacceptable.

### The Basic Counted Pattern

The core idea is to store a reference count in the object and have pointers to the object maintain their own handle that accesses this count:

```cpp
template<typename T>
class CountedPtr {
public:
    CountedPtr() = default;

    explicit CountedPtr(T* p) : ptr_(p) {
        if (ptr_) {
            ptr_->addRef();
        }
    }

    ~CountedPtr() {
        if (ptr_) {
            ptr_->release();
        }
    }

    CountedPtr(const CountedPtr& other) : ptr_(other.ptr_) {
        if (ptr_) {
            ptr_->addRef();
        }
    }

    CountedPtr& operator=(const CountedPtr& other) {
        if (other.ptr_ != ptr_) {
            if (ptr_) {
                ptr_->release();
            }
            ptr_ = other.ptr_;
            if (ptr_) {
                ptr_->addRef();
            }
        }
        return *this;
    }

    T* get() const { return ptr_; }
    T& operator*() const { return *ptr_; }
    T* operator->() const { return ptr_; }

private:
    T* ptr_ = nullptr;
};

class RefCounted {
public:
    virtual ~RefCounted() = default;

    void addRef() const { ++*refCount_; }
    void release() const {
        if (--*refCount_ == 0) {
            delete this;
        }
    }

protected:
    RefCounted() : refCount_(new int(1)) {}
    RefCounted(const RefCounted&) : refCount_(new int(1)) {}

private:
    mutable int* refCount_;
};
```

Each `CountedPtr` increments the reference count when copying and decrements when destructing. When the count reaches zero, the object deletes itself.

### Intrusive Reference Counting

The previous example uses non-intrusive counting (the count is stored separately). A more efficient approach is intrusive counting where the count lives in the object itself:

```cpp
class IntrusiveRefCounted {
public:
    void addRef() const { ++refCount_; }

    void release() const {
        if (--refCount_ == 0) {
            delete this;
        }
    }

    int refCount() const { return refCount_; }

protected:
    IntrusiveRefCounted() = default;
    virtual ~IntrusiveRefCounted() = default;

    // Prevent copying through the base class
    IntrusiveRefCounted(const IntrusiveRefCounted&) : refCount_(0) {}

private:
    mutable int refCount_ = 0;
};

template<typename T>
class Counted {
public:
    T* get() const { return static_cast<T*>(this); }

    void addRef() const { ++get()->refCount_; }

    void release() const {
        if (--get()->refCount_ == 0) {
            delete static_cast<const T*>(this);
        }
    }

protected:
    Counted() = default;
    Counted(const Counted&) : refCount_(0) {}
};
```

Now the derived class includes the count directly, avoiding separate allocation for the reference count.

### CRTP-Based Counted Pattern

The Counted Idiom combines well with CRTP for compile-time efficiency:

```cpp
template<typename Derived>
class CountedBase {
public:
    void addRef() const { ++refCount_; }

    void release() const {
        if (--refCount_ == 0) {
            delete static_cast<const Derived*>(this);
        }
    }

    int refCount() const { return refCount_; }

protected:
    CountedBase() = default;
    CountedBase(const CountedBase&) : refCount_(0) {}

private:
    mutable int refCount_ = 0;
};

class DataObject : public CountedBase<DataObject> {
public:
    DataObject() = default;
    explicit DataObject(int v) : value_(v) {}

    int value() const { return value_; }
    void setValue(int v) { value_ = v; }

private:
    int value_ = 0;
};

void useObject(CountedPtr<DataObject> obj) {
    // Use obj safely
}
```

The CRTP approach ensures no virtual function overhead and clean separation of the counting logic.

### Thread Safety in Counted Pointers

Reference counting must handle thread safety carefully:

```cpp
template<typename T>
class ThreadSafeCountedPtr {
public:
    ThreadSafeCountedPtr() = default;

    explicit ThreadSafeCountedPtr(T* p) : ptr_(p) {
        if (ptr_) {
            ptr_->addRef();
        }
    }

    // For thread-safe reference counting
    void addRef() const {
        ptr_->addRef();  // Should use atomic operations
    }

    void release() const {
        if (ptr_->decRef() == 0) {
            ptr_->deleteThis();
        }
    }

    // Copy uses atomic ref counting
    ThreadSafeCountedPtr(const ThreadSafeCountedPtr& other)
        : ptr_(other.ptr_) {
        if (ptr_) {
            ptr_->addRef();
        }
    }

private:
    T* ptr_;
};

class ThreadSafeRefCounted {
public:
    void addRef() { refCount_.fetch_add(1, std::memory_order_relaxed); }

    int decRef() {
        return refCount_.fetch_sub(1, std::memory_order_acq_rel);
    }

    void deleteThis() { delete this; }

protected:
    std::atomic<int> refCount_{0};
};
```

The atomic operations ensure correct behavior when the counted pointer is used across threads.

### Copy-on-Write with Counted Idiom

The Counted Idiom enables efficient copy-on-write patterns:

```cpp
template<typename T>
class CowPtr {
public:
    explicit CowPtr(T* p = nullptr) {
        if (p) {
            counted_ = new Counted<T>(p);
        }
    }

    const T& operator*() const { return *counted_->data_; }

    T& operator*() {
        if (counted_.useCount() > 1) {
            // Make a copy before modifying
            Counted<T>* newData = new Counted<T>(new T(*counted_->data_));
            counted_->release();
            counted_.reset(newData);
        }
        return *counted_->data_;
    }

private:
    struct Counted {
        T* data_;
        int refCount;

        explicit Counted(T* d) : data_(d), refCount(1) {}
        void addRef() { ++refCount; }
        void release() { if (--refCount == 0) delete this; }
    };

    std::shared_ptr<Counted> counted_;
};
```

Copy-on-write defers copying until modification, providing efficiency for read-heavy workloads.

### Weak References

Often you need non-owning references that don't prevent deletion:

```cpp
template<typename T>
class WeakCountedPtr {
public:
    WeakCountedPtr() = default;

    explicit WeakCountedPtr(T* p) : ptr_(p) {}

    bool expired() const {
        return !ptr_ || ptr_->refCount() == 0;
    }

    std::shared_ptr<T> lock() const {
        if (expired()) {
            return {};
        }
        ptr_->addRef();
        return std::shared_ptr<T>(ptr_.get(), [](T* p) { p->release(); });
    }

private:
    T* ptr_;
};

class RefCountedWithWeak {
public:
    void addRef() { ++refCount_; }
    bool release() { return --refCount_ == 0; }
    int refCount() const { return refCount_; }

    WeakCountedPtr<RefCountedWithWeak> weakFromThis() {
        return WeakCountedPtr<RefCountedWithWeak>(this);
    }

private:
    std::atomic<int> refCount_{0};
};
```

The weak pointer tracks the object without preventing its deletion.

### Counted Idiom vs std::shared_ptr

The Counted Idiom offers advantages in certain scenarios:

| Aspect | Counted Idiom | std::shared_ptr |
|--------|---------------|-----------------|
| Memory overhead | Just the count (typically 4 bytes) | Control block (2 pointers + count) |
| Allocation | Intrusive - no separate allocation | Separate allocation for control block |
| Flexibility | Requires explicit support in object | Works with any type |
| Thread safety | Must be implemented manually | Built-in |
| Custom deleters | Intrinsic to the object | Configurable |

Use the Counted Idiom when:
- You control the object type and can add reference counting
- Memory overhead is critical
- You need maximum performance
- The pattern is consistently used in your codebase

Use `std::shared_ptr` when:
- You can't modify the object type
- You need custom deleters
- Thread safety is required
- Flexibility matters more than overhead

### COM-Style Reference Counting

The COM (Component Object Model) pattern is the canonical example of the Counted Idiom:

```cpp
class IUnknown {
public:
    virtual HRESULT QueryInterface(REFIID riid, void** ppv) = 0;
    virtual ULONG AddRef() = 0;
    virtual ULONG Release() = 0;

protected:
    ~IUnknown() = default;
};

template<typename T>
class ComPtr {
public:
    ComPtr() = default;
    ~ComPtr() { if (ptr_) ptr_->Release(); }

    ComPtr(const ComPtr& other) : ptr_(other.ptr_) {
        if (ptr_) ptr_->AddRef();
    }

    ComPtr& operator=(const ComPtr& other) {
        if (ptr_ != other.ptr_) {
            if (ptr_) ptr_->Release();
            ptr_ = other.ptr_;
            if (ptr_) ptr_->AddRef();
        }
        return *this;
    }

    T* get() const { return ptr_; }
    T* operator->() const { return ptr_; }
    T& operator*() const { return *ptr_; }

    HRESULT QueryInterface(REFIID riid, ComPtr<T>& result) {
        return ptr_->QueryInterface(riid, reinterpret_cast<void**>(&result.ptr_));
    }

private:
    T* ptr_ = nullptr;
};
```

This pattern is fundamental to Windows programming and demonstrates the idiom's practical importance.

### Implementing a Complete Counted Type

A production-ready implementation combines these patterns:

```cpp
template<typename Derived>
class RefCountBase {
public:
    void addRef() const {
        refCount_.fetch_add(1, std::memory_order_relaxed);
    }

    void release() const {
        if (refCount_.fetch_sub(1, std::memory_order_acq_rel) == 1) {
            delete static_cast<const Derived*>(this);
        }
    }

    int refCount() const {
        return refCount_.load(std::memory_order_relaxed);
    }

    // For weak pointer support
    bool expired() const {
        return refCount_.load(std::memory_order_acquire) == 0;
    }

protected:
    RefCountBase() = default;
    RefCountBase(const RefCountBase&) : refCount_(0) {}
    RefCountBase& operator=(const RefCountBase&) = default;
    virtual ~RefCountBase() = default;

private:
    mutable std::atomic<int> refCount_{0};
};

template<typename T>
class RefPtr {
public:
    RefPtr() = default;
    explicit RefPtr(T* p) : ptr_(p) { if (ptr_) ptr_->addRef(); }
    ~RefPtr() { if (ptr_) ptr_->release(); }

    RefPtr(const RefPtr& o) : ptr_(o.ptr_) { if (ptr_) ptr_->addRef(); }
    RefPtr& operator=(const RefPtr& o) {
        if (o.ptr_ != ptr_) {
            if (ptr_) ptr_->release();
            ptr_ = o.ptr_;
            if (ptr_) ptr_->addRef();
        }
        return *this;
    }

    RefPtr(RefPtr&& o) noexcept : ptr_(o.ptr_) { o.ptr_ = nullptr; }
    RefPtr& operator=(RefPtr&& o) noexcept {
        if (this != &o) {
            if (ptr_) ptr_->release();
            ptr_ = o.ptr_;
            o.ptr_ = nullptr;
        }
        return *this;
    }

    T* get() const { return ptr_; }
    T* operator->() const { return ptr_; }
    T& operator*() const { return *ptr_; }
    explicit operator bool() const { return ptr_ != nullptr; }

private:
    T* ptr_ = nullptr;
};

class SharedData : public RefCountBase<SharedData> {
public:
    SharedData() = default;
    explicit SharedData(int v) : value_(v) {}
    int value() const { return value_; }
    void setValue(int v) { value_ = v; }

private:
    int value_ = 0;
};

RefPtr<SharedData> createData(int value) {
    return RefPtr<SharedData>(new SharedData(value));
}
```

This complete implementation provides move semantics, thread-safe reference counting, and a clear separation of concerns.

### Summary

The Counted Idiom provides efficient shared ownership by storing reference counts within the objects themselves. Intrusive reference counting avoids separate control block allocation. CRTP enables clean implementation with zero virtual overhead. Thread safety requires atomic operations. Copy-on-write patterns leverage the counted idiom for efficient modification. Weak references track objects without owning them. While `std::shared_ptr` is more flexible, the Counted Idiom offers lower overhead and is essential in performance-critical code and systems like COM.

This chapter explored static polymorphism techniques in C++—from CRTP as the foundational pattern, through static dispatch without virtual functions, to mixin-based composition and reference counting. These techniques enable zero-cost abstractions while maintaining polymorphic behavior, essential for high-performance systems programming.

This chapter explored static polymorphism techniques in C++—from CRTP as the foundational pattern, through static dispatch without virtual functions, to mixin-based composition and reference counting. These techniques enable zero-cost abstractions while maintaining polymorphic behavior, essential for high-performance systems programming.

---

## Summary

This chapter explored four related techniques for achieving static polymorphism in C++. The Curiously Recurring Template Pattern (CRTP) demonstrated how a class template can inherit from a specialization of itself, enabling compile-time polymorphic calls without virtual functions. Static polymorphism without virtual overhead showed how concepts, tag dispatch, template specialization, and type traits provide polymorphic behavior entirely at compile time. Mixin-based inheritance revealed how to compose classes from reusable template-based building blocks, creating flexible class hierarchies without traditional inheritance chains. The Counted Idiom provided efficient shared ownership through intrusive reference counting, essential for performance-critical systems.

Together, these techniques form the foundation of static polymorphism in C++. They enable zero-cost abstractions—polymorphic behavior without runtime overhead—crucial for systems programming, game engines, embedded systems, and other performance-sensitive applications. The key is choosing the right technique for the situation: CRTP when you need polymorphic behavior with known types, concepts for clear interface specification, mixins for composing behaviors, and intrusive counting for efficient shared ownership.

### Exercises

1. **CRTP Implementation**: Implement a class hierarchy for geometric shapes using CRTP, providing area(), perimeter(), and draw() methods for Circle, Square, and Triangle.

2. **Static Polymorphism**: Create a static polymorphic container that can hold any type meeting a "Serializable" concept, with serialize() and deserialize() methods.

3. **Mixin Composition**: Design a set of mixins for a game entity system: Timestamped (adds creation/modification times), Positionable (adds x, y coordinates), Renderable (adds rendering methods), and Collidable (adds collision detection).

4. **Reference Counting**: Implement a complete intrusive reference-counted pointer system supporting both strong and weak references, with thread-safe atomic operations.

5. **Policy-Based Design**: Use mixins to create a policy-based String class with policies for allocation strategy (static buffer vs. heap), thread safety (single-threaded vs. multi-threaded), and character encoding (ASCII vs. UTF-8).
