# Chapter 4: Object Composition

Object composition—the act of building complex types from simpler ones—is one of the most fundamental design decisions in object-oriented programming. While inheritance has historically been the default mechanism for expressing "is-a" relationships, composition offers advantages in flexibility, maintainability, and reduced coupling. This chapter explores idioms that make composition as powerful and expressive as inheritance while avoiding its pitfalls.

The distinction between inheritance and composition isn't merely syntactic—it represents different modeling philosophies. Inheritance builds behavior into a type hierarchy, where derived classes automatically receive parent behavior. Composition assembles behavior from independent components, where each component can be combined freely. Modern C++ best practices favor composition as the default, using inheritance only when truly necessary. The idioms in this chapter show you how to achieve the benefits of inheritance through composition when needed, and how to design classes that compose well with others.

## Composition over Inheritance

The principle "composition over inheritance" advocates for using has-a or uses-a relationships instead of is-a relationships. While the principle itself is simple, executing it well requires understanding why inheritance often fails and how composition solves those problems. This section explores the reasoning behind the principle and shows practical patterns that achieve inheritance-like behavior through composition.

The fundamental problem with inheritance is coupling. When class B inherits from class A, B is tightly bound to A's implementation details. Any change to A—whether adding a new method, changing behavior, or modifying internal state—can break B. This coupling is transitive: everything that depends on B also implicitly depends on A. In large codebases, this creates a fragile inheritance hierarchy where changes propagate unpredictably.

Consider a classic inheritance hierarchy for graphical shapes:

```cpp
class Shape {
public:
    virtual void draw() const = 0;
    virtual ~Shape() = default;
};

class Circle : public Shape {
public:
    void draw() const override;
private:
    double radius_;
    Point center_;
};

class Rectangle : public Shape {
public:
    void draw() const override;
private:
    double width_, height_;
    Point topLeft_;
};
```

This looks reasonable—a Circle is a Shape, a Rectangle is a Shape. But what happens when you need a "filled circle" or a "bordered rectangle"? Inheritance leads to combinatorial explosion:

```cpp
class FilledCircle : public Circle { /* color field */ };
class BorderedCircle : public Circle { /* border style */ };
class FilledBorderedCircle : public Circle { /* both */ };
// And the same for Rectangle...
```

The inheritance hierarchy can't cleanly express combining properties. Composition solves this by making properties explicit:

```cpp
// Composable properties as separate classes
class FillStyle {
public:
    void setColor(Color c) { color_ = c; }
    Color color() const { return color_; }
private:
    Color color_;
};

class BorderStyle {
public:
    void setWidth(double w) { width_ = w; }
    void setColor(Color c) { color_ = c; }
    double width() const { return width_; }
    Color color() const { return color_; }
private:
    double width_;
    Color color_;
};

class Circle {
public:
    void setRadius(double r) { radius_ = r; }
    double radius() const { return radius_; }
    void setCenter(const Point& p) { center_ = p; }
    Point center() const { return center_; }
    
    // Composition: can optionally have fill and border
    void setFill(std::optional<FillStyle> f) { fill_ = f; }
    void setBorder(std::optional<BorderStyle> b) { border_ = b; }
    
    void draw() const;
private:
    double radius_;
    Point center_;
    std::optional<FillStyle> fill_;
    std::optional<BorderStyle> border_;
};
```

Now you can create filled circles, bordered circles, filled bordered circles, or plain circles—all with a single Circle class. The properties compose naturally because they're independent objects that happen to be part of another object.

Beyond flexibility, composition improves testability. With inheritance, testing a derived class often requires testing the parent class too (or mocking it, which is difficult with inheritance). With composition, you can test each component independently and easily substitute test doubles:

