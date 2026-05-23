# Appendix B: Idioms Quick Reference

This appendix provides an alphabetical reference of every idiom discussed in the book, with a one-paragraph definition, the minimum C++ standard required, and guidance on when to use it.

---

## Alphabetical Reference

### Adapter (Class/Object/Template)
*Ch. 23 — Structural Patterns*

An adapter converts one interface to another. A *class adapter* inherits from both the target interface and the adaptee. An *object adapter* composes the adaptee. A *template adapter* performs the adaptation at compile time with zero runtime cost. Prefer object adapters when the adaptee's interface is large or when runtime flexibility matters; prefer template adapters when the adaptation is known at compile time and every cycle counts.

- **Minimum standard**: C++98
- **When to use**: You need to integrate a type whose interface does not match the one your code expects, and you cannot (or should not) modify the original type.

### Abstract Factory with Type Lists
*Ch. 22 — Creational Patterns*

An abstract factory parameterized by a type list, where each type in the list corresponds to a product. A `std::index_sequence` drives the instantiation of factory functions. Enables compile-time creation of factory hierarchies without code duplication.

- **Minimum standard**: C++14 (variadic templates, index sequences)
- **When to use**: You need families of related objects, and the product types are known at compile time.

### Actor Model (Concurrent)
*Ch. 14 — Concurrent Data Structures*

Each actor is an object that owns its state and communicates with other actors only through message passing. A thread-safe queue provides the communication channel. Actors avoid shared state entirely, eliminating most concurrency bugs.

- **Minimum standard**: C++11 (thread, mutex, queue)
- **When to use**: Your concurrency model benefits from isolated state and explicit message boundaries; you want to avoid shared-mutex contention.

### Adaptor, Custom Range
*Ch. 26 — Range and Views*

A C++20 range adaptor is a view class that wraps an underlying range and produces transformed elements on demand. Custom adaptors inherit from `std::ranges::view_interface` and implement a pipe operator via `range_adaptor_closure`. Stateful adaptors require careful lifetime management.

- **Minimum standard**: C++20 (ranges, views)
- **When to use**: The built-in adaptors do not cover your transformation; you need a reusable lazy view.

### Alias Template for Type Transformation
*Ch. 32 — Variadic Templates Patterns*

An alias template applied to each element of a parameter pack via `F<Ts>...` produces a new pack of transformed types. This is the type-level equivalent of `std::transform`.

- **Minimum standard**: C++11
- **When to use**: You need to map a metafunction over a parameter pack.

### Allocator-Aware Container
*Ch. 29 — Container Design*

A container that accepts a custom allocator and respects propagation policies (`propagate_on_container_copy_assignment`, `propagate_on_container_move_assignment`, `propagate_on_container_swap`). Stateful allocators require careful handling of the allocator traits interface.

- **Minimum standard**: C++11
- **When to use**: You are implementing a custom container that must support `std::scoped_allocator_adaptor`, PMR, or other custom allocation strategies.

### Any (Type Erasure)
*Ch. 8 — Type Erasure*

`std::any` stores a value of any type that satisfies `std::is_copy_constructible`. It uses the external polymorphism pattern (a non-virtual interface with a type-erased base) to hide the concrete type. Retrieval requires `std::any_cast`, which throws if the type does not match.

- **Minimum standard**: C++17
- **When to use**: You need a variable that can hold values of unrelated types, and the set of possible types is not known at compile time. Often used for script-embedding or plugin interfaces.

### Apply (`std::apply`)
*Ch. 32 — Variadic Templates Patterns*

`std::apply` calls a function with the elements of a tuple as arguments. Internally, it generates an index sequence and expands `std::get<Is>(t)...`. This is the canonical pattern for unpacking a tuple into a function call.

- **Minimum standard**: C++17
- **When to use**: You have a tuple and a function, and you want to call the function with the tuple's elements as arguments.

### Array of Structures (AoS) vs Structure of Arrays (SoA)
*Ch. 21 — Cache-Friendly Patterns*

AoS stores all fields of one object contiguously; SoA stores each field in its own contiguous array. SoA improves cache utilization when algorithms operate on a single field across many objects. Hybrid AoSoA (Array of Struct-of-Arrays) groups N objects per chunk for SIMD-friendly access.

- **Minimum standard**: C++11
- **When to use**: SoA when processing a single field of many objects (e.g., updating positions but not velocities); AoS when accessing multiple fields of one object simultaneously; AoSoA for SIMD with larger-than-native vector widths.

### Awaitable Type
*Ch. 27 — Coroutines and Async*

An awaitable type implements `await_ready`, `await_suspend`, and `await_resume` for use with `co_await`. Library authoring requires defining a promise type and connecting it to the coroutine handle.

- **Minimum standard**: C++20
- **When to use**: You are implementing a coroutine-enabled library (e.g., a task system, a generator, or an async I/O runtime).

