# Chapter 22: Creational Patterns

- Builder pattern with method chaining
- Singleton implementations and alternatives
- Abstract Factory with type lists
- Object pool patterns

## Builder Pattern with Method Chaining

Constructing complex objects is a deceptively hard problem. When an object requires many parameters — some required, some optional, some interdependent — constructor calls become unreadable, error-prone, and brittle. A `Widget` that needs a width, height, color, label, border radius, font size, and callback handler cannot express all of these clearly through positional constructor arguments. Worse, adding a new parameter later breaks every call site.

The builder pattern solves this by replacing a single massive constructor with a sequence of named method calls, each setting one piece of state, culminating in a final `build()` that produces the configured object. Method chaining — each setter returning `*this` by reference — turns construction into a fluent, readable expression:

```cpp
auto w = WidgetBuilder{}
    .set_width(320)
    .set_height(240)
    .set_color(Color::Teal)
    .set_label("Hello")
    .build();
```

Every call site names the parameter being set, so the order is irrelevant, omitted parameters are obvious, and adding a new parameter to the builder never breaks existing callers that do not use it.

### A Minimal Builder

The simplest builder is a separate class that accumulates construction parameters and then creates the target object in one shot:

```cpp
class Widget {
    int width_ = 800;
    int height_ = 600;
    Color color_ = Color::Default;
    std::string label_;
public:
    Widget(int w, int h, Color c, std::string lbl)
        : width_(w), height_(h), color_(c), label_(std::move(lbl)) {}
    // ...
};

class WidgetBuilder {
    int width_ = 800;
    int height_ = 600;
    Color color_ = Color::Default;
    std::string label_;
public:
    auto set_width(int w) -> WidgetBuilder& {
        width_ = w;
        return *this;
    }
    auto set_height(int h) -> WidgetBuilder& {
        height_ = h;
        return *this;
    }
    auto set_color(Color c) -> WidgetBuilder& {
        color_ = c;
        return *this;
    }
    auto set_label(std::string lbl) -> WidgetBuilder& {
        label_ = std::move(lbl);
        return *this;
    }
    auto build() const & -> Widget {
        return Widget{width_, height_, color_, label_};
    }
    auto build() && -> Widget {
        return Widget{width_, height_, color_, std::move(label_)};
    }
};
```

Each setter mirrors a constructor parameter but allows the caller to specify it independently. Sensible defaults are set in the builder's member initializers — callers only need to override the values they care about. The `build()` function validates and produces the final object.

The pattern transforms an opaque constructor call like:

```cpp
auto w = Widget{320, 240, Color::Teal, "Hello"};
```

Wait — which argument is width and which is height? Is the color before or after the label? The builder makes every value explicit at the cost of a few extra lines of boilerplate.

### Enforcing Required Parameters

A weakness of the simple builder above is that callers can forget to set required parameters. The object compiles, builds with defaults, and at best logs a warning; at worst it silently misbehaves. Variants of the builder pattern address this by encoding requirements into the type system.

One approach is to make the builder templated on a parameter pack that tracks which fields have been set, using the type system to reject incomplete configurations at compile time. A simpler, more idiomatic C++ alternative uses move semantics to model consumption: a parameter, once set, cannot be set again or forgotten.

```cpp
struct Width { int value; };
struct Height { int value; };
struct Color { enum Value { Default, Teal, Coral }; Value value; };

template <typename... Ts>
class WidgetBuilder;

template <>
class WidgetBuilder<> {
    // Base case: no parameters set yet
};

// Specialization when Width is present
template <typename... Rest>
class WidgetBuilder<Width, Rest...> {
    int width_;
public:
    explicit WidgetBuilder(Width w) : width_(w.value) {}
    auto build() { /* ... */ }
};
```

This is workable but verbose. In practice most C++ builders use a runtime check in `build()` that throws or returns an error if a required parameter was omitted. The C++ type system *can* enforce completeness, but the resulting complexity is rarely worth it for all but the most critical APIs.

### In-Place Builder (Fluent Construction)

A variation that is popular in the C++ standard library and in high-performance code makes the *target object itself* the builder:

```cpp
class Widget {
    int width_ = 800;
    int height_ = 600;
    Color color_ = Color::Default;
    std::string label_;
public:
    auto set_width(int w) -> Widget& {
        width_ = w;
        return *this;
    }
    auto set_height(int h) -> Widget& {
        height_ = h;
        return *this;
    }
    auto set_color(Color c) -> Widget& {
        color_ = c;
        return *this;
    }
    auto set_label(std::string lbl) -> Widget& {
        label_ = std::move(lbl);
        return *this;
    }
};
```

The caller constructs a default Widget and chains setters on it directly:

```cpp
auto w = Widget{}
    .set_width(320)
    .set_height(240)
    .set_color(Color::Teal)
    .set_label("Hello");
```

No separate builder class, no `build()` call. The object is already fully formed after the chain. This approach works well when the object has a valid default state and the setters are cheap. It works poorly when the object's invariants require that certain fields be set together atomically — nothing stops the caller from using the Widget after setting only the width.

The design question is therefore: does the object have intermediate states that should be invalid? If yes, use a separate builder that validates in `build()`. If no — if the object is always usable and setters are just configuration — the in-place builder is simpler and more efficient.

### Hierarchical Builders

When an object contains sub-objects that themselves require construction parameters, a single flat builder loses the structure. Consider a `Dialog` that contains a `Button`:

```cpp
auto dlg = DialogBuilder{}
    .set_title("Confirm")
    .add_button()
        .set_label("OK")
        .set_callback(&on_ok)
    .end_button()
    .add_button()
        .set_label("Cancel")
        .set_callback(&on_cancel)
    .end_button()
    .build();
```

The `add_button()` method returns a sub-builder for the button, and `end_button()` returns the parent `DialogBuilder`. This requires the button builder to hold a reference or pointer back to the dialog builder.