```cpp
// Production implementation
class DatabaseConnection {
public:
    virtual void connect() = 0;
    virtual void execute(const std::string& query) = 0;
    virtual ~DatabaseConnection() = default;
};

// Test double - easy to create because we use composition
class MockDatabaseConnection : public DatabaseConnection {
public:
    void connect() override { connectCalled_ = true; }
    void execute(const std::string& query) override { 
        lastQuery_ = query; 
    }
    
    bool connectCalled() const { return connectCalled_; }
    const std::string& lastQuery() const { return lastQuery_; }
private:
    bool connectCalled_ = false;
    std::string lastQuery_;
};

class UserRepository {
public:
    explicit UserRepository(std::unique_ptr<DatabaseConnection> conn)
        : connection_(std::move(conn)) {}
    
    void save(const User& user) {
        connection_->execute("INSERT INTO users...");
    }
private:
    std::unique_ptr<DatabaseConnection> connection_;
};

// Test: inject mock
auto mock = std::make_unique<MockDatabaseConnection>();
auto* mockPtr = mock.get();
UserRepository repo(std::move(mock));
repo.save(user);
assert(mockPtr->lastQuery() == "INSERT INTO users...");
```

Testing inheritance-based designs is far more complicated because you can't easily replace the parent class's behavior.

Composition also enables runtime behavior changes that inheritance cannot provide. You can swap out composed objects at runtime, implementing the Strategy pattern or similar behavioral variations without recompiling:

```cpp
class Renderer {
public:
    void setShape(std::unique_ptr<Shape> s) { shape_ = std::move(s); }
    void setOutlineStrategy(std::unique_ptr<OutlineStrategy> s) { 
        outline_ = std::move(s); 
    }
    void render() {
        shape_->draw();
        if (outline_) outline_->apply();
    }
private:
    std::unique_ptr<Shape> shape_;
    std::unique_ptr<OutlineStrategy> outline_;
};
```

All that said, inheritance remains appropriate in specific cases. When you truly have an "is-a" relationship (every derived object is conceptually also a base object), when you need to override base class behavior, and when you need to access base class implementation, inheritance may be the better choice. The key is recognizing that these cases are rarer than they initially appear.

A practical approach is to default to composition and only reach for inheritance when you've explicitly decided it's necessary. This avoids the trap of building deep inheritance hierarchies that become difficult to change later.

## Handle/Body (pImpl) Idiom

The pImpl ("pointer to implementation") idiom is a composition technique that separates a class's public interface from its implementation details. By hiding implementation in a separate class accessed through a pointer, you achieve compilation firewall benefits, faster compilation times, and the ability to change implementation without recompiling code that uses the class.

The core idea is simple: instead of directly containing member variables, the class contains a pointer to a struct or class that holds the actual implementation. The public class forwards method calls to the implementation pointer:

```cpp
// public_interface.h
class Widget {
public:
    Widget();
    ~Widget();
    
    void setTitle(const std::string& title);
    std::string title() const;
    void render();
    
    // Disable copy, enable move
    Widget(const Widget&) = delete;
    Widget& operator=(const Widget&) = delete;
    Widget(Widget&&) noexcept;
    Widget& operator=(Widget&&) noexcept;
    
private:
    struct Impl;  // Forward declaration - implementation details hidden
    std::unique_ptr<Impl> pImpl_;  // Pointer to implementation
};

// widget.cpp - implementation in separate compilation unit
struct Widget::Impl {
    std::string title_;
    int width_, height_;
    bool visible_;
    // ... all the private members that would normally be in Widget
};

Widget::Widget() : pImpl_(std::make_unique<Impl>()) {}

void Widget::setTitle(const std::string& title) {
    pImpl_->title_ = title;
}

std::string Widget::title() const {
    return pImpl_->title_;
}

void Widget::render() {
    // Render implementation
}
```

The implementation is in the .cpp file, so users of the class only see the header with the public interface. Changing the implementation—including adding new members, changing types, or even swapping the entire implementation—doesn't require recompiling client code, only relinking.

This separation provides several benefits. The most significant is compilation firewall: users of Widget depend only on what's in the header (the public interface). They don't need to see or compile the implementation's headers. In large projects, this dramatically reduces build times because changing implementation details doesn't ripple through the codebase.

