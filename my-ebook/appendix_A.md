# Appendix A: C++ Standards Overview

This appendix traces the evolution of the C++ language across its standardized versions, focusing on features that enable, simplify, or replace the idioms discussed in this book. It serves as a chronological reference: if you encounter an idiom and wonder "which standard do I need?" or "what came before?", the answer is here.

---

## Pre-C++11 Idioms Evolution

### C with Classes (1979–1983)

Bjarne Stroustrup's original "C with Classes" added Simula-inspired classes, derived classes, public/private access control, constructors and destructors, and `friend` functions to C. The first idioms were low-level resource management patterns — manual constructor/destructor pairing for file handles, memory, and locks — which would later formalize into RAII. There were no templates, no exceptions, no standard library beyond the C library.

### C++98 (ISO/IEC 14882:1998)

The first international standard codified the language. Templates, exceptions, RTTI (`typeid`, `dynamic_cast`), the Standard Template Library (STL), `iostream`, `string`, and `vector` all entered the standard. Key idioms:

- **RAII**: already in use since C with Classes, now formalized with deterministic destructors. The "resource acquisition is initialization" pattern was C++'s answer to `finally` blocks and garbage collection, and it remains the language's most important idiom.
- **Pimpl (Handle/Body)**: using a pointer to an incomplete type to hide implementation details. Before C++11, this required a raw pointer and manual copy operations (or disabling them).
- **CRTP (Curiously Recurring Template Pattern)**: discovered during early template experimentation. `std::iterator` (now deprecated) used it to provide common typedefs. The pattern provided static polymorphism decades before concepts.
- **SFINAE (Substitution Failure Is Not An Error)**: a principle of template instantiation that became a deliberate idiom for compile-time introspection. Before `void_t` and concepts, SFINAE was the only way to query type capabilities.
- **Tag dispatch**: `std::advance` used iterator category tags to select the optimal algorithm at compile time.

C++98 had no move semantics, no `auto`, no variadic templates, no lambdas. Code was verbose: a simple function object required a class definition, and typenames proliferated.

### TR1 (2007)

Technical Report 1 was not a standard but a preview of what C++11 would deliver. It added `std::shared_ptr`, `std::weak_ptr`, `std::function`, `std::bind`, `std::reference_wrapper`, `type_traits` (the original trait headers), `tuple`, `array`, `unordered_map`/`set`, `regex`, and random number facilities — all in `std::tr1::`. Many books and codebases from this era use `std::tr1::shared_ptr` rather than `std::shared_ptr`.

### Boost pre-C++11

Boost served as a proving ground for almost every C++11 feature. `boost::shared_ptr`, `boost::function`, `boost::bind`, `boost::tuple`, `boost::type_traits`, `boost::mpl`, `boost::fusion`, and `boost::spirit` were widely used. The idioms developed in Boost — policy-based design with `boost::parameter`, expression templates in Spirit and uBLAS, type erasure with `any` and `function` — directly influenced the standard.

---

## C++11/14/17/20/23 Additions

### C++11 (2011)

The largest revision in C++ history. For every pre-C++11 idiom, C++11 provided a simpler, more powerful replacement:

| Feature | Idiom Impact |
|---------|-------------|
| Move semantics and rvalue references | Enabled move constructors, `std::move`, `std::forward`. Eliminated deep copies in containers. Made `unique_ptr` (move-only) possible. |
| `auto` type deduction | Simplified iterator declarations, range-for loops, and complex template types. Changed the naming convention from explicit-verbose to type-inferred. |
| Variadic templates | Replaced preprocessor repetition and recursive template patterns. Enabled `std::tuple`, `std::function` with arbitrary arity, and parameter packs. |
| Lambdas | Replaced function objects written by hand (functors). Enabled capture-by-value and capture-by-reference in local scope. |
| `nullptr` | Replaced `NULL` and `0` for null pointer constants. Eliminated integer-pointer ambiguity in overload resolution. |
| `constexpr` | Allowed compile-time evaluation of functions. Enabled `constexpr`-based metaprogramming as an alternative to template metaprogramming. |
| `std::unique_ptr` | The exclusive-ownership smart pointer. Replaced raw pointers for ownership in most code. Made the Pimpl idiom exception-safe without manual destructors. |
| `std::shared_ptr` and `std::weak_ptr` | Standardized reference-counted ownership. `weak_ptr` broke cycles in shared-ownership graphs. |
| `std::function` | Type-erased callable wrapper. Stored lambdas, function pointers, and function objects uniformly. |
| `std::tuple` | The canonical variadic template. Demonstrated recursive inheritance, index-based access, and the EBO. |
| Range-for | Simplified iteration over containers. Interacts with `begin()`/`end()` and now with C++20 sentinels. |
| `std::array` | Fixed-size array with STL interface. Zero overhead over raw arrays. |
| `override` and `final` | Explicit virtual function control. Prevented signature mismatches in derived classes. |
| `enum class` | Scoped enums with explicit underlying type. No implicit conversion to `int`. |
| `static_assert` | Compile-time assertions. Made trait-based validation readable. |

