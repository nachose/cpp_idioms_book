# Chapter 24: Behavioral Patterns

Behavioral patterns are concerned with how objects distribute responsibilities and communicate with one another. Where structural patterns assemble objects into larger arrangements, behavioral patterns define the protocols and interactions through which those objects cooperate. The four patterns in this chapter—Strategy, Observer, Visitor, and Command—each solve a distinct problem of delegation and communication.

The Strategy pattern lets you define a family of algorithms and make them interchangeable at runtime (or at compile time via templates). The Observer pattern establishes a one-to-many dependency so that when one object changes state, all its dependents are notified. The Visitor pattern lets you add operations to a class hierarchy without modifying the classes themselves—a pattern for separating algorithms from data structures. The Command pattern turns a request into a standalone object, enabling parameterization, queuing, logging, and undoable operations.

What ties them together is a shared theme of indirection around behavior: each pattern introduces an abstraction that allows the *how* of an operation to vary independently from the *what* and the *when*.

## Strategy Pattern Implementation

The Strategy pattern defines a family of interchangeable algorithms, encapsulates each one, and makes them substitutable at a designated point in the code. The core insight is deceptively simple: instead of hard-coding a specific behavior inside a function or class, you extract that behavior behind a consistent interface and inject it from the outside.

This is useful in any situation where an object should support variations of the same operation without itself knowing which variation is in effect. Compression algorithms (gzip vs brotli vs zstd), payment processors (credit card vs PayPal vs crypto), sorting comparators, file-format exporters, and authentication methods are all textbook examples. The object that *uses* the strategy (the *context*) remains the same; only the strategy changes.

The pattern has three participants:

- **Context** — the object that delegates to a strategy. It holds a reference (or pointer) to the current strategy and forwards the relevant calls to it.
- **Strategy** — the interface common to all concrete strategies. It declares the operation(s) that the context can call.
- **Concrete Strategy** — a specific implementation of the strategy interface.

The benefit is that algorithms become independent units: you can add new strategies without changing existing code (open/closed principle), test strategies in isolation, and even swap strategies at runtime. The cost is that each strategy is a separate class or function object, so the pattern introduces indirection and, in the runtime variant, virtual dispatch.

### Classic Runtime Strategy

The classic implementation uses an abstract interface (or a `std::function` signature) and concrete classes that derive from it:

```cpp
// Strategy interface.
class CompressionStrategy {
public:
    virtual ~CompressionStrategy() = default;
    virtual std::vector<char> compress(std::span<const char> data) = 0;
    virtual std::vector<char> decompress(std::span<const char> data) = 0;
};

// Concrete strategy: gzip.
class GzipCompression : public CompressionStrategy {
public:
    std::vector<char> compress(std::span<const char> data) override;
    std::vector<char> decompress(std::span<const char> data) override;
};

// Concrete strategy: Brotli.
class BrotliCompression : public CompressionStrategy {
public:
    std::vector<char> compress(std::span<const char> data) override;
    std::vector<char> decompress(std::span<const char> data) override;
};
```

The context accepts a strategy through its constructor or a setter:

```cpp
class DataWriter {
public:
    explicit DataWriter(std::unique_ptr<CompressionStrategy> strategy)
        : strategy_(std::move(strategy)) {}

    void set_strategy(std::unique_ptr<CompressionStrategy> strategy) {
        strategy_ = std::move(strategy);
    }

    void write(const std::string& path, std::span<const char> data) {
        if (!strategy_) return;
        auto compressed = strategy_->compress(data);
        // write compressed data to file...
    }

private:
    std::unique_ptr<CompressionStrategy> strategy_;
};
```

The context owns the strategy through `unique_ptr`, which makes the relationship clear: the context is the sole owner of the strategy object, and the strategy's lifetime matches the context's. Const references or raw pointers are alternatives when the strategy is shared across multiple contexts or owned externally.

The runtime strategy trades a virtual call per operation for the flexibility to swap algorithms without recompilation. In practice, the virtual call overhead is negligible unless the strategy operation is itself extremely cheap (a single integer addition, for example). If you find yourself measuring strategy dispatch as a bottleneck, the solutions are either to make the strategy operation larger (so the dispatch is amortized) or to switch to the compile-time variant described below.

A design decision that arises frequently is whether the strategy should be stateful. A stateless strategy (like a pure compression algorithm) needs no instance variables and can be a singleton, shared across contexts. A stateful strategy (like a rate-limiter that tracks request timestamps) requires its own instance per context or per group of contexts. The interface should not assume either: document whether concrete strategies must be thread-safe or whether each context gets its own copy.

### std::function-Based Strategy

When the strategy interface consists of a single operation, a full virtual class hierarchy is overkill. A `std::function` (or a function pointer for stateless strategies) gives you the same external substitutability without requiring a derived class for each variant:

```cpp
class DataWriter {
public:
    using CompressionFunc = std::function<std::vector<char>(std::span<const char>)>;

    explicit DataWriter(CompressionFunc compress_fn)
        : compress_fn_(std::move(compress_fn)) {}

    void set_compression(CompressionFunc fn) {
        compress_fn_ = std::move(fn);
    }

    void write(const std::string& path, std::span<const char> data) {
        auto compressed = compress_fn_(data);
        // write compressed data to file...
    }

private:
    CompressionFunc compress_fn_;
};
```

Now the caller does not need to define a class at all for simple cases:

```cpp
DataWriter writer(gzip_compress);
DataWriter writer2([](std::span<const char> data) -> std::vector<char> {
    // inline Brotli compression...
});
```

The `std::function` approach is lighter than the class hierarchy: there is no abstract interface to maintain, no virtual destructor, and no separate compilation unit per strategy. The cost is that `std::function` may perform a small heap allocation for the callable it stores (unless small-buffer optimization kicks in for small stateless lambdas), and the invocation still goes through type erasure, which is roughly as expensive as a virtual call.

Use `std::function` when the strategy is a single function, the number of strategies is small, and you do not need stateful strategies with multiple member functions. Use the classic virtual interface when the strategy exposes several related operations (like `compress` *and* `decompress`) or when the strategy carries significant state that benefits from encapsulation behind a clean interface.

For the narrowest possible API surface, consider a function pointer instead of `std::function`:

```cpp
using CompressionFunc = auto (*)(std::span<const char>) -> std::vector<char>;
```

A function pointer is cheaper than `std::function` (no allocation, no type erasure), but it cannot capture state, so it works only for pure stateless functions. In C++20, you can also use `std::function_ref` (proposed for standardization, available in Abseil and LLVM) for a non-owning, non-allocating callable wrapper that handles lambdas with captures.

