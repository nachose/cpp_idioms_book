# Chapter 19: Defensive Programming

Defensive programming is the practice of writing code that anticipates, detects, and responds to errors—both your own mistakes and invalid inputs from the outside world. Unlike the error-handling idioms in the previous chapter, which focus on how to *react* when things go wrong, defensive programming is about building barriers that make things *less likely* to go wrong in the first place, and ensuring that when they do, the failure is caught early, close to its source.

The idioms in this chapter are about writing code that checks its own assumptions. They form the last line of defense between a subtle bug and your production system, and they are the primary tool for transforming crashes-that-happen-in-the-field into assertion-failures-that-happen-during-testing. The shift in timing—from "user reports a corruption" to "developer sees a stack trace in CI"—is the entire point.

## Contract Programming

Contract programming, also called Design by Contract, is a discipline where functions explicitly document and enforce their expectations through three kinds of conditions: **preconditions** (what the caller must guarantee before calling), **postconditions** (what the function guarantees after returning), and **invariants** (what must remain true throughout an object's lifetime).

The term was popularized by Bertrand Meyer in the context of the Eiffel language, where contracts are built into the language itself—the compiler understands `require`, `ensure`, and `invariant` as first-class keywords. C++ has no native contract support (a contracts proposal was considered for C++20 but ultimately removed), but the discipline translates naturally through idioms built on `assert`, `static_assert`, `noexcept`, and careful design.

### Why Contracts Matter

Contracts serve three purposes simultaneously. First, they document intent: the precondition `"index < size()"` tells the caller something that a comment could only hint at. Second, they enforce correctness during testing: when the precondition fires, you know immediately which call site violated the contract, making debugging vastly simpler. Third, they enable compiler optimizations: a function that documents `[[assume]]` conditions can generate better code because the optimizer can disregard impossible paths.

Without contracts, every function must defensively handle every conceivable input, which leads to silent error handling, deep propagation of invalid state, and debugging sessions that span six stack frames. With contracts, the same function says: "I work correctly under these conditions; anything else is a bug and should never happen."

### Preconditions

A precondition is a condition that must hold before a function begins execution. It is the caller's responsibility to satisfy it. If the precondition is violated, the function is not obligated to produce a correct result—it may crash, assert, or invoke undefined behavior.

The simplest way to express a precondition in C++ is `assert`:

```cpp
#include <cassert>
#include <vector>

int median(std::vector<int>& v) {
    assert(!v.empty() && "median requires non-empty vector");
    auto mid = v.size() / 2;
    std::nth_element(v.begin(), v.begin() + mid, v.end());
    return v[mid];
}
```

The assertion checks that the vector is not empty. If a caller passes an empty vector during a debug build, the program aborts with a clear message identifying the file, line, and failing condition. In a release build, the assert disappears, and the function executes unchecked—the precondition becomes documentation only.

This leads to a key design decision: what should happen when a precondition is violated in production? Opinions vary. Some teams compile with assertions enabled in all builds (`-UNDEBUG`), accepting the performance cost for the safety net. Others argue that assertions in production are cruder than alternatives like `std::optional` return types. The right choice depends on the cost of corrupted state versus the cost of a crash. A precondition failure always represents a bug, so there is no truly graceful recovery—only containment.

For more complex preconditions, you might wrap the check in a utility:

```cpp
template <typename T, typename... Args>
constexpr void expect(bool condition, Args&&... msg) {
    if constexpr (!std::is_constant_evaluated()) {
        if (!condition) {
            std::cerr << "Precondition failed: ";
            ((std::cerr << std::forward<Args>(msg)), ...);
            std::cerr << '\n';
            std::abort();
        }
    }
}
```

Or, more idiomatically, use the Guidelines Support Library's `Expects` macro, which serves as a standardized spelling for precondition checks:

```cpp
#include <gsl/gsl_assert>

void resize(Buffer& buf, size_t new_size) {
    Expects(new_size > 0);
    // ...
}
```

The advantage of `Expects` over raw `assert` is purely social: it is a conventional name that every reader recognizes as a precondition check, and it produces consistent error messages across a codebase.

### Postconditions

A postcondition defines what a function guarantees upon exit. It runs after the function body, checking that the promised effect actually occurred. In C++, postconditions are trickier than preconditions because they must capture both the function's result and any side effects.

A simple postcondition checks the return value:

```cpp
int factorial(int n) {
    Expects(n >= 0);
    int result = 1;
    for (int i = 2; i <= n; ++i) result *= i;
    Ensures(result > 0);
    return result;
}
```

Here, `Ensures` (from GSL, though you can define your own) checks that the factorial of any non-negative integer is positive. This particular postcondition is trivial and arguably unnecessary, but it illustrates the pattern.

More valuable postconditions check that an object's state changed correctly:

```cpp
template <typename T>
class SortedVector {
public:
    void insert(const T& value) {
        size_t old_size = size();
        data_.push_back(value);
        std::push_heap(data_.begin(), data_.end());
        Ensures(size() == old_size + 1);
        Ensures(is_heap(data_.begin(), data_.end()));
    }

    size_t size() const { return data_.size(); }

private:
    std::vector<T> data_;
};
```

The postcondition verifies that the container grew by exactly one element and that the heap property still holds. If a future maintainer accidentally breaks the heap property, the postcondition fires immediately rather than causing a subtle corruption that surfaces three call sites away.

Postconditions are most useful when they capture an invariant that the caller depends on. If you document that `pop_back` removes the last element, a postcondition checking `size() == old_size - 1` confirms that the function did what it said. This is especially important for functions with side effects: a postcondition on `save_to_file` might verify that the file's modification timestamp changed, or that `fs::file_size` matches the expected value.

### Class Invariants

A class invariant is a condition that must hold for every valid instance of a type, before and after every public operation. The constructor establishes the invariant, and every member function preserves it.

Class invariants are the backbone of RAII and of any type that manages its own state. The invariants of `std::vector` include `size() <= capacity()` and `data() != nullptr || size() == 0`. The invariants of a `unique_ptr` include that it either owns an object or is null. The invariants of a mutex-guarded counter include that the counter's value is always modified under the lock.

You can document invariants explicitly by checking them at the entry and exit of every public member function:

```cpp
class IntQueue {
public:
    explicit IntQueue(size_t capacity)
        : data_(capacity), capacity_(capacity)
    {
        Ensures(empty());
        Ensures(full() == (capacity == 0));
    }

    void push(int value) {
        check_invariant();
        Expects(!full());
        data_[write_pos_] = value;
        write_pos_ = (write_pos_ + 1) % capacity_;
        ++count_;
        check_invariant();
    }

    int pop() {
        check_invariant();
        Expects(!empty());
        int value = data_[read_pos_];
        read_pos_ = (read_pos_ + 1) % capacity_;
        --count_;
        check_invariant();
        return value;
    }

private:
    void check_invariant() const {
        Expects(count_ <= capacity_);
        Expects(read_pos_ < capacity_);
        Expects(write_pos_ < capacity_);
        Expects(empty() || (read_pos_ != write_pos_));
    }

    std::vector<int> data_;
    size_t capacity_;
    size_t read_pos_ = 0;
    size_t write_pos_ = 0;
    size_t count_ = 0;
};
```

The private `check_invariant` method is called at the beginning and end of every public operation. If any operation corrupts the queue's state, the invariant check fires at the boundary—either at the start of the next call or at the exit of the current one. This makes it impossible for the object to silently enter an invalid state that persists across multiple calls.

The cost is the repeated checking, especially in loops. If performance is a concern, you can gate invariant checks behind a macro or make them conditional on a build configuration:

```cpp
#ifndef INVARIANT_CHECKING
#define CHECK_INVARIANT()
#else
#define CHECK_INVARIANT() do { check_invariant(); } while(false)
#endif
```

Then `push` calls `CHECK_INVARIANT()` instead of `check_invariant()`. In release builds without invariant checking, the macro expands to nothing and introduces zero overhead. The price is that invariant checking is now opt-in rather than always-on, which means a release build may hide invariant violations that a debug build would catch.

### Compile-Time Contracts with static_assert

When the contract can be evaluated at compile time, `static_assert` is far stronger than any runtime check. It moves the verification from "may fail during testing" to "will fail during compilation."

```cpp
template <typename T>
constexpr T clamp(T value, T low, T high) {
    static_assert(std::is_arithmetic_v<T>,
                  "clamp requires an arithmetic type");
    static_assert(noexcept(value < low) && noexcept(value > high),
                  "comparison operations must not throw");
    if (value < low) return low;
    if (value > high) return high;
    return value;
}
```

The preconditions here are enforced by the compiler. If someone tries to call `clamp` with a `std::string`, the program does not compile. If someone provides a type whose comparison operators might throw, the program does not compile. This is the strongest form of contract: it cannot be ignored, it costs nothing at runtime, and the error message points directly to the violated constraint.

`static_assert` works best for contracts that depend only on types and compile-time constants. It cannot check runtime values like "the vector is not empty" or "the file was opened successfully." But for what it can check—type requirements, constant bounds, invariant properties of templates—it is strictly better than any runtime alternative.

### The `[[assume]]` Attribute (C++23)

C++23 introduced `[[assume]]`, which tells the compiler that a given expression is always true. The compiler may use this information for optimization, but unlike `assert`, it is not required to produce any diagnostic if the assumption is violated.

```cpp
double fast_divide(double a, double b) {
    [[assume(b != 0.0)]];
    return a / b;
}
```

This is a precondition, but it is a different kind of precondition from `assert`. With `assert`, the developer explicitly requests a runtime check. With `[[assume]]`, the developer says "I know this is always true; do not generate code to verify it, but you may use this knowledge to optimize." If `b` turns out to be zero, the behavior is undefined. There is no safety net.

`[[assume]]` should be used sparingly, and only when:
- You have measured that the runtime check is a bottleneck.
- The condition is guaranteed by the call graph (e.g., a private helper that is only called after validation).
- The alternative—reorganizing the code to make the condition obvious to the optimizer—is worse.

In general, start with `assert` (or `Expects`) for precondition checks. Replace with `[[assume]]` only after profiling shows the check matters, and document the assumption clearly so future maintainers know what they are promising.

### Contracts in Generic Code

Templates complicate contract programming because the caller is not a person but another template instantiation, and the precondition may involve properties of a type that don't exist yet. The solution is to use `static_assert` with type traits for the type-level contract, and runtime assertions for the value-level contract.

```cpp
template <typename Iter, typename T>
Iter find_or_end(Iter first, Iter last, const T& value) {
    static_assert(std::input_iterator<Iter>,
                  "find_or_end requires an input iterator");
    static_assert(std::equality_comparable_with<T,
                  decltype(*first)>,
                  "value must be comparable to the iterator's value type");
    return std::find(first, last, value);
}
```

The type traits ensure the template is never instantiated with incompatible arguments. The error message is clear and appears at compile time, which is essential for template code where a failed instantiation can produce pages of cryptic diagnostics.

For value-level checks inside generic code, use `if constexpr` to conditionally enable assertions only when the value type supports the check:

```cpp
template <typename Container>
constexpr auto last(const Container& c) {
    Expects(!c.empty());
    return c.back();
}
```

A precondition that checks `!c.empty()` is universally meaningful for sequences. But a precondition like `Expects(value >= 0)` only makes sense for numeric types and would be meaningless for strings. Use SFINAE, concepts, or `if constexpr` to scope value-level preconditions to the types that need them.

### Writing Good Contract Messages

A precondition that fires with the message "Assertion `i < n` failed" is less useful than one that says "Index 47 out of bounds for buffer of size 32". The former tells you what was checked; the latter tells you what went wrong and by how much.

Whenever practical, include the actual values in the assertion message:

```cpp
void set_color(int r, int g, int b) {
    Expects(r >= 0 && r <= 255
        && g >= 0 && g <= 255
        && b >= 0 && b <= 255);
    // ...
}
```

But a message that says "r = 300, expected range [0, 255]" is even better. Consider a helper:

```cpp
#define RANGE_CHECK(val, min, max) \
    do { \
        if ((val) < (min) || (val) > (max)) { \
            std::cerr << "Range check failed: " << #val \
                      << " = " << (val) \
                      << " not in [" << (min) << ", " << (max) << "]\n"; \
            std::abort(); \
        } \
    } while(false)
```

This trades some verbosity for significantly better debuggability. The trade-off is worth it for preconditions that you expect to fire during development. For preconditions that should almost never fire even in debug builds (e.g., internal invariants of long-stable code), a simple `assert` may suffice.

### Performance Implications

Contract checks have a cost. Every `assert` evaluates its condition, and complex conditions—deep structure comparisons, traversal of large data structures—can dominate the runtime of a function if left unchecked.

The standard strategy is to enforce contracts in debug builds and strip them from release builds:

```
# Debug build: enforce contracts
g++ -std=c++23 -O0 -g -UNDEBUG main.cpp

# Release build: remove assertions
g++ -std=c++23 -O2 -DNDEBUG main.cpp
```

This works well when: (a) your testing catches most contract violations, (b) the cost of checking is non-trivial, and (c) you accept that release builds may silently exhibit undefined behavior on violated contracts.

For cases where the check is cheap and the failure is catastrophic, keep the check in all builds:

```cpp
void write_sector(int disk, const void* data, size_t n) {
    // Always check—corrupting a disk is worse than a crash.
    if (n > MAX_SECTOR_SIZE) {
        std::cerr << "sector write exceeds maximum size\n";
        std::abort();
    }
    // ...
}
```

A middle ground is to keep cheap invariants always-on and gate expensive ones:

```cpp
void check_invariant() const {
    Expects(count_ <= capacity_);          // Always on
    Expects(is_valid_representation());    // May be too expensive for release
}
```

You can separate them with macros or function-level attributes that control whether the check is emitted.

### Trade-Offs and Alternatives

Contract programming is not universally accepted. Critics point out that:
- Contracts that are stripped in release builds provide a false sense of security. The code that runs in production is not the code that was tested.
- Contracts can encourage a "blame the caller" mentality where functions refuse to validate their inputs, pushing defensive checks to every call site.
- Overly aggressive contracts penalize performance even in debug builds, leading developers to disable them entirely.

Alternatives include:
- **Validation functions** that return `std::optional` or `std::expected` instead of asserting. These handle invalid input at runtime without crashing, but they push the error-handling burden to the caller and encourage silent recovery from situations that might be bugs.
- **Type-system enforcement** that makes invalid states unrepresentable. For example, instead of checking `index < size()`, use a `BoundedIndex` type that can only be constructed with a valid index. This moves the check from the function body to the type constructor, enforcing the contract once rather than at every use.
- **Static analysis** with tools like the Clang Static Analyzer, which can prove that certain contracts always hold (or always fail) without runtime checks. This is complementary to runtime contracts: static analysis covers what it can prove, and runtime assertions cover the rest.

Contract programming is most effective when used judiciously. Check what can meaningfully be checked—preconditions on public API boundaries, invariants of core data structures, postconditions on complex mutations—and skip the rest. An assertion that never fires and never could fire is noise. An assertion that fires once and saves a debugging session is worth ten times its weight in comments.

## Compile-Time vs Runtime Checks

Not all checks are created equal. A check that runs at compile time costs nothing at runtime and cannot be ignored. A check that runs at runtime costs CPU cycles and can be stripped by a sufficiently determined bug (or a release build with `NDEBUG`). Choosing between them is one of the most consequential decisions in defensive programming.

The principle is simple: **push verification as early in the pipeline as possible.** A bug caught at compile time never becomes a bug at runtime. A bug caught by an assertion in testing never reaches production. A bug caught by a production check damages only a single request instead of corrupting persistent state.

The reality is that most conditions depend on runtime data—the user's input, the network response, the file on disk—and cannot be checked at compile time. But a surprising number of conditions *can* be shifted left, and the idioms for doing so are distinct from the runtime assertion patterns we have already seen.

### The Spectrum of Checking

Checks in C++ exist on a spectrum from fully static to fully dynamic:

| Stage | Mechanism | Cost | When Failure Is Detected |
|---|---|---|---|
| Compile time | `static_assert`, concepts, type traits | Zero | During compilation |
| Translation time | `#error`, `#if` with constant expressions | Zero | During preprocessing |
| Link time | Linker errors for missing symbols | Zero | During linking |
| Constant evaluation | `constexpr`, `consteval` functions | Zero at runtime | During compilation or constant evaluation |
| Program startup | Global invariant checks, `constinit` validation | Once at startup | Before `main()` |
| Runtime (debug) | `assert`, `Expects`, `Ensures` | In debug builds only | During testing |
| Runtime (always) | `if` checks, exceptions, `std::expected` | Always paid | In production |

Each step from top to bottom represents a later detection point and a higher runtime cost. The goal is to find the leftmost point on this spectrum that can still express the check.

### static_assert: The Strongest Check

We touched on `static_assert` in the contract programming section, but it deserves fuller treatment as the foundational compile-time checking tool. Every `static_assert` is a compile-time firewall: if the condition fails, the program simply does not exist.

```cpp
template <size_t MaxSize>
class StaticBuffer {
    static_assert(MaxSize > 0, "buffer must have at least one element");
    static_assert(MaxSize <= 1 << 20, "buffer exceeds maximum allowed size (1 MiB)");
    std::array<std::byte, MaxSize> data_;
};
```

These checks fire the moment anyone tries to instantiate `StaticBuffer<0>` or `StaticBuffer<(1 << 21)>`. The error message points directly to the line with the violating instantiation, and the developer learns about the mistake before the program runs even once.

`static_assert` is most valuable for enforcing domain rules that are expressible as compile-time constants:

```cpp
enum class ColorSpace { RGB, SRGB, Linear, HSV };

template <ColorSpace From, ColorSpace To>
struct ConversionMatrix {
    static_assert(From != To, "converting a color to itself is a no-op");
    // ...
};
```

The key limitation is that the condition must be a constant expression. You cannot use `static_assert` to check a runtime value, a file size, or a network response. For everything else, you drop down to runtime checking.

### Concepts as Compile-Time Contracts (C++20)

C++20 concepts are a form of compile-time contract enforcement for templates. Unlike `static_assert`, which fires as a single point of failure, concepts participate in overload resolution and produce significantly better error messages.

```cpp
template <typename T>
concept ReadableFile = requires(T t) {
    { t.read(std::span<std::byte>{}) } -> std::same_as<size_t>;
    { t.seek(std::streamoff{}) } -> std::same_as<bool>;
    { t.tell() } -> std::convertible_to<size_t>;
};

template <ReadableFile File>
size_t read_all(File& file, std::span<std::byte> buffer) {
    static_assert(ReadableFile<File>, "internal invariant broken");
    size_t total = 0;
    while (auto n = file.read(buffer.subspan(total))) {
        total += n;
    }
    return total;
}
```

The concept `ReadableFile` is a precondition on the template parameter. If someone passes a type that does not satisfy the concept, the compiler rejects the call with a message like "the associated constraints are not satisfied" and lists exactly which required expressions failed. This is a dramatic improvement over the pre-C++20 alternative of pages of error messages from failed template instantiations.

The `static_assert` inside the function body is technically redundant—the concept already guarantees the precondition at the call site—but serves as a belt-and-suspenders check for internal consistency. If someone later changes the function signature or provides a constrained overload, the `static_assert` catches any violation at the point of instantiation.

Concepts also support `requires` clauses that act as conditional compile-time checks:

```cpp
template <typename T>
void serialize(const T& value) {
    if constexpr (std::integral<T>) {
        // Fixed-width encoding for integers.
    } else if constexpr (requires { value.serialize(); }) {
        // Duck-typing: if T has a serialize() member, use it.
        value.serialize();
    } else {
        // Fallback: use reflection or manual encoding.
        static_assert(always_false_v<T>,
                      "no serialization strategy for this type");
    }
}
```

The `always_false_v<T>` trick (`template <typename> constexpr bool always_false_v = false;`) ensures the `static_assert` only fires when the template is instantiated with a type that enters the fallback branch. If every possible type has a concrete strategy, this branch is dead code, and the `static_assert` is never reached. But if a developer adds a new type without updating the serialization logic, the compiler catches the omission.

### constexpr and consteval for Value Validation

The `constexpr` keyword allows functions to be evaluated at compile time when their inputs are known. This turns runtime checks into compile-time checks transparently:

```cpp
constexpr int parse_port(const char* str) {
    if (str == nullptr) return -1;  // Must be checked at runtime
    int port = 0;
    for (const char* p = str; *p != '\0'; ++p) {
        if (*p < '0' || *p > '9') return -1;
        port = port * 10 + (*p - '0');
        if (port > 65535) return -1;
    }
    return port;
}

// At compile time:
constexpr int server_port = parse_port("8080");
static_assert(server_port > 0, "server port must be valid");

// At runtime:
int user_port = parse_port(user_input);
if (user_port < 0) { /* handle error */ }
```

When `parse_port` is called with a string literal, the function executes during compilation. If the literal is malformed, the compiler (not the program) reports the error. When called with a runtime string, the same function body validates the input at runtime. The check is the same; only the timing differs.

C++20's `consteval` goes further: it forces a function to be evaluated at compile time, refusing to compile if the inputs are not constant expressions:

```cpp
consteval unsigned long const_hash(const char* str) {
    unsigned long h = 14695981039346656037ULL;
    while (*str) {
        h ^= static_cast<unsigned long>(*str++);
        h *= 1099511628211ULL;
    }
    return h;
}

// Usage - hash computed at compile time:
switch (const_hash(input_string)) {
    case const_hash("start"):  // These calls happen at compile time
        /* ... */
        break;
    case const_hash("stop"):
        /* ... */
        break;
    // ...
}
```

Any error inside a `consteval` function—an out-of-bounds access, a failed assertion, an invalid branch—becomes a **compilation error**. This is the strongest form of defensive programming: the code literally cannot be compiled unless the inputs satisfy all internal constraints. The downside, of course, is that `consteval` can only operate on compile-time inputs, which limits its applicability to configuration constants, type maps, and compile-time data structures.

### if constexpr for Conditional Compilation

The `if constexpr` statement (C++17) allows you to conditionally include or exclude code based on compile-time predicates. This is not a check per se, but it enables checks that would otherwise require preprocessor macros:

```cpp
template <typename T>
constexpr void log(const T& value) {
    if constexpr (std::is_same_v<T, std::string>) {
        static_assert(sizeof(T) > 8, "string type is too large for fast logging");
        log_string(value);
    } else if constexpr (std::is_arithmetic_v<T>) {
        log_numeric(value);
    } else {
        static_assert(always_false_v<T>, "unsupported type for logging");
    }
}
```

The `static_assert` in the `else` branch fires only when a type that is neither a string nor arithmetic is instantiated. Without `if constexpr`, the `else` branch would need to be compiled for every instantiation, making the `static_assert` unconditional.

More subtly, `if constexpr` can remove runtime overhead by checking conditions that would otherwise require dynamic dispatch:

```cpp
template <typename T>
T* allocate(size_t count) {
    if constexpr (std::is_trivially_destructible_v<T>) {
        // Can skip destructor tracking - simpler allocation.
        return static_cast<T*>(::operator new(count * sizeof(T)));
    } else {
        // Must track destructors for non-trivial types.
        return static_cast<T*>(::operator new(count * sizeof(T),
                                              std::align_val_t{alignof(T)}));
    }
}
```

The check `std::is_trivially_destructible_v<T>` is evaluated at compile time. The branch that is not taken is discarded before code generation. The resulting machine code contains no runtime condition—it directly allocates using the appropriate strategy for T. This is compile-time checking that *generates* correctness: the code path changes based on type properties, but the check itself costs nothing at runtime.

### Preprocessor Guards: The Original Compile-Time Check

Before `static_assert`, before concepts, before `constexpr`, there was the preprocessor. Conditional compilation with `#if`, `#ifdef`, and `#error` remains the only way to check conditions that depend on build configuration rather than type properties:

```cpp
#ifndef USE_SIMD
    #error "USE_SIMD must be defined: set to 1 for SIMD, 0 for scalar"
#endif

#if USE_SIMD
    #if !defined(__AVX2__) && !defined(__SSE4_2__)
        #error "SIMD mode requires AVX2 or SSE4.2"
    #endif
#endif
```

These checks happen during preprocessing, before any C++ syntax is parsed. They are crude—no type information, no scoping, no templates—but they catch configuration errors that no other mechanism can reach.

The preprocessor is also useful for platform-specific invariants:

```cpp
class AtomicCounter {
    static_assert(sizeof(std::atomic<int>) == sizeof(int),
                  "expected lock-free atomic to have same size as int");
    // ...
#if defined(__GNUC__) && !defined(__clang__)
    static_assert(__GNUC__ >= 10, "this code requires GCC 10 or later");
#endif
};
```

The platform-specific `static_assert` is a compile-time check that only fires on GCC, and only when the GCC version is too old. On Clang or MSVC, the check is simply not compiled.

### Static Analysis Integration

Compiler warnings are a form of compile-time check that sits between `static_assert` and runtime assertions. They are compile-time heuristics: the compiler emits a diagnostic when it detects a likely bug, but unlike `static_assert`, the condition cannot be guaranteed in all cases.

```cpp
[[nodiscard]] int compute_checksum(const std::vector<std::byte>& data);
// ...
compute_checksum(buffer);  // Warning: return value discarded
```

`[[nodiscard]]` is a compile-time contract: it tells the compiler that ignoring the return value is almost certainly a bug. The compiler enforces this with a warning (which can be promoted to an error with `-Werror`). This costs nothing at runtime and catches a class of bugs (forgetting to check a result) that runtime checks could never detect.

Similarly, compiler attributes like `-Wreturn-type`, `-Wuninitialized`, and `-Wsign-compare` perform compile-time checks that catch real bugs:

```cpp
int divide(int a, int b) {
    // Warning: control reaches end of non-void function
    // when b != 0 (assuming no exception)
    if (b == 0) {
        return 0;
    }
    // Missing return for the non-zero case
}
```

The compiler cannot prove that every path returns a value in all cases (it's undecidable in general), but it can catch obvious omissions. The check is a heuristic, but it is a cheap and effective one.

For stronger static analysis, tools like the Clang Static Analyzer, GCC `-fanalyzer`, and external tools like Coverity or PVS-Studio perform path-sensitive analysis that can detect null-pointer dereferences, use-after-free, and out-of-bounds accesses at compile time. These are not language features but external tools, and they work best when the code is annotated with contracts:

```cpp
void process(int* p) {
    [[maybe_unused]] int* guard = p;  // Static analyzer: p is non-null here
    *p = 42;
}
```

Annotations like GSL's `gsl::not_null` or Clang's `_Nonnull` give the static analyzer more information than it can deduce from the code alone:

```cpp
#include <gsl/gsl>
void write_buffer(gsl::not_null<FILE*> file, const std::byte* data, size_t n);
```

The analyzer can now prove that `file` is never null inside `write_buffer`, eliminating entire classes of false positives and enabling deeper analysis.

### Runtime Checks: When Compile Time Is Not Enough

For all the power of compile-time checking, most bugs involve conditions that cannot be known until the program executes. The user's input, the contents of a file, the return value of a system call, the order of operations in a multithreaded program—these are fundamentally runtime phenomena.

The question is not whether to use runtime checks, but how to use them alongside compile-time checks to maximize coverage while minimizing cost.

A common strategy is the "pyramid" approach:

1. **Compile-time checks** for type constraints, size limits, and constant validation.
2. **Static analysis** for data flow, null safety, and resource leaks.
3. **Debug-build assertions** for internal invariants and function contracts.
4. **Production checks** for user input, system calls, and external data.

Each layer catches bugs that the previous layer missed. The goal is not to eliminate any single layer but to ensure that most bugs are caught in the upper layers, where the cost of detection is lowest.

```cpp
template <typename T, size_t MaxSize>
class BoundedVector {
    static_assert(MaxSize > 0, "MaxSize must be positive");
    static_assert(std::is_nothrow_move_assignable_v<T>,
                  "BoundedVector requires noexcept-movable elements");

    void push_back(const T& value) {
        // Runtime check: the condition depends on runtime state.
        Expects(size() < MaxSize);
        data_[size_++] = value;
    }

    // ...
};
```

The template parameters (`MaxSize > 0`, `T` is noexcept-movable) are verified at compile time. The capacity check (`size() < MaxSize`) must wait until runtime because it depends on how many elements have been inserted. Both checks are necessary; neither alone is sufficient.

### The Cost of Runtime Checks

Runtime checks have a real cost, and the decision to keep them in production builds requires justification. Every `if` statement in your hot path, every bounds check in a tight loop, every precondition in a frequently-called function consumes CPU cycles.

The standard defense is to separate "correctness" checks from "performance" checks:

```cpp
class MatrixMultiplication {
public:
    void compute(const Matrix& a, const Matrix& b, Matrix& out) {
        // Correctness check: always enabled
        Expects(a.cols() == b.rows());
        Expects(out.rows() == a.rows());
        Expects(out.cols() == b.cols());

        // Performance: skip per-element checks in release builds
        for (size_t i = 0; i < a.rows(); ++i) {
            for (size_t j = 0; j < b.cols(); ++j) {
                double sum = 0;
                for (size_t k = 0; k < a.cols(); ++k) {
                    assert(k < a.cols() && k < b.rows());  // Debug only
                    sum += a(i, k) * b(k, j);
                }
                out(i, j) = sum;
            }
        }
    }
};
```

The dimension checks are cheap (three comparisons) and catch a class of bugs that would otherwise produce silently wrong results. The per-element bounds check inside the innermost loop is expensive (it runs millions of times) and is stripped in release builds. The line between "always check" and "debug-only" is drawn based on cost and severity.

### Compile-Time Registries and Runtime Dispatch

One of the most powerful patterns for combining compile-time and runtime checking is the compile-time registry. You define the set of valid operations at compile time, and the runtime checks that input falls within that set:

```cpp
enum class Opcode : uint8_t {
    Add, Sub, Mul, Div, Neg, Not,
    COUNT  // Sentinel: number of valid opcodes
};

class Interpreter {
public:
    int execute(Opcode op, int a, int b) {
        static_assert(static_cast<int>(Opcode::COUNT) <= 256,
                      "opcode value must fit in uint8_t");
        Expects(op < Opcode::COUNT);
        return operations_[static_cast<size_t>(op)](a, b);
    }

private:
    static constexpr auto operations_ = generate_table();
};
```

The `static_assert` checks at compile time that the opcode enum fits in the wire format. The `Expects` checks at runtime that the specific opcode is valid. The table generation (`generate_table`) happens at compile time using `constexpr`, which means any invalid entry (a function with the wrong signature, a missing handler) becomes a compile error.

This pattern—"check what you can at compile time, then verify the rest at runtime"—applies across domains: command parsers, protocol decoders, template engines, serialization frameworks. The compile-time portion eliminates entire classes of bugs, and the runtime portion handles the variability that only execution can reveal.

### Trade-Offs and Decision Framework

Choosing between compile-time and runtime checks involves several trade-offs:

**Flexibility vs. safety.** A compile-time check is absolute—it guarantees the condition never occurs—but it limits what you can do. A runtime check is flexible—it handles any input—but it can fail in production. The more you move to compile time, the more rigid your code becomes.

**Expressiveness vs. cost.** Compile-time checks can express type-level constraints, constant bounds, and template requirements. They cannot express "this file exists" or "the user has permission" or "the network is available." Runtime checks can express anything but cost CPU cycles for every evaluation.

**Developer experience.** Compile-time checks give immediate, local feedback. A `static_assert` fires at the exact line where the violating code is written. A runtime assertion may fire hours later, in a different context, under different inputs. The developer who introduced the bug may be long gone.

**Testing burden.** Compile-time checks are verified by the compiler; no test case is needed. Runtime checks require test coverage to be exercised. A runtime assertion that no test triggers is not a safety net—it is dead code.

The decision framework can be summarized as:

| If the condition... | Then use... |
|---|---|
| Depends only on types, constants, or template parameters | `static_assert`, concepts, `constexpr` |
| Depends on build configuration or platform | Preprocessor `#if` / `#error` |
| Is an internal invariant that should never be violated by correct code | Debug-build `assert` / `Expects` |
| Involves user input, external data, or system calls | Runtime production check (if/exception/expected) |
| Is expensive and provably guaranteed by the call graph | `[[assume]]` (after profiling) |

No single checking mechanism covers all cases. The art of defensive programming lies in distributing your checks across this spectrum—catching what you can early, verifying what you must at runtime, and knowing the difference between the two.

## Assertions and Invariants

Assertions and invariants are the most concrete tools in the defensive programmer's toolbox. An assertion is a statement that a specific condition holds at a specific point in execution. An invariant is a broader property that holds across an entire scope—the lifetime of a variable, the body of a loop, or the lifespan of an object. The two concepts are deeply connected: invariants are enforced through assertions placed at scope boundaries.

The previous sections touched on assertions as a mechanism for contracts and compile-time checks. This section focuses on the patterns and pitfalls of using assertions effectively: how to write them, where to place them, when to keep them in production, and how to design classes that maintain their invariants through any sequence of operations.

### The Anatomy of an Assertion

In its simplest form, an assertion is a boolean expression and a termination action:

```cpp
assert(ptr != nullptr);
```

When `NDEBUG` is not defined, `assert` evaluates the expression. If it is false, it calls `abort()` after printing the file, line, and expression to stderr. When `NDEBUG` is defined, the macro expands to nothing—the expression is not evaluated, and no code is generated.

This removes-the-check-in-release behavior is the most controversial aspect of `assert`. It means that code which works correctly in debug builds may exhibit different behavior in release builds if the assertion expression has side effects:

```cpp
assert(++counter < limit);  // Bug: side effect inside assertion
```

In a debug build, `counter` is incremented and checked. In a release build, the assert disappears, and `counter` is never incremented. Everything that depends on `counter` being updated breaks. This is why assertion expressions should be pure—no side effects, no function calls that modify state.

A more robust assertion macro should document that the condition is a pure check:

```cpp
#ifdef ASSERTIONS_ENABLED
#define ASSERT(cond) do { \
    if (!(cond)) { \
        std::cerr << "ASSERTION FAILED: " #cond \
                  << " at " << __FILE__ << ":" << __LINE__ << '\n'; \
        std::abort(); \
    } \
} while(false)
#else
#define ASSERT(cond) ((void)0)
#endif
```

This version avoids the side-effect problem (the condition is always a pure expression) and provides a consistent mechanism for enabling assertions independently of `NDEBUG`.

### Assertion Placement Patterns

Placement of assertions matters as much as their content. The most useful assertions sit at boundaries: function entry, function exit, and control flow forks.

**Function entry assertions** check preconditions:

```cpp
double sqrt_positive(double x) {
    assert(x >= 0 && "sqrt requires non-negative input");
    return std::sqrt(x);
}
```

These catch callers that violate the function's contract. They are most valuable on public API functions where the caller is outside your control or in a different translation unit.

**Function exit assertions** check postconditions:

```cpp
std::vector<int> sorted(std::vector<int> v) {
    std::sort(v.begin(), v.end());
    assert(std::is_sorted(v.begin(), v.end()));
    return v;
}
```

These are less common but invaluable when the function's logic is complex. A sorting function that silently produces unsorted output is a disaster; a postcondition assertion catches it immediately.

**Control flow assertions** catch impossible branches:

```cpp
switch (command) {
    case Command::Start: /* ... */ break;
    case Command::Stop:  /* ... */ break;
    case Command::Pause: /* ... */ break;
    default:
        assert(false && "unknown command");
        std::unreachable();
}
```

The `assert(false)` idiom marks a path that should never execute. If the switch reaches the default case despite the enum supposedly covering all values, the assertion fires, and `std::unreachable()` (C++23) tells the optimizer that this path is truly impossible. Combined, they ensure that adding a new enum value without updating the switch is caught immediately.

**Immutable-after-construction assertions** catch inadvertent mutation:

```cpp
class Config {
public:
    void freeze() { frozen_ = true; }

    void set_timeout(int ms) {
        assert(!frozen_ && "cannot modify config after freeze");
        timeout_ = ms;
    }

private:
    bool frozen_ = false;
    int timeout_ = 30000;
};
```

The assertion fires if any mutator is called after `freeze()`. This pattern is useful for configuration objects, builder objects that should be sealed before use, and any object that transitions from a mutable to an immutable state.

### Assertions and Undefined Behavior

An assertion that passes does not guarantee the absence of undefined behavior. The two concepts are orthogonal:

```cpp
int divide(int a, int b) {
    assert(b != 0);
    return a / b;              // Still UB if b == 0, but assert prevents it
}

int* get_ptr(std::vector<int>& v, size_t i) {
    assert(i < v.size());
    return &v[i];              // Safe only because assert guarantees i is in bounds
}
```

The assertion prevents undefined behavior by halting the program before the dangerous operation executes. This is the primary purpose of runtime assertions: to ensure that the conditions for defined behavior are met.

But assertions can also *mask* undefined behavior if the assertion itself has undefined behavior:

```cpp
assert(p != nullptr && *p == 42);  // UB if p is null: *p is evaluated
```

If `p` is null, the expression `*p == 42` dereferences a null pointer before the `&&` short-circuit can save it. The fix is to separate the checks:

```cpp
assert(p != nullptr);
assert(*p == 42);
```

This principle extends to all potentially-UB conditions: checked pointer dereferences, signed integer overflow (which is UB in C++), and access to uninitialized values should never appear inside the assertion expression itself.

### Class Invariants: Deeper Than Contracts

The contract programming section introduced class invariants as conditions checked at public method boundaries. But invariants are a richer concept than that simple pattern suggests. A well-designed class has invariants that permeate its design, and those invariants should be enforced at multiple levels.

Consider a class that represents a range of indices:

```cpp
class IndexRange {
public:
    IndexRange(size_t start, size_t end)
        : start_(start), end_(end)
    {
        assert(start_ <= end_ && "range start must not exceed end");
    }

    size_t length() const {
        assert(start_ <= end_);
        return end_ - start_;
    }

    bool contains(size_t index) const {
        assert(start_ <= end_);
        return index >= start_ && index < end_;
    }

private:
    size_t start_;
    size_t end_;
};
```

The invariant `start_ <= end_` must hold for every valid `IndexRange` instance. The constructor establishes it. Every member function preserves it. The assertions inside `length()` and `contains()` are redundant—the constructor guarantee should be sufficient—but they serve as documentation and as defense against future changes that might introduce a path that breaks the invariant.

A stronger approach encodes the invariant into the type system:

```cpp
template <typename T>
class Bounded {
public:
    Bounded(T value, T min, T max)
        : value_(value), min_(min), max_(max)
    {
        assert(min <= max && "invalid bounds");
        assert(value >= min && value <= max && "value out of bounds");
    }

    T get() const { return value_; }

private:
    T value_;
    T min_;
    T max_;
};
```

Now the invariant is enforced at construction time, and every subsequent access is trivially valid. No assertion is needed in `get()` because the constructor guarantee is sufficient.

### Loop Invariants

Loop invariants are conditions that hold before, during, and after every iteration of a loop. They are a cornerstone of program verification in formal methods, and they translate to practical defensive programming through assertions at loop boundaries.

```cpp
int sum(const std::vector<int>& v) {
    int result = 0;
    // Invariant: result == sum of v[0..i)
    for (size_t i = 0; i < v.size(); ++i) {
        assert(result == std::accumulate(v.begin(), v.begin() + i, 0));
        result += v[i];
    }
    // Postcondition: result == sum of all elements
    assert(result == std::accumulate(v.begin(), v.end(), 0));
    return result;
}
```

This is a trivial example, but the pattern scales to complex loops. A binary search, for instance, maintains the invariant that the target value is within `[low, high)`:

```cpp
int find(const std::vector<int>& sorted, int target) {
    size_t low = 0, high = sorted.size();
    // Invariant: target is in [low, high) if present at all
    while (low < high) {
        size_t mid = low + (high - low) / 2;
        assert(mid >= low && mid < high);
        assert(low <= high);
        if (sorted[mid] < target) {
            low = mid + 1;
        } else if (sorted[mid] > target) {
            high = mid;
        } else {
            return static_cast<int>(mid);
        }
    }
    return -1;
}
```

The assertions verify that the search space never expands and that the midpoint is always within bounds. If a logic error causes `low` to exceed `high` or `mid` to exit the range, the assertion fires immediately rather than producing an out-of-bounds access several iterations later.

For data structure traversal, loop invariants catch off-by-one errors:

```cpp
// Invariant: current is always a valid node or null
auto current = head;
while (current) {
    assert(current != nullptr);
    assert(current->next != current);  // No self-loop
    current = current->next;
}
```

The self-loop assertion catches circular lists in a linear traversal. Without it, the loop would run forever or until the system runs out of memory.

### Data Structure Invariants

Data structures have invariants that go beyond simple class invariants. A binary search tree requires that the left child is less than the parent and the right child is greater. A heap requires that the parent is larger (or smaller) than both children. A hash table requires that every element is at the index determined by its hash.

These invariants are expensive to check fully—verifying that a red-black tree satisfies all its properties is O(n), which defeats the purpose of the data structure. The solution is to check invariants selectively, in debug builds, and in response to specific events:

```cpp
template <typename T>
class SortedList {
public:
    void insert(const T& value) {
        // ... insertion logic ...
        assert(is_sorted(debug_verify()));
    }

    [[nodiscard]] bool debug_verify() const {
        for (size_t i = 1; i < data_.size(); ++i) {
            if (data_[i - 1] > data_[i]) return false;
        }
        return true;
    }

private:
    std::vector<T> data_;
};
```

The `debug_verify` method checks the sorted invariant by scanning the entire container. Calling it after every mutation makes the class O(n) in debug builds, which is acceptable for testing but catastrophic for production. The solution is to call it only in debug builds and only after mutating operations.

A more sophisticated approach uses a checksum or hash of the invariant state:

```cpp
template <typename T>
class Heap {
public:
    void push(const T& value) {
        data_.push_back(value);
        std::push_heap(data_.begin(), data_.end());
        invariant_hash_ = compute_invariant_hash();
    }

    T pop() {
        assert(check_invariant());
        std::pop_heap(data_.begin(), data_.end());
        T result = std::move(data_.back());
        data_.pop_back();
        invariant_hash_ = compute_invariant_hash();
        return result;
    }

    [[nodiscard]] bool check_invariant() const {
        return compute_invariant_hash() == invariant_hash_
            && std::is_heap(data_.begin(), data_.end());
    }

private:
    [[nodiscard]] size_t compute_invariant_hash() const {
        size_t h = 0;
        for (size_t i = 0; i < data_.size(); ++i) {
            h ^= std::hash<T>{}(data_[i]) + 0x9e3779b9 + (h << 6) + (h >> 2);
        }
        return h;
    }

    std::vector<T> data_;
    size_t invariant_hash_ = 0;
};
```

The hash-based invariant check detects corruption without scanning the entire data structure on every access. If `pop` is called on a heap whose state was corrupted by a dangling pointer or buffer overflow, the hash mismatch fires immediately. The cost is the hash computation on mutation, which is O(n) but with a fast constant factor, and the hash comparison on access, which is O(1). This is a practical middle ground between full checking and no checking.

### Assertions in Multithreaded Code

Assertions in multithreaded code are more complex because the condition may be true at the point of the assertion but false a nanosecond later due to another thread. The standard advice is: **assertions should only check thread-local state or state protected by a mutex that the current thread holds.**

```cpp
void ThreadSafeCounter::increment() {
    std::lock_guard lock(mutex_);
    assert(count_ >= 0);         // Safe: mutex is held
    ++count_;
    assert(count_ > 0);          // Safe: mutex is still held
}

int ThreadSafeCounter::get() const {
    std::lock_guard lock(mutex_);
    assert(count_ >= 0);         // Safe: mutex is held
    return count_;
}
```

Assertions that check shared state without holding the appropriate lock are inherently racy:

```cpp
void unsafe_check(const ThreadSafeCounter& counter) {
    // Race condition: count_ may change between check and use.
    assert(counter.count_ >= 0);  // Wrong! count_ is not thread-local
}
```

For lock-free code, assertions are even trickier. A condition that appears true under relaxed memory ordering may be false under sequential consistency, and vice versa. The safest approach is to check invariants that are independent of memory ordering—type properties, structural properties of data structures—rather than specific values:

```cpp
void lock_free_push(LFStack& stack, int value) {
    node* n = new node(value);
    do {
        n->next = stack.head.load(std::memory_order_relaxed);
    } while (!stack.head.compare_exchange_weak(
        n->next, n, std::memory_order_release, std::memory_order_relaxed));

    // Safe: n is thread-local, and head was manipulated correctly by CAS.
    assert(n->next != n && "self-loop in lock-free stack");
}
```

The assertion checks a structural invariant (no self-loop) rather than a specific value, making it safe regardless of memory ordering.

### Assertion Failures: What Happens Next?

When an assertion fires, the program must decide what to do. The options, from most to least common, are:

**Abort.** `assert` and `std::abort()` terminate the program immediately. This is the safest response: corrupted state cannot spread, and the crash dump captures the exact state at the point of failure. The downside is that all unsaved work is lost and the user experience is terrible.

**Throw an exception.** Some custom assertion frameworks throw instead of aborting. This allows the program to catch the assertion failure at a higher level, log the error, and attempt recovery. The problem is that throwing from a destructor or a `noexcept` function calls `std::terminate`, and the stack is unwound, destroying evidence of the bug.

**Log and continue.** Some teams run with assertions that log the failure and continue execution. This is almost always wrong: if an invariant is violated, continuing with corrupted state is worse than crashing, because the corruption spreads and the root cause becomes harder to diagnose.

**Invoke a debugger break.** On platforms that support it, `__builtin_trap()` or `DebugBreak()` can halt execution and attach a debugger. This is useful during development but not in production.

A pragmatic approach is to choose the response based on the build configuration:

```cpp
#ifdef ASSERTIONS_FATAL
    #define ASSERT(cond) do { \
        if (!(cond)) { \
            std::cerr << "FATAL: " #cond << std::endl; \
            std::abort(); \
        } \
    } while(false)
#elif defined(ASSERTIONS_LOG)
    #define ASSERT(cond) do { \
        if (!(cond)) { \
            std::cerr << "ASSERTION: " #cond << std::endl; \
        } \
    } while(false)
#else
    #define ASSERT(cond) ((void)0)
#endif
```

This allows different assertion policies for CI (fatal), staging (log), and production (disabled). The policy is set at build time and is uniform across the codebase.

### Assertions in constexpr and consteval

The C++ standard says that `assert` is not allowed in `constexpr` functions because its behavior depends on `NDEBUG`, which is not a constant expression. In practice, many compilers accept it and evaluate the assertion at compile time, but the behavior is not portable.

A portable approach uses a separate assertion macro for constant evaluation:

```cpp
#ifdef __cpp_lib_is_constant_evaluated
#define CONSTEXPR_ASSERT(cond) do { \
    if constexpr (std::is_constant_evaluated()) { \
        if (!(cond)) throw std::logic_error("constexpr assertion failure"); \
    } else { \
        assert(cond); \
    } \
} while(false)
#else
#define CONSTEXPR_ASSERT(cond) assert(cond)
#endif
```

In constant evaluation, the assertion throws an exception (which causes the compiler to emit a diagnostic). At runtime, it falls back to `assert`. This gives you compile-time checking for `constexpr` contexts and runtime checking elsewhere.

```cpp
constexpr int factorial(int n) {
    CONSTEXPR_ASSERT(n >= 0);
    int result = 1;
    for (int i = 2; i <= n; ++i) result *= i;
    return result;
}

static_assert(factorial(5) == 120);  // Compile-time check passes
// factorial(-1);  // Would fail at compile time with a clear error
```

### Assertion Granularity: How Many Is Too Many?

A codebase with no assertions is fragile. A codebase with assertions on every line is noisy and slow. Finding the right granularity is a matter of experience and discipline.

As a rule of thumb, assert when:
- The condition, if violated, would cause silent corruption or undefined behavior.
- The condition cannot be expressed in the type system.
- The cost of the check is low relative to the function's runtime.
- The violation would be difficult to diagnose without the assertion.

Do not assert when:
- The condition is already enforced by the type system (e.g., `gsl::not_null` instead of `assert(p != nullptr)`).
- The condition is checked by a production validation path (e.g., input validation that returns an error code).
- The check would be more expensive than the operation itself (e.g., checking that a sort function actually sorted its output—the sort is O(n log n), but the check is O(n)).

A good heuristic is that a function should have one to three assertions: at most one precondition, one postcondition, and one invariant check. More than that suggests the function is doing too much or the types are not carrying their weight.

### From Assertions to Static Verification

Assertions are a dynamic technique: they catch violations only when the violating code path is executed. Static verification tools (like the Clang Static Analyzer, GCC `-fanalyzer`, or formal verification tools like CBMC) can prove that some assertions never fail, across all possible inputs.

This changes the economics of assertions. An assertion that the static analyzer can prove never fails is a source of confidence: the program *cannot* violate this condition. An assertion that the analyzer cannot prove is a candidate for runtime testing: write a test that exercises the path.

```cpp
int divide_safe(int a, int b) {
    // Static analyzer: can it prove that b != 0 at this point?
    assert(b != 0);
    return a / b;
}
```

If the analyzer cannot prove the assertion, the division is a potential UB site. The developer must either strengthen the precondition (make it impossible to call with b == 0 through the type system) or add a runtime production check.

The most satisfying assertions are the ones that the compiler eliminates entirely because the optimizer proves they are redundant:

```cpp
void process(Buffer& buf) {
    if (buf.empty()) return;
    // Code below assumes !buf.empty()
    assert(!buf.empty());  // Optimizer may remove this as provably true
    // ...
}
```

A good optimizer sees that the assert is dominated by the early return and eliminates the check. The assertion serves as documentation for the human reader and as a safety net for future refactoring—if someone removes the early return, the assertion becomes live again.

### Summary of Patterns

| Pattern | Mechanism | Scope | When to Use |
|---|---|---|---|
| Precondition assertion | `assert` / `Expects` | Function entry | Public API functions, complex algorithms |
| Postcondition assertion | `assert` / `Ensures` | Function exit | Functions with complex state changes |
| Unreachable assertion | `assert(false)` | Dead branches | Default in switch, else in if-else chains |
| Immutability assertion | Custom check | After freeze | Config objects, builders |
| Loop invariant | `assert` at loop top | Per iteration | Search, sort, traversal algorithms |
| Data structure invariant | Custom check | After mutation | Containers with structural properties |
| Hash-based invariant | Checksum compare | On every access | Performance-sensitive data structures |
| Thread-safety assertion | Lock-held check | Under mutex | Shared state in multithreaded code |
| Constexpr assertion | Conditional macro | In constexpr fns | Compile-time functions with value constraints |

Each pattern has a specific role. The art is not in knowing the patterns but in choosing the right one for the condition you are checking, placing it at the right scope, and removing it when the type system or static analysis makes it unnecessary.

## Sanitizer Integration Patterns

The previous sections covered checks you write yourself—assertions, invariants, compile-time constraints. Sanitizers are the complement: checks that the *compiler* writes for you. A sanitizer is a compiler-instrumented runtime checker that detects specific classes of bugs—buffer overflows, use-after-free, undefined behavior, data races—by adding metadata and checks to the generated code.

Sanitizers catch bugs that assertions cannot. An assertion can check that a pointer is non-null, but it cannot detect that a pointer is dangling (pointing to freed memory). An assertion can check that an index is in bounds, but it cannot detect that a buffer overflow happened through a different pointer aliasing the same memory. These are precisely the bugs that sanitizers find, and they are the bugs that cause the most damage in production.

The key insight is that sanitizers and assertions are complementary, not alternative. Assertions check what you know to check. Sanitizers check what you did not think to check. Together, they provide coverage that neither can achieve alone.

### The Sanitizer Family

The major sanitizers in the LLVM/GCC ecosystem, each targeting a different class of bugs:

| Sanitizer | Flag | What It Detects |
|---|---|---|
| AddressSanitizer (ASan) | `-fsanitize=address` | Buffer overflows (heap, stack, global), use-after-free, use-after-return, double-free, invalid free |
| UndefinedBehaviorSanitizer (UBSan) | `-fsanitize=undefined` | Signed integer overflow, null pointer dereference, misaligned access, invalid shift, type punning violations, and dozens more |
| ThreadSanitizer (TSan) | `-fsanitize=thread` | Data races, inconsistent mutex usage, lock ordering violations |
| MemorySanitizer (MSan) | `-fsanitize=memory` | Use of uninitialized memory |
| LeakSanitizer (LSan) | `-fsanitize=leak` | Memory leaks (often enabled by default with ASan) |
| ControlFlowIntegrity (CFI) | `-fsanitize=cfi` | Violations of C++ calling conventions, virtual call hijacking |

Each sanitizer works by inserting checks at compile time. ASan adds redzones around every allocation and checks them on every access. UBSan adds condition checks before every potentially-undefined operation. TSan adds happens-before tracking for every memory access. The runtime cost varies: ASan typically slows execution by 2x, TSan by 5-10x, UBSan by 1-2x (depending on which checks are enabled).

### Compiling with Sanitizers

Sanitizers are enabled through compiler flags and must be used consistently across the entire build:

```bash
# AddressSanitizer
g++ -fsanitize=address -fno-omit-frame-pointer -g -O1 -c main.cpp -o main.o
g++ -fsanitize=address main.o -o main

# UndefinedBehaviorSanitizer
g++ -fsanitize=undefined -fno-omit-frame-pointer -g -O1 -c main.cpp -o main.o
g++ -fsanitize=undefined main.o -o main

# Both together (compatible)
g++ -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1 main.cpp -o main

# ThreadSanitizer (incompatible with ASan)
g++ -fsanitize=thread -fno-omit-frame-pointer -g -O1 -c main.cpp -o main.o
g++ -fsanitize=thread main.o -o main

# MemorySanitizer (requires all code to be compiled with MSan, including dependencies)
g++ -fsanitize=memory -fno-omit-frame-pointer -g -O1 main.cpp -o main
```

The `-fno-omit-frame-pointer` flag ensures stack traces are accurate. The `-g` flag includes debug information so the reports include file and line numbers. The `-O1` optimization level is a pragmatic choice: higher levels inline aggressively and obscure the stack trace, but `-O0` is too slow for meaningful test runs.

A critical detail is that all object files and libraries linked into the final binary must be compiled with the same sanitizer flags. Linking an ASan-instrumented object with a non-instrumented library that calls `free` on ASan-allocated memory causes false positives. For this reason, sanitizer builds typically use a dedicated build directory and compile all dependencies from source.

### Sanitizer-Friendly Code Patterns

Sanitizers can produce false positives when code uses patterns that the sanitizer does not understand. The most common source is custom memory management.

**Custom allocators** confuse ASan because ASan assumes all allocations go through `malloc`/`free` or `new`/`delete`. A pool allocator that carves memory from a pre-allocated block will not trigger ASan checks on accesses within that block:

```cpp
class PoolAllocator {
    // ASan does not know about these allocations.
    // Out-of-bounds access within the pool will not be detected.
    std::array<std::byte, 1 << 20> pool_;
    size_t offset_ = 0;
};
```

The solution is to annotate the pool with ASan's container annotation API:

```cpp
#include <sanitizer/asan_interface.h>

class PoolAllocator {
public:
    PoolAllocator() {
        // Tell ASan that the entire pool is "poisoned" (inaccessible).
        __asan_poison_memory_region(pool_.data(), pool_.size());
    }

    void* allocate(size_t size) {
        void* ptr = pool_.data() + offset_;
        // Tell ASan that this sub-region is now "unpoisoned" (accessible).
        __asan_unpoison_memory_region(ptr, size);
        offset_ += size;
        return ptr;
    }

    void deallocate(void* ptr, size_t size) {
        // Tell ASan that this region is poisoned again.
        __asan_poison_memory_region(ptr, size);
    }

private:
    alignas(64) std::array<std::byte, 1 << 20> pool_;
    size_t offset_ = 0;
};
```

With the annotations, ASan treats the pool as a regular heap: it catches out-of-bounds accesses, use-after-free (use-after-deallocate), and double-free. Without the annotations, the pool is invisible to ASan, and bugs within it go undetected.

Similarly, **small buffer optimization** (SBO) for types like `std::string` or custom `small_vector` implementations can produce false positives with ASan. ASan tracks the boundaries of the buffer but does not know that the object switches between inline and heap storage. The `__sanitizer_annotate_contiguous_container` API tells ASan about the logical container boundaries:

```cpp
template <typename T, size_t N>
class SmallVector {
    void push_back(const T& value) {
        if (size_ < N) {
            // Inline storage: annotate the new element as live.
            __sanitizer_annotate_contiguous_container(
                inline_.data(), inline_.data() + N,
                inline_.data() + size_,
                inline_.data() + size_ + 1);
            new (&inline_[size_]) T(value);
        } else {
            // Heap storage: ASan tracks this automatically.
            heap_.push_back(value);
        }
        ++size_;
    }
};
```

The annotation tells ASan that the range `[data() + old_size, data() + new_size)` contains live objects. Without it, ASan may report a "heap-buffer-overflow" when accessing the last inline element, thinking the buffer ends at `size_` rather than `N`.

### Sanitizer Suppression and Blacklisting

Not every bug found by a sanitizer is actionable. Third-party code, generated code, and known limitations can produce reports that you want to ignore without fixing. Sanitizers provide suppression mechanisms for this.

**ASan suppressions** are specified in a file or through an environment variable:

```
# asan_suppressions.txt
interceptor_via_fun:malloc
interceptor_via_lib:libfoo.so
```

Applied with `ASAN_OPTIONS=suppressions=asan_suppressions.txt`.

**UBSan suppressions** use a similar mechanism:

```
# ubsan_suppressions.txt
signed-integer-overflow:my_function
nullptr-with-nonzero-offset:third_party/*
```

Applied with `UBSAN_OPTIONS=suppressions=ubsan_suppressions.txt`.

**Function-level suppression** with attributes excludes specific functions from sanitization:

```cpp
// Skip ASan for a function that intentionally accesses memory in unconventional ways.
__attribute__((no_sanitize("address")))
void intentionally_unsafe_operation() {
    // ...
}

// Skip UBSan for a function that performs intentional overflow.
__attribute__((no_sanitize("undefined")))
int saturating_add_wrap(int a, int b) {
    int result;
    if (__builtin_add_overflow(a, b, &result)) {
        return INT_MAX;
    }
    return result;
}
```

Suppressions should be the exception, not the rule. Every suppressed sanitizer report is a bug that you are choosing not to fix. The suppression should include a comment explaining why the report is a false positive or why the code is intentionally unsafe.

### UBSan Traps: Converting UB into Hard Errors

By default, UBSan prints a diagnostic and continues execution. This allows the program to survive multiple violations, but it means the error is non-fatal and can be missed in test output. The `-fsanitize-undefined-trap-on-error` flag converts every UBSan violation into a trap instruction, causing the program to crash immediately:

```bash
g++ -fsanitize=undefined -fsanitize-undefined-trap-on-error main.cpp -o main
```

This is the strictest mode: any undefined behavior in the program causes a crash, and the crash site points directly to the UB. Adopting this mode requires fixing every UBSan violation in the codebase, which can be a significant effort for legacy projects.

A pragmatic middle ground is to enable trap mode for specific checks while keeping diagnostic mode for others:

```bash
# Trap for the most dangerous UB classes
-fsanitize=null,alignment,object-size,shift -fsanitize-trap=null,alignment,object-size,shift

# Diagnostic mode for less critical checks
-fsanitize=float-cast-overflow,float-divide-by-zero
```

This allows you to enforce the most critical checks as hard errors while tolerating less severe violations during migration.

### Sanitizer Callbacks

When a sanitizer detects an error, it calls a configurable callback before printing the report and (optionally) terminating. This callback can log additional context, upload crash information, or attempt emergency cleanup:

```cpp
#include <sanitizer/asan_interface.h>

extern "C" void __sanitizer_set_death_callback(void (*callback)(void));

void on_sanitizer_error() {
    // Log the current request ID, user, and operation.
    std::cerr << "Sanitizer error in request "
              << current_request_id() << '\n';
    std::cerr << "User: " << current_user() << '\n';
    std::cerr << "Operation: " << current_operation() << '\n';
}

void initialize_sanitizer_hook() {
    __sanitizer_set_death_callback(on_sanitizer_error);
}
```

The callback runs in a signal-safe context, so it should only perform simple operations. It is most useful for attaching domain-specific context to sanitizer reports, making them actionable in CI pipelines.

ASan also supports a **coverage callback** that records which code paths were exercised:

```cpp
#include <sanitizer/common_interface_defs.h>

extern "C" void __sanitizer_cov_trace_pc_guard_init(uint32_t* start, uint32_t* stop);
extern "C" void __sanitizer_cov_trace_pc_guard(uint32_t* guard);
```

This is the foundation for coverage-guided fuzzing (LibFuzzer), which uses ASan's instrumentation to discover which inputs trigger new code paths. The combination of fuzzing and ASan is one of the most effective bug-finding techniques available: the fuzzer generates inputs, and ASan detects the bugs that those inputs trigger.

### Detecting Sanitizer Availability in Code

Code can check whether it is being compiled with sanitizer support using `__has_feature` (Clang) or `__has_builtin` (GCC):

```cpp
#if defined(__clang__) && __has_feature(address_sanitizer)
    #define ASAN_ENABLED 1
#elif defined(__GNUC__) && defined(__SANITIZE_ADDRESS__)
    #define ASAN_ENABLED 1
#else
    #define ASAN_ENABLED 0
#endif

#if ASAN_ENABLED
    #include <sanitizer/asan_interface.h>
#endif

void guarded_function() {
#if ASAN_ENABLED
    // ASan-specific checks or annotations.
    __asan_poison_memory_region(ptr, size);
#else
    // Fallback: no ASan, so no annotation needed.
#endif
}
```

This allows the same source file to be compiled with and without sanitizers, selecting the appropriate behavior at compile time. It is essential for library code that may be used in both sanitized and non-sanitized builds.

### Sanitizer Integration in CI

The most important pattern for sanitizer integration is **always-on in CI**. Every test run should execute under ASan, UBSan, and LSan. The cost is 2-10x slower execution, but the benefit is catching bugs that would otherwise survive to production.

A typical CI configuration:

```yaml
# .github/workflows/ci.yml
jobs:
  build-and-test:
    strategy:
      matrix:
        sanitizer: [address, undefined, thread]
    steps:
      - uses: actions/checkout@v4
      - name: Configure with sanitizer
        run: >
          cmake -B build
          -DCMAKE_CXX_FLAGS="-fsanitize=${{ matrix.sanitizer }}
          -fno-omit-frame-pointer -g -O1"
          -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=${{ matrix.sanitizer }}"
      - name: Build
        run: cmake --build build -j$(nproc)
      - name: Test
        run: ctest --test-dir build --output-on-failure
```

A common refinement is to add a **regression test** mode that runs the entire suite under sanitizers, and a **fast mode** that runs without them for rapid iteration. The sanitizer mode runs nightly or on every merge to main, while the fast mode runs on every pull request commit.

Another refinement is **fuzzing integration**: combine LibFuzzer with ASan and UBSan to generate inputs that trigger sanitizer violations:

```cpp
// fuzz_target.cpp
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    std::string_view input(reinterpret_cast<const char*>(data), size);
    parse_config(input);  // ASan/UBSan will catch any bugs here.
    return 0;
}
```

Compiled with:

```bash
clang++ -fsanitize=address,fuzzer -g -O1 fuzz_target.cpp -o fuzz_target
./fuzz_target -max_len=4096 -runs=1000000 corpus/
```

The fuzzer explores the input space automatically, and ASan catches any memory safety violation or undefined behavior that results. This combination has found thousands of bugs in production C++ codebases.

### Sanitizer Trade-Offs and Limitations

Sanitizers are not a silver bullet. They have limitations that must be understood to use them effectively:

**Coverage completeness.** ASan detects buffer overflows only if the overflow affects the redzone between allocations or the poisoned region around the object. An overflow that lands in another valid allocation may go undetected. This is called the "blind spot" problem: ASan is probabilistic, not exhaustive.

**Runtime overhead.** ASan adds 2x overhead, TSan adds 5-10x. This makes sanitizers impractical for production deployment in most contexts. The exception is UBSan with a minimal subset of checks (`-fsanitize=null,alignment`), which has negligible overhead and can be enabled in production.

**False positives.** Custom allocators, memory-mapped I/O, and shared memory segments can all produce false positives. Each false positive requires investigation, annotation, or suppression, all of which take time.

**TSan incompatibility.** ThreadSanitizer is incompatible with ASan and MSan, and it reports races only if they occur during the test run. A data race that is not exercised by the test suite will not be detected. TSan also reports all benign races (e.g., statistics counters that are intentionally non-atomic), requiring annotations like `__attribute__((no_sanitize("thread")))` for known-safe cases.

**MSan limitations.** MemorySanitizer requires all code—including every linked library—to be compiled with MSan. This is impractical for projects that depend on pre-built binaries. MSan also does not detect reads of uninitialized memory that happen through inline assembly or SSE/AVX intrinsics in some cases.

### The Defensive Programming Stack

Sanitizers complete the defensive programming stack. The full stack, from strongest to weakest guarantee, is:

| Layer | Mechanism | Catches | Cost |
|---|---|---|---|
| Type system | `static_assert`, concepts, strong typedefs | Invalid type combinations, out-of-range constants | Zero |
| Static analysis | Clang analyzer, GCC `-fanalyzer`, Coverity | Null dereference, use-after-free, resource leaks | Zero (at runtime) |
| Compile-time checks | `constexpr`, `consteval` | Invalid constant expressions | Zero |
| Sanitizers | ASan, UBSan, TSan, MSan, LSan | Memory errors, UB, data races, leaks | 2-10x runtime |
| Assertions | `assert`, `Expects`, `Ensures` | Logic errors, invariant violations | Debug only |
| Production checks | `if`, exceptions, `std::expected` | User input errors, system failures | Always paid |

Each layer catches bugs that the layers above miss. A type system that uses `std::chrono::seconds` instead of `int` prevents unit confusion at compile time, before any sanitizer or assertion could fire. A sanitizer catches buffer overflows that no assertion could predict. An assertion catches logic errors that the sanitizer does not check for. A production check handles the cases that cannot be ruled out by any earlier layer.

The most robust codebases invest in all six layers. They use the type system aggressively (strong enums, `std::chrono` types, `gsl::not_null`). They run static analysis in CI. They compile with `constexpr` where possible. They run sanitizers on every test. They write assertions for every non-trivial invariant. And they validate external inputs at the boundary.

The result is code that fails rarely, fails loudly when it does, and fails in a way that points directly to the root cause. That is the goal of defensive programming, and sanitizers are an essential tool for reaching it.