C++11 also introduced the `default` and `delete` keywords for controlling special member functions, which enabled the Rule of Five (and later the Rule of Zero).

### C++14 (2014)

A smaller revision that polished C++11:

- **Generic lambdas** (`auto` parameters in lambdas). Enabled lambdas that work with any type, reducing the need for function object templates.
- **Return type deduction** for normal functions (`auto` without trailing return type). Simplified writing function templates.
- **`constexpr` relaxation**: functions could contain loops, local variables, and mutation. `constexpr` became practical for real algorithms.
- **`std::make_unique`**: finally added to the standard (it was an oversight in C++11). Idiomatic `unique_ptr` creation.
- **Digit separators** (`1'000'000`): readability.
- **Variable templates** (`template <typename T> constexpr T pi = T(3.14)`): simplified type-dependent constants.
- **`std::integer_sequence` and `std::index_sequence`**: enabling parameter pack manipulation idioms.

C++14's main contribution to idiomatic C++ was making generic code easier to write. Generic lambdas, in particular, changed how callback-heavy APIs were designed.

### C++17 (2017)

A major revision that reshaped everyday C++:

- **Structured bindings**: `auto [a, b, c] = tuple_returning_function()`. Decomposed tuples, pairs, and arrays. Required the tuple-like protocol.
- **`if constexpr`**: compile-time conditional branching in templates. Replaced many SFINAE patterns. Made recursive template functions trivial.
- **Fold expressions**: `(args + ...)` expanded parameter packs directly. Eliminated recursion for most pack operations.
- **`std::optional`**, **`std::variant`**, **`std::any`**: vocabulary types for "maybe a value," "one of several types," and "any type."
- **`std::string_view`**: non-owning string reference. Eliminated temporary string copies in function parameters.
- **Parallel algorithms** (C++17 execution policies): `std::sort(std::execution::par, ...)`. Algorithm-level parallelism without threading.
- **`std::filesystem`**: portable path and directory operations. Replaced platform-specific code.
- **Template argument deduction for class templates**: `std::pair p(1, 2.0)` instead of `std::pair<int, double>`. Reduced verbosity.
- **Inline variables**: `inline const int x = 42;` in headers. Single definition across translation units.
- **Guarded `[[maybe_unused]]`**, **`[[nodiscard]]`**, **`[[fallthrough]]`**: attribute-based intent documentation.
- **`std::clamp`**, **`std::gcd`**, **`std::lcm`**, **`std::not_fn`**: small but useful additions.
- **`std::apply`**: calling a function with arguments from a tuple. The canonical tuple-unpacking pattern.
- **`std::make_from_tuple`**: constructing an object from a tuple of constructor arguments.

C++17 made template metaprogramming dramatically more readable. `if constexpr` and fold expressions replaced TMP recursion in almost all practical cases.

### C++20 (2020)

The largest revision since C++11:

- **Concepts**: named constraints on template parameters. `std::sortable`, `std::ranges::range`, and the full Ranges library. Replaced SFINAE for most constraints. Improved error messages by failing at concept-check time rather than deep inside template instantiation.
- **Ranges**: `std::ranges::sort(v)`, `v | std::views::filter(...) | std::views::transform(...)`. Lazy composable views. Piping replaces nested algorithm calls.
- **Coroutines**: `co_await`, `co_yield`, `co_return`. Stackless coroutines for generators, async tasks, and lazy sequences. Required understanding of promise types, awaitable types, and the coroutine frame.
- **Modules**: `import std;` instead of `#include`. Faster compilation, better encapsulation, no macro leakage. Still maturing in compiler support.
- **`consteval`**: immediately-invoked `constexpr` functions. Required for `std::meta` reflection in C++26.
- **`constinit`**: guarantees static initialization order, preventing the static initialization order fiasco.
- **`std::span`**: non-owning view over contiguous sequences. Like `string_view` for arbitrary types.
- **`std::bit_cast`**: type-punning without undefined behavior. Replaced `memcpy` and `reinterpret_cast` patterns.
- **`<=>` (spaceship operator)**: three-way comparison. Auto-generates `==`, `!=`, `<`, `<=`, `>`, `>=` via `= default`.
- **Lambda extensions**: `template` syntax for explicit lambda templates, `explicit` capture, `constexpr` lambdas, capture of parameter packs by value.
- **Designated initializers**: `Point p{.x = 1, .y = 2};` (C99 style, now in C++).
- **`constexpr` virtual functions**, **`constexpr` `dynamic_cast`**, **`constexpr` `typeid`**: expanding the reach of `constexpr`.
- **`std::erase` / `std::erase_if`**: container-specific element removal.
- **`std::bind_front`**: simplified partial application.
- **`std::to_array`**: creating `std::array` from a C-style array.

C++20's impact on idioms was profound: concepts replaced SFINAE, ranges replaced raw loops + iterators in many cases, coroutines introduced entirely new async patterns, and the spaceship operator automated comparison boilerplate.

### C++23 (2023)

A smaller revision focused on library improvements and language polish:

- **`std::expected<T, E>`**: the value-or-error vocabulary type. Provides a monadic interface (`and_then`, `or_else`, `transform`, `transform_error`). Preferred over exceptions for error-expected paths.
- **`std::optional` monadic operations**: `and_then`, `transform`, `or_else` directly on `optional`. Standardized existing practice.
- **Deducing `this`**: non-static member functions can deduce their own class type. Enabled CRTP-like patterns without CRTP. Simplified mixin composition.
- **`static operator[]`**: allows the subscript operator to be declared as a `static` member function.
- **`if consteval`**: compile-time detection of constant evaluation context. Complement to `std::is_constant_evaluated`.
- **`std::print` / `std::println`**: Python-like printing. Formatted output to stdout/stderr without iostream overhead.
- **`std::flat_map` / `std::flat_set`**: sorted-vector containers with STL interface. Lower memory, better cache behavior than tree-based maps.
- **`std::generator<T>`**: the standard coroutine generator type.
- **`std::mdspan`**: multidimensional array view. Foundation for linear algebra in future standards.
- **Stacktrace library**: `std::stacktrace` for debugging.
- **`std::out_ptr` / `std::inout_ptr`**: adapting smart pointers to C-style output parameters.
- **`multidimensional `operator[]`**: non-static `operator[]` can now accept multiple arguments, enabling `array[3, 5]` syntax.
- **`auto(x)` decayed copy**: explicit use of a prvalue copy.

C++23's most significant idiomatic contribution is probably `std::expected`, which gave C++ a proper discriminated union for error handling, and deducing `this`, which provided a simpler alternative to CRTP.

---

## Upcoming C++26 Features

At time of writing, C++26 is the next major revision, with several large features finalized or nearing finalization:

### Static reflection (`std::meta`)

The most impactful addition for idiomatic C++ since C++11 concepts:

- **`^` operator**: produces a `std::meta::info` object from a type, expression, or namespace. `^int` yields info describing `int`.
- **`std::meta::info`**: a `consteval`-focused value representing program entities. Functions like `std::meta::members_of`, `std::meta::name_of`, `std::meta::type_of`, `std::meta::is_enum`, `std::meta::size_of` query info objects.
- **Code generation**: `consteval` blocks can produce source text that is spliced into the program. This enables compile-time generation of serialization code, enum-to-string conversions, visitor patterns, and more — without macros or external tools.
- **Comparison with existing idioms**: `std::meta` will replace many uses of X macros, Boost.Fusion adaptation, and code generation tools. It will coexist with (not replace) type traits, which remain simpler for single-property queries.

### Pack indexing (P2662)

`Ts...[I]` retrieves the `I`-th type from a parameter pack directly. No more indirection via `std::tuple_element_t<I, std::tuple<Ts...>>`. This simplifies recursive pack algorithms and makes index-based pack access a first-class language feature.

### Contract programming (P2900)

`[[pre: ...]]`, `[[post: ...]]`, and `[[assert: ...]]` attributes for specifying function preconditions, postconditions, and assertions. Contracts are checked or ignored based on a build-time contract level:

```cpp
int divide(int a, int b)
    [[pre: b != 0]]
    [[post r: r * b == a]];