### Compile-Time Strategy (Policy-Based)

When the strategy is known at compile time and does not need to change during the program's execution, templates eliminate the indirection entirely. This is the classic *policy-based design* made famous by `std::allocator` and the C++ standard library's containers:

```cpp
template <typename CompressionPolicy>
class DataWriter {
public:
    void write(const std::string& path, std::span<const char> data) {
        auto compressed = CompressionPolicy::compress(data);
        // write compressed data to file...
    }
};

// Policy implementations.
struct GzipPolicy {
    static std::vector<char> compress(std::span<const char> data);
};

struct BrotliPolicy {
    static std::vector<char> compress(std::span<const char> data);
};
```

Usage is:

```cpp
DataWriter<GzipPolicy> gzip_writer;
DataWriter<BrotliPolicy> brotli_writer;
```

The advantage is zero runtime overhead: `DataWriter<GzipPolicy>::write` compiles to a direct call to `GzipPolicy::compress` with no indirection, no virtual dispatch, and no type erasure. The compiler can inline the entire compression pipeline if it chooses.

The drawback is that the strategy is now part of the context's type. You cannot put `DataWriter<GzipPolicy>` and `DataWriter<BrotliPolicy>` into the same container, pass them to the same function without making that function a template, or switch strategies at runtime. Each combination of context and policy is a separate type.

This makes the template approach ideal for:

- **Embedded and real-time systems** where dispatch overhead is unacceptable.
- **Library code** where the user chooses the policy and the library provides the skeleton.
- **Hot paths** where the strategy is called millions of times per second.

It is a poor fit when the strategy depends on runtime configuration (a user-selected compression level, a config-file setting) or when you need to iterate over a collection of contexts that use different strategies.

### Stateful Strategies and Strategy Lifecycle

A subtle point that arises in real code is whether the context creates its own strategy or receives one from the outside. The classic pattern (constructor injection) assumes the caller provides the strategy. An alternative is a *strategy factory* — the context requests a strategy based on a parameter:

```cpp
class DataWriter {
public:
    enum class Compression { Gzip, Brotli, Zstd };

    explicit DataWriter(Compression type) {
        switch (type) {
        case Compression::Gzip:
            strategy_ = std::make_unique<GzipCompression>();
            break;
        case Compression::Brotli:
            strategy_ = std::make_unique<BrotliCompression>();
            break;
        case Compression::Zstd:
            strategy_ = std::make_unique<ZstdCompression>();
            break;
        }
    }
    // ...
};
```

This variant re-introduces a hard dependency on every concrete strategy within the context, violating the open/closed principle — adding a new strategy requires modifying the switch. It is useful only when the set of strategies is truly fixed and known in advance (rare in practice). Prefer constructor injection and push the decision to the caller.

### Comparison and Decision Framework

Classic virtual Strategy (interface + derived classes) is the default choice when strategies have multiple related operations, carry state, or need to be swapped at runtime. The overhead is one virtual call per operation, and the cost is one class per strategy.

`std::function`-based strategy is lighter for single-operation strategies and when callers benefit from inline lambda definitions. The type erasure cost is similar to a virtual call, and small strategies may allocate on the heap.

Template-based strategy is zero-overhead and ideal for compile-time-known policies. It is the right choice in performance-critical paths and in library code, but it bakes the strategy into the type, preventing runtime polymorphism.

| Approach              | Runtime swap | Type per strategy | Overhead       | Use case                |
|-----------------------|-------------|-------------------|----------------|-------------------------|
| Virtual interface     | Yes         | One class         | Virtual call   | Multi-op, stateful      |
| `std::function`       | Yes         | None needed       | Type erasure   | Single-op, simple       |
| Template (policy)     | No          | New type          | Zero           | Hot path, known at build|

### Exercises

1. Implement a validator strategy for user input. Start with a virtual interface `Validator` with a single `bool validate(const std::string& input)` method. Implement `NotEmptyValidator`, `LengthRangeValidator`, and `EmailFormatValidator`. Compose them into a composite validator that runs all strategies in sequence.

2. Refactor the validator exercise to use `std::function<bool(const std::string&)>` instead of the virtual interface. What changes in how you compose validators? What do you lose?

3. Implement a compile-time sorting policy for a small container class. The policy should determine whether the sort is ascending or descending. Measure (or reason about) the codegen difference compared to a runtime `std::function<bool(int, int)>` comparator.

4. A logging system needs to support different output targets: console, file, and network socket. The log level (info, warning, error) should be configurable per target. Design a strategy-based logger. Would you use a virtual interface, `std::function`, or templates? Justify your choice.

## Observer with Type Safety

The Observer pattern establishes a one-to-many dependency between objects so that when one object (the *subject*) changes state, all its dependents (the *observers*) are notified automatically. It is the foundation of event-driven programming, UI frameworks, messaging systems, and reactive architectures.

The pattern has two key participants:

- **Subject** — maintains a list of observers and provides methods to attach, detach, and notify them. The subject does not know the concrete type of its observers; it only knows that they implement a notification callback.
- **Observer** — defines the interface that subjects call when a state change occurs.

The classic Gang of Four formulation was a virtual interface with an `update()` method. But this design has long been criticized for being type-unsafe (the subject pushes a single generic payload, often a bare `void*`), for imposing a rigid interface on observers, and for providing no help with the lifetime problem — what happens when an observer is destroyed before the subject that holds a reference to it?

This section explores how to address these shortcomings in modern C++, building toward type-safe, self-cleaning observer systems.

### The Classic Observer and Its Problems

The traditional Observer interface looks like this:

```cpp
class Observer {
public:
    virtual ~Observer() = default;
    virtual void update(Subject* subject, void* extra) = 0;
};
```

Observers register themselves with a subject:

```cpp
class Subject {
public:
    void attach(Observer* obs) { observers_.push_back(obs); }
    void detach(Observer* obs) { /* linear search and remove */ }

protected:
    void notify() {
        for (auto* obs : observers_) {
            obs->update(this, nullptr);
        }
    }

private:
    std::vector<Observer*> observers_;
};
```

Concrete observers inherit from `Observer` and implement `update`. When the subject changes, it calls `notify`, which iterates over all registered observers and invokes their `update` method.

This design has three well-known problems:

1. **Type safety.** The `void* extra` parameter is a raw escape hatch. The subject and observer must agree out of band on what type the extra data actually is — an enum, a struct pointer, or something else. A mismatch causes undefined behavior at runtime. Some variants solve this by templating the Observer on the payload type, but that makes it impossible to store heterogeneous observers in a single list.