### Barrier (Memory) Patterns
*Ch. 13 — Thread-Safe Interfaces*

Memory barriers (fences) order memory operations across threads. In C++, atomics implicitly provide the required barriers; explicit fences (`std::atomic_thread_fence`) are needed only when ordering non-atomic accesses.

- **Minimum standard**: C++11
- **When to use**: You are implementing lock-free data structures and need fine-grained control over memory ordering. Prefer `std::atomic` operations with explicit ordering parameters over raw fences.

### Bind (`std::bind`)
*Ch. 11 — Function Composition*

`std::bind` creates a callable from a function and a subset of its arguments, using placeholders (`_1`, `_2`, ...) for deferred arguments.

- **Minimum standard**: C++11
- **When to use**: In legacy code; for new code, prefer lambdas, which are more readable and provide better constexpr support.

### Builder / Fluent Interface
*Ch. 22 — Creational Patterns; Ch. 28 — API Design*

Each setter returns `*this` (a reference to the object), enabling chained calls. The builder accumulates configuration and produces the final object in a `build()` step.

- **Minimum standard**: C++98
- **When to use**: Construction requires many optional parameters, or configuration involves a sequence of steps.

### Cache Line Alignment
*Ch. 21 — Cache-Friendly Patterns*

`alignas(std::hardware_destructive_interference_size)` ensures that variables accessed by different threads lie on different cache lines, preventing false sharing. Conversely, `alignas(std::hardware_constructive_interference_size)` places frequently accessed data on the same line.

- **Minimum standard**: C++17
- **When to use**: Use destructive alignment for thread-local counters or producer-consumer flags to avoid false sharing. Use constructive alignment for hot data accessed in a tight loop.

### Command Pattern with Type Erasure
*Ch. 24 — Behavioral Patterns*

Encapsulates a request as an object. In C++, type erasure (e.g., `std::function`) stores commands of different types uniformly. Queues of commands enable undo, logging, and deferred execution.

- **Minimum standard**: C++11 (`std::function`); C++17 (`std::any` for more general commands)
- **When to use**: You need to parameterize objects with operations, queue operations, or support undo/redo.

### Composition over Inheritance
*Ch. 4 — Object Composition*

Instead of inheriting behavior from a base class, compose the object from independent capability objects. This avoids the combinatorial explosion of deep inheritance hierarchies.

- **Minimum standard**: C++98
- **When to use**: When you find yourself adding "is-a" relationships that do not truly model the domain; when you need runtime flexibility that inheritance cannot provide.

### Concepts (C++20)
*Ch. 10 — Tag Dispatch and SFINAE; Ch. 15 — Type Manipulation*

Named constraints on template parameters. Concepts replace SFINAE for most type-checking use cases, produce better error messages, and enable function overloading on type properties.

- **Minimum standard**: C++20
- **When to use**: Whenever you would previously use `enable_if` or `void_t` to constrain a template. Also use to document the requirements of a template interface.

### constexpr and consteval
*Ch. 2 — C++ Fundamentals; Ch. 20 — Zero-Cost Abstractions*

`constexpr` functions can be evaluated at compile time if all arguments are constant. `consteval` functions are *required* to be evaluated at compile time. Together, they enable compile-time computation without template metaprogramming.

- **Minimum standard**: C++11 (basic `constexpr`); C++14 (loops); C++17 (if constexpr); C++20 (consteval)
- **When to use**: Use `constexpr` for any function that can reasonably be computed at compile time. Use `consteval` when the function must never reach runtime.

### Contract Programming
*Ch. 19 — Defensive Programming*

Preconditions, postconditions, and invariants specified as part of the function signature (C++26: `[[pre: ...]]`, `[[post: ...]]`, `[[assert: ...]]`). Enforce correctness at function boundaries.

- **Minimum standard**: C++26 (native support); C++98 (manual via `assert()`)
- **When to use**: Any public API should document its preconditions. Use contracts for validation that must be testable and optionally disabled in production.

### Coroutine (Generator / Task)
*Ch. 27 — Coroutines and Async*

A coroutine is a function that can suspend and resume. In C++, the coroutine is defined by its return type, which must satisfy the promise-type protocol. `std::generator<T>` (C++23) is the standard generator.

- **Minimum standard**: C++20 (coroutine framework); C++23 (`std::generator`)
- **When to use**: Generators for lazy sequences; tasks for asynchronous operations; co_await for callbacks that would otherwise compose poorly.

### CRTP (Curiously Recurring Template Pattern)
*Ch. 9 — CRTP and Static Polymorphism*

A derived class passes itself as a template argument to its base class: `struct Derived : Base<Derived>`. The base can then call static member functions of the derived class, achieving compile-time polymorphism.

- **Minimum standard**: C++98
- **When to use**: You need static polymorphism (no virtual dispatch); you are implementing mixin behavior accessed from a base; you want the enable_shared_from_this pattern.

