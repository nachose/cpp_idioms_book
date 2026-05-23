# Chapter 5: Object Lifetime and Initialization

Object lifetime and initialization are at the heart of correct C++ programming. An uninitialized object contains indeterminate values and using it leads to undefined behavior. Incorrect initialization order can cause crashes or subtle bugs. Managing special member functions determines whether your objects can be copied, moved, or need custom lifecycle management. This chapter explores idioms that give you precise control over how objects are created, initialized, and destroyed.

These idioms address different aspects of object lifecycle. Constructor delegation lets one constructor call another to avoid code duplication. Understanding initialization order prevents subtle bugs when constructors depend on each other. The Rule of Zero/Five guides you to either let the compiler generate special member functions or implement them correctly. Type list construction enables compile-time construction of heterogeneous collections.

## Constructor Delegation

Constructor delegation allows one constructor to call another constructor of the same class, initializing the object through a different path while avoiding code duplication. Before C++11, you might have duplicated initialization logic or extracted it to a private `init()` method. Delegation provides a cleaner solution that keeps initialization logic in constructors.

Consider a class with multiple constructors that share common initialization:

```cpp
class Connection {
public:
    Connection() 
        : host_("localhost"), port_(80), timeout_(30), 
          secure_(false), connected_(false) {}
    
    Connection(const std::string& host, int port)
        : host_(host), port_(port), timeout_(30), 
          secure_(false), connected_(false) {}
    
    Connection(const std::string& host, int port, bool secure)
        : host_(host), port_(port), timeout_(30), 
          secure_(secure), connected_(false) {}
    
    Connection(const std::string& host, int port, int timeout, bool secure)
        : host_(host), port_(port), timeout_(timeout), 
          secure_(secure), connected_(false) {}
};
```

Without delegation, you either duplicate initialization or extract to a helper. With delegation, you can chain constructors:

```cpp
class Connection {
public:
    Connection() 
        : Connection("localhost", 80, 30, false) {}
    
    Connection(const std::string& host, int port)
        : Connection(host, port, 30, false) {}
    
    Connection(const std::string& host, int port, bool secure)
        : Connection(host, port, 30, secure) {}
    
    Connection(std::string host, int port, int timeout, bool secure)
        : host_(std::move(host)), port_(port), timeout_(timeout), 
          secure_(secure), connected_(false) {}
    
private:
    std::string host_;
    int port_;
    int timeout_;
    bool secure_;
    bool connected_;
};
```

Now there's exactly one place where members are initialized—the "master" constructor that all others delegate to. This eliminates duplication and ensures consistency: if you add a new member, you only need to update one constructor.

The syntax uses a constructor call in the member initializer list, separated from other initializers by a colon. One constraint: the delegated constructor runs before any other member initializers, so you cannot initialize a member in both the delegated constructor and the delegating constructor:

```cpp
class Example {
public:
    // Valid: this constructor delegates, then no other initializers
    Example(int x) : Example(x, 0) {}
    
    // Invalid: can't have both delegation AND other initializers
    // Example(int x) : Example(x, 0), value_(x) {}  // ERROR
    
    Example(int x, int y) : value_(x + y) {}
    
private:
    int value_;
};
```

Delegation also works with base class initialization:

```cpp
class Base {
public:
    Base(int value) : value_(value) {}
protected:
    int value_;
};

class Derived : public Base {
public:
    Derived() : Derived(0) {}
    
    Derived(int value) : Base(value), extra_(value * 2) {}
    
    Derived(int value, const std::string& name) 
        : Base(value), name_(name), extra_(value * 2) {}
    
private:
    std::string name_;
    int extra_;
};
```

A key insight is that constructor delegation doesn't call the default constructor then the delegated constructor—it directly constructs the object through the delegated path. This is more efficient than the pre-C++11 pattern of `init()` methods that ran after construction.

Delegation does have limitations. You cannot have multiple delegations (A delegates to B, which delegates to C)—at least one must be non-delegating. Also, if your constructors have different exception guarantees, delegating from one to another can change exception safety. Ensure the delegated constructor provides the appropriate guarantees for all code paths.