2. **Rigid interface.** Every observer must inherit from `Observer` and name its method `update`. This forces a base-class dependency on all observing code, even when the observer's reaction is trivial (a single lambda) or when the observer already has its own interface and cannot inherit a second base class without introducing diamond inheritance.

3. **Lifetime management.** The subject stores raw pointers to observers. If an observer is destroyed without first calling `detach`, the subject holds a dangling pointer and the next notification triggers undefined behavior. The pattern as originally described puts the burden of correct detach on the programmer — a fragile arrangement in any non-trivial codebase.

Modern C++ mitigates each of these problems. The solutions form a progression: from type-safe interfaces via templates, through flexible callbacks via `std::function`, to automatic lifetime management via `weak_ptr` and connection objects.

### Type-Safe Observer with Templates

The simplest improvement is to template the observer interface on the payload type, eliminating the `void*` cast:

```cpp
template <typename Event>
class Observer {
public:
    virtual ~Observer() = default;
    virtual void on_event(const Event& event) = 0;
};

template <typename Event>
class Subject {
public:
    void attach(Observer<Event>* obs) { observers_.push_back(obs); }
    void detach(Observer<Event>* obs) { /* remove */ }

protected:
    void notify(const Event& event) {
        for (auto* obs : observers_) {
            obs->on_event(event);
        }
    }

private:
    std::vector<Observer<Event>*> observers_;
};
```

Now each subject-observation relationship is statically typed. A `Subject<KeyPress>` only accepts `Observer<KeyPress>` observers, and the notification delivers a `const KeyPress&` instead of a `void*`. The compiler catches type mismatches.

But this is still an intrusive design: the observer must inherit from `Observer<Event>` and implement `on_event`. Heterogeneous observers that want to listen to multiple event types now face diamond inheritance (observing both `KeyPress` and `MouseClick` requires inheriting from `Observer<KeyPress>` *and* `Observer<MouseClick>`, which in turn requires the subject to store multiple observer lists, one per event type).

One solution is the *multi-method observer* — a single observer interface with overloaded `on_event` for each event type it cares about:

```cpp
template <typename... Events>
class MultiObserver : public Observer<Events>... {
public:
    using Observer<Events>::on_event...;
};
```

But this is complex to implement and still requires inheritance. The next step removes the inheritance requirement entirely.

### Callback-Based Observer with std::function

If the only thing the subject needs from an observer is a callable, then the observer *interface* is unnecessary. A subject can store `std::function` objects directly:

```cpp
template <typename Event>
class Subject {
public:
    using Callback = std::function<void(const Event&)>;

    std::size_t connect(Callback cb) {
        callbacks_.push_back(std::move(cb));
        return callbacks_.size() - 1;  // simple numeric id
    }

    void disconnect(std::size_t id) {
        // mark or remove callback by id
    }

    void notify(const Event& event) {
        for (auto& cb : callbacks_) {
            if (cb) cb(event);
        }
    }

private:
    std::vector<Callback> callbacks_;
};
```

Now any callable — a free function, a lambda, a `bind` expression, or a member function wrapped in a lambda — can observe the subject:

```cpp
Subject<KeyPress> key_subject;

key_subject.connect([](const KeyPress& k) {
    std::cout << "Key pressed: " << k.code << "\n";
});

SomeWidget widget;
key_subject.connect([&widget](const KeyPress& k) {
    widget.on_key(k);
});
```

No base class. No virtual inheritance. No `void*`. The subject is a template, so each event type gets a fully type-safe subject.

The `std::function` approach solves the rigid-interface problem completely: any callable with the right signature can be an observer, whether it is a lambda, a function object, or a `std::bind` expression. It does not, however, solve the lifetime problem. If `widget` is destroyed before the subject, the lambda inside the callback captures a dangling reference, and the next notification will use-after-free. The solution is to make the connection self-cleaning.

### Lifetime Management and Connection Objects

The lifetime problem boils down to a simple question: who is responsible for disconnecting an observer before the observer dies? The answer is that the observer itself cannot be — the observer may not even know it is registered. The subject cannot be either — the subject does not know when observers die. The solution is a *connection object* that both sides hold, and that automatically severs the registration when either end is destroyed.

The technique uses `std::shared_ptr` for the subject's callback storage and `std::weak_ptr` for the observer's connection handle. Here is the core idea:

```cpp
template <typename Event>
class Subject {
public:
    using Callback = std::function<void(const Event&)>;

    // A handle that both the subject and observer can hold.
    struct Connection {
        std::shared_ptr<bool> alive;  // shared flag

        Connection() : alive(std::make_shared<bool>(true)) {}
        bool connected() const { return alive && *alive; }
        void disconnect() { if (alive) *alive = false; }
    };

    Connection connect(Callback cb) {
        auto conn = Connection();
        callbacks_.push_back({conn.alive, std::move(cb)});
        return conn;
    }

    void notify(const Event& event) {
        for (auto& [alive, cb] : callbacks_) {
            if (alive && *alive && cb) {
                cb(event);
            }
        }
        // Optional: garbage-collect disconnected entries.
        std::erase_if(callbacks_, [](const auto& entry) {
            return !*entry.alive;
        });
    }

private:
    std::vector<std::pair<std::shared_ptr<bool>, Callback>> callbacks_;
};
```

The observer keeps a `Connection` object. When the observer is destroyed, the `Connection` goes with it, which means the `shared_ptr<bool>` reference count drops to zero, the `bool` is freed, and `*entry.alive` evaluates to `false`. The subject's `notify` skips that entry.

A slightly more robust approach ties the connection lifetime to the observer's lifetime by making the `Connection` hold a `weak_ptr` to the observer's control block:

```cpp
template <typename Observer>
struct WeakConnection {
    std::weak_ptr<Observer> observer;
    std::function<void(Observer&)> notify_fn;

    void notify_if_alive(/*...*/) {
        if (auto obs = observer.lock()) {
            notify_fn(*obs);
        }
    }
};
```

Here, the subject stores `weak_ptr<Observer>` instead of a raw callback. When the observer is destroyed, the `weak_ptr` expires, `lock()` returns null, and the subject skips the notification. This pattern is common in signal-slot libraries like Boost.Signals2.

The trade-off is an extra level of indirection and a heap allocation per connection (for the shared state or the weak_ptr control block). For event streams that fire thousands of times per second, this overhead may matter. In practice, most observer relationships are established once and fire infrequently (UI events, configuration changes, lifecycle hooks), so the cost is negligible.

