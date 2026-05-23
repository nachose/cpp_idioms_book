# C++ Idioms - Book Outline

---

## Part I: Introduction and Foundations

### Chapter 1: Introduction to C++ Idioms
[DEVELOPED - Full content written to chapter_01.md]

This chapter covers:
- What are idioms and why they matter (including RAII motivation, example, trade-offs)
- The philosophy behind idiomatic C++ (zero-overhead, value semantics, compile-time focus)
- Relationship between idioms and design patterns
- Overview of the book structure
- Summary and exercises for reinforcing understanding

### Chapter 2: C++ Fundamentals for Idiomatic Programming
[DEVELOPED - All five sections fully written to chapter_02.md]

**Full chapter content developed:**
- RAII and resource management (detailed motivation, mental model, RAII wrapper examples, Rule of Zero/Five introduction, std::unique_ptr with custom deleters, trade-offs vs GC/manual management, exercises)
- Value semantics vs reference semantics (copy semantics vs aliasing, why value is default, const& for performance, decision tree, common anti-patterns like output parameters and shared_ptr overuse, exercises)
- Type deduction and `auto` (how auto deduction works, relationship to value/reference semantics, decltype and decltype(auto), when to use auto vs explicit types, common pitfalls like lifetime issues with auto&, structured bindings, exercises)
- Move semantics and perfect forwarding (rvalue references, move constructor/assignment, std::move, move-only types like unique_ptr, perfect forwarding with T&& and std::forward, use cases in generic factories and wrappers, when NOT to use move, mental model, exercises)
- Const-correctness and constexpr (const at different levels, const member functions and mutable, constexpr functions/variables, constexpr vs const, consteval, static initialization safety, trade-offs, exercises, chapter summary)

---

## Part II: Core Idioms

### Chapter 3: Object Creation and Destruction
[DEVELOPED - Full content written to chapter_03.md]

**Full chapter content developed:**
- Factory methods and virtual constructors (virtual constructor idiom, polymorphic factory methods, create/clone pattern, comparison with separate factory classes, trade-offs)
- Named Constructor Idiom (clarifying constructor intent, enforcing invariants through private constructors, preventing direct construction, use cases, trade-offs vs alternatives)
- Virtual Clone Idiom (slicing problem explained, virtual clone pattern, return type considerations, Cloneable template variant, common use cases, trade-offs)
- Prototype Pattern implementation (prototype registry, clone-based creation, runtime type registration, configuration-driven creation, comparison with factory methods, trade-offs, chapter summary and exercises)

### Chapter 4: Object Composition
[DEVELOPED - Full content written to chapter_04.md]

**Full chapter content developed:**
- Composition over Inheritance (why inheritance fails, combinatorial explosion, composition benefits for flexibility/testability/runtime changes, when inheritance is appropriate, decision guidance)
- Handle/Body (pImpl) Idiom (implementation separation, compilation firewall, binary compatibility, std::unique_ptr usage, exception safety considerations, when to use)
- Interface Segregation with Mixins (fat interface problem, independent capability mixins, template-based mixins with CRTP, diamond inheritance considerations, policy design extension)
- Policy-based Design (compile-time composition, policy template parameters, allocation/copy policy examples, zero-runtime-overhead customization, policy bundling, trade-offs vs runtime configuration, chapter summary and exercises)

### Chapter 5: Object Lifetime and Initialization
[DEVELOPED - Full content written to chapter_05.md]

**Full chapter content developed:**
- Constructor delegation (chaining constructors to avoid duplication, constraints on simultaneous delegation and member initialization, combination with factory methods)
- Initialization order guarantees (fixed order regardless of initializer list ordering, static initialization order fiasco and construct-on-first-use pattern, in-member initialization for defaults)
- Rule of Zero / Rule of Five / Rule of Six (conditional generation of special member functions, =default and =delete patterns, resource management implications, TrackingWidget example)
- Object construction with type lists (TypeList template, compile-time type traversal, ObjectFactory with TypeList, plugin registration, VariadicConstructor for heterogeneous construction)