A common pattern combines delegation with factory methods when you want to prevent direct construction:

```cpp
class DatabaseConnection {
public:
    // Factory method returning configured connection
    static DatabaseConnection createLocal() {
        return DatabaseConnection("localhost", 5432);
    }
    
    static DatabaseConnection createRemote(const std::string& host) {
        return DatabaseConnection(host, 5432);
    }
    
    // Allow construction only through factory methods
    // by making constructors private and factories friends,
    // or by using tagged construction
    
private:
    DatabaseConnection(const std::string& host, int port) 
        : host_(host), port_(port), connected_(false) {}
    
    std::string host_;
    int port_;
    bool connected_;
};
```

This approach ensures all connections are created through known, controlled paths—delegation helps maintain a single initialization point within each path.

## Initialization Order Guarantees

C++ guarantees a specific order for member and base class initialization, and understanding this order is crucial for writing correct code. The order is: base classes first (in declaration order), then members (in declaration order), then the constructor body runs. This order is fixed regardless of the order in the initializer list—if you write `MemberInitializerList{ b_, a_ }` but `a_` is declared before `b_`, `a_` still initializes first.

This fixed order prevents confusion but can lead to subtle bugs when constructors depend on each other:

```cpp
class Widget {
public:
    Widget(int size) : buffer_(size), data_(buffer_.data()) {}
    // WRONG: buffer_ initializes first, then data_ is set to buffer_.data()
    // This seems fine but the order is guaranteed regardless of initializer list
    
private:
    std::vector<char> buffer_;
    char* data_;  // Points into buffer_
};
```

The `data_` member is initialized after `buffer_`, so this code technically works—but it's fragile and relies on understanding the order. A more robust design would initialize `data_` within the constructor body after both members exist, or better, avoid depending on initialization order at all.

Initialization order issues become more complex with multiple inheritance:

```cpp
class Base1 {
public:
    Base1() { std::cout << "Base1\n"; }
};

class Base2 {
public:
    Base2() { std::cout << "Base2\n"; }
};

class Derived : public Base2, public Base1 {
public:
    Derived() { std::cout << "Derived\n"; }
};

// Output: Base2, Base1, Derived
// Base2 initializes first because it's listed first in the inheritance list
```

Base classes initialize in the order they're declared in the class definition, not the order in the initializer list. Similarly, members initialize in declaration order, not initializer list order. This is intentional—it prevents confusion from having different orders in different places—but means you must declare members in the order you want them initialized.

A common anti-pattern involves one member initializing based on another:

```cpp
class Processor {
public:
    Processor() : config_(loadConfig()), 
                  state_(config_.initialState()) {}  // Could be fragile
    
private:
    Config config_;
    State state_;
    // If state_ depends on config_ being fully initialized, 
    // this works only because config_ is declared first
};
```

The solution is careful declaration order, or better, avoiding dependencies between members entirely. Use constructor body initialization when members must compute values based on each other:

```cpp
class Processor {
public:
    Processor() {
        // Both members initialized to defaults; state_ can use config_ here
        state_ = State(config_.initialState());
    }
    
private:
    Config config_;
    State state_;
};
```

Static initialization order between different translation units creates a different category of problems. If object A's initialization depends on object B from another .cpp file, and the initialization order is unspecified, you might access an uninitialized object. The solution is the "construct on first use" pattern:

```cpp
// config.h
Config& getConfig() {
    static Config instance;  // Initialized on first call, safely
    return instance;
}

// In any .cpp file
void initialize() {
    Config& cfg = getConfig();  // Config is initialized before use
}
```

Local static variables are initialized the first time execution reaches their declaration, and this initialization is thread-safe in C++11 and later. This pattern solves the static initialization order problem reliably.

For member initialization, prefer in-member initialization (C++11) for simple defaults and constructor initializer lists for values that require construction arguments:

```cpp
class Player {
public:
    Player() = default;
    Player(const std::string& name, int score) 
        : name_(name), score_(score) {}
    
private:
    std::string name_;
    int score_ = 0;  // In-member initialization as default
    bool active_ = true;  // Simple default
};
```

This approach is clear, avoids empty constructor bodies, and makes default values visible in the class definition.

## Rule of Zero / Rule of Five / Rule of Six

The Rule of Zero, Rule of Five, and Rule of Six describe how special member functions (constructors and assignment operators) should interact. Understanding these rules helps you avoid the common pitfall of accidentally disabling operations or creating inconsistent copy/move semantics.

The Rule of Five states that if you define any of these five special member functions—destructor, copy constructor, copy assignment operator, move constructor, or move assignment operator—then you should probably define all five:

```cpp
class Resource {
public:
    Resource() : data_(new int[100]) {}
    
    ~Resource() { delete[] data_; }
    
    // If we define destructor, we probably need the rest for proper handling
    Resource(const Resource& other) : data_(new int[100]) {
        std::copy(other.data_, other.data_ + 100, data_);
    }
    
    Resource& operator=(const Resource& other) {
        if (this != &other) {
            delete[] data_;
            data_ = new int[100];
            std::copy(other.data_, other.data_ + 100, data_);
        }
        return *this;
    }
    
    Resource(Resource&& other) noexcept : data_(other.data_) {
        other.data_ = nullptr;
    }
    
    Resource& operator=(Resource&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = other.data_;
            other.data_ = nullptr;
        }
        return *this;
    }
    
private:
    int* data_;
};
```

The rationale is that if you're managing a resource manually (like raw memory), each operation must handle that resource correctly. Omitting one creates subtle bugs: a move constructor that does a shallow copy while the copy constructor does a deep copy, for instance.

The Rule of Zero is the ideal: don't define any special member functions, and let the compiler generate them. For classes that don't manage resources specially, default behavior is correct:

```cpp
class Point {
public:
    Point(double x, double y) : x_(x), y_(y) {}
    // Compiler generates: destructor, copy constructor, copy assignment,
    // move constructor, move assignment—all correct for simple members
    
private:
    double x_;
    double y_;
};
```

The compiler-generated operations do member-wise copy or move, which is exactly right for classes containing simple types or types that handle their own resources correctly.

The Rule of Six extends the Rule of Five to include a sixth operation: the constructor with parameters. Specifically, it states that if you define a parameterized constructor (or any constructor other than the copy/move constructors), you should also explicitly default or delete the other five operations to make your intent clear:

```cpp
class Logger {
public:
    Logger(const std::string& name) : name_(name) {}
    
    // Explicitly default special members to keep them working
    Logger(const Logger&) = default;
    Logger(Logger&&) = default;
    Logger& operator=(const Logger&) = default;
    Logger& operator=(Logger&&) = default;
    ~Logger() = default;
    
private:
    std::string name_;
};
```

This makes explicit that the parameterized constructor doesn't change the copy/move semantics—it's just adding a convenience constructor.

Modern C++ provides tools to make following these rules easier. `= default` tells the compiler to generate the special member function with its default implementation. `= delete` prevents accidental use:

```cpp
class NonCopyable {
public:
    NonCopyable() = default;
    
    NonCopyable(const NonCopyable&) = delete;
    NonCopyable& operator=(const NonCopyable&) = delete;
    
    // Moves can still be allowed
    NonCopyable(NonCopyable&&) = default;
    NonCopyable& operator=(NonCopyable&&) = default;
};

class MoveOnly {
public:
    MoveOnly() = default;
    
    MoveOnly(const MoveOnly&) = delete;
    MoveOnly& operator=(const MoveOnly&) = delete;
    
    MoveOnly(MoveOnly&&) = default;
    MoveOnly& operator=(MoveOnly&&) = default;
};
```

One subtlety is that the compiler generates special member functions conditionally. If you declare a copy constructor, the compiler won't generate a move constructor. If you declare a move constructor, the copy operations are deleted. This conditional generation can lead to unexpected behavior:

```cpp
class Problematic {
public:
    Problematic() = default;
    
    Problematic(const Problematic&) { /* custom copy */ }
    // Move constructor is NOT generated now (deleted implicitly)
    
    // Problematic can no longer be moved!
    // This often surprises developers
};
```

The solution is to explicitly declare all five operations if you customize any of them, or better, use the Rule of Zero by using RAII types that manage resources correctly.

A common application is with resource-owning members:

```cpp
class Widget {
public:
    Widget() = default;
    
    // All five: let compiler generate them
    // The unique_ptr member handles its own resource
    
private:
    std::unique_ptr<Impl> impl_;  // Handles its own lifetime
};
```

The `std::unique_ptr` member means the class is not trivially copyable, but that's fine—the compiler generates correct copy/move operations that delegate to `unique_ptr`'s operations.

When you need custom behavior, use `= default` for the operations you don't customize:

```cpp
class TrackingWidget {
public:
    TrackingWidget() { ++constructionCount; }
    ~TrackingWidget() { ++destructionCount; }
    
    TrackingWidget(const TrackingWidget&) { ++copyCount; }
    TrackingWidget& operator=(const TrackingWidget&) { 
        ++copyAssignCount; return *this; 
    }
    
    TrackingWidget(TrackingWidget&&) noexcept { ++moveCount; }
    TrackingWidget& operator=(TrackingWidget&&) noexcept { 
        ++moveAssignCount; return *this; 
    }
    
    static void printStats() {
        std::cout << "Construct: " << constructionCount << "\n"
                  << "Destroy: " << destructionCount << "\n"
                  << "Copy: " << copyCount << "\n"
                  << "Move: " << moveCount << "\n";
    }
    
private:
    static int constructionCount;
    static int destructionCount;
    static int copyCount;
    static int copyAssignCount;
    static int moveCount;
    static int moveAssignCount;
};
```

This explicitly defines all five with tracking, making behavior visible and intentional.

## Object Construction with Type Lists

Type lists are a compile-time technique for storing and manipulating lists of types. While C++ standard containers hold values, type lists hold types, enabling compile-time algorithms and metaprogramming. One application is constructing objects from heterogeneous type lists—creating objects of different types based on compile-time type information.

A type list is a simple template structure that holds a type:

```cpp
template<typename... Types>
struct TypeList {};

template<typename Head, typename Tail>
struct TypeListNode {
    using head = Head;
    using tail = Tail;
};
```

With this foundation, you can build algorithms that operate on types:

```cpp
template<typename List>
struct Length;

template<>
struct Length<TypeList<>> {
    static constexpr size_t value = 0;
};

template<typename Head, typename Tail>
struct Length<TypeListNode<Head, Tail>> {
    static constexpr size_t value = 1 + Length<Tail>::value;
};
```

For object construction, you can use type lists to create factories that produce objects of any type in the list:

```cpp
template<typename... Types>
struct TypeList {};

// Type-at: get the Nth type from a type list
template<typename List, size_t Index>
struct TypeAt;

template<typename Head, typename Tail>
struct TypeAt<TypeListNode<Head, Tail>, 0> {
    using type = Head;
};

template<typename Head, typename Tail, size_t Index>
struct TypeAt<TypeListNode<Head, Tail>, Index> {
    using type = typename TypeAt<Tail, Index - 1>::type;
};

// Factory that creates objects of types in the list
template<typename TypeList>
class ObjectFactory;

// Specialization for non-empty list
template<typename Head, typename... Tail>
class ObjectFactory<TypeList<Head, Tail...>> {
public:
    template<typename T>
    std::unique_ptr<T> create() {
        static_assert(MatchesOneOf<T, Head, Tail...>::value);
        return std::make_unique<T>();
    }
    
    template<size_t Index>
    auto createAt() -> std::unique_ptr<typename TypeAt<TypeList, Index>::type> {
        using Type = typename TypeAt<TypeList, Index>::type;
        return std::make_unique<Type>();
    }
};

template<>
class ObjectFactory<TypeList<>> {
public:
    template<typename T>
    std::unique_ptr<T> create() {
        static_assert(sizeof(T) == 0, "Cannot create from empty type list");
        return nullptr;
    }
};
```