The idiom also enables binary compatibility across library versions. If you ship a compiled library and later change the implementation (without changing the interface), existing binaries continue to work because they only depend on the stable ABI defined by the public header.

A subtle benefit is that pImpl makes it harder to accidentally access implementation details. Without pImpl, all private members are visible in the header, and it's tempting to access them directly or create tight coupling. With pImpl, the implementation is truly hidden, enforcing clean public interfaces.

However, pImpl has costs. There's a slight runtime overhead from indirection—each member access goes through the pointer. The pattern adds code complexity and requires managing move semantics carefully (you need to implement move constructor and assignment to transfer ownership of the implementation pointer). For small, frequently-used classes, this overhead might not be worth it.

Modern C++ makes pImpl cleaner with `std::unique_ptr`. Earlier implementations used raw pointers and manual memory management, which introduced opportunities for leaks and required careful attention to the Rule of Three. With `std::unique_ptr`, the implementation pointer is automatically managed.

One consideration is exception safety. If your class already uses RAII for resources, adding pImpl doesn't change that—you still need to ensure no-throw move operations if you want to guarantee strong exception safety. The implementation object itself can contain whatever RAII wrappers are needed.

The pImpl idiom is particularly valuable for classes that will be widely used in a library or framework, where compilation times and binary stability matter. It's less necessary for application-internal classes where build time isn't critical.

## Interface Segregation with Mixins

Mixins are a composition technique where classes are constructed by combining independent "mix" classes that each provide specific functionality. The term comes from "mixing in" additional behavior. Unlike traditional inheritance where you inherit from a single base, mixins let you compose behavior from multiple sources, giving fine-grained control over what functionality a class provides.

C++ doesn't have built-in mixin support, but you can achieve similar results through multiple inheritance or template-based mixins. The goal is interface segregation—ensuring that classes only depend on the methods they actually use, rather than inheriting a large interface they don't need.

Consider a base class with many methods:

```cpp
class Document {
public:
    virtual void load(const std::string& path) = 0;
    virtual void save(const std::string& path) = 0;
    virtual void print() const = 0;
    virtual void undo() = 0;
    virtual void redo() = 0;
    virtual void copy() = 0;
    virtual void paste() = 0;
    virtual void spellCheck() = 0;
    virtual ~Document() = default;
};
```

If you want a simple document that only supports load and save, you still inherit the entire interface. You must implement all methods or have the base class provide default (often empty) implementations. This creates a fat interface problem.

Mixin-based design solves this by decomposing functionality into independent aspects:

```cpp
// Independent capability mixins
class Loadable {
public:
    virtual void load(const std::string& path) = 0;
    virtual ~Loadable() = default;
};

class Saveable {
public:
    virtual void save(const std::string& path) = 0;
    virtual ~Saveable() = default;
};

class Printable {
public:
    virtual void print() const = 0;
    virtual ~Printable() = default;
};

class Undoable {
public:
    virtual void undo() = 0;
    virtual void redo() = 0;
    virtual ~Undoable() = default;
};

// Your class inherits only what it needs
class SimpleDocument : public Loadable, public Saveable {
public:
    void load(const std::string& path) override;
    void save(const std::string& path) override;
    
private:
    // SimpleDocument's specific data
};

class EditableDocument : public Loadable, public Saveable, 
                         public Printable, public Undoable {
public:
    void load(const std::string& path) override;
    void save(const std::string& path) override;
    void print() const override;
    void undo() override;
    void redo() override;
    
private:
    std::vector<std::string> undoStack_;
    std::vector<std::string> redoStack_;
};
```

Now each class has exactly the interface it needs. There's no pressure to implement unused methods, and clients that work with Loadable don't know about Undoable functionality.

Template-based mixins provide a more powerful pattern. Rather than inheriting concrete classes, you inherit templates that add functionality parameterized by the derived class:

```cpp
template<typename Derived>
class SerializableMixin {
public:
    void save(std::ostream& out) const {
        auto* self = static_cast<const Derived*>(this);
        self->serialize(out);
    }
    
    void load(std::istream& in) {
        auto* self = static_cast<Derived*>(this);
        self->deserialize(in);
    }
};

template<typename Derived>
class PrintableMixin {
public:
    void print(std::ostream& out) const {
        auto* self = static_cast<const Derived*>(this);
        self->render(out);
    }
};

class MyDocument : public SerializableMixin<MyDocument>,
                   public PrintableMixin<MyDocument> {
public:
    void serialize(std::ostream& out) const;
    void deserialize(std::istream& in);
    void render(std::ostream& out) const;
};
```

This pattern adds functionality to any class by mixing it in. The mixin uses CRTP (Curiously Recurring Template Pattern) to call the derived class's methods, enabling compile-time polymorphism without virtual functions.

Mixins do have limitations in C++. Diamond inheritance issues can arise if mixins share a common base. Virtual inheritance solves this but adds runtime cost. Also, mixins with state can lead to complex initialization order issues. Despite these challenges, they remain powerful for building flexible class hierarchies.

The interface segregation principle underlying mixins extends beyond class design. When designing APIs, consider providing narrow, focused interfaces rather than large catch-all interfaces. Clients can then compose exactly what they need.

## Policy-Based Design

Policy-based design is a compile-time composition technique where class behavior is determined by template parameters ("policies") rather than runtime configuration. Each policy is a template parameter that provides a specific aspect of behavior, and the class combines these policies to produce its final behavior. This enables extensive customization without runtime overhead.

The technique emerged from libraries like Loki and Boost, where it's used to provide configurable components. The key insight is that policies are typically small classes or class templates with specific interfaces that the host class expects:

```cpp
// Policy definitions
template<typename T>
struct DefaultAllocationPolicy {
    static T* allocate() { return new T(); }
    static void deallocate(T* p) { delete p; }
};

template<typename T>
struct PoolAllocationPolicy {
    static T* allocate() { 
        return static_cast<T*>(pool.allocate(sizeof(T))); 
    }
    static void deallocate(T* p) { pool.deallocate(p); }
private:
    static MemoryPool pool;
};

template<typename T>
struct NoCopyPolicy {
    NoCopyPolicy() = default;
    NoCopyPolicy(const NoCopyPolicy&) = delete;
    NoCopyPolicy& operator=(const NoCopyPolicy&) = delete;
};

template<typename T>
struct RefCountPolicy {
    RefCountPolicy() : refCount_(new int(1)) {}
    RefCountPolicy(const RefCountPolicy& other) : refCount_(other.refCount_) {
        ++(*refCount_);
    }
    RefCountPolicy& operator=(const RefCountPolicy& other) {
        if (this != &other) {
            if (--(*refCount_) == 0) delete refCount_;
            refCount_ = other.refCount_;
            ++(*refCount_);
        }
        return *this;
    }
    ~RefCountPolicy() { if (--(*refCount_) == 0) delete refCount_; }
    
private:
    int* refCount_;
};

// Policy-based class
template<typename T, 
         typename AllocationPolicy = DefaultAllocationPolicy<T>,
         typename CopyPolicy = NoCopyPolicy<T>>
class SmartPointer : private AllocationPolicy<T>, private CopyPolicy<T> {
public:
    T* get() const { return ptr_; }
    T& operator*() const { return *ptr_; }
    
    void reset() {
        if (ptr_) {
            AllocationPolicy<T>::deallocate(ptr_);
        }
        ptr_ = nullptr;
    }
    
    // Copy and move constructors use CopyPolicy
    SmartPointer(const SmartPointer& other) : CopyPolicy<T>(other) {
        ptr_ = AllocationPolicy<T>::allocate();
        *ptr_ = *other.ptr_;
    }
    
private:
    T* ptr_;
};
```