---

## Part III: Memory and Resource Management

### Chapter 6: Smart Pointers and Ownership
[DEVELOPED - Full content written to chapter_06.md]

**Full chapter content developed:**
- `unique_ptr` patterns (exclusive ownership, move semantics, array handling, polymorphic objects, containers with unique_ptr, pImpl pattern, converting raw to unique)
- `shared_ptr` and `weak_ptr` cycles (shared ownership model, reference counting, cycle problem with objects referencing each other, weak_ptr as solution, lock() pattern, caching with weak_ptr, performance considerations)
- Custom Deleters and Aliasing Constructors (custom deleter types, file/handle deleters, non-default deallocation, aliasing constructor for subobjects, combining deleters with intrusive refcounting)
- Smart Pointers as Class Members (unique_ptr members with default semantics, implementing copy for exclusive ownership, shared_ptr members, weak_ptr for optional observation, factory patterns returning pointers)
- Interfacing with Legacy Code (wrapping C APIs with custom deleters, passing raw pointers from smart pointers, callbacks requiring shared ownership, const data without deletion, bridging principles)

### Chapter 7: Buffer and Memory Management
[DEVELOPED - Full chapter written to chapter_07.md]

- Buffer management idioms (DETAILED - sizing strategies, ownership, zero-copy, ring buffers, migration)
- Small Buffer Optimization (SBO) (DETAILED - SSO, custom SBO, union-based, performance)
- Placement new for custom memory (DETAILED - explicit placement, destructor calls, allocators, exception safety)
- Memory pool patterns (DETAILED - fixed/variable pools, slab, arena, thread-local, object pools)

---

## Part IV: Polymorphism and Type Systems

### Chapter 8: Type Erasure
[DEVELOPED - Full chapter written to chapter_08.md]

- Type erasure for polymorphism (DETAILED - concept/model pattern, value storage, move semantics)
- `std::function` implementation patterns (DETAILED - SBO, invocation mechanism, storage, callable types)
- Any type with type erasure (DETAILED - interface, type info, any_cast, SBO)
- Type lists and compile-time polymorphism (DETAILED - operations, iteration, dispatch, variants)

### Chapter 9: CRTP and Static Polymorphism
[DEVELOPED - Full chapter written to chapter_09.md]

- Curiously Recurring Template Pattern (DETAILED - mechanism, examples, advantages, comparisons)
- Static polymorphism without virtual overhead (DETAILED - concepts, tag dispatch, performance)
- Mixin-based inheritance (DETAILED - composition, CRTP, state, policies, conflicts)
- Counted idiom (DETAILED - intrusive counting, thread safety, weak refs, COM-style)

### Chapter 10: Tag Dispatch and SFINAE
[DEVELOPED - Full chapter written to chapter_10.md]

**Full chapter content developed:**
- Tag-based function overload resolution (DETAILED - tags, hierarchy, dispatch, standard library usage)
- `enable_if` and conditional compilation (DETAILED - enable_if patterns, constraints, overload selection)
- Type traits and detection idioms (DETAILED - category traits, relationships, void_t, custom traits)
- Compile-time introspection (DETAILED - capability detection, conditional compilation, type lists)

---

## Part V: Functional Programming Patterns

### Chapter 11: Function Composition
[DEVELOPED - Full chapter written to chapter_11.md]

**Full chapter content developed:**
- Higher-order functions in C++ (DETAILED - functions as parameters/returns, generic higher-order, capturing state)
- Monadic operations on containers (DETAILED - map, flatMap, filter, fold, optional monad, result type)
- Function adapters and composition (DETAILED - std::bind, negation, composition, custom adapters)
- Lazy evaluation patterns (DETAILED - lazy vs eager, generators, expression templates, infinite sequences)

### Chapter 12: Monads in C++
[DEVELOPED - Full chapter written to chapter_12.md]