```cpp
class DialogBuilder {
    std::string title_;
    std::vector<Button> buttons_;
public:
    auto set_title(std::string t) -> DialogBuilder& {
        title_ = std::move(t);
        return *this;
    }
    auto add_button() -> ButtonBuilder<DialogBuilder>;
    auto build() const -> Dialog { /* ... */ }
};

template <typename Parent>
class ButtonBuilder {
    Parent* parent_;
    std::string label_;
    Callback callback_;
public:
    ButtonBuilder(Parent* p) : parent_(p) {}
    auto set_label(std::string l) -> ButtonBuilder& {
        label_ = std::move(l);
        return *this;
    }
    auto set_callback(Callback cb) -> ButtonBuilder& {
        callback_ = std::move(cb);
        return *this;
    }
    auto end_button() -> Parent& {
        parent_->add_constructed_button({label_, callback_});
        return *parent_;
    }
};
```

The parent returns a temporary sub-builder from `add_button()`, and that sub-builder returns a reference to the parent from `end_button()`. The caller cannot accidentally keep a dangling sub-builder reference because the sub-builder is a temporary in the expression. This pattern is common in GUI libraries, JSON construction APIs, and test fixture builders.

### Trade-offs and Alternatives

The builder pattern trades verbosity for readability and flexibility. Writing the builder class adds lines that must be maintained alongside the target class. The alternatives each have their own balance:

- **Designated initializers (C++20)**: Allow you to name struct members at the call site: `Widget{.width=320, .height=240, .color=Teal}`. This is zero-overhead and requires no builder class. It works only for aggregates, does not support validation, and adding a required field breaks callers silently (the field is simply left defaulted).

- **Named function parameters (simulated with structs)**: Pack parameters into a struct and pass it to the constructor. This gives named arguments but every caller must build the struct, and default values require careful handling.

- **Constructor with default arguments**: Works when the parameter count is small (≤4). Beyond that, the risk of misordering arguments grows rapidly.

- **Separate builder**: The most flexible. Supports validation, complex interdependencies between parameters, hierarchical construction, and immutable target objects (the builder mutates, the target is const after construction). The cost is boilerplate and runtime overhead from the extra indirection, though in practice the compiler inlines the chain to zero overhead in optimized builds.

The builder pattern is overkill for simple objects with three or four constructor parameters that rarely change. It shines when an object takes many parameters (six or more), when many of those parameters are optional, when parameters have logical dependencies, or when the construction itself is a domain concept that should be named and tested independently.

### Exercises

1. Convert a class that takes seven positional constructor parameters into a builder-based API. Show both the builder class and an example chain.

2. Implement a builder for an `HttpRequest` that requires a URL, accepts optional headers (any number), an optional body, and an optional timeout. Enforce that the URL is set before `build()` is called.

3. Write a hierarchical builder that constructs an HTML table: `TableBuilder{} .add_row() .add_cell("Name") .add_cell("Age") .end_row() .build()`. Discuss whether the end_row / end_button pattern is worth the complexity compared to a flat API.

## Singleton Implementations and Alternatives

The Singleton is one of the most controversial patterns in the Gang of Four catalog — widely used and widely reviled in equal measure. Its intent is straightforward: ensure a class has exactly one instance and provide a global point of access to it. In C++, the implementation choices reveal a spectrum of trade-offs between thread safety, initialization cost, lifetime control, and testability.

The core problem the Singleton solves is different from what many assume. It is not about "one instance" — it is about *coordinated access* to a shared resource. A logger, a configuration registry, a hardware driver, or a global clock all need a single point of coordination so that different parts of the program see a consistent view. The Singleton is one way to enforce that coordination, but it is rarely the best way in modern C++.

### Meyer's Singleton

The simplest and most robust C++ Singleton is Scott Meyer's pattern: a function-local `static` variable:

```cpp
class Logger {
public:
    static Logger& instance() {
        static Logger log;
        return log;
    }

    void log(std::string_view msg) {
        std::lock_guard<std::mutex> lock(mutex_);
        // write to file...
    }

private:
    Logger() = default;
    ~Logger() = default;
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;

    std::mutex mutex_;
};
```

The `static` local variable is initialized on the first call to `instance()` and destroyed in reverse order of construction at program exit. Since C++11, the standard guarantees that function-local `static` initialization is thread-safe: if two threads call `instance()` simultaneously, the runtime synchronizes the initialization so that only one thread constructs the object, and all other threads block until construction completes.

This is the recommended Singleton in C++ unless you need fine-grained control over the initialization order or lifetime. It is zero-cost after initialization — the `static` variable is simply a global at a fixed address — and the thread-safe initialization is provided by the runtime with no explicit locking in user code.

### The Destruction Problem

A function-local `static` is destroyed during the static destruction phase, after `main()` returns. If another global object's destructor calls `Logger::instance()` after the Logger has been destroyed, the program crashes. This is the *static destruction order fiasco*.

```cpp
struct Config {
    ~Config() {
        Logger::instance().log("Config destroyed");  // Crash: Logger already destroyed
    }
};

Config global_config;  // Destroyed after Logger because it was constructed before Logger
```

The problem arises because C++ destroys static objects in reverse order of construction, and the construction order across translation units is undefined. A Logger constructed on first use (late) may be destroyed before an object constructed earlier (and thus destroyed later, since destruction is reverse order).

Solutions:
1. **Do not call Singletons from destructors of other globals** — the simplest rule but hard to enforce.
2. **Use a two-phase Singleton** with an explicit `shutdown()` function that destroys the instance before the static destruction phase, ensuring a predictable order.
3. **Use a `std::shared_ptr`-based Singleton with a custom lifetime** that can be reset explicitly.
4. **Accept the risk and document** — in practice, the phase ordering is deterministic within a single translation unit and rarely causes problems in well-structured code.

### Double-Checked Locking (Pre-C++11)

Before C++11 guaranteed thread-safe static initialization, the standard approach to lazy Singleton creation was double-checked locking:

```cpp
class Logger {
public:
    static Logger& instance() {
        if (!instance_) {                         // First check (no lock)
            std::lock_guard<std::mutex> lock(mutex_);
            if (!instance_) {                     // Second check (under lock)
                instance_ = new Logger();
            }
        }
        return *instance_;
    }

private:
    static Logger* volatile instance_;
    static std::mutex mutex_;
};
```

The pattern attempts to avoid the cost of locking on every access by checking the pointer before acquiring the mutex. If the pointer is non-null, the Singleton is already initialized and the mutex is skipped. The second check under the lock prevents multiple threads from creating duplicate instances if they both pass the first check simultaneously.

The `volatile` keyword was intended to prevent the compiler from reordering the assignment of `instance_` before the `Logger` constructor completes. In practice, `volatile` does not prevent hardware reordering on multi-core CPUs, so double-checked locking was not safe on many platforms until C++11 introduced `std::atomic`. The modern equivalent uses `std::atomic`:

```cpp
static std::atomic<Logger*> instance_{nullptr};

static Logger& instance() {
    Logger* log = instance_.load(std::memory_order_acquire);
    if (!log) {
        std::lock_guard<std::mutex> lock(mutex_);
        log = instance_.load(std::memory_order_relaxed);
        if (!log) {
            log = new Logger();
            instance_.store(log, std::memory_order_release);
        }
    }
    return *log;
}
```

The `memory_order_acquire` on the load ensures that subsequent reads of the Logger's data see the initialized state. The `memory_order_release` on the store ensures that the constructor's writes are visible before `instance_` becomes visible to other threads. In modern C++, there is no reason to write double-checked locking yourself — function-local `static` handles it correctly — but understanding the pattern is valuable for maintaining legacy code.

### `std::call_once` and Lazy Construction

A cleaner alternative to manual double-checked locking uses `std::once_flag` and `std::call_once`:

```cpp
class Logger {
public:
    static Logger& instance() {
        std::call_once(flag_, [] {
            instance_ = new Logger();
        });
        return *instance_;
    }

private:
    static Logger* instance_;
    static std::once_flag flag_;
};
```

`std::call_once` guarantees that the initialization lambda executes exactly once, even in the presence of exceptions (if the lambda throws, `call_once` retries on the next invocation — the flag is not considered set). The implementation typically uses a fast path (a single atomic load in the common case) and a slow path (mutex) for the first call, similar to double-checked locking but encapsulated.

This approach gives more control than function-local `static` — you can choose to allocate on the heap, use a custom allocator, or construct the instance with arguments determined at runtime. It is the preferred pattern when you need lazy construction with dynamic parameters.

### The `std::shared_ptr` Singleton with Lifetime Control

For fine-grained control over destruction order, a Singleton backed by `std::shared_ptr` allows explicit reset:

```cpp
class Logger {
public:
    static std::shared_ptr<Logger> instance() {
        std::call_once(flag_, [] {
            instance_ = std::make_shared<Logger>();
        });
        return instance_;
    }

    static void reset() {
        instance_.reset();
    }

private:
    static std::shared_ptr<Logger> instance_;
    static std::once_flag flag_;
};
```

Callers hold a `shared_ptr<Logger>` while using the logger, preventing destruction. The `reset()` function destroys the instance at a known point, before other global destructors run. This eliminates the static destruction order fiasco because the lifetime is explicitly managed.

The cost is that every access involves atomic reference count operations on the `shared_ptr`. For frequently accessed Singletons (like a logger called from every function), this overhead can be significant. A compromise is to return a raw pointer or reference after acquiring the `shared_ptr` once per scope:

```cpp
void process() {
    auto log = Logger::instance();  // Hold the shared_ptr to prevent destruction
    log.log("Processing...");
    log.log("Done.");
}
```

### Problems with Singletons

The Singleton pattern is widely criticized for reasons that go beyond implementation details:

**Global state.** A Singleton is a global variable in disguise. Any part of the program can access it, creating implicit coupling between components that would otherwise be independent. Testing one module requires the Singleton to be in the correct state, which may depend on the order in which previous tests ran.

**Hidden dependencies.** Functions that call `Logger::instance()` internally have a hidden dependency on the Logger. The function's signature does not declare it, so callers cannot see the dependency without reading the implementation. This makes code harder to reason about and refactor.

**Violation of the Single Responsibility Principle.** A Singleton class manages both its own business logic and its own lifecycle (ensuring a single instance). These are two distinct responsibilities.

**Threading complexity.** Even with thread-safe initialization, the Singleton's state must be internally thread-safe if accessed from multiple threads — a requirement that applies regardless of the Singleton pattern.

**Testability.** Tests cannot easily replace a Singleton with a mock or substitute because the type is hard-coded. Techniques like template policy parameters or virtual base classes can mitigate this, but they add complexity that the simple Singleton avoids.

### Alternatives to Singleton

The alternatives replace the "global point of access" with explicit dependency injection or scoped lifetime management.

**Dependency injection (DI).** Instead of a class accessing the Singleton directly, the dependency is passed as a constructor argument or function parameter:

```cpp
class Application {
    Logger& logger_;
    Config& config_;
public:
    Application(Logger& log, Config& cfg)
        : logger_(log), config_(cfg) {}
    // ...
};

auto& log = Logger::instance();  // Still a single instance, but created in main()
auto& cfg = Config::instance();
Application app(log, cfg);       // Dependencies are explicit
```