This factory can create any object whose type appears in the type list. You could extend it to support construction with arguments, using variadic templates to pass parameters through.

A practical use case is a plugin system where plugins register themselves, and the system constructs instances of registered types:

```cpp
// Registration mechanism
class PluginRegistry {
public:
    template<typename T>
    void registerPlugin(const std::string& name) {
        static_assert(std::is_base_of_v<Plugin, T>);
        creators_[name] = []() -> std::unique_ptr<Plugin> {
            return std::make_unique<T>();
        };
    }
    
    std::unique_ptr<Plugin> create(const std::string& name) {
        auto it = creators_.find(name);
        if (it != creators_.end()) {
            return it->second();
        }
        return nullptr;
    }
    
    template<typename T>
    bool has() const {
        return creators_.contains(typeid(T).name());
    }
    
private:
    std::unordered_map<std::string, std::function<std::unique_ptr<Plugin>()>> creators_;
};
```

Type lists also enable compile-time parameter packs manipulation for constructing multiple objects:

```cpp
template<typename... Types>
struct VariadicConstructor {
    template<typename Factory>
    static auto construct(Factory& factory) {
        return std::make_tuple(factory.template create<Types>()...);
    }
};

// Usage:
using Types = TypeList<Button, Label, TextBox>;
auto widgets = VariadicConstructor::construct<Button, Label, TextBox>(factory);
```

The key insight is that type list construction moves work from runtime to compile time. When the set of types is fixed at compile time, constructing objects of those types can be handled entirely by template instantiation, eliminating runtime type switching or registration.

However, type lists have limitations. They're complex to implement correctly and can lead to cryptic error messages when something goes wrong. For most applications, runtime polymorphism (virtual functions) is simpler and sufficient. Use type lists when you need compile-time type manipulation—policy selection, code generation, or metaprogramming—rather than runtime flexibility.

## Summary

This chapter explored four idioms for controlling object lifetime and initialization. Constructor delegation provides a clean mechanism for sharing initialization logic between constructors, avoiding duplication while maintaining clear initialization paths. Initialization order guarantees explained the fixed order in which bases and members initialize, emphasizing the importance of declaration order and the pitfalls of depending on initializer list order. The Rule of Zero/Five/Six provides a framework for deciding when to define special member functions explicitly, with the ideal being the Rule of Zero—letting the compiler generate correct behavior unless you truly need custom implementation. Object construction with type lists demonstrates how to use compile-time type manipulation to construct heterogeneous collections, moving work from runtime to compile time.

These idioms address different aspects of object lifecycle. Delegation and initialization order help you initialize objects correctly and consistently. The Rules of Zero/Five/Six guide you toward correct copy and move semantics. Type list construction enables compile-time construction patterns for metaprogramming scenarios.

Mastering these patterns gives you precise control over how objects come into existence, maintain their invariants, and are cleaned up. This control is fundamental to writing robust C++ code that neither leaks resources nor creates dangling references.

### Exercises

1. **Delegation Design**: Design a class hierarchy for a database connection pool with multiple connection types (MySQL, PostgreSQL, SQLite). Use constructor delegation to share common initialization while allowing type-specific configuration.

2. **Initialization Order Bug**: Find or create a case where member initialization order matters and causes incorrect behavior if declared in the wrong order. Explain how the fixed initialization order prevents confusion compared to relying on initializer list order.

3. **Rule of Five Implementation**: Implement a class that manages a file handle, ensuring proper copy and move semantics. Use `= default` where appropriate and explain your decisions.

4. **Type List Library**: Build a small type list library with: `Length`, `TypeAt`, `Contains`, and `Append`. Then implement a factory that can construct objects from any type in the list and a function that applies a function to all types in the list.

5. **Comparison**: Compare type list construction with runtime polymorphism (virtual functions and factory methods). Under what conditions would each approach be preferable? Create a decision matrix for common scenarios.