**Full chapter content developed:**
- Maybe/Optional monad (motivation for std::optional vs sentinel values, and_then for chaining, map/transform, value_or patterns, trade-offs and considerations)
- Either monad for error handling (Either concept, Result type implementation, error propagation patterns, map_error, comparison with exceptions)
- IO monad concepts (making effects explicit, composing IO actions, practical application in library design)
- Monadic bind and lift operations (understanding bind vs lift, custom monads in C++, monadic laws, implementation patterns)

---

## Part VI: Concurrency and Threading

### Chapter 13: Thread-Safe Interfaces
[DEVELOPED - Full chapter written to chapter_13.md]

**Full chapter content developed:**
- Thread-agnostic design (why thread-agnostic matters, designing for immutability, value types and thread safety, thread-agnostic member functions, trade-offs)
- Lock granularity and lock-free idioms (coarse vs fine-grained locking, lock ordering to prevent deadlock, lock-free concepts with CAS, lock-free considerations)
- Thread-local storage patterns (thread_local keyword, common use cases, performance considerations, static storage duration, trade-offs)
- Reader-Writer lock patterns (problem with simple mutexes, std::shared_mutex usage, read-copy-update pattern, trade-offs and considerations)

### Chapter 14: Concurrent Data Structures
- Thread-safe queues [DEVELOPED - Full content written to chapter_14.md]
- Double-checked locking [DEVELOPED - Full content written to chapter_14.md]
- Actor model implementation [DEVELOPED - Full content written to chapter_14.md]
- Futures and promises patterns [DEVELOPED - Full content written to chapter_14.md]

---

## Part VII: Template Metaprogramming

### Chapter 15: Type Manipulation
- Type manipulation utilities [DEVELOPED - Full content written to chapter_15.md]
- Type introspection and traits [DEVELOPED - Full content written to chapter_15.md]
- Template specialization strategies [DEVELOPED - Full content written to chapter_15.md]
- Template argument deduction [DEVELOPED - Full content written to chapter_15.md]

### Chapter 16: Compile-Time Computation
- Template recursion patterns [DEVELOPED - Full content written to chapter_16.md]
- Parameter packs and pack expansion [DEVELOPED - Full content written to chapter_16.md]
- Fold expressions [DEVELOPED - Full content written to chapter_16.md]
- Static assertions and constraints [DEVELOPED - Full content written to chapter_16.md]

### Chapter 17: Policy-based Design
- Policy-based class design [DEVELOPED - Full content written to chapter_17.md]
- Combining policies [DEVELOPED - Full content written to chapter_17.md]
- Runtime polymorphism vs policy-based design [DEVELOPED - Full content written to chapter_17.md]
- Expression templates [DEVELOPED - Full content written to chapter_17.md]

---

## Part VIII: Error Handling and Robustness

### Chapter 18: Error Handling Idioms
[DEVELOPED - Full chapter written to chapter_18.md]

- Exception safety guarantees [DEVELOPED - Full content written]
- RAII for exception safety [DEVELOPED - Full content written]
- Error code vs exception patterns [DEVELOPED - Full content written]
- Expected/Result types [DEVELOPED - Full content written]

### Chapter 19: Defensive Programming
- Contract programming [DEVELOPED - Full content written to chapter_19.md]
- Compile-time vs runtime checks [DEVELOPED - Full content written to chapter_19.md]
- Assertions and invariants [DEVELOPED - Full content written to chapter_19.md]
- Sanitizer integration patterns [DEVELOPED - Full content written to chapter_19.md]

---

## Part IX: Performance Optimization

### Chapter 20: Zero-Cost Abstractions
- Type-based optimization [DEVELOPED - Full content written to chapter_20.md]
- Small object optimization [DEVELOPED - Full content written to chapter_20.md]
- Inlining and constexpr [DEVELOPED - Full content written to chapter_20.md]
- Iterator categories and optimization [DEVELOPED - Full content written to chapter_20.md]

### Chapter 21: Cache-Friendly Patterns
[DEVELOPED - Full chapter written to chapter_21.md]