### Custom Deleter
*Ch. 6 — Smart Pointers and Ownership*

A `std::unique_ptr` can accept a custom deleter, either as a function pointer, a lambda, or a functor. This is the standard pattern for wrapping C-style handles (file descriptors, sockets, library contexts).

- **Minimum standard**: C++11
- **When to use**: When managing resources other than heap memory (files, sockets, database connections); when the resource requires non-default deallocation.

### Data-Oriented Design
*Ch. 21 — Cache-Friendly Patterns*

Design data structures around access patterns rather than around objects. Separate hot (frequently accessed) fields from cold fields. Process arrays of data in streams rather than objects one at a time.

- **Minimum standard**: C++98 (language); requires profiler-guided optimization
- **When to use**: Performance-critical systems where cache misses dominate (games, real-time simulation, databases).

### Decorator (Runtime / Template / Policy)
*Ch. 23 — Structural Patterns*

Adds behavior to an object without modifying its interface. Runtime decorators use virtual dispatch and `unique_ptr` ownership. Template decorators use CRTP for compile-time composition. Policy-based decorators use tag dispatch for fine-grained control.

- **Minimum standard**: C++11 (runtime); C++98 (CRTP template); C++11 (policy)
- **When to use**: When you need to add optional, layered behavior without affecting the core type or other clients.

### Detection Idiom (`void_t`)
*Ch. 10 — Tag Dispatch and SFINAE; Ch. 33 — Reflection*

A pattern using `void_t<T>` to enable partial specialization on expression validity. Detects whether a type has a member type, function, or data member at compile time.

- **Minimum standard**: C++11 (alias templates, SFINAE); C++17 (`void_t`)
- **When to use**: When you need to check a type property that is not covered by `<type_traits>`; when C++20 concepts are unavailable.

### Double-Checked Locking
*Ch. 14 — Concurrent Data Structures*

A two-step lock: check the shared resource without locking, then lock and recheck if an update is needed. In C++, the first check must use an atomic to prevent data races. `std::call_once` and `std::once_flag` are often cleaner alternatives.

- **Minimum standard**: C++11 (atomic)
- **When to use**: Lazy initialization of a shared resource with infrequent writes. Prefer `std::call_once` unless you need the explicit two-step pattern.

### Emplace vs Insert
*Ch. 29 — Container Design*

`emplace` constructs the element in place from arguments, avoiding a temporary. However, `emplace` is not always an optimization — it can cause narrowing conversions or leak exceptions from the constructor. `try_emplace` (C++17) avoids the temporary key construction for associative containers.

- **Minimum standard**: C++11 (emplace); C++17 (try_emplace)
- **When to use**: Use `emplace` when the arguments are not already wrapped in a value object. Use `insert` when you already have a value.

### Error Code vs Exception
*Ch. 18 — Error Handling Idioms*

Error codes (`std::error_code`) are lightweight, deterministic, and suited for expected failures. Exceptions are for truly exceptional conditions that cannot be handled locally. `std::expected` (C++23) provides a middle ground.

- **Minimum standard**: C++98 (exceptions); C++11 (`std::error_code`); C++23 (`std::expected`)
- **When to use**: Use error codes in performance-critical hot paths and in interfaces that must not throw. Use exceptions for errors that propagate across many abstraction layers.

### Expected / Result Types
*Ch. 18 — Error Handling Idioms*

`std::expected<T, E>` (C++23) holds either a value of type `T` or an error of type `E`. It provides a monadic interface: `and_then`, `or_else`, `transform`, `transform_error`. This is the idiomatic way to handle recoverable errors without exceptions.

- **Minimum standard**: C++23
- **When to use**: For functions that can fail but where the failure is an expected outcome (validation, parsing, I/O).

### Expression Templates
*Ch. 31 — Expression Templates*

A technique where arithmetic operators return proxy objects that capture the expression structure instead of computing eagerly. The assignment operator evaluates the entire expression in a fused loop. Used by Eigen, Blaze, and Boost.Lambda.

- **Minimum standard**: C++11 (move semantics, perfect forwarding); C++17 (fold expressions)
- **When to use**: When implementing a domain-specific embedded language (DSEL) for vector/matrix arithmetic, or any operation that benefits from loop fusion.

### Facade
*Ch. 23 — Structural Patterns*

Provides a unified interface to a set of subsystem interfaces. In C++, facades are often combined with RAII (the facade acquires and releases subsystem resources), and compile-time facades use template parameter packs and fold expressions.

- **Minimum standard**: C++98 (runtime); C++11 (variadic compile-time)
- **When to use**: To simplify a complex subsystem API; to create a single entry point for initialization and cleanup.

### Factory Method / Virtual Constructor
*Ch. 3 — Object Creation and Destruction*

A base class provides a virtual `clone()` or `create()` that each derived class implements. Returns a smart pointer (typically `unique_ptr`) to the base. The virtual constructor idiom solves the problem of constructing objects when the concrete type is unknown.

