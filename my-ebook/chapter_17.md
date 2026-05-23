# Chapter 17: Policy-based Design

Policy-based design is a compile-time composition technique that assembles class behavior from small, interchangeable building blocks called *policies*. Each policy encapsulates a single concern—allocation strategy, threading model, comparison criterion, storage format—and the host class combines them through template parameters. The result is a family of related classes where each member combines policies differently, all without runtime overhead.

This chapter treats policy-based design as a metaprogramming idiom, not merely a composition technique. The focus is on how templates enable this pattern: how policy interfaces are specified and documented, how default policies work, how policies interact through template instantiation, and how the pattern achieves zero-cost abstraction. Later chapters (especially Chapter 31 on Expression Templates) build on these ideas.

Policy-based design emerged from C++ template metaprogramming in the late 1990s and was popularized by Andrei Alexandrescu's Loki library. The standard library now uses it extensively: `std::unique_ptr` accepts a deleter policy, `std::map` accepts an allocator and comparison policy, and `std::thread` policies include launch parameters. Understanding the pattern reveals how these library components achieve their flexibility.

## Policy-based Class Design

A *policy class* is a template parameter that provides a specific capability to a host class. The host defines an expected interface—a set of member functions, types, or static methods—and each policy argument satisfies that interface. The host then delegates the corresponding concern to the policy, selecting behavior at compile time through template instantiation.

The most common formulation uses default template parameters so the host class works out of the box, while allowing callers to customize one or more policies when they need different behavior:

```cpp
template<typename T,
         typename ThreadingPolicy = SingleThreaded,
         typename StoragePolicy = HeapStorage,
         typename LockingPolicy = NoLocking>
class ConcurrentContainer;
```

The policies here are orthogonal: threading, storage, and locking each address a separate dimension of variation. A caller can replace just the locking policy while keeping the defaults for threading and storage. This selective customization is a hallmark of policy-based design—it avoids the combinatorial explosion of separate classes for each combination.

### Defining a Policy Interface

A policy interface is an implicit contract, not a formal base class. Because policies are template parameters, the host class uses them through duck typing: if the policy provides the required members, it works. This is both the strength (no inheritance overhead, no coupling to a specific hierarchy) and the weakness (no compiler enforcement of the interface without concepts or static assertions).

Consider a serialization policy for a configuration system. The host expects two static methods:

```cpp
// Policy: SerializationPolicy
// Required interface:
//   static std::string serialize(const T& value);
//   static T deserialize(const std::string& data);

struct XmlSerialization {
    template<typename T>
    static std::string serialize(const T& value) {
        // Convert to XML string
        return toXml(value);
    }

    template<typename T>
    static T deserialize(const std::string& data) {
        // Parse XML string to T
        return fromXml<T>(data);
    }
};

struct JsonSerialization {
    template<typename T>
    static std::string serialize(const T& value) {
        return toJson(value);
    }

    template<typename T>
    static T deserialize(const std::string& data) {
        return fromJson<T>(data);
    }
};
```

The interface is defined purely by usage: `XmlSerialization::serialize<int>(42)` and `XmlSerialization::deserialize<int>("42")`. Any policy that provides these operations is interchangeable. The host then accepts the policy as a template parameter and assumes the interface exists:

```cpp
template<typename T, typename Serializer = JsonSerialization>
class ConfigValue {
public:
    explicit ConfigValue(const T& value) : value_(value) {}

    std::string serialize() const {
        return Serializer::serialize(value_);
    }

    static ConfigValue deserialize(const std::string& data) {
        return ConfigValue(Serializer::template deserialize<T>(data));
    }

    const T& value() const { return value_; }

private:
    T value_;
};
```

The host class never references a specific serialization format. It delegates entirely to the policy. Adding a new format—BinarySerialization, YAMLSerialization, ProtoBufSerialization—requires no changes to the host. This is the fundamental benefit: the host is decoupled from the concern the policy addresses.

### Stateless vs Stateful Policies

Policies come in two flavors: stateless and stateful. Stateless policies provide only static methods or use no member data. They are simpler, cheaper, and avoid initialization ordering issues. Stateful policies carry data, which means the host must instantiate and manage the policy object.

Stateless policies are ideal when the policy only transforms data or provides configuration-free behavior:

```cpp
// Stateless: no data members, only static methods
struct StatelessLogger {
    static void log(const std::string& msg) {
        std::clog << msg << "\n";
    }
};

// The host can use static dispatch
template<typename Logger = StatelessLogger>
class Component {
public:
    void doWork() {
        Logger::log("Starting work");
        // ... work ...
        Logger::log("Finished work");
    }
};
```

Stateful policies carry configuration or state. The host must store them as data members and forward constructor arguments:

```cpp
// Stateful: carries a log file handle
struct FileLogger {
    explicit FileLogger(const std::string& path) : file_(path, std::ios::app) {}

    void log(const std::string& msg) {
        file_ << msg << "\n";
    }

private:
    std::ofstream file_;
};

// The host must store and use the policy as a member
template<typename Logger = StatelessLogger>
class Component {
public:
    // Default constructor uses default-constructed policy
    Component() : logger_{} {}

    // Constructor forwarding for stateful policies
    template<typename... Args>
    requires (sizeof...(Args) > 0 && (... && !std::is_same_v<std::remove_cvref_t<Args>, Component>))
    explicit Component(Args&&... args)
        : logger_(std::forward<Args>(args)...) {}

    void doWork() {
        logger_.log("Starting work");
        // ... work ...
        logger_.log("Finished work");
    }

private:
    Logger logger_;
};
```

The forwarding constructor pattern `template<typename... Args> explicit Component(Args&&... args)` is critical for stateful policies. It allows the caller to pass the policy's constructor arguments directly, without knowing the policy type at the call site:

```cpp
Component<FileLogger> comp("app.log");  // Forwards "app.log" to FileLogger's constructor
Component<StatelessLogger> comp;        // Default-constructs the stateless policy
```

### Private Inheritance vs Composition for Policies

The host class can integrate policies through composition (member data) or private inheritance. Both work, but they differ in behavior when the policy has virtual functions or when empty-base optimization matters.

Composition is the straightforward approach: the policy is a data member:

```cpp
template<typename Logger>
class Component_Composition {
    // ...
private:
    Logger logger_;
};
```

Private inheritance enables the empty-base optimization (EBO). When a policy is stateless (no data members), inheriting from it consumes zero bytes, while composition consumes at least one byte:

```cpp
template<typename Logger>
class Component_Inheritance : private Logger {
public:
    void doWork() {
        Logger::log("Starting work");  // Uses inherited policy
    }
};
```

With a stateless `StatelessLogger`, `Component_Inheritance<StatelessLogger>` is smaller than `Component_Composition<StatelessLogger>` by one byte per policy. In deeply nested policy combinations or containers of such objects, this savings compounds.

However, private inheritance introduces complications: it changes access control, can interfere with the host's own interface if the policy has member functions with the same name, and can cause diamond inheritance issues when multiple policies share a common base. Many policy-based libraries use a hybrid: private inheritance for stateless policies (via EBO helper templates) and composition for stateful ones.

Modern C++ provides `[[no_unique_address]]` (since C++20) which gives composition the same empty-class benefit as inheritance, making pure composition viable:

```cpp
template<typename Logger>
class Component {
    // ...
private:
    [[no_unique_address]] Logger logger_;
};
```

The guideline for policy integration is: prefer composition for simplicity; use private inheritance or `[[no_unique_address]]` when the zero-byte overhead matters (containers, embedded systems, large arrays of policy objects).

### Policy Defaults and Bundling

Well-designed policy parameters have sensible defaults. The caller should be able to use the host class without specifying any policies, while also being able to customize individual policies:

```cpp
template<typename T,
         typename Allocator = std::allocator<T>,
         typename Comparator = std::less<T>>
class CustomMap;
```

The defaults are chosen to satisfy the most common use case. This follows the principle of least surprise: `CustomMap<int>` works like `std::map<int>`, but `CustomMap<int, MyAllocator<int>>` adjusts just the allocation.

As the number of policies grows, specifying them in order becomes error-prone. The standard solution is to introduce policy bundles—aggregate types that group related policies:

```cpp
// Policy bundle grouping allocator and comparator
struct DefaultMapPolicies {
    template<typename T>
    using Allocator = std::allocator<T>;

    template<typename T>
    using Comparator = std::less<T>;
};

struct DebugMapPolicies {
    template<typename T>
    using Allocator = DebugAllocator<T>;

    template<typename T>
    using Comparator = std::less<T>;
};

template<typename T,
         typename Policies = DefaultMapPolicies>
class CustomMap {
    using allocator_type = typename Policies::template Allocator<T>;
    using comparator_type = typename Policies::template Comparator<T>;
    // ...
};
```

This approach bundles related concerns into a single template parameter, reducing verbosity at the call site. When the user needs to customize just one policy, they can inherit from the default bundle and override specific parts:

```cpp
struct CustomAllocPolicies : DefaultMapPolicies {
    template<typename T>
    using Allocator = CustomAllocator<T>;
};

CustomMap<int, CustomAllocPolicies> map;  // Custom allocator, default comparator
```

### Enforcing Policy Interfaces

Because policies use duck typing, a policy that fails to provide the expected interface produces deep, inscrutable template errors at the point of use, not at the point of instantiation. The two tools for improving this are `static_assert` with type traits and C++20 concepts.

Using type traits, the host can check policy compliance early:

```cpp
template<typename T, typename Serializer>
class ConfigValue {
    static_assert(
        std::is_same_v<decltype(Serializer::serialize(std::declval<const T&>())),
                       std::string>,
        "Serializer must provide: static std::string serialize(const T&)"
    );
    // ...
};
```

C++20 concepts make this more natural by defining the policy interface explicitly:

```cpp
template<typename S, typename T>
concept Serializer = requires(const T& value) {
    { S::serialize(value) } -> std::same_as<std::string>;
    { S::template deserialize<T>(std::declval<const std::string&>()) } -> std::same_as<T>;
};

template<typename T, typename S>
    requires Serializer<S, T>
class ConfigValue;
```

The concept definition serves as documentation and produces cleaner errors: the compiler reports "the required concept 'Serializer' was not satisfied" with the specific missing operation, rather than failing deep inside the class implementation.

### A Complete Example: Policy-Based Thread Pool

To illustrate how policies compose in a real design, consider a thread pool that accepts policies for task queueing, thread creation, and error handling:

```cpp
#include <vector>
#include <queue>
#include <thread>
#include <functional>
#include <mutex>

// ---- Policies ----

// QueueingPolicy: determines how tasks are stored and ordered
struct FifoQueue {
    std::queue<std::function<void()>> queue;

    void push(std::function<void()> task) {
        queue.push(std::move(task));
    }

    std::function<void()> pop() {
        auto task = std::move(queue.front());
        queue.pop();
        return task;
    }

    bool empty() const { return queue.empty(); }
};

struct LifoQueue {
    std::vector<std::function<void()>> stack;

    void push(std::function<void()> task) {
        stack.push_back(std::move(task));
    }

    std::function<void()> pop() {
        auto task = std::move(stack.back());
        stack.pop_back();
        return task;
    }

    bool empty() const { return stack.empty(); }
};

// ThreadCreationPolicy: controls how worker threads are created
struct CreateDetachedThreads {
    template<typename Func>
    static void spawn(Func&& func) {
        std::thread(std::forward<Func>(func)).detach();
    }
};

struct CreateJoinableThreads {
    std::vector<std::thread> threads;

    template<typename Func>
    void spawn(Func&& func) {
        threads.emplace_back(std::forward<Func>(func));
    }

    void joinAll() {
        for (auto& t : threads) {
            if (t.joinable()) t.join();
        }
    }
};

// ---- Host class ----

template<typename QueueingPolicy = FifoQueue,
         typename ThreadPolicy = CreateDetachedThreads>
class ThreadPool : private QueueingPolicy, private ThreadPolicy {
public:
    template<typename... QueueArgs>
    explicit ThreadPool(size_t numWorkers, QueueArgs&&... queueArgs)
        : QueueingPolicy(std::forward<QueueArgs>(queueArgs)...)
        , stop_(false)
    {
        for (size_t i = 0; i < numWorkers; ++i) {
            this->spawn([this] { workerLoop(); });
        }
    }

    ~ThreadPool() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stop_ = true;
        }
        condition_.notify_all();
        // If using joinable threads, join them
        if constexpr (requires { this->joinAll(); }) {
            this->joinAll();
        }
    }

    void enqueue(std::function<void()> task) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            QueueingPolicy::push(std::move(task));
        }
        condition_.notify_one();
    }

    template<typename QueueArgs>
    void enqueueWithPriority(std::function<void()> task, QueueArgs&& arg) {
        // Polymorphic queue behavior through the policy interface
        {
            std::lock_guard<std::mutex> lock(mutex_);
            QueueingPolicy::push(std::move(task));
        }
        condition_.notify_one();
    }

private:
    void workerLoop() {
        while (true) {
            std::function<void()> task;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                condition_.wait(lock, [this] {
                    return stop_ || !QueueingPolicy::empty();
                });
                if (stop_ && QueueingPolicy::empty()) return;
                task = QueueingPolicy::pop();
            }
            task();
        }
    }

    std::mutex mutex_;
    std::condition_variable condition_;
    bool stop_;
};
```

This thread pool combines two orthogonal policies. The queueing policy determines task ordering (FIFO, LIFO, or custom priority). The thread creation policy controls whether threads are detached immediately or collected for joining. Users instantiate the pool with different combinations:

```cpp
// Default: FIFO queue, detached threads
ThreadPool pool(4);

// LIFO (stack) ordering with detached threads
ThreadPool<LifoQueue> lifoPool(4);

// FIFO queue with joinable threads
ThreadPool<FifoQueue, CreateJoinableThreads> joinablePool(4);
```

The policies are truly independent. Adding a `PriorityQueue` policy or an `AffinityThreadCreation` policy requires no changes to the host—they just need to satisfy the implicit interfaces (`push`, `pop`, `empty` for queueing; `spawn` for thread creation).

### When Policy-Based Design Shines

Policy-based design excels when you have multiple, orthogonal dimensions of variation where combinations are known at compile time. The dimensions are orthogonal when changing one does not affect the others: serialization format does not change the threading model, queue ordering does not affect allocation strategy.

The compile-time requirement is critical. If the policy needs to change at runtime (e.g., the user selects a serialization format from a configuration file), policy-based design is the wrong tool. Runtime polymorphism (Strategy pattern, virtual dispatch) is the appropriate alternative.

Policy-based design works well for:
- Library components where users decide policy at compile time: containers, allocators, smart pointers
- Performance-critical code where the policy dispatch must be inlined or eliminated entirely
- Frameworks where users customize behavior through template specialization
- Code generators where the set of policies is known during code generation

It works poorly for:
- Systems where policy choices are made at runtime (users loading configuration files)
- Small projects where the complexity of template metaprogramming outweighs the flexibility benefit
- Cases where policy interaction is poorly understood or creates surprising behavior

### Limitations and Pitfalls

Policy interfaces suffer from the lack of formal specification. Unlike virtual base classes (where the compiler enforces the interface), a policy that gets an interface wrong produces template instantiation errors far from the mistake. Concepts (C++20) mitigate this but are not yet universally adopted.

Stateful policies with multiple policies can introduce ABI complications. When policies have different sizes, the host class layout changes. This binary incompatibility means you cannot link translation units compiled with different policy choices. In practice, this is rarely an issue because policy combinations are typically fixed per translation unit.

Policy interaction is the most subtle pitfall. Two policies that individually work correctly may interfere when combined. For example, a logging policy that acquires a mutex inside a hot path and a concurrency policy that expects lock-free operations create a contradictory combination. The compiler will not catch these semantic conflicts—they manifest as performance degradation, deadlocks, or correctness bugs. Documentation, policy test suites for common combinations, and careful design of orthogonal policy dimensions are the only defenses.

The combinatorial explosion of template instantiations can also increase compile times and binary sizes. Each unique combination of policies produces a separate class instantiation. A host class with three policies each having five variants creates 125 distinct instantiations. Use judiciously, and consider runtime alternatives when the number of policy variants is large.

## Combining Policies

Real-world policy-based designs rarely use a single policy. Most host classes accept two, three, or more policy parameters, each addressing a different concern: allocation, threading, comparison, serialization, validation, logging. The way these policies combine—how they interact, how they are ordered, how conflicts are detected, and how new policies emerge from existing ones—determines whether the design remains manageable or collapses into template spaghetti.

This section explores the patterns for combining policies. Some are purely mechanical (how to forward multiple policies to sub-components). Others address deeper issues: what happens when two policies make assumptions about each other, how to build compound policies from primitives, and how to accept an arbitrary number of policies without exploding template parameter counts.

### Policy Ordering and Dependency

When a host class accepts multiple policies, the order of template parameters matters. The convention (followed by the standard library) is to order policies from most general to most specific, with the most commonly customized policy first:

```cpp
template<typename T,
         typename Allocator = std::allocator<T>,     // Most commonly customized
         typename Comparator = std::less<T>,          // Sometimes customized
         typename Validation = NoValidation>           // Rarely customized
class Container;
```

This ordering lets users specify only the first few policies without naming the rest. If `Validation` were first, every user would have to specify it just to change the allocator—defeating the purpose of defaults.

Policy dependency introduces a more subtle consideration. Some policies require others to be present or to have specific properties. A `ThreadSafe` logging policy may require a `Mutex` policy. A `Bounded` queueing policy may require an `Overflow` policy. These dependencies can be expressed through template template parameters or through static assertions:

```cpp
template<typename T,
         typename MutexPolicy = StdMutex,
         typename LogPolicy = NoLogging>
class ConcurrentQueue {
    static_assert(MutexPolicy::is_mutex_policy,
                  "ConcurrentQueue requires a mutex policy as the first parameter");
    // ...
};
```

The tag `is_mutex_policy` is a convention: each policy defines a compile-time constant that advertises its role:

```cpp
struct StdMutex {
    using mutex_type = std::mutex;
    static constexpr bool is_mutex_policy = true;

    void lock() { mtx_.lock(); }
    void unlock() { mtx_.unlock(); }

private:
    std::mutex mtx_;
};

struct SpinMutex {
    static constexpr bool is_mutex_policy = true;

    void lock() { /* spin until acquired */ }
    void unlock() { /* release */ }
};

struct NoMutex {
    static constexpr bool is_mutex_policy = false;  // Not a mutex policy

    void lock() {}
    void unlock() {}
};
```

The host checks `is_mutex_policy` and rejects invalid combinations early with a clear error, rather than failing deep inside a template instantiation with a cryptic message about missing member `lock`.

### Policy Tagging with Role Detection

The tagging pattern generalizes beyond simple boolean checks. Each policy can advertise its category through a type alias, enabling the host to detect roles and adjust behavior:

```cpp
// Each policy advertises its role
struct DebugAllocator {
    using role = allocator_tag;
    // ...
};

struct HeapAllocator {
    using role = allocator_tag;
    // ...
};

struct FifoQueue {
    using role = queueing_tag;
    // ...
};

// The host can query roles at compile time
template<typename T,
         typename AllocPolicy,
         typename QueuePolicy>
class Container {
    static_assert(std::is_same_v<typename AllocPolicy::role, allocator_tag>,
                  "First policy must be an allocator");
    static_assert(std::is_same_v<typename QueuePolicy::role, queueing_tag>,
                  "Second policy must be a queueing policy");
    // ...
};
```

This pattern is especially useful when policies share similar interfaces but serve different roles. Both `DebugAllocator` and `FifoQueue` might provide an `allocate` method, but they mean different things. The role tag disambiguates at compile time:

```cpp
// Without role tags, this is ambiguous:
Container<int, DebugAllocator, HeapAllocator> c;

// The host can detect that both are allocators and produce a clear error
```

### Layered Policies: Wrapping and Decorating

Policies can themselves be composed from other policies using a wrapper or decorator pattern. A logging policy can wrap an allocator policy, adding instrumentation around each allocation:

```cpp
template<typename AllocPolicy>
struct LoggingAllocator : private AllocPolicy {
    using role = allocator_tag;

    template<typename T>
    T* allocate(size_t count) {
        std::clog << "Allocating " << count << " elements of type "
                  << typeid(T).name() << "\n";
        return AllocPolicy::template allocate<T>(count);
    }

    template<typename T>
    void deallocate(T* ptr, size_t count) {
        std::clog << "Deallocating " << count << " elements of type "
                  << typeid(T).name() << "\n";
        AllocPolicy::template deallocate<T>(ptr, count);
    }
};
```

Now `LoggingAllocator<HeapAllocator>` is itself a valid allocator policy. The host sees only the `role` tag and the allocator interface—it does not know or care that the policy is a wrapper. This layering enables policy composition without modifying the host:

```cpp
template<typename T>
using TracingHeapVector = Container<T, LoggingAllocator<HeapAllocator>>;

template<typename T>
using TracingPoolVector = Container<T, LoggingAllocator<PoolAllocator>>;
```

Layering composes policies along a single dimension (allocation in this case), but introduces a forwarding burden: each wrapped method must be explicitly forwarded. C++ offers no automatic delegation, so wrapper policies must manually re-export every member of the wrapped policy's interface. This can be mitigated with macros or, in C++23, with deducing `this` and forwarding call operators, but in practice the overhead is manageable because policy interfaces are typically small (3--5 methods).

### Policy Chaining Through Inheritance

When policies contribute distinct, non-overlapping capabilities, the host can inherit from all of them. Each policy adds its behavior through private inheritance, and the host composes by calling the appropriate policy's methods:

```cpp
template<typename T,
         typename Serializer,
         typename Validator,
 typename Logger>
class DataProcessor : private Serializer,
                      private Validator,
                      private Logger {
public:
    bool process(const std::string& input) {
        auto data = Serializer::template deserialize<T>(input);

        if (!Validator::validate(data)) {
            Logger::log("Validation failed");
            return false;
        }

        Logger::log("Processing data");
        // ... process ...
        return true;
    }
};
```

Each policy contributes independently. The host calls each policy at the appropriate point in its logic. This works well when the policies are orthogonal—they each handle a separate stage of processing and do not share state.

Problems arise when policies have overlapping method names. If both `Serializer` and `Validator` define a `configure` method, the call becomes ambiguous. The host must explicitly qualify:

```cpp
Serializer::configure(config);
Validator::configure(config);
```

This explicit qualification is acceptable for a handful of policies, but becomes burdensome with many. Design your policy interfaces with unique method names, or use the role-tagging pattern to dispatch through overloaded helper functions.

### Variadic Policies

When the number of policy dimensions is not fixed at design time, variadic template parameters allow the host to accept an arbitrary number of policies. This pattern is used in the standard library's `std::tuple` and in many modern C++ libraries:

```cpp
template<typename T, typename... Policies>
class ConfigurableObject;
```

The challenge with variadic policies is extracting and dispatching to individual policies. One approach is to iterate over the pack using fold expressions, calling a method on each policy that supports it:

```cpp
template<typename... Policies>
class PluginHost : private Policies... {
public:
    // Call 'init' on every policy that provides it
    void initialize() {
        (initialize_policy(static_cast<Policies*>(this)), ...);
    }

    // Call 'shutdown' on every policy that provides it
    void shutdown() {
        (shutdown_policy(static_cast<Policies*>(this)), ...);
    }

private:
    // SFINAE helpers: call init only if the policy defines it
    template<typename P>
    auto initialize_policy(P* p) -> decltype(p->init(), void()) {
        p->init();
    }

    template<typename P>
    void initialize_policy(...) {
        // Policy does not have init(); no-op
    }

    template<typename P>
    auto shutdown_policy(P* p) -> decltype(p->shutdown(), void()) {
        p->shutdown();
    }

    template<typename P>
    void shutdown_policy(...) {
        // Policy does not have shutdown(); no-op
    }
};
```

The fold expression `(initialize_policy(static_cast<Policies*>(this)), ...)` calls the helper for each policy in the pack. The SFINAE overloads detect whether the policy provides the method and silently skip it if not. The host can now be extended with new policies without changing its implementation:

```cpp
struct LoggingPlugin {
    void init() { std::clog << "Logging initialized\n"; }
    void shutdown() { std::clog << "Logging shut down\n"; }
};

struct MetricsPlugin {
    void init() { /* start metrics collection */ }
    void report() { /* generate report */ }
    // No shutdown method - the SFINAE helper handles this
};

struct CachePlugin {
    void configure(size_t maxSize) { cache_.reserve(maxSize); }
    // No init or shutdown
};

// All three work with PluginHost
PluginHost<LoggingPlugin, MetricsPlugin, CachePlugin> host;
host.initialize();  // Calls init on LoggingPlugin and MetricsPlugin, skips CachePlugin
```

The variadic approach trades compile-time structure for flexibility. The host cannot directly address a specific policy by name—there is no `LoggingPlugin::init()` call, only a generic iteration over all policies. If the host needs type-specific access, it can use a type-indexed lookup:

```cpp
template<typename... Policies>
class PluginHost : private Policies... {
public:
    template<typename SpecificPolicy>
    SpecificPolicy& get() {
        return static_cast<SpecificPolicy&>(*this);
    }
};

// Usage:
host.get<MetricsPlugin>().report();
```

Combining fold iteration (for lifecycle methods) with type-indexed access (for specific functionality) gives the best of both approaches: bulk operations for common concerns and targeted access for policy-specific interfaces.

### Policy Selection via Type Traits

The host can select a policy automatically based on properties of the type parameter `T`, reducing the burden on the caller. This technique uses type traits and `std::conditional_t` to choose the appropriate policy at compile time:

```cpp
#include <type_traits>
#include <cstdint>

// Serialization policies
struct BinarySerializer { /* compact binary format */ };
struct TextSerializer {   /* human-readable format */ };
struct JsonSerializer {   /* JSON format */ };

// Policy selector: choose serializer based on type properties
template<typename T>
using DefaultSerializer = std::conditional_t<
    std::is_trivially_copyable_v<T>,
    BinarySerializer,
    std::conditional_t<
        std::is_arithmetic_v<T>,
        TextSerializer,
        JsonSerializer
    >
>;

// Host uses the selected policy by default
template<typename T,
         typename Serializer = DefaultSerializer<T>>
class ConfigValue {
    // Uses BinarySerializer for int, double, etc.
    // Uses TextSerializer for arithmetic types
    // Uses JsonSerializer for complex types
};
```