- Data-oriented design (DETAILED - DOD philosophy, hot/cold splitting, data stream thinking, trade-offs)
- Cache line alignment (DETAILED - alignas, false sharing, struct reordering, large pages, ABI considerations)
- Structure of Arrays vs Array of Structures (DETAILED - memory access patterns, SIMD impact, hybrid AoSoA, measurement guidance)
- Memory prefetching idioms (DETAILED - hardware prefetching, software prefetching with __builtin_prefetch, linked structures, non-temporal stores, tuning)

---

## Part X: Design Patterns as Idioms

### Chapter 22: Creational Patterns
- Builder pattern with method chaining [DEVELOPED - Full content written to chapter_22.md]
- Singleton implementations and alternatives [DEVELOPED - Full content written to chapter_22.md]
- Abstract Factory with type lists [DEVELOPED - Full content written to chapter_22.md]
- Object pool patterns [DEVELOPED - Full content written to chapter_22.md]

### Chapter 23: Structural Patterns
[DEVELOPED - Full content written to chapter_23.md]

**Full chapter content developed:**
- Adapter and wrapper idioms (class adapter via multiple inheritance, object adapter via composition, template adapter for compile-time zero-cost adaptation, wrapper idioms beyond adapter including type-safe wrappers, ownership wrappers, protocol wrappers, trade-offs and exercises)
- Facade patterns for libraries (subsystem encapsulation with RAII, compile-time facade with templates and fold expressions, module facade in C++20 for source-level encapsulation, comparison with mediator and wrapper patterns, trade-offs and exercises)
- Flyweight for memory optimization (intrinsic vs extrinsic state, flyweight factory, string interning pool, intrusive flyweight with shared_ptr for automatic lifetime, extrinsic state strategies, flyweight examples in the C++ standard library, trade-offs and exercises)
- Decorator patterns (classic runtime decorator with virtual dispatch and unique_ptr ownership, template-based decorator with CRTP for compile-time composition, variadic decorator stack, functional decorators with std::function for callable wrapping, policy-based decorators with tag dispatch, comparison with inheritance and strategy patterns, known pitfalls like identity and interface alignment, exercises)

### Chapter 24: Behavioral Patterns
- Strategy pattern implementation [DEVELOPED - Full content written to chapter_24.md]
- Observer with type safety [DEVELOPED - Full content written to chapter_24.md]
- Visitor pattern with double dispatch [DEVELOPED - Full content written to chapter_24.md]
- Command pattern with type erasure [DEVELOPED - Full content written to chapter_24.md]

---

## Part XI: Modern C++ Idioms (C++11 and Beyond)

### Chapter 25: Lambda Patterns
- Lambda capture strategies [DEVELOPED - Full content written to chapter_25.md]
- Generic lambdas [DEVELOPED - Full content written to chapter_25.md]
- Lambda as callback storage [DEVELOPED - Full content written to chapter_25.md]
- Stateful lambdas and closure patterns [DEVELOPED - Full content written to chapter_25.md]

### Chapter 26: Range and Views
[DEVELOPED - Full content written to chapter_26.md]

**Full chapter content developed:**
- Range-based algorithms (motivation for single-argument ranges, constrained algorithms with concepts, projections for separating "what" from "how", sentinel-based algorithms for condition-ended sequences, pipeable vs non-pipeable distinction)
- Lazy evaluation with views (non-owning lazy iteration, ownership and dangling prevention, commonly used views: filter/transform/take/drop/reverse/split/join/keys/values, the `auto` deduction trap, performance characteristics of lazy pipelines)
- Custom range adaptors (view class anatomy with view_interface inheritance, making views pipeable with range_adaptor_closure, composing from existing views vs full custom views, stateful views warning)
- Pipeline composition (pipe operator mechanics, reverse vs nested notation readability, terminal operations for breaking laziness, eager vs lazy materialization decisions, short-circuiting with early-exit algorithms, side effects in pipelines, debugging strategies)