- **Minimum standard**: C++11 (unique_ptr return)
- **When to use**: When code must create objects of a type known only through a base-class pointer.

### Flat Map / Flat Set
*Ch. 23 — Structural Patterns*

A sorted vector container with STL interface. Lower memory overhead and better cache performance than tree-based associative containers. Insertion/deletion costs are higher (O(n)).

- **Minimum standard**: C++23
- **When to use**: When the container is updated rarely but queried frequently; when memory is constrained.

### Flyweight
*Ch. 23 — Structural Patterns*

Splits an object into intrinsic (shared, immutable) and extrinsic (context-dependent, mutable) state. A factory manages the shared intrinsic objects. Often used in text rendering (shared glyph shapes) and game development.

- **Minimum standard**: C++11 (smart pointers for automatic reclamation of shared objects)
- **When to use**: When a large number of similar objects can share state, and the cost of storing duplicated state is measurable.

### Fold Expressions
*Ch. 16 — Compile-Time Computation; Ch. 32 — Variadic Templates*

A fold expression applies a binary operator to all elements of a parameter pack: `(args + ...)`. Unary folds apply the operator; binary folds provide an initial value. C++17 introduced left, right, unary, and binary folds.

- **Minimum standard**: C++17
- **When to use**: Any operation over a parameter pack that can be expressed with a binary operator (sum, product, logical and/or, comma sequencing).

### Function Adapters
*Ch. 11 — Function Composition*

Wrappers that modify the behavior of a function: `std::not_fn` for negation, `std::bind_front` for partial application, and custom adapters for composition.

- **Minimum standard**: C++17 (`std::not_fn`); C++20 (`std::bind_front`)
- **When to use**: When you need to adapt a function's signature or behavior without rewriting it.

### Futures and Promises
*Ch. 14 — Concurrent Data Structures*

`std::future` receives a value (or exception) from a `std::promise` (or `std::packaged_task`). Enables one-shot communication between threads. For repeated or composable async, prefer coroutines or sender/receiver.

- **Minimum standard**: C++11
- **When to use**: Simple async one-shot operations. For complex pipelines, use `std::async` with launch policies, or move to C++20 coroutines.

### Generator (Coroutine)
*Ch. 27 — Coroutines and Async*

A coroutine that produces a sequence of values lazily, using `co_yield` to suspend after each value. `std::generator<T>` (C++23) is the standard implementation.

- **Minimum standard**: C++20 (coroutines); C++23 (`std::generator`)
- **When to use**: When producing a sequence of values where eager generation would be expensive or infinite.

### Handle/Body (Pimpl)
*Ch. 4 — Object Composition*

A pointer-to-implementation hides the class's private members from its header. With `std::unique_ptr` and a destructor declared in the `.cpp` file, the Pimpl idiom provides compilation firewalls and ABI stability.

- **Minimum standard**: C++11 (unique_ptr); C++98 (raw pointer, manual destruction)
- **When to use**: Large classes where implementation changes should not force recompilation of clients; library interfaces requiring ABI stability.

### Higher-Order Functions
*Ch. 11 — Function Composition*

Functions that accept other functions as parameters or return them. Supported by C++ through function pointers, `std::function`, and (most idiomatically) templates and lambdas.

- **Minimum standard**: C++11 (lambdas, `std::function`)
- **When to use**: When the behavior of a function depends on an operation that its caller should customize (e.g., `std::sort` with a custom comparator).

### Index Sequence
*Ch. 32 — Variadic Templates Patterns*

`std::index_sequence<Is...>` and its generator `std::make_index_sequence<N>` produce a pack of `std::size_t` constants from 0 to N-1. Used to drive algorithm iteration over parameter packs and tuple elements.

- **Minimum standard**: C++14
- **When to use**: Whenever you need to iterate over the elements of a pack or tuple at compile time, constructing a second pack of index constants.

### Interface Segregation with Mixins
*Ch. 4 — Object Composition*

Instead of a large base class with optional methods, compose objects from small, independent capability mixins. Each mixin adds one concept.

- **Minimum standard**: C++11 (template-based mixins)
- **When to use**: When a class hierarchy has many unrelated capabilities, and clients need only a subset.

### Iterator Categories and Algorithm Selection
*Ch. 10 — Tag Dispatch and SFINAE; Ch. 29 — Container Design*

Iterator category tags (input, forward, bidirectional, random_access) allow the same algorithm name to dispatch to different implementations. `std::advance` and `std::distance` are canonical examples. C++20 ranges and concepts provide a cleaner categorization.

- **Minimum standard**: C++98 (tag dispatch); C++20 (concepts)
- **When to use**: When an algorithm can be implemented more efficiently for stronger iterator categories.

### Lazy Evaluation (Views / Expressions)
*Ch. 11 — Function Composition; Ch. 26 — Range and Views; Ch. 31 — Expression Templates*