### Signal-Slot Implementations

The signal-slot pattern is the Observer pattern under a different name, popularized by Qt and formalized in libraries like Boost.Signals2. A *signal* is a subject that can be called like a function, and a *slot* is any callable connected to the signal:

```cpp
Signal<int, std::string> signal;

auto conn = signal.connect([](int id, const std::string& name) {
    std::cout << id << ": " << name << "\n";
});

signal.emit(1, "hello");  // invokes all connected slots
conn.disconnect();        // remove this slot
```

Implementing a simple signal type in C++ is a good exercise in variadic templates and type erasure:

```cpp
template <typename... Args>
class Signal {
public:
    using Callback = std::function<void(Args...)>;
    using Connection = size_t;

    Connection connect(Callback cb) {
        slots_.push_back(std::move(cb));
        return next_id_++;
    }

    void disconnect(Connection id) {
        // Mark slot for removal (shown later)
    }

    void emit(Args... args) {
        for (auto& slot : slots_) {
            if (slot) slot(args...);
        }
    }

private:
    std::vector<Callback> slots_;
    size_t next_id_ = 0;
};
```

The variadic `Signal` template accepts any number of argument types, making it fully type-safe. The subject is the signal itself; observers are slots connected via `connect`. The `emit` call notifies all connected slots.

In real code, you would add:

- **Return value aggregation** — allow slots to return a value and collect results (e.g., `std::vector<R>` from a `Signal<R(Args...)>`).
- **Slot ordering** — slots connected with high priority fire before low-priority ones.
- **Scoped connections** — a `ScopedConnection` that disconnects in its destructor, so the observer simply holds a `ScopedConnection` member and cleanup is automatic.
- **Thread safety** — a mutex around the slots vector so that `connect`, `disconnect`, and `emit` can be called from different threads.

A `ScopedConnection` is straightforward and eliminates the most common lifetime bug:

```cpp
class ScopedConnection {
public:
    ScopedConnection() = default;

    ScopedConnection(std::function<void()> disconnect_fn)
        : disconnect_(std::move(disconnect_fn)) {}

    ~ScopedConnection() {
        if (disconnect_) disconnect_();
    }

    ScopedConnection(ScopedConnection&&) = default;
    ScopedConnection& operator=(ScopedConnection&&) = default;

    // No copy — a connection belongs to one owner.
    ScopedConnection(const ScopedConnection&) = delete;
    ScopedConnection& operator=(const ScopedConnection&) = delete;

    void disconnect() {
        if (disconnect_) disconnect_();
        disconnect_ = nullptr;
    }

private:
    std::function<void()> disconnect_;
};
```

The observer stores a `ScopedConnection` for each signal it listens to. When the observer is destroyed, each `ScopedConnection` destructor fires and automatically disconnects the slot from the signal. No manual `detach` calls, no dangling pointers.

### Thread Safety Considerations

Observer systems are notoriously tricky in multithreaded environments. A notification may fire on thread A while observer state is being modified on thread B. Three strategies help:

1. **Thread-agnostic design** — make the event data immutable (or at least copyable) and guarantee that observers do not mutate shared state during notification. This is the ideal approach and works for the majority of cases.

2. **Mutex per subject** — protect the slot list with a mutex so that `connect`, `disconnect`, and `emit` are serialized. The downside is that `emit` may block while a slot is being added or removed, and if a slot tries to connect to the same signal during notification (re-entrancy), you get a deadlock (or need a recursive mutex).

3. **Reader-writer lock** — use `std::shared_mutex` so that multiple `emit` calls can proceed concurrently but `connect`/`disconnect` serialize with exclusive access. This helps when emits are frequent and mutations are rare.

A re-entrancy-safe approach uses a *deferred mutation queue*: `connect` and `disconnect` during `emit` are not applied immediately but collected in a pending list and flushed after the notification loop completes. This avoids deadlocks and iterator invalidation without requiring a recursive mutex.

### Comparison and Decision Framework

| Approach                     | Type-safe | No base class | Auto cleanup | Overhead             |
|------------------------------|-----------|---------------|--------------|----------------------|
| Classic virtual Observer     | No        | No            | No           | Virtual call         |
| Templated Observer           | Yes       | No            | No           | Virtual call         |
| `std::function` subject      | Yes       | Yes           | No           | Type erasure         |
| Signal with Connection       | Yes       | Yes           | Yes          | Shared ptr + virtual |
| Weak-ptr observer            | Yes       | No            | Yes          | Weak ptr lock        |

The classic virtual Observer is still useful in embedded or legacy C++98 codebases but should be avoided in new code. The templated Observer improves type safety but still imposes a base class.

For most modern C++ code, the `std::function` subject coupled with `ScopedConnection` (or a similar RAII handle) offers the best balance of type safety, flexibility, and safety. The combination requires no base class, supports any callable as an observer, and automatically disconnects when the observer dies.

If you need higher performance — for example, a signal that fires millions of times per second in a real-time audio callback — consider a lock-free ring-buffer approach where the subject pushes events to a queue and observers pull from their own queue in their own thread. This is more complex but avoids all shared-state contention.

### Exercises

1. Implement a minimal `Signal<void(int)>` class with `connect`, `disconnect`, and `emit`. Add `ScopedConnection` support. Verify that destroying a `ScopedConnection` removes the slot.

2. Extend your signal to support return-value aggregation. If multiple slots return a `bool`, should the signal stop on the first `false`? Provide both "all must succeed" and "stop on first failure" modes.

3. Implement a `WeakSignal` that stores `std::weak_ptr` to observers instead of raw callbacks. The observer must inherit from `std::enable_shared_from_this` and register via `shared_from_this()`. Compare the API ergonomics with the `ScopedConnection` approach.

4. A configuration system needs to notify components when a key-value pair changes. Design a type-safe observer system where different keys have different value types (e.g., `"timeout"` is an `int`, `"name"` is a `std::string`). How would you register observers for specific keys and specific types without resorting to `std::any` or `void*`?

## Visitor Pattern with Double Dispatch

The Visitor pattern lets you add new operations to a class hierarchy without modifying the classes in that hierarchy. It answers a specific need: you have a stable set of types (an abstract syntax tree, a document model, a geometry representation) and a growing set of operations you want to perform on those types (serialization, validation, code generation, pretty-printing). The pattern separates the algorithm from the data structure it operates on.

The pattern has two participants:

- **Element** — a base class in a hierarchy that defines an `accept` method. Each concrete element implements `accept` by calling the appropriate `visit` overload on the visitor.
- **Visitor** — an abstract interface with a `visit` overload for each concrete element type. Each overload implements the operation for that specific type.

The trick that makes this work is *double dispatch*: the operation is selected by both the element's dynamic type and the visitor's dynamic type. Single dispatch (ordinary virtual functions) selects the method based on only one dynamic type — the object the method is called on. Double dispatch needs a second dimension, which the `accept`/`visit` pair provides.

### The Problem: Single Dispatch Is Not Enough

Consider a document model with paragraphs, headings, and images. If you wanted to export to HTML, you might write:

```cpp
class Node {
public:
    virtual ~Node() = default;
    virtual std::string to_html() const = 0;
};
```

Each concrete node implements `to_html` differently. This works — until you need a second format (Markdown, LaTeX, plain text). Every new format requires adding a new virtual function to every node class, which means modifying every class in the hierarchy. The format operations cross-cut the hierarchy; they do not belong in any single class.

Visitor solves this by moving the operations out of the nodes and into separate visitor classes. The nodes expose only a single virtual function — `accept` — whose sole purpose is to re-dispatch the call to the correct visitor overload.

### Classic GoF Visitor

The classic implementation uses a visitor interface with one `visit` overload per concrete element:

```cpp
// Forward declarations.
class Paragraph;
class Heading;
class Image;

class Visitor {
public:
    virtual ~Visitor() = default;
    virtual void visit(const Paragraph& elem) = 0;
    virtual void visit(const Heading& elem) = 0;
    virtual void visit(const Image& elem) = 0;
};
```

Each element class declares an `accept` method that takes a `Visitor&` and calls the correct `visit` overload:

```cpp
class Element {
public:
    virtual ~Element() = default;
    virtual void accept(Visitor& v) const = 0;
};

class Paragraph : public Element {
public:
    void accept(Visitor& v) const override {
        v.visit(*this);  // calls Visitor::visit(const Paragraph&)
    }
};

class Heading : public Element {
public:
    void accept(Visitor& v) const override {
        v.visit(*this);  // calls Visitor::visit(const Heading&)
    }
};
```

Now a concrete visitor implements the operation for each type:

```cpp
class HtmlExporter : public Visitor {
public:
    void visit(const Paragraph& elem) override {
        result_ += "<p>" + elem.text() + "</p>\n";
    }
    void visit(const Heading& elem) override {
        result_ += "<h" + std::to_string(elem.level()) + ">"
                 + elem.text() + "</h" + std::to_string(elem.level()) + ">\n";
    }
    void visit(const Image& elem) override {
        result_ += "<img src=\"" + elem.src() + "\" />\n";
    }

    std::string result() const { return result_; }

private:
    std::string result_;
};
```

To export a document, the client iterates over elements and calls `accept`:

```cpp
void export_to_html(const std::vector<std::unique_ptr<Element>>& doc) {
    HtmlExporter exporter;
    for (const auto& elem : doc) {
        elem->accept(exporter);
    }
    std::cout << exporter.result();
}
```

Double dispatch happens in two steps:

1. `elem->accept(exporter)` — first dispatch: the element's virtual table selects the correct `accept` override (`Paragraph::accept`, `Heading::accept`, etc.).
2. Inside `accept`, `v.visit(*this)` — second dispatch: the visitor's virtual table selects the correct `visit` overload for the element type.

The result is that the operation varies along two axes — the element type and the visitor type — using only single-dispatch virtual functions. No language support for multiple dispatch is needed.

### The Cyclic Dependency Problem

The classic Visitor has a well-known weakness: the visitor interface must declare one `visit` overload for every concrete element type. This creates a cyclic dependency between the element hierarchy and the visitor:

- The element hierarchy must know the visitor interface (it calls `visit` in `accept`).
- The visitor interface must know every concrete element type (it declares a `visit` for each one).

Adding a new concrete element type (say, `CodeBlock`) requires:

1. Adding a `visit(const CodeBlock&)` pure virtual function to the `Visitor` base class.
2. Implementing `visit` in every single concrete visitor — including visitors that may have nothing meaningful to do with `CodeBlock`.

This violates the open/closed principle in its own way: the visitor interface is closed against adding new element types. The pattern works well when the element hierarchy is stable and the operations are what change. It works poorly when element types are added frequently, because every visitor in the system must be updated.

### Acyclic Visitor

The Acyclic Visitor breaks the cyclic dependency by using `dynamic_cast` instead of a monolithic visitor interface. Instead of one visitor base with a `visit` overload for every type, each element type defines its own narrow visitor interface:

```cpp
class ParagraphVisitor {
public:
    virtual ~ParagraphVisitor() = default;
    virtual void visit(const Paragraph& elem) = 0;
};

class HeadingVisitor {
public:
    virtual ~HeadingVisitor() = default;
    virtual void visit(const Heading& elem) = 0;
};

class ImageVisitor {
public:
    virtual ~ImageVisitor() = default;
    virtual void visit(const Image& elem) = 0;
};
```

A concrete visitor inherits from the interfaces it supports:

```cpp
class HtmlExporter : public ParagraphVisitor,
                     public HeadingVisitor,
                     public ImageVisitor {
public:
    void visit(const Paragraph& elem) override { /* HTML for paragraph */ }
    void visit(const Heading& elem) override   { /* HTML for heading */ }
    void visit(const Image& elem) override     { /* HTML for image */ }
};
```

The element's `accept` uses `dynamic_cast` to discover whether the visitor supports this element type:

```cpp
class Paragraph : public Element {
public:
    void accept(Visitor& v) const override {
        if (auto* pv = dynamic_cast<ParagraphVisitor*>(&v)) {
            pv->visit(*this);
        }
        // If the visitor does not implement ParagraphVisitor, the
        // dynamic_cast returns null and we silently skip the element.
    }
};
```

Now adding a new `CodeBlock` element requires:

1. Defining a `CodeBlockVisitor` interface with a single `visit(const CodeBlock&)` method.
2. Inheriting from `CodeBlockVisitor` only in those visitors that care about code blocks.
3. No changes to existing visitors.

The trade-off is that `accept` now performs a `dynamic_cast` per element, which is slower than a virtual call. In hierarchies with tens of types and frequent visitation, the cost of `dynamic_cast` (which walks the RTTI graph) can become measurable. The Acyclic Visitor also makes no guarantee that every element is handled — a visitor that omits an element type will silently skip it, which may or may not be the desired behavior.