### Chapter 27: Coroutines and Async
- Coroutine fundamentals [DEVELOPED - Full section written to chapter_27.md]
- Generator patterns [DEVELOPED - Full section written to chapter_27.md]
- Awaitable types [DEVELOPED - Full section written to chapter_27.md]
- Task-based async patterns [DEVELOPED - Full section written to chapter_27.md]

---

## Part XII: Library Design Idioms

### Chapter 28: API Design
- Rule of least surprise [DEVELOPED - Full section written to chapter_28.md]
- Type safety in APIs [DEVELOPED - Full section written to chapter_28.md]
- Builder and fluent interfaces [DEVELOPED - Full section written to chapter_28.md]
- Error propagation strategies [DEVELOPED - Full section written to chapter_28.md]

### Chapter 29: Container Design
[DEVELOPED - Full chapter written to chapter_29.md]

**Full chapter content developed:**
- Custom allocator integration (DETAILED - allocator_traits vs direct calls, stateful vs stateless allocators, propagation policies, scoped allocator adaptor, pmr polymorphic allocators, allocator-aware container checklist)
- Iterator design and traits (DETAILED - iterator categories hierarchy, iterator_traits member types, complete random-access iterator example with modular arithmetic, const/non-const split, sentinels, iterator adaptors, C++20 iterator concepts compatibility)
- Emplace vs insert semantics (DETAILED - conceptual difference and performance analysis, when emplace is not an optimization including narrowing conversions and leak-prone raw pointers, exception safety differences with strong vs basic guarantee, try_emplace and piecewise_construct for associative containers, hint-based insertion, custom container interface design)
- Type-erased containers (DETAILED - concept/model external polymorphism pattern, small buffer optimization for inline storage, heterogeneous containers per element, function-pointer-based type erasure without virtual dispatch, type-erased iterators, trade-offs vs std::variant)

---

## Part XIII: Advanced Topics

### Chapter 30: Mixin and Mixin-Based Design
[DEVELOPED - Full content written to chapter_30.md]

**Full chapter content developed:**
- Mixin class composition (DETAILED - stateful vs stateless mixins, diamond problem and virtual inheritance, initialization order, named arguments via mixins, common pitfalls including name collisions and object slicing)
- CRTP-based mixins (DETAILED - operator injection via friend functions in CRTP, mixin-based extension for cross-cutting concerns like synchronization, property mixins, composition of multiple CRTP mixins, comparison with virtual inheritance)
- Template mixin patterns (DETAILED - parameterized mixin classes, variadic mixin composition, policy mixin composition, mixin-from-below pattern, SFINAE-constrained mixins, named mixin factories, storage mixins, trade-offs including compilation time and error messages)

### Chapter 31: Expression Templates
[DEVELOPED - Full content written to chapter_31.md]

**Full chapter content developed:**
- Expression template fundamentals (DETAILED - motivation from eager vector arithmetic creating temporaries and multiple loops, CRTP-based VecExpr base class, VecAdd/VecScalarMul expression proxy types, lazy operators returning proxy objects, assignment operator as evaluation point fusing loops, trade-offs including compile time, error messages, and binary size)
- Lazy evaluation in expressions (DETAILED - deferred computation model, loop fusion combining multiple operations into a single pass, the assignment-as-evaluation-point pattern, the `auto` deduction trap causing dangling references, when lazy evaluation hurts including small vectors, complex control flow, non-trivial element access, and debugging complexity)
- Operator overloading patterns (DETAILED - returning expression proxies from operators, composing expressions of different concrete types via common VecExpr interface, handling mixed scalar/vector operations with ScalarExpr or dedicated types, mixed-precision handling with CommonType traits, common pitfalls including non-const reference parameters, return type deduction failures, namespace pollution, and type deduction failures)
- Advanced expression template techniques (DETAILED - compile-time expression trees with ExprTraits for optimization passes, evaluation strategies including block/SIMD/parallel dispatch, integration with C++20 ranges and range adapters, constant folding and expression rewriting, comparison with macro-based and lambda-based alternatives)