Deferred computation: a range view or expression template captures the operation but does not compute it until evaluation is forced (by materialization or assignment). Avoids intermediate storage and enables loop fusion.

- **Minimum standard**: C++20 (range views); C++17 (fold expressions for lazy evaluation patterns)
- **When to use**: Pipeline-style operations on large data sets; arithmetic on large vectors; any operation where intermediate temporaries dominate.

### Lock Granularity
*Ch. 13 — Thread-Safe Interfaces*

Coarse-grained locking (one mutex for all data) is simple but reduces concurrency. Fine-grained locking increases throughput but risks deadlock. The trade-off is between simplicity and performance.

- **Minimum standard**: C++11
- **When to use**: Start with coarse-grained locking; profile; refine to fine-grained only where contention is proven.

### Memory Pool
*Ch. 7 — Buffer and Memory Management*

Pre-allocates a block of memory and divides it into fixed- or variable-size chunks. Eliminates per-allocation overhead and fragmentation. Implementations include slab allocators, arena allocators, and thread-local pools.

- **Minimum standard**: C++11
- **When to use**: Frequent allocation of objects of the same size; real-time systems where allocation latency is critical; embedded systems with limited memory.

### Mixin (CRTP / Template)
*Ch. 4 — Object Composition; Ch. 30 — Mixin-Based Design*

A class that adds a specific capability to a derived class via inheritance. CRTP mixins provide static dispatch. Template mixins parameterize the mixin behavior. Variadic mixin composition combines multiple mixins.

- **Minimum standard**: C++98 (CRTP); C++11 (template/parameterized); C++23 (deducing this simplifies CRTP)
- **When to use**: Separating cross-cutting concerns (logging, synchronization, serialization) from core business logic.

### Monadic Operations (Optional, Expected)
*Ch. 12 — Monads in C++; Ch. 18 — Error Handling Idioms*

`and_then`, `or_else`, `transform`, and `transform_error` allow chaining operations on `std::optional` or `std::expected` without nested if-statements or try-catch. Each operation short-circuits if the value is absent or errored.

- **Minimum standard**: C++23 (monadic optional and expected)
- **When to use**: Any sequence of operations where each step depends on the success of the previous step.

### Named Constructor Idiom
*Ch. 3 — Object Creation and Destruction*

Private constructors exposed through public static factory methods with descriptive names. Clarifies intent (e.g., `Point::cartesian(x, y)` vs `Point::polar(r, theta)`) and enforces invariants by controlling all construction paths.

- **Minimum standard**: C++11 (for delegating constructors to reduce duplication)
- **When to use**: When a type has multiple construction semantics and the constructor signature alone is ambiguous.

### Object Pool
*Ch. 22 — Creational Patterns*

Pre-allocates a collection of reusable objects. Borrowers acquire and return objects to the pool. Avoids allocation overhead for objects that are created and destroyed frequently.

- **Minimum standard**: C++11
- **When to use**: Objects that are expensive to create but cheap to reset; systems with strict allocation budgets (games, embedded).

### Observer (with Type Safety)
*Ch. 24 — Behavioral Patterns*

One subject notifies many observers of state changes. In C++, type safety is achieved by making the observer a typed callback or using `std::function` with specific signatures. `weak_ptr` prevents observers from extending the subject's lifetime.

- **Minimum standard**: C++11 (function, shared_ptr, weak_ptr)
- **When to use**: Event-driven architectures where one change affects multiple dependent components.

### Pack Indexing (C++26)
*Ch. 32 — Variadic Templates Patterns*

`Ts...[I]` retrieves the `I`-th type from a parameter pack directly. No more indirection via `std::tuple_element`.

- **Minimum standard**: C++26
- **When to use**: Any direct element access to a parameter pack. Simplifies pack manipulation and tuple-like types.

### Parameter Pack Expansion
*Ch. 32 — Variadic Templates Patterns*

The `...` after a pattern containing a pack name repeats the pattern for each element. The fundamental variadic operation.

- **Minimum standard**: C++11
- **When to use**: Whenever you declare or use a variadic template.

### Pipeline Composition (Ranges)
*Ch. 26 — Range and Views*

The `|` operator chains range adaptors: `v | views::filter(pred) | views::transform(f)`. Each adaptor is a lazy view. The pipeline reads from left to right, from source to terminal operation.

- **Minimum standard**: C++20
- **When to use**: Any sequence of data transformations; replacing nested `std::transform`/`std::copy_if` calls.

### Placement New
*Ch. 7 — Buffer and Memory Management*

Constructs an object at a specific memory address. Used in custom allocators, memory pools, and embedded systems. Must be paired with an explicit destructor call.

- **Minimum standard**: C++98
- **When to use**: When you control memory allocation separately from object construction (arenas, shared memory, custom allocators).