```

Contracts formalize what was previously done with `assert()`, manual if-checks, or the `[[nodiscard]]` attribute. They interact with the exception safety guarantees discussed in Chapter 18.

### `= delete` with a reason (P2957)

`= delete("reason")` allows providing an explanatory string that appears in compiler diagnostics:

```cpp
void bad() = delete("use good() instead");
```

Improves error message quality for intentionally disabled functions.

### Concurrent queues (P0260)

`std::queue` and `std::priority_queue` for concurrent access, part of the ongoing effort to standardize thread-safe containers.

### Relaxed `constexpr` and `constexpr` `std::vector`

Further expansion of `constexpr` into dynamic allocation. `std::vector` and `std::string` can be used in `constexpr` contexts with transient allocation.

### `std::execution` for async (P2300)

A sender/receiver model for asynchronous composition. `std::execution` provides `just`, `then`, `upon_error`, `when_all`, `let_value`, and other combinators that compose into async task graphs. This is a more general and composable alternative to the callback patterns described in Chapter 27.

---

## Standards and Feature Availability

Not all compilers implement a standard completely at the time of its publication. The table below summarizes typical availability:

| Standard | Published | Compiler Maturity | Key Adoption Phase |
|----------|-----------|-------------------|-------------------|
| C++98 | 1998 | Complete (all) | Legacy baseline |
| C++03 | 2003 | Complete (all) | Bug-fix release, same language |
| C++11 | 2011 | Complete (all) | Wide adoption by 2015 |
| C++14 | 2014 | Complete (all) | Quickly superseded C++11 |
| C++17 | 2017 | Complete (all) | Current baseline for most projects |
| C++20 | 2020 | Major features complete (GCC, Clang, MSVC) | Rapidly maturing |
| C++23 | 2023 | Partial (all vendors) | Emerging |
| C++26 | (2026) | Experimental | Not yet final |

When selecting a C++ standard for a project, the general recommendation is to use the latest standard that all target compilers fully support. At the time of writing, C++17 is the safest baseline for maximum portability; C++20 is the practical choice for new projects; C++23 features are usable on the latest toolchains; and C++26 is experimental.

---

## Summary

Each C++ standard has made the language more expressive while preserving the core philosophy of zero-cost abstraction. Pre-C++11 code relied on raw pointers, manual memory management, and elaborate template metaprogramming. C++11 added the ownership model and variadic templates. C++17 made TMP readable. C++20 added concepts and ranges. C++23 and C++26 are automating what previously required macro or codegen solutions — deducing `this`, static reflection, contract programming, and sender/receiver asynchrony.

The idioms in this book are organized by concept, not by standard. The table below maps each chapter to the minimum C++ standard required to use the idioms it describes:

| Chapter | Minimum Standard |
|---------|-----------------|
| 1–2: Foundations | C++98 for RAII; C++11 for move |
| 3: Object Creation | C++11 (unique_ptr, move) |
| 4: Object Composition | C++11 (unique_ptr, lambda) |
| 5: Object Lifetime | C++11 |
| 6: Smart Pointers | C++11 |
| 7: Buffer Management | C++11 (placement new, allocators) |
| 8: Type Erasure | C++11 (variadic templates, move) |
| 9: CRTP | C++98; C++11 for variadic CRTP |
| 10: Tag Dispatch | C++98; C++17 (if constexpr) |
| 11–12: Functional | C++11 (lambdas, bind); C++17 (fold) |
| 13–14: Concurrency | C++11 (thread, mutex, future) |
| 15–17: TMP | C++11 (variadic); C++17 (fold); C++20 (concepts) |
| 18–19: Error Handling | C++98 (exceptions); C++23 (expected) |
| 20–21: Performance | C++11 (constexpr); C++17 (parallel) |
| 22–24: Design Patterns | C++11 (smart pointers, move) |
| 25–27: Modern C++ | C++11 (lambdas); C++20 (ranges, coroutines) |
| 28–29: Library Design | C++11; C++20 (concepts, span) |
| 30: Mixins | C++11; C++23 (deducing this) |
| 31: Expression Templates | C++11; C++17 |
| 32: Variadic Templates | C++11; C++17 (fold) |
| 33: Reflection | C++11 (traits); C++26 (std::meta) |

Use this appendix as a quick reference when choosing which standard to target for a particular idiom, and when reading code from older codebases to understand why it uses the patterns it does.