### Chapter 32: Variadic Templates Patterns
[DEVELOPED - Full content written to chapter_32.md]

**Full chapter content developed:**
- Variadic type construction (parameter packs, pack expansion, building types from packs, recursive type construction, fold expressions for type construction, mental model of map/filter/fold at the type level)
- Parameter pack manipulation (index sequences and pack indexing, type filtering with conditional, transforming packs with alias templates, zip operations on multiple packs, concatenation and splitting via head/tail decomposition)
- Tuple implementation (recursive inheritance-based tuple, empty base optimization, element access via std::get with partial specialization, flat tuple with index-based element holders, std::apply and tuple algorithms, structured bindings and tuple-like protocol)

### Chapter 33: Reflection and Introspection
[DEVELOPED - Full content written to chapter_33.md]

**Full chapter content developed:**
- Compile-time reflection patterns (type traits as introspection, the detection idiom with void_t, member detection, C++26 static reflection with std::meta and the ^ operator, compile-time code generation)
- Reflection with macros (preprocessor operators # and ##, X macros for single-source-of-truth code generation, struct field enumeration, limitations of macro approaches including diagnostics and scope, Boost.Preprocessor patterns)
- Automatic serialization (the serialization problem in C++, visitor-based serialization, Boost.Fusion adaptation, X-macro serialization for multiple formats, template-based serialization for tuple-like types, external serialization frameworks comparison with protobuf/FlatBuffers, choosing a serialization approach)

---

## Part XIV: Appendices

### Appendix A: C++ Standards Overview
[DEVELOPED - Full content written to appendix_A.md]

**Full appendix content developed:**
- Pre-C++11 idioms evolution (C with Classes origins, C++98, TR1, Boost pre-C++11)
- C++11/14/17/20/23 additions (comprehensive standard-by-standard feature table with idiom impact, key language/library additions per revision)
- Upcoming C++26 features (static reflection with std::meta, pack indexing, contract programming, concurrent queues, sender/receiver model)
- Standards availability table and chapter-to-standard mapping

### Appendix B: Idioms Quick Reference
[DEVELOPED - Full content written to appendix_B.md]

**Full appendix content developed:**
- Alphabetical reference (60+ idioms, each with one-paragraph definition, minimum standard, and when-to-use guidance)
- Decision guide organized by problem domain (resource management, polymorphism, code organization, compile-time programming, error handling, concurrency, performance, construction)
- Tables mapping problem to idiom to standard

### Appendix C: Code Style and Conventions
[DEVELOPED - Full content written to appendix_C.md]

**Full appendix content developed:**
- Naming conventions (PascalCase for types, camelCase for functions, snake_case for variables, trailing underscore for members, SCREAMING_CASE for macros)
- Code organization (file naming, header structure, implementation files, forward declarations, namespace organization, access level ordering)
- Documentation patterns (Doxygen, inline comments, precondition documentation, when and what to document)
- Formatting conventions (4-space indentation, 80-char lines, K&R braces)

---

## Summary of Parts

- **Part I**: Introduction and Foundations (Chapters 1-2)
- **Part II**: Core Idioms (Chapters 3-5)
- **Part III**: Memory and Resource Management (Chapters 6-7)
- **Part IV**: Polymorphism and Type Systems (Chapters 8-10)
- **Part V**: Functional Programming Patterns (Chapters 11-12)
- **Part VI**: Concurrency and Threading (Chapters 13-14)
- **Part VII**: Template Metaprogramming (Chapters 15-17)
- **Part VIII**: Error Handling and Robustness (Chapters 18-19)
- **Part IX**: Performance Optimization (Chapters 20-21)
- **Part X**: Design Patterns as Idioms (Chapters 22-24)
- **Part XI**: Modern C++ Idioms (Chapters 25-27)
- **Part XII**: Library Design Idioms (Chapters 28-29)
- **Part XIII**: Advanced Topics (Chapters 30-33)
- **Part XIV**: Appendices (Appendix A-C)

---