This example demonstrates how policies compose. You can create smart pointers with different allocation strategies (default heap, memory pool) and different copy semantics (no copy, reference counting), all determined at compile time with no runtime overhead for the policy selection.

A more practical example from the standard library is `std::unique_ptr`. The second template parameter is a deleter policy:

```cpp
std::unique_ptr<File, FileDeleter> openFile(const char* path);

// Custom deleter policy
struct CustomDeleter {
    void operator()(FILE* f) const {
        if (f) fclose(f);
    }
};
std::unique_ptr<FILE, CustomDeleter> file(fopen("data.txt", "r"));
```

Policy-based design works best when you have multiple orthogonal dimensions of variation. If you only have one or two variations, simple template parameters or runtime configuration may be simpler. But when you have many potential variations that can be combined arbitrarily, policies provide a clean combinatorial approach.

One challenge with policy-based design is that the number of template parameters can grow unwieldy. Techniques to manage this include grouping related policies into policy bundles, using default policy parameters, and providing named type aliases that bundle common policy combinations:

```cpp
template<typename T, typename... Policies>
class FlexibleClass;

// Common combinations as type aliases
using DefaultFlexibleClass = FlexibleClass<MyType, DefaultPolicy>;
using ThreadSafeFlexibleClass = FlexibleClass<MyType, DefaultPolicy, ThreadSafePolicy>;
```

Another challenge is policy interaction. When policies have state, combining them can lead to complex initialization and potential ordering issues. Policy design should favor stateless policies when possible, or provide clear initialization semantics.

The tradeoff between policy-based design and runtime configuration (like Strategy pattern) is fundamental. Policy-based design gives zero runtime overhead—you choose behavior at compile time and the compiler eliminates any abstraction cost. Runtime configuration adds flexibility—you can change behavior without recompiling—but incurs some runtime cost. Choose based on whether behavior is fixed at compile time or needs to change at runtime.

## Summary

This chapter explored four composition idioms that give you flexibility in building complex types from simpler components. Composition over Inheritance provides the philosophical foundation: favor has-a relationships over is-a relationships to reduce coupling, improve testability, and avoid the combinatorial explosion of inheritance hierarchies. The Handle/Body (pImpl) idiom adds a practical technique for separating interface from implementation, reducing compilation dependencies and enabling binary compatibility. Interface segregation with mixins shows how to build classes from independent capability components rather than a monolithic inheritance chain. Policy-based design extends composition to compile-time parameterization, enabling extensive customization with zero runtime cost.

These idioms share a common theme: they give you control over how components combine. Whether you're building classes from capabilities (mixins), configuring behavior at compile time (policies), or separating interface from implementation (pImpl), composition gives you flexibility that inheritance cannot match.

As your designs grow in complexity, these patterns become essential. A class that uses pImpl can change its implementation without breaking clients. A class built from mixins can recombine capabilities as requirements evolve. A policy-based container can adapt to different use cases without runtime overhead. Master these patterns, and you'll be equipped to build maintainable, flexible software systems.

### Exercises

1. **Composition Refactoring**: Take an inheritance hierarchy from your codebase or a known example (like the classic `Employee` hierarchy with `Manager`, `Engineer`, `Salesperson`) and refactor it to use composition. Identify what properties are being inherited and how they could become composed objects instead.

2. **pImpl Implementation**: Implement a pImpl version of `std::vector` (simplified) and measure the compile time difference when you change the implementation versus the interface. Explain why the difference exists.

3. **Mixin Library**: Create a small library of useful mixins for a GUI framework, including mixins for serializable, draggable, focusable, and themed widgets. Show how these can be combined to create specific widget types.

4. **Policy-Based Container**: Design a policy-based vector that supports policies for: allocation strategy (heap, pool, stack), initialization (zero-initialize, default-construct, copy-construct), and bounds checking (none, assert, exception). Provide benchmarks comparing different policy combinations.

5. **Comparison Analysis**: Compare policy-based design with the Strategy pattern. When would you choose each? Create a decision tree that helps developers choose between them based on their specific requirements.