### Policy-Based Design
*Ch. 4 — Object Composition; Ch. 17 — Policy-Based Design; Ch. 23 — Structural Patterns*

A class template parameterized by policy classes that control its behavior. Policies are selected at compile time, enabling zero-cost customization. Used in `std::allocator`, smart pointer deleters, and threading policies.

- **Minimum standard**: C++11 (variadic templates simplify combining multiple policies)
- **When to use**: A class needs configurable behavior in multiple orthogonal dimensions, and the configuration is known at compile time.

### RAII (Resource Acquisition Is Initialization)
*Ch. 2 — C++ Fundamentals; Ch. 18 — Error Handling Idioms*

The most important C++ idiom. Resource acquisition is tied to object construction; resource release is tied to destruction. The destructor runs automatically when an exception or scope exit occurs, providing deterministic cleanup.

- **Minimum standard**: C++98
- **When to use**: Any resource that must be acquired and released: memory, locks, file handles, sockets, database connections, and profiling scopes.

### Range-Based Algorithm
*Ch. 26 — Range and Views*

`std::ranges::sort(v)` instead of `std::sort(v.begin(), v.end())`. Single-argument ranges simplify the common case and eliminate iterator-pair mismatches.

- **Minimum standard**: C++20
- **When to use**: Any algorithm call on an entire range. The single-argument form is preferred over the iterator-pair form.

### Reader-Writer Lock
*Ch. 13 — Thread-Safe Interfaces*

`std::shared_mutex` allows multiple concurrent readers or one exclusive writer. Readers acquire a shared lock; the writer acquires a unique lock. Use for data that is read much more often than it is written.

- **Minimum standard**: C++17 (`std::shared_mutex`); C++14 (`std::shared_timed_mutex`)
- **When to use**: Read-dominant data structures: caches, configuration tables, lookup tables.

### Reflection (`std::meta`, C++26)
*Ch. 33 — Reflection and Introspection*

Compile-time reflection using the `^` operator and `std::meta::info`. Queries type structure (members, bases, names) and generates code without macros or external tools.

- **Minimum standard**: C++26
- **When to use**: Enum-to-string conversion, serialization, visitor generation, and other code-generation tasks that previously required X macros or external codegen.

### Rule of Zero / Rule of Five
*Ch. 2 — C++ Fundamentals; Ch. 5 — Object Lifetime*

- **Rule of Zero**: If a class does not manage resources directly, it should not define any special member functions (destructor, copy/move constructor, copy/move assignment). The compiler-generated defaults are correct.
- **Rule of Five**: If a class must define a custom destructor, copy constructor, or copy assignment, it likely needs all five special member functions (including move operations).
- **Rule of Six**: Add a swap function for the copy-and-swap idiom.

- **Minimum standard**: C++11 (move operations)
- **When to use**: Always prefer Rule of Zero. Use Rule of Five when managing a resource that is not already wrapped in a RAII type.

### SFINAE (Substitution Failure Is Not An Error)
*Ch. 10 — Tag Dispatch and SFINAE*

When template argument substitution fails for a particular specialization, the compiler does not emit an error — it discards that specialization and looks for another. This enables compile-time introspection and overload selection.

- **Minimum standard**: C++98 (language feature); C++11 (enable_if in standard library)
- **When to use**: When C++20 concepts are unavailable and you need to conditionally enable/disable a template.

### Singleton (and Alternatives)
*Ch. 22 — Creational Patterns*

A class with at most one instance. In C++11 and later, Meyers' singleton (`static T& instance() { static T t; return t; }`) is thread-safe due to guaranteed static initialization. For testability, consider dependency injection instead.

- **Minimum standard**: C++11 (thread-safe static local)
- **When to use**: Logging, configuration, hardware interface. Prefer dependency injection for code that must be tested in isolation.

### Small Buffer Optimization (SBO)
*Ch. 7 — Buffer and Memory Management; Ch. 8 — Type Erasure; Ch. 29 — Container Design*

A small inline buffer avoids heap allocation for small objects. Used by `std::string` (SSO), `std::function`, and many custom type-erased containers. The threshold (typically 16–64 bytes) must be tuned for the expected value distribution.

- **Minimum standard**: C++11 (alignment control, move semantics for buffer management)
- **When to use**: Types that store values of varying size where most values fit in a small buffer.

### Smart Pointer as Member
*Ch. 6 — Smart Pointers and Ownership*

Use `unique_ptr` for exclusive ownership, `shared_ptr` for shared ownership, and `weak_ptr` for non-owning observation. Smart pointer members eliminate manual destructors and simplify copy/move semantics.

- **Minimum standard**: C++11
- **When to use**: Always prefer smart pointer members over raw pointer members for owning relationships.

### Span (`std::span`)
*Ch. 28 — API Design*

A non-owning view over a contiguous sequence of elements. Pass `std::span<const T>` to functions that accept array data. Accepts `std::vector`, `std::array`, C arrays, and `std::span` itself.

