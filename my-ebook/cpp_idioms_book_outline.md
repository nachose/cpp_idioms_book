# C++ Idioms - Book Outline

---

## Part I: Introduction and Foundations

### Chapter 1: Introduction to C++ Idioms
- What are idioms and why they matter
- The philosophy behind idiomatic C++
- Relationship between idioms and design patterns
- Overview of the book structure

### Chapter 2: C++ Fundamentals for Idiomatic Programming
- RAII and resource management
- Value semantics vs reference semantics
- Type deduction and `auto`
- Move semantics and perfect forwarding
- Const-correctness and constexpr

---

## Part II: Core Idioms

### Chapter 3: Object Creation and Destruction
- Factory methods and virtual constructors
- Named Constructor Idiom
- Virtual Clone Idiom
- Prototype Pattern implementation

### Chapter 4: Object Composition
- Composition over Inheritance
- Handle/Body (pImpl) Idiom
- Interface segregation with mixins
- Policy-based design

### Chapter 5: Object Lifetime and Initialization
- Constructor delegation
- Initialization order guarantees
- Rule of Zero / Rule of Five / Rule of Six
- Object construction with type lists

---

## Part III: Memory and Resource Management

### Chapter 6: Smart Pointers and Ownership
- `unique_ptr` patterns
- `shared_ptr` and `weak_ptr` cycles
- Custom deleters and aliasing constructors
- Smart pointer as class members
- Interfacing with legacy code

### Chapter 7: Buffer and Memory Management
- Buffer management idioms
- Small Buffer Optimization (SBO)
- Placement new for custom memory
- Memory pool patterns

---

## Part IV: Polymorphism and Type Systems

### Chapter 8: Type Erasure
- Type erasure for polymorphism
- `std::function` implementation patterns
- Any type with type erasure
- Type lists and compile-time polymorphism

### Chapter 9: CRTP and Static Polymorphism
- Curiously Recurring Template Pattern
- Static polymorphism without virtual overhead
- Mixin-based inheritance
- Counted idiom

### Chapter 10: Tag Dispatch and SFINAE
- Tag-based function overload resolution
- `enable_if` and conditional compilation
- Type traits and detection idioms
- Compile-time introspection

---

## Part V: Functional Programming Patterns

### Chapter 11: Function Composition
- Higher-order functions in C++
- Monadic operations on containers
- Function adapters and composition
- Lazy evaluation patterns

### Chapter 12: Monads in C++
- Maybe/Optional monad
- Either monad for error handling
- IO monad concepts
- Monadic bind and lift operations

---

## Part VI: Concurrency and Threading

### Chapter 13: Thread-Safe Interfaces
- Thread-agnostic design
- Lock granularity and lock-free idioms
- Thread-local storage patterns
- Reader-Writer锁 patterns

### Chapter 14: Concurrent Data Structures
- Thread-safe queues
- Double-checked locking
- Actor model implementation
- Futures and promises patterns

---

## Part VII: Template Metaprogramming

### Chapter 15: Type Manipulation
- Type manipulation utilities
- Type introspection and traits
- Template specialization strategies
- Template argument deduction

### Chapter 16: Compile-Time Computation
- Template recursion patterns
- Parameter packs and pack expansion
- Fold expressions
- Static assertions and constraints

### Chapter 17: Policy-based Design
- Policy-based class design
- Combining policies
- Runtime polymorphism vs policy-based design
- Expression templates

---

## Part VIII: Error Handling and Robustness

### Chapter 18: Error Handling Idioms
- Exception safety guarantees
- RAII for exception safety
- Error code vs exception patterns
- Expected/Result types

### Chapter 19: Defensive Programming
- Contract programming
- Compile-time vs runtime checks
- Assertions and invariants
- Sanitizer integration patterns

---

## Part IX: Performance Optimization

### Chapter 20: Zero-Cost Abstractions
- Type-based optimization
- Small object optimization
- Inlining and constexpr
- Iterator categories and optimization

### Chapter 21: Cache-Friendly Patterns
- Data-oriented design
- Cache line alignment
- Structure of Arrays (SoA) vs Array of Structures (AoS)
- Memory prefetching idioms

---

## Part X: Design Patterns as Idioms

### Chapter 22: Creational Patterns
- Builder pattern with method chaining
- Singleton implementations and alternatives
- Abstract Factory with type lists
- Object pool patterns

### Chapter 23: Structural Patterns
- Adapter and wrapper idioms
- Facade patterns for libraries
- Flyweight for memory optimization
- Decorator patterns

### Chapter 24: Behavioral Patterns
- Strategy pattern implementation
- Observer with type safety
- Visitor pattern with double dispatch
- Command pattern with type erasure

---

## Part XI: Modern C++ Idioms (C++11 and Beyond)

### Chapter 25: Lambda Patterns
- Lambda capture strategies
- Generic lambdas
- Lambda as callback storage
- Stateful lambdas and closure patterns

### Chapter 26: Range and Views
- Range-based algorithms
- Lazy evaluation with views
- Custom range adaptors
- Pipeline composition

### Chapter 27: Coroutines and Async
- Coroutine fundamentals
- Generator patterns
- Awaitable types
- Task-based async patterns

---

## Part XII: Library Design Idioms

### Chapter 28: API Design
- Rule of least surprise
- Type safety in APIs
- Builder and fluent interfaces
- Error propagation strategies

### Chapter 29: Container Design
- Custom allocator integration
- Iterator design and traits
- Emplace vs insert semantics
- Type-erased containers

---

## Part XIII: Advanced Topics

### Chapter 30: Mixin and Mixin-Based Design
- Mixin class composition
- CRTP-based mixins
- Template mixin patterns

### Chapter 31: Expression Templates
- Expression template fundamentals
- Lazy evaluation in expressions
- Operator overloading patterns

### Chapter 32: Variadic Templates Patterns
- Variadic type construction
- Parameter pack manipulation
- Tuple implementation

### Chapter 33: Reflection and Introspection
- Compile-time reflection patterns
- Reflection with macros
- Automatic serialization

---

## Part XIV: Appendices

### Appendix A: C++ Standards Overview
- Pre-C++11 idioms evolution
- C++11/14/17/20/23 additions
- Upcoming C++26 features

### Appendix B: Idioms Quick Reference
- Alphabetical reference
- Common use cases
- When to use each idiom

### Appendix C: Code Style and Conventions
- Naming conventions
- Code organization
- Documentation patterns

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