This pattern automates policy selection. The caller gets sensible defaults without specifying policy parameters. When the automatic choice is wrong, the caller overrides explicitly:

```cpp
ConfigValue<int> v1;          // Uses BinarySerializer (trivially copyable)
ConfigValue<std::string> v2;  // Uses JsonSerializer (complex type)
ConfigValue<int, TextSerializer> v3;  // Explicit override to text format
```

For more complex selection logic, a traits class can compute the entire set of policies based on `T`:

```cpp
template<typename T>
struct ContainerPolicyTraits {
    using Allocator = std::allocator<T>;
    using Comparator = std::less<T>;
    using Validation = std::conditional_t<
        std::is_integral_v<T>,
        RangeValidator<T>,
        NoValidation
    >;
};

template<typename T,
         typename Policies = ContainerPolicyTraits<T>>
class Container {
    using allocator_type = typename Policies::Allocator;
    using comparator_type = typename Policies::Comparator;
    using validation_type = typename Policies::Validation;
    // ...
};
```

The traits approach moves policy selection into a single, customizable extension point. Users who need different policy mappings specialize `ContainerPolicyTraits` for their types:

```cpp
template<>
struct ContainerPolicyTraits<CustomType> {
    using Allocator = CustomAllocator<CustomType>;
    using Comparator = CustomComparator;
    using Validation = CustomValidation;
};
```

### Policy Conflict Detection

As the number of policies grows, the risk of conflicting combinations increases. A conflict occurs when two policies make incompatible assumptions about the environment. For example, a `Reentrant` logging policy assumes that logging can happen recursively, while a `MutexLocking` policy might deadlock on reentrant calls.

Conflicts can be detected at compile time through a combination of static assertions, type tags, and requires clauses:

```cpp
// Each policy advertises its requirements and guarantees
struct ReentrantLogger {
    static constexpr bool requires_reentrant_mutex = true;
    // ...
};

struct MutexLocking {
    static constexpr bool provides_reentrant = false;
    // ...
};

template<typename Logger, typename LockPolicy>
class ThreadSafeComponent {
    static_assert(
        !Logger::requires_reentrant_mutex ||
        LockPolicy::provides_reentrant,
        "Reentrant logger requires a reentrant-capable lock policy"
    );
    // ...
};
```

This compile-time contract checking is more verbose than runtime checking, but catches errors at the point of template instantiation rather than at runtime under load. The cost is that each policy must explicitly declare its requirements and guarantees through static constants or type aliases.

For C++20 and later, concepts provide a more natural way to express these relationships:

```cpp
template<typename LockPolicy>
concept ReentrantLock = LockPolicy::provides_reentrant;

template<typename Logger>
concept ReentrantLogger = Logger::requires_reentrant_mutex;

template<typename Logger, typename LockPolicy>
    requires (!ReentrantLogger<Logger> || ReentrantLock<LockPolicy>)
class ThreadSafeComponent;
```

The constraint says: "if the logger requires reentrancy, the lock must provide it." This is a logical implication encoded at the type level, checked at compile time, and producing a clear error when violated.

### Mixing Policies from Different Sources

A practical challenge in larger codebases is that policies come from different libraries or modules, each with its own conventions. One library might define policies as classes with static methods; another might use classes with instance methods; a third might use free functions and tag types.

To combine these disparate sources, the host (or an adapter layer) must normalize the policy interface. The adapter pattern for policies wraps an external implementation to match the expected interface:

```cpp
// External library provides this free function
void external_serialize(const MyType& value, std::ostream& out);

// Adapter: wraps the free function into the policy interface
struct ExternalSerializerAdapter {
    template<typename T>
    static std::string serialize(const T& value) {
        std::ostringstream out;
        external_serialize(value, out);  // Assumes T supports this
        return out.str();
    }

    template<typename T>
    static T deserialize(const std::string& data) {
        T value;
        std::istringstream in(data);
        external_deserialize(value, in);  // Assumes T supports this
        return value;
    }
};

// Now ExternalSerializerAdapter works where any Serializer policy is expected
ConfigValue<MyType, ExternalSerializerAdapter> config;
```

For function-based policies (a single free function), a generic adapter can wrap any callable into a policy:

```cpp
template<auto Func>
struct FuncToPolicy {
    template<typename T>
    static auto serialize(const T& value)
        -> decltype(Func(value)) {
        return Func(value);
    }
};

// Usage with a lambda or function
inline auto myCustomSerialize = [](const auto& v) {
    return std::to_string(v);
};

using MySerializer = FuncToPolicy<myCustomSerialize>;
ConfigValue<int, MySerializer> config;
```

These adapters let you combine policies written in different styles without modifying either the host or the external code.

### Policy Rebinding

Some policies need to be rebound to a different type. The canonical example is `std::allocator<T>`, which provides a rebinding mechanism:

```cpp
template<typename T>
struct AllocatorPolicy {
    template<typename U>
    struct rebind {
        using other = AllocatorPolicy<U>;
    };
    // ...
};
```

The host uses `rebind` when it needs to allocate memory for a type different from `T`:

```cpp
template<typename T, typename Alloc = std::allocator<T>>
class Container {
    using allocator_type = Alloc;

    // When we need to allocate nodes (not T directly):
    struct Node { T value; Node* next; };

    using node_allocator = typename Alloc::template rebind<Node>::other;
    node_allocator nodeAlloc_;
    // ...
};
```

Rebinding is essential for container-like hosts that manage internal data structures. Without it, a policy that allocates `T` cannot allocate the container's internal nodes. The standard library's allocator model depends on rebinding, and any custom allocation policy for container use must provide it.

Not all policies need rebinding. Serialization policies, validation policies, and logging policies operate on the type directly and have no need to rebind. Reserve rebinding for policies that manage storage or resources of the parameterized type.

### Summary: Combining Policies

Combining policies is where the power and complexity of policy-based design converge. The patterns in this section address the practical challenges that arise when moving from a single-policy demonstration to a multi-policy production design:

- Policy ordering and role tagging make multi-policy interfaces navigable and self-documenting.
- Layered policies provide decorator-like composition along a single dimension.
- Variadic policies enable extensible designs where the set of concerns is not fixed in advance.
- Type-trait-based selection automates policy choice while preserving the option for explicit override.
- Compile-time conflict detection catches incompatible combinations at the point of instantiation.
- Adapters bridge different policy conventions from separate libraries.
- Rebinding handles the storage-type mismatch that arises in container implementations.

The unifying theme is that combining policies is not merely concatenation. Each combination introduces potential interactions, and the design must account for them. Well-designed policies are orthogonal by default (they do not depend on each other), and their combined behavior is the sum of their parts. When orthogonality is not achievable, explicit dependency declarations and compile-time assertions make the interactions observable and diagnosable.

## Runtime Polymorphism vs Policy-Based Design

Policy-based design achieves polymorphism at compile time through template parameters. Runtime polymorphism achieves it at run time through virtual function dispatch. Both solve the same fundamental problem—varying behavior without changing the host class—but they make radically different trade-offs along performance, flexibility, complexity, and testing dimensions.

This section compares the two approaches across these dimensions, presents scenarios where each excels, and shows hybrid patterns that combine both.

### The Core Difference: When Binding Happens

The essential difference is *when* behavior is selected. Policy-based design binds behavior at compile time: each template instantiation produces a separate class, and the compiler resolves all policy calls before the program runs. Runtime polymorphism binds behavior at run time: the same class calls virtual functions through a vtable pointer, and the concrete implementation is chosen when the program executes.

```cpp
// Policy-based: compile-time binding
template<typename Serializer>
class ConfigValue {
public:
    std::string save() const {
        return Serializer::serialize(data_);  // Inlined, resolved at compile time
    }
private:
    SomeType data_;
};

// Runtime polymorphism: runtime binding
class ISerializer {
public:
    virtual ~ISerializer() = default;
    virtual std::string serialize(const SomeType&) const = 0;
};

class ConfigValue {
public:
    explicit ConfigValue(std::unique_ptr<ISerializer> s) : serializer_(std::move(s)) {}

    std::string save() const {
        return serializer_->serialize(data_);  // vtable dispatch at runtime
    }
private:
    SomeType data_;
    std::unique_ptr<ISerializer> serializer_;
};
```

In the policy-based version, `ConfigValue<JsonSerializer>` and `ConfigValue<XmlSerializer>` are separate types with no runtime overhead for the polymorphism. In the runtime version, a single `ConfigValue` class works with any serializer, but each call to `save()` incurs a vtable indirection.

This difference cascades into every other dimension of comparison.

### Performance Characteristics

Policy-based design is zero-overhead in the sense of "you don't pay for what you don't use." The policy calls are direct function calls or even inlined, and the compiler can optimize across policy boundaries:

```cpp
template<typename SortPolicy>
class Sorter {
public:
    void sort(std::vector<int>& data) {
        SortPolicy::sort(data);  // Inlined: no call overhead
    }
};

struct QuickSortPolicy {
    static void sort(std::vector<int>& data) {
        // Full quicksort implementation here
    }
};

// Usage
Sorter<QuickSortPolicy> sorter;
std::vector<int> data = {4, 2, 7, 1};
sorter.sort(data);  // The compiler sees the full sort() implementation
                    // and can inline it into sort(), then into the call site
```

The policy-based version enables the compiler to see through the entire call chain. Inlining, constant propagation, dead code elimination, and loop optimization all work across the boundary between the host and the policy.

The runtime version blocks these optimizations:

```cpp
struct ISortPolicy {
    virtual ~ISortPolicy() = default;
    virtual void sort(std::vector<int>& data) const = 0;
};

class Sorter {
public:
    explicit Sorter(std::unique_ptr<ISortPolicy> p) : policy_(std::move(p)) {}

    void sort(std::vector<int>& data) {
        policy_->sort(data);  // The compiler sees only the vtable call
                              // Cannot inline sort() into this call site
    }
private:
    std::unique_ptr<ISortPolicy> policy_;
};
```

The vtable call is indirect: the compiler cannot know at compile time which `sort` implementation will be called. This prevents inlining, which prevents all downstream optimizations. The performance gap widens when the operation is small and called frequently. For a large operation (sorting a million elements), the vtable overhead is negligible. For a small operation (comparing two integers in a tight loop), the policy-based version can be an order of magnitude faster.

However, the runtime version has a hidden performance advantage: instruction cache locality. Policy-based design creates multiple, separate instantiations of the host class, each with its own machine code. If a program uses many policy combinations, the instruction cache may thrash between them. The runtime version uses one code path, keeping the instruction cache hot:

```cpp
// Policy-based: three separate instantiations, three code paths
std::vector<Sorter<QuickSortPolicy>> qsorters(1000);
std::vector<Sorter<HeapSortPolicy>> hsorters(1000);
std::vector<Sorter<MergeSortPolicy>> msorters(1000);

// Each vector's sort() call goes to a different code address
// The instruction cache must switch between them

// Runtime: one code path
std::vector<Sorter> sorters(1000);
sorters[0] = Sorter(std::make_unique<QuickSortPolicy>());
sorters[1] = Sorter(std::make_unique<HeapSortPolicy>());
// All call the same sort() function, which delegates through the vtable
// The instruction cache stays hot for the sort() function itself
```

In mixed-workload scenarios where many different policy combinations are used in the same execution, the runtime version's single code path can outperform the policy-based version's multiple code paths, despite the vtable overhead.

**General guideline:** Use policy-based design when the call is hot (called millions of times per second) and the operation is small. Use runtime polymorphism when the operation dominates execution time (the vtable overhead is negligible) or when workload mixing keeps the instruction cache busy with many different combinations.

### Flexibility Dimensions

Flexibility is where runtime polymorphism decisively wins. Runtime polymorphism can change behavior:
- At startup (reading a configuration file)
- Mid-execution (switching strategies based on load)
- Through plugin systems (loading shared libraries at runtime)
- Through user interaction (selecting a format from a dropdown)

Policy-based design cannot do any of these. The policy is fixed at compile time. To change it, you must recompile:

```cpp
// Runtime: serializer chosen from config file
std::unique_ptr<ISerializer> make_serializer(const Config& cfg) {
    if (cfg.format == "json") return std::make_unique<JsonSerializer>();
    if (cfg.format == "xml")  return std::make_unique<XmlSerializer>();
    if (cfg.format == "yaml") return std::make_unique<YamlSerializer>();
    throw std::runtime_error("Unknown format: " + cfg.format);
}

ConfigValue config(make_serializer(userConfig));

// Policy-based: serializer must be known at compile time
using MySerializer = JsonSerializer;  // Hard-coded
ConfigValue<MySerializer> config;
```

This limitation is fundamental. Policy-based design is not a tool for runtime configurability. Its flexibility is of a different kind: it enables combinatorial flexibility at compile time. If you need to support five serialization formats and three hashing algorithms, policy-based design gives you 15 combinations without writing 15 classes. Runtime polymorphism gives you the same combinatorial power but through delegation rather than instantiation.

The flexibility advantage of runtime polymorphism extends to binary distribution. A shared library compiled with runtime polymorphism can be used by any caller that understands the interface. A shared library compiled with policy-based design is tied to specific policy choices—different callers that want different policies must compile their own versions:

```cpp
// Shared library header (runtime): works for all callers
class EXPORT Logger {
public:
    explicit Logger(std::unique_ptr<ILogSink> sink);
    void log(const std::string& msg);
};

// Shared library header (policy-based): each caller needs different instantiation
template<typename SinkPolicy = ConsoleSink>
class Logger {
public:
    void log(const std::string& msg);
};
// Cannot export this from a shared library without explicit instantiation
// for each policy combination
```

For library authors distributing headers, policy-based design works fine (everything is in headers). For library authors distributing binaries, runtime polymorphism is the only practical option.

### Binary Size and Compile Time

Policy-based design generates code for each unique combination of template arguments. A host class with three policies, each available in five variants, produces up to 125 class instantiations. Each instantiation includes the full implementation of the host class, specialized for that policy set:

```cpp
template<typename Alloc, typename Serializer, typename Validator>
class Processor;

// These three instantiations produce three copies of Processor's code:
Processor<HeapAlloc, JsonSerializer, NoValidator> p1;
Processor<HeapAlloc, XmlSerializer, NoValidator>  p2;
Processor<PoolAlloc, JsonSerializer, RangeValidator> p3;
```

The compiler cannot share code between these instantiations because the policy methods are inlined and type-specific. Even if the host class's logic is identical across instantiations, the machine code differs because the policy-specific calls are resolved to different addresses.

This code bloat translates directly to:
- Larger binaries (more text section bytes)
- Longer compile times (more template instantiations to process)
- More memory usage during compilation (more types in the symbol table)

Runtime polymorphism avoids this entirely. One implementation of the host class serves all policy variants:

```cpp
// One implementation, any number of concrete strategies
class Processor {
public:
    void process(const Data& data) {
        alloc_->allocate(data.size());
        auto serialized = serializer_->serialize(data);
        if (!validator_->validate(serialized)) {
            throw ValidationError("Invalid data");
        }
    }
private:
    std::unique_ptr<IAllocator> alloc_;
    std::unique_ptr<ISerializer> serializer_;
    std::unique_ptr<IValidator> validator_;
};

// Add new strategies without recompiling the Processor:
class YamlSerializer : public ISerializer { /* ... */ };
class BinaryValidator : public IValidator { /* ... */ };
```

The host class compiles once. New strategies compile independently. Binary size grows linearly with the number of strategy classes, not multiplicatively with the number of combinations.

The compile-time difference is dramatic for large codebases. A policy-based library with many combinations can add minutes to compile times, while the runtime equivalent compiles in seconds. This is the primary reason large projects (Chromium, LLVM, game engines) favor runtime polymorphism for internal APIs.

### Code Complexity and Error Messages

Policy-based design produces famously unreadable error messages. A single mismatch in a policy interface can generate pages of template instantiation backtrace, burying the actual mistake:

```cpp
// Host expects: static void log(const std::string&)
struct FileLogger {
    void log(const std::string& msg);  // Missing 'static'!
};

template<typename Logger>
class Component : private Logger { /* ... */ };

Component<FileLogger> comp;  // Error: dozens of lines of template backtrace
// The real issue: 'this' pointer mismatch because log() is not static
// but the error message says something about "cannot convert 'FileLogger*' to ..."
```

The C++20 concepts improve this significantly, but many codebases target C++17 or earlier and must live with the poor diagnostics.

Runtime polymorphism produces cleaner errors. If a class does not implement the full interface, the compiler immediately reports which pure virtual functions are unimplemented. The error points directly to the problem class and the missing function:

```cpp
class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void log(const std::string&) = 0;
    virtual void flush() = 0;
};

class FileLogger : public ILogger {
public:
    void log(const std::string& msg) override { /* ... */ }
    // Forgot to implement flush()
};

// FileLogger f;  // Error: cannot instantiate abstract class
//               // Message: "FileLogger: unimplemented pure virtual 'flush'"
```

The error message is concise, points to the right file and line, and tells you exactly what is missing.

Code complexity also differs in maintenance. A policy-based design requires all users to understand templates. A runtime polymorphic design uses inheritance, which is familiar to any programmer who knows OOP. This lower barrier to entry is significant for teams with varying levels of C++ expertise.

### Testing and Mocking

Runtime polymorphism integrates naturally with mock objects. Testing a class that uses a strategy is straightforward: create a mock implementation of the interface, inject it, and verify interactions:

```cpp
// Mock serializer for testing
struct MockSerializer : ISerializer {
    MOCK_METHOD(std::string, serialize, (const Data&), (const, override));
};

TEST(ProcessorTest, DelegatesToSerializer) {
    auto mock = std::make_unique<MockSerializer>();
    EXPECT_CALL(*mock, serialize(_)).Times(1);

    Processor processor(std::move(mock), ...);
    processor.process(testData);
}
```

The mock completely replaces the real implementation. The test runs in isolation, with no real I/O, no network calls, no database connections.

Policy-based design makes mocking harder. Since the policy is a template parameter, the mock must be a compatible type at compile time:

```cpp
// Mock serializer as a policy
struct MockSerializer {
    static std::string serialize(const Data& data) {
        ++callCount;
        return "mocked";
    }

    inline static int callCount = 0;
};

// Test
TEST(ProcessorTest, CallsSerializer) {
    Processor<MockSerializer, ...> processor;
    processor.process(testData);
    EXPECT_EQ(MockSerializer::callCount, 1);
}
```

This works but has limitations. The mock must satisfy the policy interface exactly. If the interface includes non-static methods or specific constructor signatures, the mock must match those too. And because the mock is a template argument, each test configuration creates a distinct type, which can lead to longer compile times for the test suite.

A more fundamental limitation: policy-based mock objects cannot easily verify call order, capture arguments, or set up complex expectations. The mock serialization library (Google Mock, trompeloeil) works with virtual interfaces, not with template parameters. Teams that rely on mocking heavily should prefer runtime polymorphism.

### Hybrid Approaches

The strongest designs often combine both techniques, using each where it excels. The hybrid patterns let you choose the binding time per concern, rather than committing entirely to one approach.

**Pattern 1: Runtime Polymorphism Wrapper Around Policy-Based Internals**

Use policy-based design for the performance-critical internals, then wrap the instantiation in a runtime dispatcher:

```cpp
// Policy-based implementations (header-only, fast)
template<typename SortAlgo>
class SorterImpl {
public:
    void sort(std::vector<int>& data) {
        SortAlgo::sort(data);
    }
};

// Runtime wrapper (single type, OOP interface)
class Sorter {
public:
    enum class Algorithm { Quick, Heap, Merge };

    explicit Sorter(Algorithm algo) {
        switch (algo) {
        case Algorithm::Quick:
            impl_ = []<typename T>(T& c) { SorterImpl<QuickSortPolicy>().sort(c); };
            break;
        case Algorithm::Heap:
            impl_ = []<typename T>(T& c) { SorterImpl<HeapSortPolicy>().sort(c); };
            break;
        case Algorithm::Merge:
            impl_ = []<typename T>(T& c) { SorterImpl<MergeSortPolicy>().sort(c); };
            break;
        }
    }

    void sort(std::vector<int>& data) {
        impl_(data);  // Dispatches to the correct policy-based instantiation
    }

private:
    std::function<void(std::vector<int>&)> impl_;
};
```

The caller works with a single `Sorter` type (runtime dispatch) while the actual sorting uses the policy-based implementations. The cost is one indirect function call (in the `std::function`) plus one branch (in the switch). This is typically negligible compared to the sorting itself.

This pattern is especially useful for library authors who want the performance of policy-based design internally while exposing a simple, type-erased interface to users.

**Pattern 2: Policy-Based Shell with Runtime Strategy Injection**

The host class uses policy-based design for its internal mechanics but accepts a runtime strategy for decisions that need runtime flexibility:

```cpp
template<typename Serializer, typename Compressor>
class DataPipeline {
public:
    explicit DataPipeline(std::unique_ptr<IEncryptionPolicy> encryption)
        : encryption_(std::move(encryption)) {}

    std::vector<char> process(const Data& data) {
        auto serialized = Serializer::serialize(data);
        auto compressed = Compressor::compress(serialized);
        auto encrypted = encryption_->encrypt(compressed);  // Runtime dispatch
        return encrypted;
    }

private:
    std::unique_ptr<IEncryptionPolicy> encryption_;
};
```

Here, serialization and compression are compile-time choices (performance-critical, known at compile time), while encryption is a runtime policy (must support different standards, key management, hardware acceleration). Each concern is handled with the appropriate binding time.

**Pattern 3: Type-Erased Policy Adapters**

When you need to store heterogeneous policy objects in a container or pass them across API boundaries, type erasure bridges the gap. The policy-based host is wrapped in an erased container that erases the specific policy type while preserving the interface:

```cpp
// The "any serializer" wrapper
class AnySerializer {
public:
    template<typename S>
    explicit AnySerializer(S serializer)
        : storage_(std::make_shared<Model<S>>(std::move(serializer))) {}

    std::string serialize(const Data& data) const {
        return storage_->serialize(data);
    }

private:
    struct Concept {
        virtual ~Concept() = default;
        virtual std::string serialize(const Data&) const = 0;
    };

    template<typename S>
    struct Model : Concept {
        explicit Model(S s) : serializer_(std::move(s)) {}
        std::string serialize(const Data& data) const override {
            return serializer_.serialize(data);
        }
        S serializer_;
    };

    std::shared_ptr<const Concept> storage_;
};
```

Now `AnySerializer` can be used polymorphically without templates, but internally it delegates to any policy-based serializer. This is how `std::function` works: it type-erases any callable into a single runtime type.

### Decision Framework

The choice between policy-based design and runtime polymorphism depends on the specific requirements of each concern in the system. The following table summarizes the trade-offs:

| Dimension | Policy-Based Design | Runtime Polymorphism |
|---|---|---|
| Performance (hot path) | No overhead, inlining possible | Vtable dispatch, no inlining |
| Instruction cache | Multiple code paths | Single code path |
| Flexibility (when) | Compile time only | Any time (startup, runtime, plugins) |
| Binary size | Multiplicative (N × M instantiations) | Additive (N + M classes) |
| Compile time | Longer (template instantiation) | Shorter (one compilation) |
| Error messages | Poor (template backtrace) | Good (direct error location) |
| Team accessibility | Requires template expertise | Basic OOP |
| Mocking | Limited (template-based) | Full (virtual-based frameworks) |
| Binary distribution | Header-only required | Shared libraries work |
| Combinatorial scale | Excellent (N × M combinations) | Good (N + M implementations) |

**Use policy-based design when:**

- The policy choices are known at compile time and will not change during execution.
- The policy calls are on a hot path and the operation is small enough that inlining matters.
- You are writing a header-only library where users explicitly select combinations.
- You need to combine multiple orthogonal dimensions and the number of combinations exceeds the number of implementations (combinatorial advantage).
- You are writing performance-critical code for embedded systems, games, or high-frequency trading where every indirection counts.

**Use runtime polymorphism when:**

- The behavior needs to change at runtime (configuration files, user input, plugin systems).
- You are distributing a binary library that must work across different calling contexts.
- The operation is large enough that vtable overhead is negligible.
- You need to mock the dependency for testing.
- Your team has mixed C++ expertise and the template complexity would be a barrier.
- You need stable ABI across compiler versions or platform boundaries.

**Use the hybrid approach when:**

- Some concerns are compile-time fixed while others are runtime configurable.
- You want the performance of policies internally but the simplicity of runtime types externally.
- You need to store heterogeneous policy instances in containers or pass them through non-template interfaces.

### Summary

Policy-based design and runtime polymorphism solve the same problem—varying behavior independently from the host—but at different binding times. The choice between them is not a matter of one being "better" but of matching the binding time to the requirement.

Policy-based design excels when the set of variations is fixed at compile time and performance matters. Runtime polymorphism excels when the set of variations is open at runtime and maintainability matters. The hybrid patterns show that these are not mutually exclusive: you can use policy-based design for the internals that benefit from compile-time optimization and runtime polymorphism for the boundaries that need runtime flexibility.

The key insight is that binding time is a design parameter, not an ideology. Each concern in a system can have its own binding time, chosen based on where it falls on the performance-flexibility spectrum. A serializer bound at compile time. A compression algorithm bound at compile time. An encryption standard bound at runtime. All in the same class, each using the technique that fits its requirements.

## Expression Templates

Expression templates are a C++ metaprogramming technique where arithmetic expressions are encoded as template types, deferring computation until the expression is assigned or evaluated. The expression itself becomes a type—a compile-time tree structure where each node represents an operation, and each leaf represents an operand. This deferred representation enables optimizations that are impossible with eager evaluation: loop fusion, elimination of temporaries, and domain-specific algebraic transformations.

The connection to policy-based design is deep. Expression templates use the same compile-time composition mechanism: operations are policy classes that transform inputs, and the expression tree is a hierarchy of composed policies. The expression type determines *how* computation proceeds—which operations fuse, which temporaries are elided, which algebraic identities apply—all resolved at compile time through template instantiation.