- **Minimum standard**: C++20
- **When to use**: Any function parameter that accepts a contiguous sequence. Prefer `std::span` over `const T*` + size parameters.

### Static Polymorphism (CRTP / Concepts)
*Ch. 9 — CRTP and Static Polymorphism*

Polymorphism without virtual dispatch. CRTP provides it through template derivation. Concepts provide constrained templates. Both eliminate vtable overhead and enable inlining.

- **Minimum standard**: C++98 (CRTP); C++20 (concepts)
- **When to use**: Performance-critical polymorphic interfaces where the set of implementing types is known at compile time.

### Strategy Pattern
*Ch. 24 — Behavioral Patterns*

Encapsulates an algorithm behind a common interface. In C++, strategies are typically passed as lambdas, function pointers, or `std::function`. Template strategies (policy-based design) provide zero-cost compile-time selection.

- **Minimum standard**: C++11 (lambdas, std::function); C++98 (virtual interface)
- **When to use**: When a class needs to vary its behavior by delegating to an algorithm selected by the caller.

### Structured Bindings
*Ch. 2 — C++ Fundamentals*

`auto [a, b, c] = expr;` decomposes a tuple, pair, array, or tuple-like type into named variables. The decomposition works through `std::tuple_size`, `std::tuple_element`, and `get<I>`.

- **Minimum standard**: C++17
- **When to use**: When a function returns multiple values (via tuple/pair) or when iterating over associative containers.

### Tag Dispatch
*Ch. 10 — Tag Dispatch and SFINAE*

Overloaded functions distinguished by empty tag types. The caller selects the tag to choose the implementation. Used by the standard library for iterator category dispatch (`std::advance`).

- **Minimum standard**: C++98
- **When to use**: When you need compile-time overload selection and the selection criterion is a type (tag) that callers can provide.

### Thread-Local Storage (TLS)
*Ch. 13 — Thread-Safe Interfaces*

`thread_local` storage duration gives each thread its own instance of a variable. Avoids synchronization for per-thread state.

- **Minimum standard**: C++11
- **When to use**: Per-thread caches, random number generators, log buffers. Avoid for large objects (the TLS space is limited).

### Thread-Safe Queue
*Ch. 14 — Concurrent Data Structures*

A queue protected by a mutex and condition variable. Producers push items; consumers block until items are available.

- **Minimum standard**: C++11
- **When to use**: Producer-consumer patterns, thread pools, and actor-model message passing.

### Tuple Implementation (Recursive / Flat)
*Ch. 32 — Variadic Templates Patterns*

Recursive inheritance (each level stores one element and inherits from the remainder) or flat index-based inheritance (each element stored in a uniquely-indexed holder). Both approaches demonstrate the full variadic pattern suite.

- **Minimum standard**: C++11
- **When to use**: When you need a fixed-size collection of heterogeneous types; understanding the implementation helps debug `std::tuple`-related errors and build custom tuple-like types.

### Type Erasure
*Ch. 8 — Type Erasure*

Hides the concrete type behind a non-virtual interface. The model/concept pattern (external polymorphism) stores an interface pointer alongside a type-erased model object. `std::function`, `std::any`, and `std::shared_ptr` with aliasing constructors are standard examples.

- **Minimum standard**: C++11 (move semantics, variadic templates)
- **When to use**: When you need a uniform interface for objects of unrelated types, and the set of types is open at compile time.

### Type Lists and Compile-Time Algorithms
*Ch. 8 — Type Erasure; Ch. 15 — Type Manipulation*

A `TypeList<Ts...>` encodes a sequence of types as a template. Compile-time algorithms (transform, filter, fold) operate on type lists through partial specialization. The foundation of TMP.

- **Minimum standard**: C++11 (variadic templates)
- **When to use**: Implementing `std::tuple`, `std::variant`, or any compile-time type container.

### Type Safety in APIs
*Ch. 28 — API Design*

Strong typing through wrapper types, `enum class`, and constructor arguments. Eliminates implicit conversions and invalid state by making illegal states unrepresentable.

- **Minimum standard**: C++11 (enum class)
- **When to use**: Any public API. Especially important for parameters that share the same fundamental type (e.g., IDs, quantities with units).

### Variadic Type Construction
*Ch. 32 — Variadic Templates Patterns*

Constructing types from parameter packs via expansions: `std::tuple<Ts...>`, `std::variant<Ts...>`, `std::function<Ts...>`, and custom transformations with `F<Ts>...`.

- **Minimum standard**: C++11
- **When to use**: Any variadic template design.

### Virtual Clone
*Ch. 3 — Object Creation and Destruction*

A virtual `clone()` method returns a `unique_ptr` to a copy of the object, solving the slicing problem. Return type covariance allows the derived `clone()` to return `unique_ptr<Derived>`.

- **Minimum standard**: C++11 (unique_ptr, return type covariance)
- **When to use**: When you need to copy an object through a pointer to its base class.