Use the Acyclic Visitor when the element hierarchy changes frequently and you cannot afford to update every visitor. Use the classic cyclic Visitor when the hierarchy is fixed and performance matters.

### Variant-Based Visitation

If you control the element type entirely and do not need an open class hierarchy, `std::variant` provides a built-in visitation mechanism that is faster and simpler than the object-oriented Visitor:

```cpp
struct Paragraph { std::string text; };
struct Heading   { int level; std::string text; };
struct Image     { std::string src; std::string alt; };

using DocumentNode = std::variant<Paragraph, Heading, Image>;
```

Visiting a variant uses `std::visit` with a callable that has an overload for each alternative:

```cpp
struct HtmlExporter {
    std::string result;

    void operator()(const Paragraph& elem) {
        result += "<p>" + elem.text + "</p>\n";
    }
    void operator()(const Heading& elem) {
        result += "<h" + std::to_string(elem.level) + ">"
               + elem.text + "</h" + std::to_string(elem.level) + ">\n";
    }
    void operator()(const Image& elem) {
        result += "<img src=\"" + elem.src + "\" />\n";
    }
};

std::vector<DocumentNode> doc = { Paragraph{"hello"}, Heading{1, "title"} };
HtmlExporter exporter;
for (const auto& node : doc) {
    std::visit(exporter, node);
}
```

`std::visit` uses a jump table indexed by the variant's discriminator, which is faster than a virtual call or a `dynamic_cast`. The compiler generates a flat array of function pointers and indexes into it directly — no vtable lookup, no RTTI traversal.

The variant approach has three key differences from the object-oriented Visitor:

1. **Closed set of types.** The variant's alternatives are fixed at compile time. You cannot add a `CodeBlock` type without modifying the `std::variant` definition. This is the inverse trade-off from the OO Visitor: where the classic Visitor makes operations open but types closed, the variant makes types closed but operations open.

2. **No inheritance.** The element types are plain structs or classes with no virtual functions, no base class, and no `accept` method. This simplifies the data model and eliminates vtable overhead for the elements themselves.

3. **Exhaustiveness checking.** The compiler can warn when a visitor does not handle all alternatives (with `if constexpr` and variadic lambdas, or by returning a type from each overload). The classic Visitor has no equivalent — a visitor that forgets to implement a `visit` overload will fail at link time (pure virtual call) or compile time (if the base class declares it pure virtual), but only if the function is actually called.

A common pattern with large variant types is a *generic lambda fallback* that handles every alternative uniformly, with specific overloads for the few types that need special treatment:

```cpp
auto visitor = [](const auto& node) {
    // Default: skip this node.
} | [](const Paragraph& p) {
    // Handle paragraph specifically.
} | [](const Heading& h) {
    // Handle heading specifically.
};
```

This depends on the deducing-this or overloaded-lambda pattern (available via a helper struct that chains `operator()` overloads with `using` declarations), which is straightforward to implement and is widely used in C++17 and later codebases.

### When to Use Visitor vs Alternatives

The Visitor pattern occupies a specific niche: you have a class hierarchy, you want to keep operations out of those classes, and the set of classes is more stable than the set of operations. Within that niche:

- **Classic cyclic Visitor** — when performance matters and the element types are truly fixed (e.g., Clang's AST, where new node types are added only in major releases, and every AST visitor should handle every node type). The cost is one virtual call per element dispatch.

- **Acyclic Visitor** — when element types grow over time and visitors should opt in to the types they handle. The cost is one `dynamic_cast` per dispatch. Useful in plugin systems or extensible frameworks.

- **`std::variant` + `std::visit`** — when you control the type set and do not need an open hierarchy. The cost is a jump-table index (essentially free). This is the preferred approach in new code that does not require runtime type extensibility.

- **Virtual functions directly on elements** — when the number of operations is small and stable, and adding a virtual function is simpler than maintaining a separate visitor hierarchy. This is the right choice for the majority of cases; Visitor is a solution to a specific structural tension, not a default pattern.

The decision framework:

| Approach              | Open types | Open ops | Dispatch cost      | Type safety    |
|-----------------------|------------|----------|--------------------|----------------|
| Virtual function      | Yes        | No       | Virtual call       | Static         |
| Classic Visitor       | No         | Yes      | Virtual call × 2   | Static         |
| Acyclic Visitor       | Yes        | Yes      | dyncast + vcall    | Runtime        |
| `std::visit`          | No         | Yes      | Jump table index   | Static + exhaust|

The column "Open types" means whether you can add a new element type without modifying existing code. The column "Open ops" means whether you can add a new operation without modifying existing element classes.

### Exercises

1. Implement a classic Visitor for a geometry hierarchy: `Circle`, `Rectangle`, `Triangle`. Write visitors for area calculation and bounding-box computation. How many lines of code does adding a `Polygon` type require? How many lines does adding a `to_svg` visitor require?

2. Refactor the geometry visitor to the Acyclic Visitor. Measure (or reason about) the performance difference using `dynamic_cast` vs virtual calls. Under what conditions would the Acyclic Visitor be the better choice?

3. Represent the same geometry types as a `std::variant<Circle, Rectangle, Triangle>`. Implement `area` and `bounding_box` using `std::visit`. Compare the code size and the compiler's ability to inline across the dispatch boundary. What happens when you add `Polygon` to the variant — does the compiler catch every visitor that needs updating?

4. Clang's AST uses the classic cyclic Visitor pattern. Read the Clang `RecursiveASTVisitor` source (it is open source). Why does Clang choose the cyclic Visitor despite the large number of node types? What mechanism does it use to avoid forcing every visitor to implement every `visit` overload?

## Command Pattern with Type Erasure

The Command pattern turns a request into a standalone object. Instead of invoking an operation directly, you package everything needed to perform that operation — the function to call, the arguments to pass, the object to call it on — into a command object with a uniform interface (typically `execute`). This indirection enables a set of capabilities that direct invocation cannot: you can parameterize clients with different commands, queue commands for later execution, log them, serialize them, compose them into macros, or reverse them with an `undo` operation.

The pattern has four participants:

- **Command** — the interface that declares `execute` (and optionally `undo`). All concrete commands share this interface.
- **Concrete Command** — implements the command interface by binding an action to a receiver. It stores whatever state is needed to perform (and reverse) the action.
- **Receiver** — the object that knows how to actually perform the operation. The command delegates to it.
- **Invoker** — the object that triggers the command. It knows only the Command interface, not the concrete command type.

In C++, the pattern is closely tied to *type erasure*: the invoker should not know what the command does or what types it involves. It only knows that the command has an `execute` method (and optionally an `undo` method). Type erasure is the mechanism that makes this possible, and C++ offers several approaches with different trade-offs.

### Classic Command with Virtual Dispatch

The textbook implementation uses an abstract base class:

```cpp
class Command {
public:
    virtual ~Command() = default;
    virtual void execute() = 0;
    virtual void undo() = 0;
};
```

Concrete commands capture a receiver and arguments:

```cpp
class BlurCommand : public Command {
public:
    BlurCommand(Image& image, double radius)
        : image_(&image), radius_(radius) {}

    void execute() override {
        original_ = *image_;  // save for undo
        image_->apply_blur(radius_);
    }

    void undo() override {
        *image_ = std::move(original_);
    }

private:
    Image* image_;
    double radius_;
    Image original_;  // snapshot for undo
};
```

The invoker operates on the `Command` interface:

```cpp
class CommandQueue {
public:
    void push(std::unique_ptr<Command> cmd) {
        cmd->execute();
        history_.push_back(std::move(cmd));
    }

    void undo() {
        if (!history_.empty()) {
            history_.back()->undo();
            history_.pop_back();
        }
    }

private:
    std::vector<std::unique_ptr<Command>> history_;
};
```

The invoker never needs to know that `BlurCommand`, `CropCommand`, or `ResizeCommand` exist. It only knows `Command`. This is the classic form of type erasure: the virtual table erases the concrete type behind a uniform interface.

The limitation of the virtual approach is that each command is a named class (or a lambda-like struct). For simple operations, writing a separate class for each command becomes boilerplate. The second limitation is that the undo strategy is baked into the command — some commands snapshot the entire receiver state (expensive but safe), others store only the inverse parameters (efficient but fragile). The classic pattern gives no guidance on choosing.

### Type Erasure with std::function

When the command is a single operation with no undo requirement, `std::function` provides type erasure without a base class:

```cpp
class CommandQueue {
public:
    using Command = std::function<void()>;

    void push(Command cmd) {
        cmd();                          // execute immediately
        history_.push_back(std::move(cmd));
    }

    // No undo — we have no inverse operation stored.
    // We could re-execute, but that is rarely useful.

private:
    std::vector<Command> history_;
};
```

Usage is concise:

```cpp
CommandQueue queue;

Image img("photo.jpg");
queue.push([&img] { img.apply_blur(5.0); });
queue.push([&img] { img.apply_crop(100, 100); });
```

The `std::function` erases the type of the lambda, storing any callable with the right signature in a uniform container. The cost is a small heap allocation (unless the lambda fits in the small-buffer optimization) and an indirect call through the type-erased wrapper.

For undo support with `std::function`, the command pair pattern is useful: instead of one command that knows how to undo itself, you push both a "do" function and an "undo" function:

```cpp
struct CommandPair {
    std::function<void()> execute;
    std::function<void()> undo;
};

class CommandQueue {
public:
    void push(CommandPair cmd) {
        cmd.execute();
        history_.push_back(std::move(cmd));
    }

    void undo() {
        if (!history_.empty()) {
            history_.back().undo();
            history_.pop_back();
        }
    }

private:
    std::vector<CommandPair> history_;
};
```

Now the caller provides both halves at the point of use:

```cpp
Image img("photo.jpg");

queue.push({
    .execute = [&img] { img.apply_blur(5.0); },
    .undo    = [&img] { img.revert_last_operation(); },
});
```

This separates the undo logic from the command object, which is sometimes cleaner than baking it into a class. The downside is that the caller must remember to supply an undo function — nothing enforces it at the type level.

### Custom Type Erasure for Commands

When performance matters or when you need to avoid the heap allocation of `std::function`, a custom type-erased command wrapper gives you control over storage and invocation. The technique is the same "concept + model + type erasure" pattern used by `std::any` and `std::function` themselves:

```cpp
class Command {
public:
    // Type-erased constructor: accepts any callable.
    template <typename F>
        requires (!std::same_as<std::decay_t<F>, Command>)
    Command(F&& f)
        : self_(std::make_shared<Model<std::decay_t<F>>>(std::forward<F>(f))) {}

    void execute() { self_->execute(); }
    void undo()    { self_->undo(); }

private:
    struct Concept {
        virtual ~Concept() = default;
        virtual void execute() = 0;
        virtual void undo() = 0;
    };

    template <typename F>
    struct Model : Concept {
        explicit Model(F&& f) : fn_(std::forward<F>(f)) {}
        void execute() override { fn_.execute(); }
        void undo()    override { fn_.undo(); }
        F fn_;
    };

    std::shared_ptr<Concept> self_;
};
```

The caller defines a command as any type that provides `execute` and `undo` — a struct, a class with named methods, or a lambda that exposes both via a helper:

```cpp
struct BlurCmd {
    Image* image;
    double radius;

    void execute() { /* apply blur */ }
    void undo()    { /* revert blur */ }
};

Command cmd = BlurCmd{&img, 5.0};
cmd.execute();
```

The custom erasure has the same semantics as `std::function` (type erasure through a virtual interface) but lets you define exactly which operations the erased type supports. You are not limited to `operator()` — you can have `execute`, `undo`, `serialize`, `validate`, or any other set of operations.

The shared_ptr-based storage copies the command into a heap-allocated model object. For small commands, a small-buffer optimization (SBO) can avoid the heap allocation by storing the model inline, exactly as `std::function` does:

```cpp
class Command {
    static constexpr size_t BufferSize = 32;

    alignas(std::max_align_t) char buffer_[BufferSize];
    Concept* self_ = nullptr;
    // ...
};
```

Implementing SBO correctly requires handling alignment, move semantics, and type-erased destruction. It is doable (and a good exercise) but for most command scenarios the heap allocation per command is acceptable — commands are created far less frequently than they are executed.

### Undo and Redo Strategies

Undo/redo is the killer feature of the Command pattern. The standard approach is a two-stack history: one stack for past commands (which can be undone) and one for undone commands (which can be redone).

```cpp
class UndoRedoStack {
public:
    void execute(std::unique_ptr<Command> cmd) {
        cmd->execute();
        undo_stack_.push_back(std::move(cmd));
        redo_stack_.clear();  // new command invalidates redo history
    }

    void undo() {
        if (undo_stack_.empty()) return;
        auto cmd = std::move(undo_stack_.back());
        undo_stack_.pop_back();
        cmd->undo();
        redo_stack_.push_back(std::move(cmd));
    }

    void redo() {
        if (redo_stack_.empty()) return;
        auto cmd = std::move(redo_stack_.back());
        redo_stack_.pop_back();
        cmd->execute();
        undo_stack_.push_back(std::move(cmd));
    }

private:
    std::vector<std::unique_ptr<Command>> undo_stack_;
    std::vector<std::unique_ptr<Command>> redo_stack_;
};
```

The redo stack is cleared when a new command is executed — after branching, the old redo history is no longer valid because the state diverged.

The undo strategy per command varies in three common patterns:

1. **Snapshot undo.** Before executing, the command saves a copy of the receiver's entire state. On undo, it restores the snapshot. Simple and correct for any operation, but expensive for large state.

2. **Inverse operation undo.** The command stores just enough information to reverse the operation mathematically. For example, a `MoveCommand` stores the original position and moves back on undo. Efficient, but requires every operation to have a well-defined inverse — not all operations do (consider a "delete" command).

3. **Compensation undo.** The command executes a new operation that compensates for the original. For example, an "add user" command performs a "remove user" on undo. This is the most flexible approach but requires careful design to ensure the compensation actually restores the original state.

In practice, many commands use a hybrid: snapshot for complex operations where computing the inverse is impractical, inverse operation for simple transformations where the inverse is cheap and well-defined.

A useful technique is *command composition* — grouping several commands into a single compound command that implements undo by reversing the order:

```cpp
class CompositeCommand : public Command {
public:
    void add(std::unique_ptr<Command> cmd) {
        commands_.push_back(std::move(cmd));
    }

    void execute() override {
        for (auto& cmd : commands_) cmd->execute();
    }

    void undo() override {
        for (auto it = commands_.rbegin(); it != commands_.rend(); ++it) {
            (*it)->undo();
        }
    }

private:
    std::vector<std::unique_ptr<Command>> commands_;
};
```

This is the foundation of macro recording: the user performs a sequence of operations, the system records each as a command in a `CompositeCommand`, and the macro can be executed, undone, and stored as a single unit.

### Command Queues and Logging

Beyond undo/redo, the command pattern enables two other important capabilities: queuing and logging.

A command queue decouples the producer of commands from their execution. Instead of executing immediately, commands are enqueued and processed by a separate thread or after a triggering event:

```cpp
class AsyncCommandQueue {
public:
    void push(std::unique_ptr<Command> cmd) {
        std::lock_guard lock(mutex_);
        queue_.push_back(std::move(cmd));
        cv_.notify_one();
    }

    void process() {
        std::unique_lock lock(mutex_);
        cv_.wait(lock, [this] { return !queue_.empty() || done_; });
        while (!queue_.empty()) {
            auto cmd = std::move(queue_.front());
            queue_.pop_front();
            lock.unlock();
            cmd->execute();
            lock.lock();
        }
    }

    void shutdown() {
        done_ = true;
        cv_.notify_one();
    }

private:
    std::deque<std::unique_ptr<Command>> queue_;
    std::mutex mutex_;
    std::condition_variable cv_;
    bool done_ = false;
};
```

This is the core of job dispatchers, task schedulers, and GUI event loops. The invoker posts commands and moves on; the processor thread drains the queue at its own pace.

Command logging is straightforward when commands are objects: serialize them. A command that logs itself can write to a file, a network socket, or a database:

```cpp
class LoggingCommand : public Command {
public:
    LoggingCommand(std::unique_ptr<Command> cmd, Logger& logger)
        : cmd_(std::move(cmd)), logger_(&logger) {}

    void execute() override {
        logger_->log("Executing: " + cmd_->describe());
        cmd_->execute();
    }

    void undo() override {
        logger_->log("Undoing: " + cmd_->describe());
        cmd_->undo();
    }

private:
    std::unique_ptr<Command> cmd_;
    Logger* logger_;
};
```

The logging command is a decorator — it wraps a real command and adds cross-cutting behavior (logging, auditing, timing, metrics) without modifying the command or the invoker. This is the same Decorator pattern from Chapter 23 applied to commands.

For audit trails and replay, commands can be serialized to a portable format:

```cpp
class SerializableCommand : public Command {
public:
    virtual void serialize(std::ostream& os) const = 0;
    virtual void deserialize(std::istream& is) = 0;
};
```

A replay system reads serialized commands from a log and executes them in sequence. This is how video game replays work, how database replication logs work, and how some test frameworks record and replay user interactions.

### Comparison and Decision Framework

| Approach              | Undo support | Heap alloc | Boilerplate | Flexibility        |
|-----------------------|--------------|------------|-------------|--------------------|
| Virtual Command base  | Built in     | Per cmd    | Class per cmd| Full control      |
| `std::function`       | Separate undo fn | Maybe SBO | None       | Single operation   |
| Custom type erasure   | Custom       | Per cmd    | One-time infra | Full control    |
| Command pair          | Pair per cmd | Maybe SBO  | None        | Manual undo pairing|

- **Virtual base class** — the workhorse for serious undo/redo systems (editors, design tools). Static type checking, full control over undo strategy, and clear separation of concerns. The boilerplate of one class per command is acceptable when commands have real logic.

- **`std::function`** — best for simple fire-and-forget commands where undo is not needed or is handled externally. The concise syntax makes it ideal for callbacks, event handlers, and one-shot tasks.

- **Custom type erasure** — useful when you need a richer interface than `operator()` but want to avoid forcing users to inherit from a base class. The implementation effort is moderate; libraries like `function2` and `stdext` provide ready-made alternatives.

- **Command pair** — a pragmatic middle ground: no inheritance, simple undo support, and easy to use. The lack of enforcement (nothing checks that the undo function is correct) is a concern for large systems.

### Exercises

1. Implement a command-based text editor with insert and delete operations. Each command should support undo by storing the inverse operation. Use the virtual Command base class. Test that undo restores the document to its previous state after any sequence of operations.

2. Refactor the text editor commands to use the command-pair pattern with `std::function`. Compare the line count and the code clarity. Under what circumstances would the command-pair approach be preferable to the virtual base class?

3. Implement a macro recorder that records a sequence of commands into a `CompositeCommand` and can replay them. Add serialization so the macro can be saved to a file and loaded later. What are the design challenges in serializing arbitrary commands?

4. Design a command queue for a multi-threaded renderer. Commands (draw calls, state changes, resource uploads) are produced by the game logic thread and consumed by the render thread. What thread-safety guarantees must the command objects provide? How would you handle commands that own resources with move-only semantics?