This section introduces expression templates as a policy-based technique and shows how policies control expression evaluation behavior. Chapter 31 covers expression templates in full depth, including advanced implementation patterns and integration with the C++ type system. Here we focus on how the policy mindset applies: what the policies are, how they compose, and where the design decisions lie.

### Expression Structure as Policy Composition

Consider a vector addition expression `a + b + c`. Under eager evaluation, this creates a temporary for `a + b`, then adds `c`. Under expression templates, the expression `a + b + c` is represented by a type like:

```
Add<Add<VecExpr, VecExpr>, VecExpr>
```

This type is not computed yet—it is a description of the computation. Each node in this type tree is a policy that knows how to perform its operation. The root `Add` policy composes the inner `Add` policy and the leaf `VecExpr` policy:

```cpp
// Leaf: represents a vector variable in the expression
template<typename T>
class VecExpr {
public:
    explicit VecExpr(const T* data) : data_(data) {}

    T operator[](size_t i) const { return data_[i]; }
    size_t size() const { /* ... */ }

private:
    const T* data_;
};

// Operation node: an Add policy that composes two sub-expressions
template<typename LHS, typename RHS>
struct Add {
    const LHS& lhs_;
    const RHS& rhs_;

    Add(const LHS& lhs, const RHS& rhs) : lhs_(lhs), rhs_(rhs) {}

    auto operator[](size_t i) const {
        return lhs_[i] + rhs_[i];
    }

    size_t size() const { return lhs_.size(); }
};

// The expression type is composed:
// Add<Add<VecExpr<double>, VecExpr<double>>, VecExpr<double>>
```

This is pure policy composition. Each `Add` node is a policy parameterized by its operand types, and the full expression tree is a nested composition of policies. The computation is produced by walking this tree at evaluation time, but the tree itself—the type—is assembled at compile time.

The policy perspective reveals the design space: you can create policies for different operations (add, multiply, subtract, sin, cos, abs, clamp), for different storage strategies (reference, value, lazy-loaded), and for different evaluation strategies (element-by-element, block-wise, vectorized). All of these are template parameters that determine how the expression computes.

### Evaluation Policy: Lazy vs Eager

The most fundamental policy in expression templates is the evaluation strategy. Should the expression compute immediately (eager) or defer until assigned (lazy)? This is a binary choice that affects memory usage, optimization opportunities, and API design.

Lazy evaluation (the default for expression templates) builds the expression tree but does not compute until the result is assigned to a concrete object:

```cpp
// Lazy expression: no computation happens here
auto expr = vec_a + vec_b + vec_c;

// Computation happens here: operator= converts the expression to a concrete vector
Vector result = expr;

// Or equivalently, at the assignment:
Vector result = vec_a + vec_b + vec_c;
```

The evaluation policy is encoded in the expression type itself. A `Vector` class can accept any expression type and compute eagerly upon assignment:

```cpp
class Vector {
public:
    template<typename Expr>
    Vector& operator=(const Expr& expr) {
        for (size_t i = 0; i < size_; ++i) {
            data_[i] = expr[i];  // Triggers full expression evaluation per element
        }
        return *this;
    }

private:
    std::vector<double> data_;
    size_t size_;
};
```

The loop `for each i: expr[i]` is where the fused computation occurs. Instead of computing `temp = a + b`, then `result = temp + c`, the loop computes `result[i] = a[i] + b[i] + c[i]` in one pass. This is loop fusion, and it eliminates the temporary vector and the associated allocation and copy.

An eager policy would compute intermediate results immediately:

```cpp
// Eager evaluation policy
struct EagerEval {
    template<typename LHS, typename RHS>
    static auto compute(const LHS& lhs, const RHS& rhs) {
        // Compute the full result now, return a concrete Vector
        Vector result(lhs.size());
        for (size_t i = 0; i < lhs.size(); ++i) {
            result[i] = lhs[i] + rhs[i];
        }
        return result;
    }
};

// The operation policy uses the evaluation policy
template<typename LHS, typename RHS, typename Eval = LazyEval>
struct Add;
```

The choice between lazy and eager affects memory usage. Lazy evaluation avoids temporaries but requires the operands to outlive the expression. Eager evaluation creates temporaries but can free operands immediately. The right choice depends on whether the expression is used briefly (lazy wins) or stored for later (eager wins):

```cpp
// Lazy: operands must outlive the expression
auto expr = vec_a + vec_b;
// ... some code ...
// If vec_a or vec_b are destroyed here, expr becomes dangling
Vector result = expr;  // Undefined behavior if vec_a is gone

// Eager: temporaries captured by value, no lifetime issue
auto expr = eager_add(vec_a, vec_b);
// vec_a and vec_b can be safely destroyed
```

### Storage Policy: Reference vs Value Semantics

Expression nodes hold their operands by reference by default (to avoid copying large vectors). But this creates the lifetime problem above. A storage policy controls whether operands are held by reference (cheap, risky) or by value (safe, potentially expensive):

```cpp
// Reference storage: points to existing data, zero-copy
template<typename T>
struct ByReference {
    using storage_type = const T&;
    static constexpr bool is_owning = false;

    static const T& access(const T& ref) { return ref; }
};

// Value storage: copies small operands, safe, owning
template<typename T>
struct ByValue {
    using storage_type = T;
    static constexpr bool is_owning = true;

    static const T& access(const T& val) { return val; }
};

// The expression node is parameterized by storage policy
template<typename LHS, typename RHS,
         typename Storage = ByReference<LHS>>
struct Add {
    typename Storage::storage_type lhs_;
    typename Storage::storage_type rhs_;

    Add(const LHS& lhs, const RHS& rhs)
        : lhs_(Storage::access(lhs))
        , rhs_(Storage::access(rhs)) {}
};
```

For scalar operands (which are cheap to copy), the storage policy should be `ByValue`. For vector operands (which are expensive to copy), it should be `ByReference`. The policy can be selected automatically using type traits:

```cpp
template<typename T>
using DefaultStorage = std::conditional_t<
    sizeof(T) <= sizeof(double) * 4,  // Small objects: copy
    ByValue<T>,
    ByReference<T>
>;
```

This is an instance of the "policy selection via type traits" pattern from the Combining Policies section. The expression template infrastructure can automatically choose storage strategies based on operand characteristics.

### Element Access and Traversal Policy

How elements are accessed and computed is another dimension of policy. The simplest policy accesses elements one at a time with `operator[]`. More advanced policies can batch access for vectorized instructions (SIMD), reorder traversal for cache locality, or parallelize across threads:

```cpp
// Sequential element access
struct SequentialAccess {
    template<typename Expr, typename Func>
    static void traverse(const Expr& expr, Func&& func) {
        for (size_t i = 0; i < expr.size(); ++i) {
            func(expr[i], i);
        }
    }
};

// SIMD-vectorized access (using hypothetical SIMD wrapper)
struct SimdAccess {
    template<typename Expr, typename Func>
    static void traverse(const Expr& expr, Func&& func) {
        for (size_t i = 0; i < expr.size(); i += simd_width) {
            auto vec = simd_load(expr, i);
            func(vec, i);
        }
    }
};

// Parallel access
struct ParallelAccess {
    template<typename Expr, typename Func>
    static void traverse(const Expr& expr, Func&& func) {
        #pragma omp parallel for
        for (size_t i = 0; i < expr.size(); ++i) {
            func(expr[i], i);
        }
    }
};
```

The `Vector::operator=` from earlier can accept the traversal policy as a template parameter:

```cpp
template<typename Expr, typename Traversal = SequentialAccess>
class VectorExprAssignment {
public:
    static void assign(Vector& result, const Expr& expr) {
        Traversal::traverse(expr, [&](auto value, size_t i) {
            result[i] = value;
        });
    }
};
```

This lets the caller choose the evaluation strategy per assignment:

```cpp
Vector result(vec.size());
VectorExprAssignment<decltype(expr), SimdAccess>::assign(result, expr);
```

Or, more practically, encode the traversal policy in the vector type itself:

```cpp
template<typename T, typename Traversal = SequentialAccess>
class Vector {
    // ...
    template<typename Expr>
    Vector& operator=(const Expr& expr) {
        Traversal::traverse(expr, [&](auto value, size_t i) {
            data_[i] = value;
        });
        return *this;
    }
};

using SimdVector = Vector<double, SimdAccess>;
using ParallelVector = Vector<double, ParallelAccess>;
```

### Complete Example: Policy-Driven Expression Template

Putting the pieces together, here is a minimal but complete expression template for vector arithmetic that uses policies for evaluation strategy and storage:

```cpp
#include <vector>
#include <cstddef>
#include <type_traits>

// ---- Storage policies ----
struct RefStorage {
    template<typename T>
    using type = const T&;

    template<typename T>
    static const T& wrap(const T& t) { return t; }

    static constexpr bool owning = false;
};

struct ValStorage {
    template<typename T>
    using type = T;

    template<typename T>
    static T wrap(const T& t) { return t; }

    static constexpr bool owning = true;
};

// ---- Expression base (CRTP) ----
template<typename Derived>
class Expr {
public:
    auto operator[](size_t i) const { return static_cast<const Derived&>(*this)[i]; }
    size_t size() const { return static_cast<const Derived&>(*this).size(); }
};

// ---- Concrete vector ----
template<typename T, typename Access = SequentialAccess>
class Vector : public Expr<Vector<T, Access>> {
public:
    explicit Vector(size_t n) : data_(n) {}

    template<typename E>
    Vector(const Expr<E>& expr) : data_(expr.size()) {
        Access::traverse(static_cast<const E&>(expr), [&](auto v, size_t i) {
            data_[i] = v;
        });
    }

    T& operator[](size_t i) { return data_[i]; }
    const T& operator[](size_t i) const { return data_[i]; }
    size_t size() const { return data_.size(); }

private:
    std::vector<T> data_;
};

// ---- Binary operation node ----
template<typename Op, typename LHS, typename RHS,
         typename StorageLHS = RefStorage,
         typename StorageRHS = RefStorage>
class BinExpr : public Expr<BinExpr<Op, LHS, RHS, StorageLHS, StorageRHS>> {
public:
    BinExpr(const LHS& lhs, const RHS& rhs)
        : lhs_(StorageLHS::wrap(lhs)), rhs_(StorageRHS::wrap(rhs)) {}

    auto operator[](size_t i) const {
        return Op::apply(lhs_[i], rhs_[i]);
    }

    size_t size() const { return lhs_.size(); }

private:
    typename StorageLHS::template type<LHS> lhs_;
    typename StorageRHS::template type<RHS> rhs_;
};

// ---- Operation policies ----
struct AddOp {
    template<typename T>
    static auto apply(const T& a, const T& b) { return a + b; }
};

struct MulOp {
    template<typename T>
    static auto apply(const T& a, const T& b) { return a * b; }
};

// ---- Operator overloads (expression builders) ----
template <typename T> struct is_vector : std::false_type {};
template <typename T, typename A> struct is_vector<Vector<T, A>> : std::true_type {};
template <typename T> inline constexpr bool is_vector_v = is_vector<T>::value;

// ---- Operator overloads (expression builders) ----
template<typename LHS, typename RHS>
auto operator+(const Expr<LHS>& lhs, const Expr<RHS>& rhs) {
    // Select storage: use ValStorage for expressions (already lightweight),
    // RefStorage for concrete vectors
    using StorageL = std::conditional_t<
        std::is_base_of_v<Expr<LHS>, LHS> && !is_vector_v<LHS>,
        ValStorage, RefStorage>;
    using StorageR = std::conditional_t<
        std::is_base_of_v<Expr<RHS>, RHS> && !is_vector_v<RHS>,
        ValStorage, RefStorage>;

    return BinExpr<AddOp, LHS, RHS, StorageL, StorageR>(
        static_cast<const LHS&>(lhs),
        static_cast<const RHS&>(rhs)
    );
}

// Usage:
// Vector<double> a(100), b(100), c(100);
// Vector<double> result = a + b + c;
// -- No temporary vectors are created --
// -- The loop computes result[i] = a[i] + b[i] + c[i] in one pass --
```

This example demonstrates how policy-based design applies to expression templates at multiple levels:

- **Operation policies** (`AddOp`, `MulOp`) are the most fundamental: each is a stateless policy with a single static `apply` method.
- **Storage policies** (`RefStorage`, `ValStorage`) control whether operands are held by reference or by value, trading safety for performance.
- **Traversal policies** (`SequentialAccess`, `SimdAccess`, `ParallelAccess`) control how elements are computed—sequentially, with vector instructions, or in parallel.
- **Type-trait-based policy selection** chooses the appropriate storage policy automatically based on operand characteristics.

The host class is `BinExpr`, templated on all of these policies. Each combination produces a different expression type with different behavior, all without runtime overhead for the policy selection.

### The Policy Nature of Expression Rewriting

A more advanced application of policies in expression templates is *expression rewriting*: transforming the expression tree before evaluation to apply algebraic optimizations. Common rewrites include:

- Constant folding: `(2 + 3) * x` → `5 * x`
- Distributive law: `a * x + b * x` → `(a + b) * x`
- Identity elimination: `x * 0` → `0`, `x + 0` → `x`
- Associative reordering: `(a + b) + c` → `a + (b + c)` for better pipelining

Each rewrite can be implemented as a policy that transforms one expression type into another:

```cpp
// Identity elimination policy: removes no-op operations
template<typename Expr>
struct EliminateIdentities {
    // Default: no transformation
    using type = Expr;
};

// Specialization: multiply by zero becomes zero
template<typename T>
template<int N>
struct Scalar {
    static constexpr int value = N;
    auto operator[](size_t) const { return N; }
    size_t size() const { return 0; } // Scalars have no size in this context
};

// Identity elimination policy: removes no-op operations
template<typename Expr>
struct EliminateIdentities {
    // Default: no transformation
    using type = Expr;
};
    using type = Scalar<0>;
};

// Specialization: add zero becomes identity
template<typename T>
struct EliminateIdentities<BinExpr<AddOp, T, Scalar<0>>> {
    using type = T;  // Just the other operand
};
```

The host applies these rewrites before constructing the expression:

```cpp
template<typename RewritePolicy, typename Expr>
using OptimizedExpr = typename RewritePolicy::template apply<Expr>;

// Usage:
// auto expr = a + 0;
// The expression type is rewritten from BinExpr<AddOp, Vec, Scalar<0>> to Vec
```

These rewriting policies are themselves composable. A pipeline of rewrite policies can apply multiple transformations:

```cpp
template<typename Expr>
using Optimized = EliminateIdentities<
                   ConstantFold<
                    DistributeMul<Expr>>>;
```

This is policy-based design applied to the expression template itself: not just controlling how elements are computed, but transforming the computation graph before execution.

### Complexity and Compile-Time Costs

Expression templates impose significant compile-time costs. Each expression creates a unique nested type, and deeply nested expressions can produce types with hundreds of template parameters. Compilers must instantiate, specialize, and optimize these types, which consumes memory and time:

```cpp
// A moderately complex expression:
auto expr = a * b + c * d - e / f + sin(g);

// The type is:
// Add<Add<Mul<Vec, Vec>, Mul<Vec, Vec>>,
//     Sub<Div<Vec, Vec>,
//         Sin<Vec>>>
// Each node is a distinct instantiation
```

For a single expression, this is manageable. For a library that evaluates many expressions in different contexts, the total number of instantiations can rival a policy-based container with many policies. Compile times of minutes are not uncommon for libraries like Eigen (which uses expression templates extensively).

Debugging expression templates is also challenging. The types in compiler error messages and debugger call stacks can be hundreds of characters long, and a simple type mismatch (e.g., adding a vector and a matrix) produces a page of template instantiation backtrace. C++20 concepts improve this, but most expression template libraries target C++17 or earlier.

### When Expression Templates Belong in a Policy-Based Chapter

Expression templates appear in this chapter, rather than solely in Chapter 31, because they are a direct application of policy-based thinking to computation. The key insights that connect them are:

- **Computation is a type**: In policy-based design, behavior is a template parameter. In expression templates, the computation itself is a type—a nested composition of operation and storage policies.
- **Policy composition scales to trees**: The same mechanisms that combine two or three policies in a host class combine dozens of operation nodes in an expression tree.
- **Zero-cost abstraction is the goal**: Both techniques aim to make the abstraction invisible after compilation. A policy-based container has the same layout as a handwritten one; an expression template produces the same machine code as a hand-fused loop.
- **Policy selection can be automatic**: Type-trait-based policy selection, discussed in the Combining Policies section, finds a natural application in expression templates where storage and traversal choices can be inferred from operand types.

Chapter 31 builds on this foundation with advanced implementation techniques: expression trees with multiple return types, integration with custom allocators, inter-expression optimization across statement boundaries, and the interaction between expression templates and C++20 ranges.

### Summary

Expression templates extend policy-based design from class configuration to computation representation. The expression is a compile-time tree of operation policies, each parameterized by its operand types and storage strategy. The key policies in expression template design—evaluation strategy (lazy vs eager), storage (reference vs value), traversal (sequential vs SIMD vs parallel), and algebraic rewriting—all follow the same patterns established earlier in this chapter.

The compile-time cost of expression templates is significant, and the debugging difficulty is real. But for performance-critical numerical code—linear algebra, signal processing, physics simulations—expression templates provide optimizations that are impossible to achieve with runtime polymorphism or eager evaluation. The machine code that results from `a + b + c` with expression templates is identical to a hand-written fused loop, but the abstraction is far more composable and maintainable.

Expression templates represent the furthest extent of the policy-based design philosophy: not just "class behavior as a template parameter," but "computation itself as a template type." This unification of data and computation at compile time is what makes C++ template metaprogramming unique among mainstream languages.