### Visitor (with Double Dispatch)
*Ch. 24 — Behavioral Patterns*

A visitor class defines a `visit` overload for each type in a variant or class hierarchy. In C++17, `std::visit` dispatches a visitor over a `std::variant`. The overloaded pattern (`template<class... Ts> struct overloaded : Ts...`) builds a visitor from lambdas.

- **Minimum standard**: C++11 (virtual visitor); C++17 (variant visitor, overloaded pattern)
- **When to use**: When an operation must behave differently for each type in a closed set. Especially useful for variant-based value semantics.

---

## When to Use Each Idiom: Decision Guide

The decision tables below group idioms by the problem they solve.

### Resource Management

| Problem | Idiom | Standard |
|---------|-------|----------|
| Any resource must be cleaned up automatically | RAII | C++98 |
| Exclusive ownership | `unique_ptr` | C++11 |
| Shared ownership | `shared_ptr` + `weak_ptr` | C++11 |
| Custom deallocation | Custom deleter | C++11 |
| Frequent allocations of same-size objects | Memory pool | C++11 |
| Reusing expensive objects | Object pool | C++11 |
| Array-to-pointer decay | `std::span` | C++20 |

### Polymorphism

| Problem | Idiom | Standard |
|---------|-------|----------|
| Runtime polymorphism with inheritance | Virtual functions | C++98 |
| Static polymorphism without vtable | CRTP | C++98 |
| Polymorphism for unrelated types | Type erasure | C++11 |
| Constrained templates | Concepts | C++20 |
| Compile-time interface selection | Tag dispatch | C++98 |
| Same interface, different algorithms | Strategy | C++11 |

### Code Organization

| Problem | Idiom | Standard |
|---------|-------|----------|
| Hide implementation details | Pimpl | C++11 |
| Simplify subsystem interface | Facade | C++98 |
| Add layered behavior | Decorator | C++11 |
| Convert interfaces | Adapter | C++98 |
| Reduce many-to-many coupling | Observer | C++11 |
| Compose orthogonal policies | Policy-based design | C++11 |
| Compose capabilities | Mixin (CRTP) | C++98 |

### Compile-Time Programming

| Problem | Idiom | Standard |
|---------|-------|----------|
| Query type properties | Type traits | C++11 |
| Check arbitrary type properties | Detection idiom (`void_t`) | C++11 |
| Constrain templates | SFINAE / enable_if | C++98 |
| Constrain templates (readable) | Concepts | C++20 |
| Iterate over types | Type lists, pack expansion | C++11 |
| Operate over packs | Fold expressions | C++17 |
| Compute at compile time | `constexpr` / `consteval` | C++11 |
| Generate code from type structure | Reflection (`std::meta`) | C++26 |
| Single-source-of-truth codegen | X macros | C++98 |

### Error Handling

| Problem | Idiom | Standard |
|---------|-------|----------|
| Unexpected errors | Exceptions | C++98 |
| Expected errors, local handling | `std::expected` | C++23 |
| Optional values | `std::optional` | C++17 |
| Chaining fallible operations | Monadic optional/expected | C++23 |
| Express pre/post conditions | Contract programming | C++26 |
| Deterministic cleanup | RAII + destructors | C++98 |

### Concurrency

| Problem | Idiom | Standard |
|---------|-------|----------|
| Protect shared data | Mutex + lock guard | C++11 |
| Multiple readers, one writer | Reader-writer lock | C++17 |
| Per-thread state | Thread-local storage | C++11 |
| Produce-consumer | Thread-safe queue | C++11 |
| Lazy initialization | `std::call_once` | C++11 |
| Message-passing concurrency | Actor model | C++11 |
| Async one-shot operation | Future/promise | C++11 |
| Lazy sequences | Coroutine generator | C++20 |
| Async task composition | Sender/receiver | C++26 |

### Performance

| Problem | Idiom | Standard |
|---------|-------|----------|
| Avoid false sharing | Cache line alignment | C++17 |
| Improve cache locality | SoA vs AoS | C++98 |
| Focus on memory access | Data-oriented design | C++98 |
| Loop fusion for math | Expression templates | C++11 |
| Deferred computation | Lazy views | C++20 |
| Avoid small allocations | Small buffer optimization | C++11 |

### Construction

| Problem | Idiom | Standard |
|---------|-------|----------|
| Complex/optional construction | Builder / fluent interface | C++98 |
| Clarify constructor intent | Named constructor | C++11 |
| Copy through base pointer | Virtual clone | C++11 |
| Object creation by type registry | Factory method | C++11 |
| Related object families | Abstract factory | C++14 |
| One instance only | Singleton | C++11 |
| Share immutable state | Flyweight | C++11 |

---

Use this appendix as a quick lookup when you know the problem but not the idiom name, or as a reminder of which C++ standard a given idiom requires.