The instance is still created once (typically in `main()` or at the program's entry point), but the dependency is passed explicitly rather than fetched from a global. This makes the dependency visible in the constructor signature and testable — you can pass a mock Logger in unit tests.

**Monostate pattern.** The Monostate pattern guarantees a single logical state without enforcing a single instance. All instances share the same static data:

```cpp
class MonostateLogger {
public:
    void log(std::string_view msg) {
        std::lock_guard<std::mutex> lock(mutex_);
        // write to file...
    }

private:
    static std::mutex mutex_;
    // All state is static — every instance shares it
};
```

Multiple `MonostateLogger` objects can be created, but they all write to the same log file. The advantage is that the class behaves like a normal class (can be passed by value, stored in containers, etc.) while maintaining a single shared state. The disadvantage is that the shared state is obscured — callers who read the class definition see instance members and may not realize they are sharing the underlying data.

**Context object.** Pass a shared context or environment object through the call chain. This is a structured way to provide shared services without either a Singleton or full dependency injection:

```cpp
struct Context {
    Logger& logger;
    Config& config;
    Database& db;
};

void handle_request(Context& ctx, Request& req) {
    ctx.logger.log("Handling request");
    ctx.db.query(req.query());
}
```

The Context is created once in `main()` and threaded through the call chain. It provides a single place to add or remove global services without changing every function signature when a new service is needed. The drawback is that every function in the chain must accept and forward the Context — a form of explicit plumbing that can be verbose.

**Passkey idiom for controlled construction.** In rare cases where you want to restrict instantiation without using global state, the passkey idiom allows only specific classes to construct the instance:

```cpp
class Logger {
public:
    struct Key { explicit Key() = default; };

    explicit Logger(Key) {}
    // ...
};

class Application {
public:
    Application() : logger_(Logger::Key{}) {}
    Logger& get_logger() { return logger_; }
private:
    Logger logger_;
};
```

Only `Application` can construct a `Logger` because only it can create a `Key` (whose constructor is `explicit` and private to `Logger`'s interface but accessible because `Application` is not explicitly excluded). This enforces a single responsible owner for the Logger without global access.

### When to Use (and Not Use) a Singleton

Use a Singleton when:

- The resource is truly global and genuinely needs one instance (hardware registers, platform-specific managers, interrupt controllers).
- The cost of passing the dependency through every function call is prohibitive, and the dependency is inarguably universal (e.g., a memory allocator in a custom embedded system).
- You are interfacing with a C API that requires a single handle and the Singleton wrapper is the cleanest abstraction.

Do not use a Singleton when:

- The "singleton" is a design convenience rather than a physical necessity — you want one instance now but may need multiple later.
- Testability is a priority — Singletons make tests order-dependent and hard to isolate.
- The dependency is used in a small, localized part of the codebase and can be passed explicitly.

### Exercises

1. Convert a `Configuration` Singleton into a dependency-injected alternative. Show the before and after signatures of three functions that use the configuration.

2. Implement a thread-safe Singleton using `std::call_once` for a `RandomNumberGenerator` that wraps a Mersenne Twister engine. Ensure that the destructor calls a `shutdown()` method to log a message.

3. Compare the performance of Meyer's Singleton, double-checked locking with `std::atomic`, and `std::call_once` by writing a microbenchmark that calls `instance()` 10 million times in a tight loop from a single thread. Explain the differences.

4. Refactor a codebase that uses three different Singletons (Logger, Config, Database) into a single `Context` object that is passed through the call chain. Discuss how the refactoring changes the testability of the system.

## Abstract Factory with Type Lists

The Abstract Factory pattern provides an interface for creating families of related objects without specifying their concrete classes. A GUI toolkit might have an abstract factory that creates buttons, windows, and scrollbars — each product family has a concrete factory per platform (WindowsFactory, MacFactory, LinuxFactory), and the client code uses only the abstract factory interface to remain platform-independent.

The classic implementation is straightforward but verbose:

```cpp
struct Button { virtual ~Button() = default; virtual void draw() = 0; };
struct Window { virtual ~Window() = default; virtual void show() = 0; };
struct Scrollbar { virtual ~Scrollbar() = default; virtual void scroll(int) = 0; };

struct WinButton : Button { void draw() override { /* Windows rendering */ } };
struct WinWindow : Window { void show() override { /* Windows window */ } };
struct WinScrollbar : Scrollbar { void scroll(int) override { /* ... */ } };

struct MacButton : Button { void draw() override { /* Mac rendering */ } };
struct MacWindow : Window { void show() override { /* Mac window */ } };
struct MacScrollbar : Scrollbar { void scroll(int) override { /* ... */ } };

class GUIFactory {
public:
    virtual ~GUIFactory() = default;
    virtual std::unique_ptr<Button> create_button() = 0;
    virtual std::unique_ptr<Window> create_window() = 0;
    virtual std::unique_ptr<Scrollbar> create_scrollbar() = 0;
};

class WinFactory : public GUIFactory {
    std::unique_ptr<Button> create_button() override
        { return std::make_unique<WinButton>(); }
    std::unique_ptr<Window> create_window() override
        { return std::make_unique<WinWindow>(); }
    std::unique_ptr<Scrollbar> create_scrollbar() override
        { return std::make_unique<WinScrollbar>(); }
};

class MacFactory : public GUIFactory {
    std::unique_ptr<Button> create_button() override
        { return std::make_unique<MacButton>(); }
    std::unique_ptr<Window> create_window() override
        { return std::make_unique<MacWindow>(); }
    std::unique_ptr<Scrollbar> create_scrollbar() override
        { return std::make_unique<MacScrollbar>(); }
};
```

Every new product type — `Menu`, `Toolbar`, `Dialog` — requires adding a virtual function to the `GUIFactory` base class and implementing it in every concrete factory. This is the fundamental maintenance burden of the classic Abstract Factory.

### The Type List Approach

A type list is a compile-time sequence of types. The idea, popularized by Andrei Alexandrescu in *Modern C++ Design*, is to encode the product types as a type list and generate the abstract factory interface — and its concrete implementations — automatically through templates, eliminating the repetitive virtual function declarations.

In traditional C++03 style, a type list is a recursive data structure:

```cpp
struct NullType {};

template <typename Head, typename Tail = NullType>
struct TypeList {
    using head = Head;
    using tail = Tail;
};

// Product types encoded as a type list
using GUIOptions = TypeList<Button, TypeList<Window, TypeList<Scrollbar, NullType>>>;
```

The abstract factory interface is generated by a template that iterates over the type list and declares a pure virtual `create()` function for each type:

```cpp
template <typename TList>
class AbstractFactory {
public:
    virtual ~AbstractFactory() = default;

    // Recursively declare create functions for each type in the list
    template <typename T>
    std::unique_ptr<T> create();

    // The recursive declaration happens through specialization
};
```

The implementation relies on a recursive helper template that processes the type list one element at a time, declaring a virtual function for the head and inheriting from the next level of recursion. This generates a base class with one pure virtual `create()` per product type — exactly what the classic pattern requires, but generated by the compiler.

The concrete factory uses similar machinery:

```cpp
template <typename TList, typename ConcreteProduct>
class ConcreteFactory;

// Specialization: for each type in the list, define the creation function
// that returns the appropriate concrete product
```

### Variadic Template Modernization

C++11 variadic templates eliminate the need for the recursive `TypeList` struct and the `NullType` sentinel. The same pattern can be expressed with a parameter pack:

```cpp
template <typename... Products>
class AbstractFactory {
public:
    virtual ~AbstractFactory() = default;

    // One pure virtual create per product type
    virtual std::unique_ptr<Products> create()... = 0;
};
```

The pack expansion `virtual std::unique_ptr<Products> create()... = 0;` expands to one pure virtual function declaration for each type in the parameter pack. This is the compile-time equivalent of the handwritten `GUIFactory` interface above — but it is generated automatically from the type list.

Unfortunately, C++ does not allow pack expansions in virtual function declarations directly. The expansion must happen through a helper base class using either recursive inheritance or a fold expression:

```cpp
template <typename Product>
struct AbstractFactoryUnit {
    virtual ~AbstractFactoryUnit() = default;
    virtual std::unique_ptr<Product> create() = 0;
};

template <typename... Products>
class AbstractFactory : public AbstractFactoryUnit<Products>... {
public:
    ~AbstractFactory() override = default;
    // Inherits create() for each Product via the base class pack
    using AbstractFactoryUnit<Products>::create...;
};
```

The `using ...create;` declaration (C++17) brings all inherited `create()` functions into the derived class's scope, resolving any ambiguity from the multiple base classes. Each `AbstractFactoryUnit<Products>` declares a single pure virtual `create()` that returns `std::unique_ptr<Products>`.

The concrete factory follows the same pattern:

```cpp
template <typename Product, typename ConcreteProduct>
struct ConcreteFactoryUnit : AbstractFactoryUnit<Product> {
    std::unique_ptr<Product> create() override {
        return std::make_unique<ConcreteProduct>();
    }
};

template <typename... Mappings>
class ConcreteFactory : public ConcreteFactoryUnit<Mappings>... {
public:
    using ConcreteFactoryUnit<Mappings>::create...;
};

// Usage:
using Factory = AbstractFactory<Button, Window, Scrollbar>;
using WinFactory = ConcreteFactory<
    Button,   WinButton,
    Window,   WinWindow,
    Scrollbar, WinScrollbar
>;
```

Each `ConcreteFactoryUnit` maps one abstract product type to its concrete implementation. The variadic template `ConcreteFactory` accepts pairs of types — product followed by concrete implementation — and inherits from each unit. The `create()` functions are brought into scope with another `using` declaration.

The caller uses the factory through the abstract interface, exactly as in the classic pattern:

```cpp
void build_ui(Factory& factory) {
    auto btn  = factory.create<Button>();
    auto win  = factory.create<Window>();
    auto scr  = factory.create<Scrollbar>();
    // ... use them polymorphically
}

ConcreteFactory<Button, WinButton, Window, WinWindow, Scrollbar, WinScrollbar> win_factory;
build_ui(win_factory);  // Creates Windows-specific products
```

### Type-Safe Dispatching

A refinement of the variadic approach replaces the polymorphic `create()` return with a more general `create()` that takes a tag type as a template parameter, allowing the factory to be used without dynamic dispatch when the concrete factory type is known at compile time:

```cpp
template <typename Product>
struct FactoryUnit {
    virtual std::unique_ptr<Product> create() = 0;
};

template <typename... Products>
class GenericFactory : public FactoryUnit<Products>... {
public:
    using FactoryUnit<Products>::create...;

    template <typename T>
    std::unique_ptr<T> create() {
        return static_cast<FactoryUnit<T>&>(*this).create();
    }
};
```

The `create<T>()` member template dispatches to the correct base class `create()`, which is either virtual (if used through a base pointer) or resolved statically (if called on the concrete type). This gives the caller a uniform `factory.create<Button>()` syntax regardless of whether the factory is accessed through the abstract interface or the concrete type.

### The Registration-Based Alternative

The type-list approach generates factory interfaces at compile time. An alternative is a registration-based factory that accepts a map from string identifiers (or type-erased keys) to creator functions:

```cpp
class AbstractFactory {
public:
    template <typename T>
    std::unique_ptr<T> create(const std::string& key) {
        auto it = registry_.find(key);
        if (it != registry_.end()) {
            return std::unique_ptr<T>(static_cast<T*>(it->second()));
        }
        throw std::runtime_error("Unknown product: " + key);
    }

    template <typename T>
    bool register_type(const std::string& key, std::unique_ptr<T> (*creator)()) {
        return registry_.emplace(key, [creator]() -> void* {
            return creator().release();
        }).second;
    }

private:
    std::map<std::string, void*(*)()> registry_;
};
```

Registration-based factories are more flexible — new product types can be added at runtime without recompiling the factory — but they sacrifice type safety and performance. The type list approach catches missing product implementations at compile time and generates zero-overhead virtual dispatch.

### Trade-offs

The type-list Abstract Factory trades off:

- **Compile-time safety vs. runtime flexibility.** The type list approach ensures at compile time that every product type has a concrete implementation. Registration-based factories defer this guarantee to runtime, which is both more flexible and more error-prone.
- **Binary size vs. hand-written code.** Each template instantiation generates distinct code. For a factory with 10 product types and 3 platforms, the type-list approach produces 30 `create()` function bodies — the same number as a hand-written implementation, but generated automatically. The difference is in the header: the template version is entirely in headers, which can increase compilation time.
- **Readability vs. genericity.** The variadic template version using `AbstractFactoryUnit<Products>...` is concise and readable once you are familiar with the pattern. The Loki-style recursive type list version is terse but cryptic. Both are harder for newcomers to understand than a hand-written abstract factory with explicit virtual functions.
- **Error messages.** Template metaprogramming errors are notoriously inscrutable. A missing `create()` override in the concrete factory produces a wall of template instantiation backtraces. Concepts (C++20) can improve this by constraining the factory mappings, but the diagnostic quality remains behind that of hand-written virtual functions.

### When to Use

The type-list Abstract Factory is most valuable when:
- The product family is fixed and known at compile time.
- The number of products is large enough that manual virtual function declarations become tedious (typically 5+ products).
- Multiple concrete factories exist for different configurations or platforms.
- The product types are added or removed in lockstep across all factories.

It is not a good fit when:
- The product family changes frequently and the compile-edit-debug cycle for template-heavy code is too slow.
- The team is not comfortable with variadic templates and multiple inheritance from template bases.
- Products need to be registered dynamically (e.g., loaded from plugins at runtime).

### Exercises

1. Implement a type-list based Abstract Factory for a document editor that creates `Paragraph`, `Image`, `Table`, and `Header` objects, with concrete factories for `HtmlDocument` and `PdfDocument`. Use variadic templates.

2. Compare the compilation time and binary size of the type-list factory with a hand-written equivalent for 4 product types and 2 concrete factories. Use `-ftime-trace` (Clang) to measure template instantiation time.

3. Add a `create_or_null()` function to the abstract factory that returns `nullptr` instead of throwing when a product type is not supported by a particular concrete factory (e.g., a `PlainTextFactory` that does not support `Image`). Discuss how this affects the type-list design.

## Object Pool Patterns

Dynamic allocation is expensive. Every call to `new` and `delete` — or their `std::allocator` equivalents — performs a heap walk, possibly a system call, and eventually a free-list coalescing operation. For objects allocated and freed at high frequency (network connections, particle instances, message buffers, thread workers), the overhead of memory management can dominate the actual work the object performs.

An object pool pre-allocates a collection of reusable objects and hands them out on request. Clients borrow an object from the pool, use it, and return it. The pool never deallocates the object individually — it recycles it. This turns O(n) heap operations into amortized O(1) pool operations, at the cost of a fixed memory reservation.

### A Minimal Object Pool

The simplest pool allocates a fixed number of objects up front and tracks which are available with a stack of indices:

```cpp
template <typename T>
class ObjectPool {
public:
    template <typename... Args>
    ObjectPool(size_t capacity, Args&&... args)
        : pool_(capacity)
    {
        for (size_t i = 0; i < capacity; ++i) {
            pool_[i] = std::make_unique<T>(std::forward<Args>(args)...);
            available_.push(i);
        }
    }

    T* acquire() {
        if (available_.empty()) {
            return nullptr;
        }
        size_t index = available_.top();
        available_.pop();
        return pool_[index].get();
    }

    void release(T* obj) {
        // Find the index of the returned object
        auto it = std::find_if(pool_.begin(), pool_.end(),
            [obj](const auto& ptr) { return ptr.get() == obj; });
        if (it != pool_.end()) {
            size_t index = std::distance(pool_.begin(), it);
            available_.push(index);
        }
    }

private:
    std::vector<std::unique_ptr<T>> pool_;
    std::stack<size_t> available_;
};
```

The constructor allocates `capacity` objects using a forwarded argument list — useful when all objects share the same construction parameters (e.g., a buffer size or a socket port). The `acquire()` function pops the next available index, and `release()` pushes it back.

The obvious inefficiency is `release()`: finding the index requires a linear search over all pool entries. For large pools, this O(n) release cost defeats the purpose of pooling.

### Index-Based Release

A better design stores the index inside the object itself, or returns a handle that encodes the index. A common C++ approach embeds an index or an "available next" link directly into the pooled object's memory — an intrusive free list:

```cpp
template <typename T>
class IntrusivePool {
    union Slot {
        T object;
        size_t next_free;
    };

    std::vector<Slot> slots_;
    size_t head_;  // Index of the first free slot

public:
    template <typename... Args>
    IntrusivePool(size_t capacity, Args&&... args)
        : slots_(capacity), head_(0)
    {
        for (size_t i = 0; i < capacity - 1; ++i) {
            slots_[i].next_free = i + 1;
        }
        slots_[capacity - 1].next_free = static_cast<size_t>(-1);  // End marker

        // Construct all objects in-place
        for (size_t i = 0; i < capacity; ++i) {
            new (&slots_[i].object) T(std::forward<Args>(args)...);
        }
    }

    T* acquire() {
        if (head_ == static_cast<size_t>(-1)) {
            return nullptr;
        }
        size_t index = head_;
        head_ = slots_[index].next_free;
        return &slots_[index].object;
    }

    void release(T* obj) {
        Slot* slot = reinterpret_cast<Slot*>(obj);
        size_t index = slot - slots_.data();
        slot->object.~T();                             // Destroy
        slot->next_free = head_; // Set next free (overwrites object memory)
        head_ = index;
    }
};
```

The `union Slot` overlays the object storage and a free-list pointer — they never coexist, so no space is wasted. The free list is a singly linked list threaded through the slots themselves, requiring no external data structure. Release is O(1): given the object pointer, compute its index via pointer arithmetic, destroy and reconstruct the object (or call a reset method), then push the slot back onto the free list.

The destructor-and-reconstruct pattern on release ensures that the object is returned to a pristine default state. If the object has an expensive default constructor, a `reset()` method may be cheaper than full destruction and reconstruction — but the trade-off is that `reset()` must be manually maintained.

### RAII Wrapper for Automatic Release

Pool users should not call `release()` manually. An RAII wrapper ensures that objects are returned to the pool when they go out of scope:

```cpp
template <typename T>
class PoolHandle {
    T* obj_;
    IntrusivePool<T>* pool_;
public:
    PoolHandle(T* obj, IntrusivePool<T>* pool)
        : obj_(obj), pool_(pool) {}

    ~PoolHandle() {
        if (obj_) {
            pool_->release(obj_);
        }
    }

    PoolHandle(PoolHandle&& other) noexcept
        : obj_(std::exchange(other.obj_, nullptr)),
          pool_(other.pool_) {}

    PoolHandle(const PoolHandle&) = delete;
    PoolHandle& operator=(const PoolHandle&) = delete;

    T* operator->() { return obj_; }
    const T* operator->() const { return obj_; }
    T& operator*() { return *obj_; }
    const T& operator*() const { return *obj_; }
};
```

The factory function that acquires from the pool returns a `PoolHandle<T>` instead of a raw pointer:

```cpp
template <typename T>
class IntrusivePool {
public:
    PoolHandle<T> acquire() {
        T* obj = acquire_impl();  // internal acquire
        return PoolHandle<T>{obj, this};
    }
    // ...
};
```

The caller never calls `release()` directly. When the `PoolHandle` goes out of scope — whether by normal exit, early return, or exception — the destructor returns the object to the pool. This eliminates the most common object pool bug: forgetting to release.

### Thread-Safe Pool

The pools above are not thread-safe. For multi-threaded use, each mutating operation (acquire, release) must be synchronized:

```cpp
template <typename T>
class ThreadSafePool {
    std::mutex mutex_;
    std::vector<std::unique_ptr<T>> pool_;
    std::stack<size_t> available_;
public:
    T* acquire() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (available_.empty()) return nullptr;
        size_t index = available_.top();
        available_.pop();
        return pool_[index].get();
    }

    void release(T* obj) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = std::find_if(pool_.begin(), pool_.end(),
            [obj](const auto& ptr) { return ptr.get() == obj; });
        if (it != pool_.end()) {
            available_.push(std::distance(pool_.begin(), it));
        }
    }
};
```

The mutex serializes all pool operations. For high-contention scenarios, a lock-free pool using `std::atomic` and a concurrent free-list can reduce contention, but the implementation is significantly more complex:

```cpp
template <typename T>
class LockFreePool {
    struct Slot {
        T object;
        std::atomic<Slot*> next_free;
    };

    std::vector<Slot> slots_;
    std::atomic<Slot*> head_;

public:
    T* acquire() {
        Slot* old_head = head_.load(std::memory_order_acquire);
        Slot* new_head;
        do {
            if (!old_head) return nullptr;
            new_head = old_head->next_free.load(std::memory_order_relaxed);
        } while (!head_.compare_exchange_weak(old_head, new_head,
                 std::memory_order_acq_rel, std::memory_order_acquire));
        return &old_head->object;
    }

    void release(T* obj) {
        Slot* slot = reinterpret_cast<Slot*>(obj);
        slot->object.~T();
        new (&slot->object) T();

        Slot* old_head = head_.load(std::memory_order_acquire);
        do {
            slot->next_free.store(old_head, std::memory_order_relaxed);
        } while (!head_.compare_exchange_weak(old_head, slot,
                 std::memory_order_acq_rel, std::memory_order_acquire));
    }
};
```

The lock-free pool uses a compare-and-swap (CAS) loop on the head pointer. Each acquire attempts to swing the head to the next free slot; if another thread concurrently acquires, the CAS fails and the loop retries. The ABA problem is avoided here because the head pointer changes address on every pop (or a tagged pointer is used for safety in high-contention environments).

Lock-free pools can outperform mutex-based pools under high contention, but they require careful memory ordering and thorough testing on the target architecture. For most applications, the mutex-based pool — or a per-thread pool (see below) — is the safer choice.

### Growth Strategies

A fixed-size pool rejects acquisitions when empty. This is acceptable when the maximum number of concurrent objects is known and bounded (e.g., a thread pool with a fixed number of workers). In other scenarios, the pool should grow on demand:

```cpp
template <typename T>
class GrowingPool {
    std::vector<std::unique_ptr<T>> pool_;
    std::stack<size_t> available_;
    std::mutex mutex_;

    void grow() {
        size_t old_size = pool_.size();
        size_t new_capacity = pool_.capacity() == 0
            ? 16
            : pool_.capacity() * 2;
        pool_.reserve(new_capacity);

        for (size_t i = old_size; i < new_capacity; ++i) {
            pool_.push_back(std::make_unique<T>());
            available_.push(i);
        }
    }

public:
    T* acquire() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (available_.empty()) {
            grow();
        }
        size_t index = available_.top();
        available_.pop();
        return pool_[index].get();
    }

    void release(T* obj) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = std::find_if(pool_.begin(), pool_.end(),
            [obj](const auto& ptr) { return ptr.get() == obj; });
        if (it != pool_.end()) {
            available_.push(std::distance(pool_.begin(), it));
        }
    }
};
```

The growth factor (here, doubling) is a trade-off. A small growth factor minimizes wasted memory but causes more frequent reallocations and object constructions. A large growth factor wastes memory but reduces the number of growth events. The standard container trade-offs apply.

Shrinking — releasing memory back to the system when the pool is underutilized — is more complex. A shrinking pool tracks usage over time and deallocates excess slots when utilization drops below a threshold. The challenge is distinguishing a temporary dip in demand from a lasting reduction. Most pools in practice do not shrink; they rely on the fact that the peak number of objects is reached quickly and the memory is reused rather than returned.

### Per-Thread Pools

A mutex-protected pool can become a bottleneck when many threads acquire and release objects frequently. An alternative is to give each thread its own local pool:

```cpp
template <typename T>
class ThreadLocalPool {
    static thread_local IntrusivePool<T> local_pool_;

public:
    static PoolHandle<T> acquire() {
        return local_pool_.acquire();
    }
};
```

Each thread holds its own pool and never contends with other threads. The drawback is that objects released on one thread cannot be reused by another thread — in practice, this means the total memory usage is the sum of each thread's peak, not the global peak. Thread-local pools work well when objects are typically acquired and released on the same thread (connection-per-thread, render threads, worker threads with dedicated resources).

### Type-Erased Pools

Sometimes you need a pool that stores objects of different types, or the pooled type is not known until runtime. A type-erased pool stores raw memory blocks and constructs objects in-place using placement new:

```cpp
class GenericPool {
    struct Block {
        void* memory;
        bool available;
    };

    std::vector<Block> blocks_;
    size_t object_size_;
    size_t alignment_;
    std::mutex mutex_;

public:
    GenericPool(size_t capacity, size_t obj_size, size_t align)
        : object_size_(obj_size), alignment_(align)
    {
        for (size_t i = 0; i < capacity; ++i) {
            void* mem = std::aligned_alloc(align, (obj_size + align - 1) & ~(align - 1));
            blocks_.push_back({mem, true});
        }
    }

    ~GenericPool() {
        for (auto& block : blocks_) {
            std::free(block.memory);
        }
    }

    template <typename T, typename... Args>
    T* construct(Args&&... args) {
        static_assert(sizeof(T) <= object_size_);
        static_assert(alignof(T) <= alignment_);

        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& block : blocks_) {
            if (block.available) {
                block.available = false;
                return new (block.memory) T(std::forward<Args>(args)...);
            }
        }
        return nullptr;
    }

    template <typename T>
    void destroy(T* obj) {
        obj->~T();
        for (auto& block : blocks_) {
            if (block.memory == obj) {
                block.available = true;
                return;
            }
        }
    }
};
```

The pool allocates raw memory blocks of sufficient size and alignment for the largest expected type. Callers use `construct<T>()` to create an object in a slot (via placement new) and `destroy<T>()` to call the destructor and mark the slot available. The pool itself never knows the concrete type — only the size and alignment of the storage.

The cost of type erasure is the O(n) linear scan for an available slot and the loss of type safety in the destroy call (the caller must pass the correct type to invoke the right destructor). A tagged slot can store the type's destructor function pointer, but that adds complexity.

### Poolable Object Mixin

An alternative to a separate pool class is an intrusive approach where the object itself knows how to return to its pool. This is common in game engines and real-time systems:

```cpp
template <typename T>
class Poolable {
public:
    void* operator new(size_t) = delete;

    template <typename... Args>
    static T* create(Args&&... args) {
        auto* pool = get_pool();
        T* obj = static_cast<T*>(pool->acquire());
        if (obj) {
            new (obj) T(std::forward<Args>(args)...);
        }
        return obj;
    }

    void destroy() {
        this->~T();
        get_pool()->release(this);
    }

protected:
    static IntrusivePool<T>*& get_pool() {
        static IntrusivePool<T>* pool = nullptr;
        return pool;
    }

public:
    static void init_pool(size_t capacity) {
        get_pool() = new IntrusivePool<T>(capacity);
    }

    static void shutdown_pool() {
        delete get_pool();
        get_pool() = nullptr;
    }
};

// Usage:
struct Particle : Poolable<Particle> {
    float x, y, z;
    float lifetime;
    // ...
};

Particle::init_pool(1024);
Particle* p = Particle::create(0.0f, 0.0f, 0.0f, 1.0f);
// ... use p ...
p->destroy();
Particle::shutdown_pool();
```

The `Poolable<T>` mixin provides static `create()` and `destroy()` methods that wrap acquisition, construction, destruction, and release. The pool itself is stored as a function-local `static` pointer, initialized once via `init_pool()`. This pattern is convenient — the caller does not need to manage a separate pool object — but it couples the class to the pooling mechanism and prevents the use of multiple pools for the same type (e.g., a short-lived and long-lived particle pool).

### When to Pool (and When Not To)

Object pooling is an optimization, and all optimization rules apply: measure first.

Pooling is beneficial when:
- Objects are allocated and freed at very high frequency (thousands per second).
- Each object's construction or destruction is expensive (e.g., opening a database connection, allocating a large buffer).
- Allocation latency must be predictable and low (real-time audio, game loops, trading systems).
- Memory fragmentation from many small allocations is a concern (long-running servers).

Pooling is unnecessary or harmful when:
- Objects are long-lived and allocated infrequently — a pool just wastes memory.
- The maximum number of simultaneous objects is small and unpredictable — the pool either over-allocates (wasting memory) or under-allocates (causing fallback to the heap anyway).
- Objects have variable size or type — a generic pool either wastes space (allocating for the largest type) or requires complex fragmentation management.
- The memory footprint of the application is already a constraint — pools reserve memory that other parts of the system could use.

Even when pooling is appropriate, consider whether a simpler alternative suffices:
- **Stack allocation** — if objects are used in a LIFO pattern, a stack-based allocator is faster than a pool.
- **`std::vector` reuse** — instead of pooling individual elements, resize and clear a vector of objects.
- **`std::pmr::monotonic_buffer_resource`** — the polymorphic memory resource (C++17) provides a fast bump-allocator that can replace pooling for short-lived objects.

### Exercises

1. Implement a pool for `Message` objects (containing a `std::vector<uint8_t>` payload) that reuses the vector's capacity across acquisitions. Measure the allocation savings compared to creating fresh `Message` objects.

2. Extend the intrusive free-list pool with a `reset()` callback that allows the pooled object type to define its own cleanup logic (instead of destroy-and-reconstruct). Compare the performance with the destroy-reconstruct version for a type with an expensive constructor.

3. Build a thread-safe pool that grows exponentially but never shrinks. Add a `shrink_to_fit()` method that releases unused memory. Measure memory usage over a workload that alternates between high and low demand.

4. Implement a two-level pool: a thread-local cache for fast acquire/release, with a global fallback pool for objects that are released on a different thread. Compare its throughput against a single mutex-protected pool for a workload where 90% of acquire/release pairs happen on the same thread.
