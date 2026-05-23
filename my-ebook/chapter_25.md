# Chapter 25: Lambda Patterns

Lambdas—anonymous function objects introduced in C++11—are one of the most transformative features in modern C++. They let you define callable objects inline, at the point of use, without writing a separate functor class or function. Every lambda is syntactic sugar for a compiler-generated class with an `operator()`, and the **capture list** specifies what data that generated class stores and how it accesses it.

Understanding capture strategies is the single most important skill for writing correct and efficient lambdas. The capture list determines the lifetime, mutability, and ownership semantics of the data the lambda closes over. Get it wrong, and you get dangling references, unintended copies, or subtle data races.

---

## Lambda Capture Strategies

A lambda's capture list sits between the square brackets and specifies which variables from the surrounding scope are accessible inside the lambda body, and how they are accessed—by value or by reference. What makes captures subtle is that they are not merely a syntactic convenience: each captured variable becomes a data member of the compiler-generated closure type, with constructor, copy, and destruction semantics that you must reason about just as you would for any class.

### Motivation: The Problem Lambdas Solve

Before lambdas, callbacks and custom operations required either a named function (which could not capture local state) or a hand-written functor class:

```cpp
// C++03 style: manual functor
struct ThresholdFilter {
    int threshold;
    explicit ThresholdFilter(int t) : threshold(t) {}
    bool operator()(int value) const { return value > threshold; }
};

auto it = std::find_if(data.begin(), data.end(), ThresholdFilter(42));
```

The functor `ThresholdFilter` stores `threshold` as a data member and initializes it through a constructor. This works, but it is verbose: the connection between the captured variable and its use is separated by the class definition, the constructor, and the instantiation site. A lambda collapses all of this into a single expression:

```cpp
auto it = std::find_if(data.begin(), data.end(), [threshold = 42](int value) {
    return value > threshold;
});
```

The capture `threshold = 42` declares a data member in the closure, initializes it, and makes it available in the body—all in one place. The lambda's compactness is not just about fewer keystrokes; it improves locality of reasoning. The reader sees the captured state and its use side by side.

### Capture by Value — The Default Mental Model

When you capture a variable by value, the closure stores a **copy** of that variable at the point where the lambda is created. The copied value persists for the lifetime of the closure, independent of the original variable.

```cpp
int factor = 2;
auto multiplier = [factor](int x) { return x * factor; };
factor = 10;

std::cout << multiplier(5);  // Prints 10 (2 * 5), not 50
```

The closure's data member `factor` is initialized from the local `factor` at the moment the lambda is defined. Later changes to the local `factor` have no effect on the lambda's copy. This is the same behavior you would get from a functor class with `int factor_` initialized in its constructor.

**When to prefer capture by value:**

- The lambda outlives the scope where it is created (e.g., stored in a callback registry, passed to a thread, returned from a function).
- The captured variable is small (built-in numeric types, pointers, small structs) and copying is cheap.
- You want the lambda to be self-contained and independent of its creation context.

**When to avoid it:**

- The captured variable is large or expensive to copy (e.g., `std::vector` with thousands of elements).
- You need the lambda to observe changes to the variable after creation.
- The variable is a move-only type that cannot be copied (requires init capture, discussed below).

Capturing by value sounds safe, but it introduces a common pitfall with **non-copyable and non-trivial types**. If the captured type is a large container, a mutex, or any resource-owning object, a by-value capture triggers a copy—or a compilation error if the type is move-only. The C++ rule is pragmatic: by-value capture works for copyable types, and the cost of copying is paid once, at lambda creation.

### Capture by Reference — Aliasing the Outside World

When you capture a variable by reference, the closure stores a **reference** (or pointer, in the generated code) to the original variable. No copy is made; the lambda accesses the original through the reference each time it is invoked.

```cpp
int counter = 0;
auto increment = [&counter]() { ++counter; };
increment();
increment();
std::cout << counter;  // Prints 2
```

The closure's `operator()` modifies `counter` directly because it holds a reference to the original stack variable. This is equivalent to a functor with an `int&` member.

**When to prefer capture by reference:**

- The captured variable is large or expensive to copy.
- You need the lambda to modify the original variable.
- The lambda is used synchronously within the same scope and does not outlive the captured variables.

**The cardinal rule: never let a reference-capturing lambda outlive the lifetime of the variables it captures.** This is the single most common source of lambda-related undefined behavior.

```cpp
std::function<int()> create_bad_lambda() {
    int x = 42;
    return [&x]() { return x; };  // Dangling reference!
}  // x is destroyed; the returned lambda holds a dangling reference.
```

The lambda returns from `create_bad_lambda` holding a reference to a local variable that no longer exists. Invoking the lambda is undefined behavior. The compiler will not warn about this in general because the capture mechanism is invisible to the type system.

A reference capture creates an aliasing relationship: the lambda is not an independent object; it is a window into someone else's storage. This makes reference captures unsuitable for asynchronous callbacks, thread pools, or any scenario where the lambda may execute after its creation scope has exited.

### Default Capture Modes — Convenience and Its Costs

C++ allows shorthand capture modes that bring in all automatic variables from the surrounding scope:

- `[=]` — captures every variable used in the body **by value**.
- `[&]` — captures every variable used in the body **by reference**.
- `[=, &x]` — captures everything by value except `x`, which is captured by reference.
- `[&, x]` — captures everything by reference except `x`, which is captured by value.

Default captures are convenient for short lambdas in a narrow scope, but they are widely discouraged in production code for several reasons:

**Reason 1: Implicit captures make the closure's state invisible to readers.** A lambda with `[=]` copies every variable it touches. A reader must scan the entire lambda body to discover what is captured and how. With explicit captures like `[x, &y]`, the closure's data members are listed at the top.

**Reason 2: Default captures interact poorly with member variables.** Consider:

```cpp
class Processor {
    int threshold_ = 42;
public:
    void process(const std::vector<int>& data) {
        auto is_above = [=](int v) { return v > threshold_; };
        // ...
    }
};
```

The capture `[=]` captures `this` by value (i.e., the pointer `this`), not `threshold_` by value. The lambda body accesses `threshold_` as `this->threshold_`. If the lambda outlives the `Processor` object, it holds a dangling `this` pointer. The correct approach is:

```cpp
auto is_above = [this](int v) { return v > threshold_; };       // captures this by value (pointer)
auto is_above = [*this](int v) { return v > threshold_; };      // C++17: captures a copy of *this
```

The `[*this]` capture (available since C++17) makes an actual copy of the entire object, eliminating the lifetime dependency.

**Reason 3: Static and global variables are not captured (they are accessible directly), which can create a misleading impression of what the closure owns.**

Because of these pitfalls, the prevalent advice in the C++ community is: **prefer explicit captures over default captures**. Explicit captures make the closure's state obvious, prevent accidental captures, and force the programmer to think about lifetime and copy semantics. The only situation where a default capture is arguably acceptable is a trivial, immediately-invoked lambda within a single function scope, where the reader can see the entire lambda and its surrounding context in one glance.

### Init Captures (C++14) — Generalized Capture

Init captures, introduced in C++14, allow you to initialize a capture variable with an arbitrary expression, not just the name of an existing variable. This solves several problems that by-value and by-reference captures cannot handle directly.

**Problem 1: Capturing a move-only type.**

```cpp
auto up = std::make_unique<Widget>();

// Error: unique_ptr is not copyable
auto lambda = [up]() { up->do_something(); };
```

By-value capture requires copyability. The solution is an init capture that moves the unique_ptr into the closure:

```cpp
auto lambda = [up = std::move(up)]() { up->do_something(); };
```

The init capture declares a new data member `up` in the closure, initialized with `std::move(up)` from the surrounding scope. After this, the original `up` is in the moved-from state.

**Problem 2: Capturing the result of an expression.**

```cpp
// Capture the current time at lambda creation.
auto lambda = [now = std::chrono::steady_clock::now()]() {
    return std::chrono::steady_clock::now() - now;
};
```

Here, `now` is not a variable from the surrounding scope at all; it is a fresh data member initialized with the result of a function call. This pattern is especially useful for capturing expensive computations whose results should be frozen at lambda creation time.

**Problem 3: Capturing by move with a default.**

```cpp
auto data = std::make_shared<ExpensiveObject>();
auto lambda = [data = std::move(data)]() { /* ... */ };
```

This moves the shared_ptr into the closure, transferring ownership. The difference from capture by value is meaningful: a by-value capture of a shared_ptr increments the reference count; a move capture does not. For large shared objects that will be exclusively owned by the lambda, the move avoids an atomic increment that would otherwise persist for the closure's lifetime.

**Problem 4: Capture with transformation.**

```cpp
auto lambda = [sorted = get_sorted_copy(large_vector)]() {
    // Use sorted, which is already sorted.
};
```

The init capture first processes the data before storing it in the closure. The original `large_vector` remains unmodified and is not captured at all.

Init captures are the most flexible capture mechanism and should be your default when the variable being captured requires any transformation (move, copy and mutate, compute derivative, etc.) beyond a simple by-value or by-reference binding.

### Capturing `this` and `*this` — Member Function Lambdas

When a lambda is defined inside a non-static member function, the capture list has special behavior: `[=]` and `[&]` capture `this` (the pointer), not the individual member variables. This has significant lifetime implications.

```cpp
struct Server {
    std::vector<Connection> connections_;
    
    void start() {
        // Launches a background thread. BAD: this may be gone by the time the thread runs.
        std::thread t([=]() { poll_connections(); });
        t.detach();
    }
    
    void poll_connections() { /* work with connections_ */ }
};
```

This lambda captures `this` by value (the pointer). When the thread runs `poll_connections()`, it accesses `this->connections_`, but the `Server` object may have been destroyed already—dangling pointer, undefined behavior.

C++17 introduced `[*this]` to capture a **copy** of the entire object:

```cpp
std::thread t([*this]() { poll_connections(); });
```

Now the lambda holds its own copy of the `Server` object, safe to use after the original is destroyed. Of course, this requires `Server` to be copyable, and copying a server may be expensive—you must weigh the safety against the cost. For objects that are cheap to copy (e.g., POD configuration structs), `[*this]` is a simple correctness win. For heavy objects, consider restricting the capture to only the needed data.

In C++20, `[=, this]` is deprecated in favor of explicit `[this]` or `[*this]`, reinforcing the principle that captures should be explicit.

### Mutable Lambdas — When the Closure Needs to Change

By default, a lambda's `operator()` is `const`—it cannot modify its by-value captures. To allow mutation, add the `mutable` keyword after the parameter list:

```cpp
int count = 0;
auto counter = [count]() mutable { return ++count; };

std::cout << counter();  // 1
std::cout << counter();  // 2
std::cout << count;      // 0 — the original is untouched
```

The `mutable` keyword makes the closure's `operator()` non-const, allowing the lambda to modify its own copies of captured values. Each invocation increments the lambda's private `count` copy, leaving the original untouched.

Without `mutable`, modifying a by-value capture is a compilation error—the closure acts like a class with `int count_` and `int operator()() const`. This design is intentional: the default const-ness reflects the fact that lambdas are often used as predicates or comparators in algorithms, which require const callability. Adding `mutable` is a deliberate opt-in that signals "this lambda has state that changes over time," which also means it cannot be used with algorithms that require a const callable (e.g., a `mutable` lambda cannot be stored in a `const` variable).

Mutable lambdas are most useful for local generators, accumulators, or ad-hoc state machines within a single function scope. They become dangerous when shared across threads: if the same mutable lambda is invoked from multiple threads without synchronization, the mutation is a data race.

### `constexpr` Lambdas (C++17) and Consteval Lambdas (C++20)

Since C++17, a lambda can be declared `constexpr` if its body satisfies the requirements for a `constexpr` function. Since C++20, `consteval` lambdas are also possible. All captures in such lambdas must be usable in constant expressions. This means the capture list must not contain runtime variables:

```cpp
constexpr int factor = 2;
auto lambda = [factor](int x) constexpr { return x * factor; };
static_assert(lambda(3) == 6);
```

A `constexpr` lambda is evaluated at compile time when possible, providing a zero-overhead abstraction. The capture semantics are identical to runtime lambdas, but the captured values must be constant expressions for the lambda to be usable in a `constexpr` context.

### Decision Framework for Choosing a Capture Strategy

When writing a lambda, ask four questions in order:

1. **Does the lambda outlive the scope where it is created?** If yes, use by-value capture (or init capture with move). Reference captures would dangle.

2. **Is the captured variable large or expensive to copy?** If yes, and the lambda does not outlive the scope, a reference capture avoids the copy. If the lambda does outlive the scope, you cannot use a reference—consider capturing a shared_ptr or restructuring the code to avoid capturing the large object entirely.

3. **Is the variable move-only (e.g., unique_ptr)?** Use an init capture with `std::move`. By-value capture fails (no copy), and by-reference capture ties you to the original's lifetime.

4. **Does the lambda need to modify the captured variable?** If the variable is small and you want the lambda to isolate its mutations from the original, use `mutable` with by-value capture. If you want to modify the original, use by-reference capture (with lifetime guarantees).

The following table summarizes the strategies and their primary use cases:

| Strategy | Syntax | Closure stores | Lifetime concern | Best for |
|---|---|---|---|---|
| By value | `[x]` | Copy of `x` | None (owns copy) | Small types, lambdas that outlive scope |
| By reference | `[&x]` | Reference to `x` | Must not outlive `x` | Large types, synchronous use |
| Default by value | `[=]` | Copies of all used vars | Captures `this` implicitly | Avoid in production; okay for trivial local lambdas |
| Default by ref | `[&]` | References to all used vars | All must outlive lambda | Avoid in production |
| Init capture | `[x = expr]` | Result of `expr` | Depends on `expr` | Move captures, transformed captures |
| Capture `*this` | `[*this]` | Copy of enclosing object | None (owns copy) | Threads, async, member function lambdas |
| Capture `this` | `[this]` | Pointer to enclosing object | Object must outlive lambda | Synchronous member function lambdas |
| Mutable by value | `[x]() mutable` | Copy of `x` (non-const access) | None (owns copy) | Local generators, accumulators |

The overarching principle is: **make the closure's ownership and lifetime visible**. An explicit capture list is a declaration of the closure's data members. Treat it with the same care you would a class definition—because that is exactly what the compiler does.

---

## Generic Lambdas

A generic lambda is a lambda that declares at least one parameter with `auto` instead of a concrete type. Introduced in C++14, this feature eliminates the most significant limitation of C++11 lambdas: the inability to operate on different types without writing separate lambdas or using cumbersome template wrappers.

The `auto` parameter in a generic lambda is not dynamic typing — it is **template parameter deduction** in disguise. The compiler generates a `template<typename T>` for each `auto` parameter, and the closure's `operator()` becomes a member function template. This distinction matters because it means all the rules of template argument deduction, overload resolution, and SFINAE apply — including the pitfalls.

### Motivation: Why Generic Lambdas Exist

Before C++14, writing a lambda that worked with multiple types required either a manual functor template or type erasure:

```cpp
// C++11: must specify concrete types
auto int_lambda = [](int x) { return x * 2; };
auto double_lambda = [](double x) { return x * 2; };

// Or: manually wrap with a template
struct Doubler {
    template <typename T>
    T operator()(T x) const { return x * 2; }
};
```

The functor template works, but it defeats the purpose of a lambda — you are back to writing a named class. A generic lambda collapses the template into the lambda syntax:

```cpp
auto doubler = [](auto x) { return x * 2; };

std::cout << doubler(3);       // int:  6
std::cout << doubler(3.14);    // double: 6.28
std::cout << doubler("!");     // Error: no operator* for const char*
```

The body must be valid for every type the lambda is instantiated with. The error on `const char*` is not a declaration error; it is a **template instantiation error** — the lambda is well-formed as written, but it cannot be called with a type that lacks `operator*`.

### How Generic Lambdas Work Under the Hood

The compiler transforms each generic lambda into an unnamed class with a templated `operator()`. A generic lambda:

```cpp
auto is_greater_than = [limit](auto value) { return value > limit; };
```

generates a closure equivalent to:

```cpp
class __AnonymousLambda {
    int limit;
public:
    __AnonymousLambda(int limit) : limit(limit) {}

    template <typename T>
    auto operator()(T value) const -> decltype(value > limit) {
        return value > limit;
    }
};
```

Each `auto` parameter becomes an independent template parameter. The return type is deduced from the body using the usual rules for `auto` return type deduction. This means you can use the lambda with any type that supports `>` against the captured `limit`, including user-defined types with overloaded operators.

The template nature of generic lambdas has practical consequences:

- **Separate instantiations are generated for each distinct type.** Calling `is_greater_than(3)` and `is_greater_than(3.0)` produces two different instantiations of the closure's `operator()`. This is identical to the code generation for an explicit functor template — there is no runtime overhead, but there may be binary size implications if the lambda is instantiated with many types.

- **The template parameter is deduced, not explicitly specified.** There is no way in C++14/17 to force a specific instantiation of a generic lambda — you cannot write `doubler.operator()<int>(3)`. This limitation was removed in C++20, which allows explicit template syntax on lambdas.

- **SFINAE applies.** If the body is invalid for a given type, the `operator()` is simply not a candidate for that type, enabling the lambda to participate in overload resolution in the same way any function template would.

### Multi-Parameter Generic Lambdas

A generic lambda can have multiple `auto` parameters, each independently deduced:

```cpp
auto zip_with = [](auto func, auto a, auto b) {
    return func(a, b);
};

int result = zip_with([](int x, int y) { return x + y; }, 3, 4);
// result = 7
```

Each `auto` is a separate template parameter: `func` is deduced as a callable type, `a` and `b` are deduced independently. The deduction follows normal template rules, which means `a` and `b` can be different types — the call succeeds as long as `func(a, b)` is valid.

This independence is useful but can surprise when you expect two parameters to share the same type:

```cpp
auto add = [](auto a, auto b) { return a + b; };
// Works: add(3, 4)       -> int + int
// Works: add(3.0, 4)    -> double + int (promotion)
// Works: add(string, string) -> concatenation
```

If you need two parameters to have the **exact same type**, you cannot express that with plain `auto` parameters — each is independently deduced. In C++20, you can use explicit template parameters to enforce this:

```cpp
// C++20: same-type constraint
auto add = []<typename T>(T a, T b) { return a + b; };
add(3, 4);       // OK, both int
add(3.0, 4);     // Error: deduced T as double vs int — deduction fails
```

The explicit template syntax `<typename T>` in the lambda (C++20) gives you the same control as a named function template. This is discussed further below.

### Generic Lambdas with Standard Library Algorithms

The most common use case for generic lambdas is with standard library algorithms, where the element type is often generic or template-dependent:

```cpp
template <typename Container>
void process(const Container& c) {
    // Without generic lambda: must know the value_type
    std::for_each(c.begin(), c.end(), [](const typename Container::value_type& v) {
        std::cout << v << " ";
    });

    // With generic lambda: works with any container of any printable type
    std::for_each(c.begin(), c.end(), [](const auto& v) {
        std::cout << v << " ";
    });
}
```

The generic lambda version is not only shorter — it is more correct in subtle ways. It works with `std::vector<bool>` whose `value_type` is a proxy reference, not `bool&`. It works with containers whose `value_type` is deduced from iterator traversal, such as `std::map`'s `value_type` which is `std::pair<const Key, Value>`. And it works with views and ranges whose element types may be different from the underlying container's value type.

Before C++14, developers commonly wrote helper functions or used `decltype` to work around this — patterns that generic lambdas render unnecessary.

### Constraining Generic Lambdas (C++20)

A generic lambda with `auto` parameters accepts any type that compiles in the body. If the body uses operations that are only valid for certain types, the errors surface as deep template instantiation failures. C++20 concepts allow you to constrain the parameter types at the declaration site, producing clearer errors and better overload resolution:

```cpp
// Unconstrained: confusing error if called with wrong type
auto square = [](auto x) { return x * x; };
square("hello");  // Deep template error about operator* not found

// Constrained (C++20):
auto square = [](std::integral auto x) { return x * x; };
square("hello");  // Clear: constraint 'std::integral<const char*>' not satisfied
```

Constrained `auto` parameters use the familiar "constrained auto" syntax — the same one used in function templates. The constraint `std::integral` (from `<concepts>`) restricts the lambda to integer types, and any violation produces a compiler error at the call site rather than inside the lambda body.

Multiple constraints can be composed with `&&`:

```cpp
auto serialize = [](std::integral auto value, std::output_iterator<char> auto out) {
    // write value to out
};
```

The constraint syntax works uniformly with `auto` parameters in lambdas, giving generic lambdas the same type-safety benefits as named template functions.

### Variadic Generic Lambdas (C++14/17)

A generic lambda can accept a variadic parameter pack — the lambda equivalent of a variadic function template:

```cpp
// C++14: variadic generic lambda
auto print_all = [](const auto&... args) {
    ((std::cout << args << " "), ...);  // C++17 fold expression
};

print_all(1, "hello", 3.14);  // Prints: 1 hello 3.14
```

The `auto&...` is a variadic pack of deduced types. Inside the body, you expand the pack using all the usual template metaprogramming techniques: fold expressions (C++17), recursion, or comma-fold patterns.

This is especially useful for building type-erased callbacks and visitor patterns:

```cpp
// A lambda that can accept any number of visitors
auto visit_all = [](const auto&... visitors) {
    return [&](const auto& value) {
        ((visitors(value)), ...);
    };
};

auto visitor = visit_all(
    [](int i) { std::cout << "int: " << i << "\n"; },
    [](const std::string& s) { std::cout << "str: " << s << "\n"; }
);
visitor(42);      // Prints: int: 42
visitor("hello"); // Prints: str: hello
```

This pattern is the foundation of the `std::visit` overloaded idiom, discussed in the Stateful Lambdas section.

### Explicit Template Parameters (C++20)

C++20 extended lambda syntax to allow explicit template parameter lists before the function parameters:

```cpp
// C++20: explicit template lambda
auto to_string = []<typename T>(const T& value) {
    if constexpr (std::is_arithmetic_v<T>) {
        return std::to_string(value);
    } else {
        return std::string(value);
    }
};
```

Before C++20, the only way to refer to the deduced type by name was through the parameter type itself — you could not write `T` explicitly. This made some patterns awkward, especially when you needed to reference the type in multiple places or in helper declarations within the body:

```cpp
// Pre-C++20 workaround: decltype
auto lambda = [](const auto& value) {
    using T = std::decay_t<decltype(value)>;
    // now T is available
};
```

With explicit template syntax, `T` is available directly. This is particularly valuable when:

- The return type depends on the template parameter in a way that cannot be expressed through `auto` deduction alone.
- You need to constrain the template parameter with a concept.
- You are writing a lambda that forwards its argument (requiring `T&&` with perfect forwarding):

```cpp
// C++20: perfect forwarding in a lambda
auto emplace = []<typename T, typename... Args>(std::vector<T>& v, Args&&... args) {
    v.emplace_back(std::forward<Args>(args)...);
};
```

The explicit template parameter list makes generic lambdas a full replacement for local function templates — there is nothing you can express with a local `template<typename T>` struct that you cannot now express with a lambda.

### Return Type Deduction and Trailing Return Types

Generic lambdas deduce their return type from the body using `auto` return type deduction. All return statements must deduce to the same type, or the code fails to compile:

```cpp
auto lambda = [](auto x) {
    if (x > 0) return x;           // deduced as decltype(x)
    else return -x;                // must match — works if x is signed
};
```

When the lambda returns different types in different branches, you must specify an explicit return type using the trailing return type syntax:

```cpp
auto lambda = [](auto x) -> std::common_type_t<decltype(x), double> {
    if (x > 0) return x;
    else return -x * 1.5;
};
```

This pattern is common when converting between types in generic code — for example, a generic map function that always returns a `std::vector`:

```cpp
auto to_vector = []<typename T>(const auto& container) -> std::vector<T> {
    std::vector<T> result;
    for (const auto& elem : container) {
        result.push_back(static_cast<T>(elem));
    }
    return result;
};
```

### Generic Lambdas vs Named Function Templates

When should you use a generic lambda instead of a named function template? The decision hinges on scope and reuse:

- **Use a generic lambda** when the callable is needed only in a narrow context — as an argument to an algorithm, as a local helper within a function, or when it captures state from the surrounding scope.
- **Use a named function template** when the operation is a reusable abstraction that should be tested independently, has a clear domain meaning, or is part of a public API.

A generic lambda in a header file that is instantiated with many types across multiple translation units can cause binary bloat because each translation unit generates its own copy of the lambda closure. A named function template in a header can be marked `inline` to avoid this — but in practice, the linker usually merges duplicate lambda instantiations when LTO is enabled.

The converse is also true: a generic lambda inside a `.cpp` file that is only used locally is strictly better than a named function template because it keeps the implementation private and reduces the surface area of the translation unit.

### Common Patterns with Generic Lambdas

**Pattern 1: Generic visitor for variant.**

```cpp
template <typename... Ts>
struct overloaded : Ts... { using Ts::operator()...; };

template <typename... Ts>
overloaded(Ts...) -> overloaded<Ts...>;  // deduction guide

auto visitor = overloaded{
    [](int i) { /* handle int */ },
    [](const std::string& s) { /* handle string */ },
    [](auto) { /* handle anything else */ }  // generic fallback
};

std::visit(visitor, my_variant);
```

The generic fallback lambda `[](auto) { ... }` handles any type not covered by the other overloads. Without it, a missing overload would produce a compiler error.

**Pattern 2: Type-erased callbacks from generic lambdas.**

```cpp
std::function<int(int)> callback = [](auto x) { return x * 2; };
```

The generic lambda's `operator()` is a template, but `std::function` requires a concrete type. The template is instantiated with `int` when the lambda is assigned to the `std::function<int(int)>`, and the generic nature is erased. This is safe and common, but note that the lambda cannot be generic at the call site if it is stored in a `std::function` — the concrete type is fixed at the point of assignment.

**Pattern 3: Recursive generic lambdas (C++14).**

A lambda cannot call itself directly because it has no name. With a generic lambda and a helper, you can write recursive lambdas:

```cpp
auto factorial = [](auto self, int n) -> int {
    return n <= 1 ? 1 : n * self(self, n - 1);
};

int result = factorial(factorial, 5);  // 120
```

The standard trick uses `std::function` or a Y-combinator pattern, but this self-passing form is the most readable. The key insight is that `self` is a generic parameter — its type is deduced as the lambda's own closure type.

A more ergonomic C++14 pattern wraps the recursion into a helper:

```cpp
auto factorial = [](int n) {
    auto impl = [](auto self, int n) -> int {
        return n <= 1 ? 1 : n * self(self, n - 1);
    };
    return impl(impl, n);
};
```

### Trade-offs and Limitations

Generic lambdas are not a free abstraction. Understanding their costs helps you decide when they are appropriate:

**Compilation time.** The compiler must instantiate the lambda's `operator()` for every distinct combination of types the lambda is called with. For a lambda used in a single translation unit with one or two types, the cost is negligible. For a lambda in a header that is instantiated with dozens of types across hundreds of translation units, the cost can be significant.

**Error messages.** Generic lambdas inherit the notorious error message quality of templates. An unconstrained generic lambda called with an incompatible type produces pages of template instantiation backtrace. This is mitigated by C++20 constraints, which catch the error at the call site before instantiation.

**Binary size.** Each instantiation generates separate code. For small lambdas that the compiler inlines at each call site, the impact is minimal — the lambda disappears into the surrounding code. For larger lambdas called through function pointers or `std::function`, multiple instantiations persist as separate functions in the binary.

**No separate declaration.** Unlike a named template, a generic lambda cannot be forward-declared or reused across translation units without being copied. If the same generic lambda is needed in multiple files, extract it into a named function template or a variable template.

The decision framework is straightforward: use generic lambdas freely within a single function or a single translation unit. For reusable generic callables across a library, prefer named function templates or function objects, which give better control over ODR, documentation, and testing.

---

## Lambda as Callback Storage

Lambdas are often created at one point in the program and invoked at another — perhaps later in the same function, perhaps on a different thread, perhaps in response to an external event. The gap between creation and invocation raises the question of **storage**: how do you preserve a lambda so that it can be called later? The answer depends on whether the callable type is known statically, whether the lambda captures state, and what performance and flexibility constraints apply.

### The Three Fundamental Storage Strategies

Every approach to storing a lambda is a variation on one of three strategies: **static type** (the caller and callee agree on the concrete type at compile time), **type erasure** (the concrete type is hidden behind an indirect call), or **function pointer** (only non-capturing lambdas, which have no state to store).

### Strategy 1: Function Pointer — The Zero-Overhead Case

A lambda that captures nothing can decay to a function pointer. This is the simplest and most efficient storage mechanism.

```cpp
using Callback = void(*)(int);

void register_callback(Callback cb) {
    // store and invoke later
}

register_callback([](int x) { std::cout << x; });  // OK: no capture
```

The conversion is implicit: a non-capturing lambda has a `operator()` that can be represented as a plain function pointer. The generated code is identical to passing a free function — no closure object, no type erasure, no indirection.

```cpp
auto lambda = [](int x) { return x * 2; };
int(*fp)(int) = lambda;     // implicit conversion
int result = fp(21);         // 42
```

The limitation is absolute: a capturing lambda cannot be converted to a function pointer. The compiler rejects the conversion because the function pointer cannot carry the captured state.

```cpp
int factor = 2;
auto lambda = [factor](int x) { return x * factor; };
int(*fp)(int) = lambda;     // Error: cannot convert
```

Function pointer callbacks are appropriate when the callback has no state, the callback is called synchronously within the same scope, and the overhead of a function pointer call (one indirection) is acceptable. They appear in C APIs (`qsort`, `pthread_create`), in embedded systems where type erasure overhead is prohibitive, and in any interface where the callback truly needs no context.

When a C API demands a `void*` context parameter alongside a function pointer, lambdas can still be used — but the capture must be passed through the opaque pointer:

```cpp
// C API that accepts callback + void* context
void register_handler(void (*handler)(int, void*), void* context);

auto lambda = [factor](int x) { /* use factor */ };

// We must allocate the lambda on the heap and pass it through context
auto* ptr = new decltype(lambda)(lambda);
register_handler(
    [](int x, void* ctx) {
        (*static_cast<decltype(lambda)*>(ctx))(x);
    },
    ptr
);
// Remember to delete ptr when the handler is unregistered
```

This "bridge" pattern is tedious but unavoidable when interfacing lambdas with C-style APIs. The lifetime of the heap-allocated closure must be managed manually — typically through a registration/deregistration pair. This is one area where RAII wrappers around C APIs pay significant dividends: they can encapsulate the `void*` management and delete the closure when the handler is removed.

### Strategy 2: `std::function` — Type Erasure with a Cost

`std::function` is the most general storage mechanism: it can hold any callable — lambda, function pointer, member function pointer, or functor — as long as the call signature matches. It does so through **type erasure**: the concrete callable type is hidden behind a virtual-like dispatch mechanism.

```cpp
std::function<int(int)> callback;

callback = [](int x) { return x * 2; };               // lambda, no capture
callback = [factor](int x) { return x * factor; };     // lambda with capture
callback = std::negate<int>{};                         // functor
callback = &some_free_function;                        // function pointer
```

The interface is uniform regardless of the underlying type. This makes `std::function` the natural choice for callback registries, event systems, and any API that must accept heterogeneous callables.

**The cost of type erasure:**

- **Heap allocation for large closures.** `std::function` may perform a small buffer optimization (SBO) — typically storing 16–32 bytes inline. Small lambdas (a single captured `int` or pointer) fit in this buffer. Larger closures (a lambda capturing a `std::array` or multiple large objects) trigger a heap allocation for the closure object.
- **Indirect call overhead.** Invoking a `std::function` requires two indirections: one to fetch the function pointer (or vtable-style entry) from the type-erased storage, and a second to actually call the target. This is typically 10–30 nanoseconds more than a direct call — negligible for infrequent callbacks but meaningful in hot paths.
- **No inlining.** The compiler cannot inline through a `std::function` call because the concrete type is unknown at the call site. This is often the largest hidden cost: a lambda that could be inlined into an algorithm becomes a opaque function call.
- **Copy overhead.** Copying a `std::function` may copy the stored callable (including its captured state) or trigger a reference count increment if the implementation uses shared state for small objects. This matters when callbacks are stored in containers.

The trade-off is a spectrum: `std::function` provides maximum flexibility at the cost of performance predictability. It is the right choice when the callback is registered rarely and invoked infrequently, when the codebase values interface uniformity over micro-optimization, or when the callback must be copyable and assignable.

**When NOT to use `std::function`:**

- The callback is called millions of times per second in a tight loop.
- The callback is always a specific lambda with known type — use a template parameter instead.
- The lambda is move-only (captures a `unique_ptr`) — this requires C++23's `std::move_only_function`.
- The embedded or real-time context prohibits heap allocation — use a template or a custom function_ref.

### Strategy 3: Template Parameter — Static Polymorphism

When the callback type is known at the call site, you can avoid type erasure entirely by making the callback a template parameter:

```cpp
template <typename Callback>
void for_each_widget(Callback cb) {
    for (auto& w : widgets_) {
        cb(w);
    }
}

// Usage: pass any lambda
for_each_widget([threshold](const Widget& w) {
    if (w.value() > threshold) activate(w);
});
```

The `Callback` template parameter is deduced to the lambda's concrete closure type. The compiler generates a separate instantiation of `for_each_widget` for each distinct lambda type, enabling full inlining — the call to `cb(w)` becomes a direct call to the lambda's `operator()`, which the compiler can inline into the surrounding loop.

This is the approach used throughout the standard library: `std::for_each`, `std::sort`, `std::transform` all take callables as template parameters. It is the most efficient storage mechanism because there is no storage at all — the lambda's type is baked into the generated code, and the lambda object is passed by value (or by reference) through the template instantiation.

**The trade-off** is that the function itself becomes a template, which must be defined in a header (or explicitly instantiated). This increases compilation time and binary size if the function is large and instantiated with many different lambda types. Additionally, the callback type cannot be changed at runtime — a template parameter is a compile-time decision.

**When to use template parameters:**

- The function accepting the callback is itself generic (like standard algorithms).
- Performance matters and the callback call site is hot.
- The callback is used locally within a single translation unit.
- You need move-only callbacks (lambda capturing `unique_ptr`) without waiting for C++23.

**When to avoid them:**

- The callback registry must accept heterogeneous callables at runtime.
- The function is part of a binary interface (shared library boundary) — template instantiations cannot cross shared library boundaries in a portable way.
- The function is large and instantiated with many callback types, causing binary bloat.
- The implementation must be hidden in a `.cpp` file.

### Strategy 4: `function_ref` and `callback_ref` — Non-Owning Callback View

Between `std::function` (owning, type-erased) and template parameters (static, compile-time) lies a middle ground: a non-owning type-erased reference to a callable. This is not standardized until C++26 (when `std::function_ref` is expected), but the pattern is widely used in practice under names like `function_ref`, `callback_ref`, or `AnyInvocable`:

```cpp
// A simple function_ref implementation
class function_ref {
    void* obj_;
    void (*invoke_)(void*, int);

    template <typename F>
    static void invoke_fn(void* obj, int arg) {
        (*static_cast<F*>(obj))(arg);
    }

public:
    template <typename F>
    function_ref(F&& f)
        : obj_(const_cast<std::remove_reference_t<F>*>(&f))
        , invoke_(invoke_fn<std::remove_reference_t<F>>) {}

    void operator()(int arg) const {
        invoke_(obj_, arg);
    }
};
```

A `function_ref` stores a pointer to the original callable and a function pointer to the invocation. It does **not** own the callable — the caller must ensure the lambda outlives the `function_ref`. It does **not** allocate. It **can** be inlined in some cases if the compiler sees through the indirection, though this is less reliable than with templates.

The use case is precisely the "borrowed callback" pattern: a function that accepts a callback, uses it synchronously, and returns. By accepting `function_ref` instead of a template parameter, you can keep the implementation in a `.cpp` file while still supporting any callable type:

```cpp
// In header
void process_data(function_ref<void(int)> callback);

// In .cpp
void process_data(function_ref<void(int)> callback) {
    for (int i = 0; i < 100; ++i) {
        callback(i);
    }
}
```

The caller passes a lambda, the implementation is hidden, and there is no heap allocation. This is often the right choice for library APIs that accept callbacks.

### Storing Lambdas in Containers

When you need a collection of callbacks — an event system, a middleware pipeline, a signal-slot mechanism — you must decide on the stored type.

**Homogeneous callbacks** (same signature):

```cpp
// A simple signal
class Signal {
    std::vector<std::function<void(int)>> slots_;
public:
    void connect(std::function<void(int)> slot) {
        slots_.push_back(std::move(slot));
    }

    void emit(int value) {
        for (auto& slot : slots_) {
            slot(value);
        }
    }
};
```

This works but has a subtle performance characteristic: iterating over the vector calls each `std::function` through its type-erased dispatch. For small numbers of slots, the overhead is trivial. For hundreds of slots invoked frequently, the indirection cost accumulates.

**Heterogeneous callbacks** (different signatures) require either a common base type (like `std::function<void()>` with argument binding) or a variant of function types:

```cpp
using Callback = std::variant<
    std::function<void(int)>,
    std::function<void(const std::string&)>,
    std::function<void()>
>;

std::vector<Callback> handlers;
```

This is manageable when the set of signatures is small and known. For fully open heterogeneous callbacks, consider `std::any` with type-checked invocation, though this adds overhead.

### Lifetime Management: The Stored Callback Problem

When a lambda captures `this` or a reference to an object, storing it for later invocation creates a lifetime dependency:

```cpp
struct Button {
    std::function<void()> on_click_;

    template <typename F>
    void set_on_click(F&& f) { on_click_ = std::forward<F>(f); }

    void click() { if (on_click_) on_click_(); }
};

struct Window {
    Button ok_button_;
    int click_count_ = 0;

    void setup() {
        ok_button_.set_on_click([this] { ++click_count_; });
        // Whoops: if Window is destroyed before the button is clicked,
        // the lambda's this pointer dangles.
    }
};
```

Three approaches to solve this:

**Approach 1: Explicit disconnection.** The owning object disconnects its callbacks before destruction. This requires a registration API that returns a token or a `shared_ptr`-based observation:

```cpp
struct Window : std::enable_shared_from_this<Window> {
    Button ok_button_;
    int click_count_ = 0;
    std::vector<ConnectionToken> tokens_;

    void setup() {
        auto self = shared_from_this();
        tokens_.push_back(ok_button_.set_on_click(
            [self] { ++self->click_count_; }
        ));
    }
};
```

By capturing a `shared_ptr` to `this` instead of a raw `this`, the lambda extends the object's lifetime for as long as the callback exists. This eliminates the dangling pointer at the cost of preventing the object from being destroyed until all callbacks are released — which may or may not be desirable.

**Approach 2: Weak callback pattern.** For optional observation where the callback should be a no-op if the object is gone, use `weak_ptr`:

```cpp
auto weak_self = weak_from_this();
ok_button_.set_on_click([weak_self] {
    if (auto self = weak_self.lock()) {
        ++self->click_count_;
    }
});
```

The callback checks whether the target object is still alive before invoking. This is the safest pattern for event systems where objects may be destroyed before events are delivered.

**Approach 3: Copy by value.** When the captured state is small and independent, capture by value (`[*this]` or individual values) to eliminate the lifetime dependency entirely:

```cpp
ok_button_.set_on_click([count = click_count_]() mutable {
    // Works with own copy of count, no this dependency
    ++count;
    std::cout << "Clicked " << count << " times\n";
});
```

This works only when the callback does not need to observe the object's evolving state — it gets a snapshot.

### Move-Only Callbacks: `std::move_only_function` (C++23)

A lambda that captures a move-only type like `std::unique_ptr` cannot be stored in `std::function` because `std::function` requires its stored callable to be copyable. C++23 introduces `std::move_only_function` to fill this gap:

```cpp
auto lambda = [up = std::make_unique<Widget>()] {
    up->do_something();
};

// C++17/20: Error - unique_ptr not copyable
std::function<void()> cb = std::move(lambda);  // Error

// C++23: OK
std::move_only_function<void()> cb = std::move(lambda);
cb();  // invokes, then the callback is moved-from
```

`std::move_only_function` is also invocable from rvalue reference context (its `operator()` is `&&`-qualified), which allows transferring ownership of the captured resources at invocation time. This enables "one-shot" callbacks that are destroyed after being called:

```cpp
std::move_only_function<void()> cb = [up = std::make_unique<Widget>()] {
    // up is destroyed when this returns
};
std::move(cb)();  // cb is empty after this call
```

For move-only callbacks in C++17/20, the workaround is a template parameter (which accepts any lambda including move-only ones) or a heap-allocated wrapper using `std::shared_ptr` with a custom deleter.

### Storing Lambdas in Class Members

When a lambda is a class member, the storage type must be part of the class definition. The three choices mirror the strategic options:

```cpp
class Processor {
    // Option 1: std::function - most flexible, runtime cost
    std::function<void(int)> callback_;

    // Option 2: template - compile-time type, must be in header
    // (Cannot write this directly - would need to make Processor a template)

    // Option 3: fixed function pointer - no captures allowed
    void (*callback_fp_)(int) = nullptr;
};
```

Option 2 requires templatizing the class:

```cpp
template <typename Callback>
class Processor {
    Callback callback_;
public:
    Processor(Callback cb) : callback_(std::move(cb)) {}
    void run(int value) { callback_(value); }
};
```

This is maximally efficient but forces the class definition into a header and generates separate instantiations for each callback type. It is the right choice for performance-critical code where the callback type is known at compile time and the class is not part of a stable ABI.

### Callback Disposal and Reentrancy

Stored callbacks introduce two subtle correctness concerns beyond lifetime:

**Reentrancy:** A callback may trigger the same event system that stores it, leading to recursive invocation. If the callback container is modified during iteration (the callback registers or unregisters another callback), iterators may be invalidated:

```cpp
void emit(int value) {
    // BAD: slots_ may be modified during iteration
    for (auto& slot : slots_) {
        slot(value);  // What if this adds a new slot?
    }
}
```

The standard solution is to iterate over a copy, or to defer additions and removals:

```cpp
void emit(int value) {
    auto current = slots_;  // copy
    for (auto& slot : current) {
        slot(value);
    }
}
```

Copying a vector of `std::function` has its own cost; the alternative is to use an index-based loop and mark added/removed slots for post-processing.

**Disposal during invocation:** If a stored callback triggers destruction of the object that owns the callback container, the container itself may be destroyed while it is being iterated. A shared-ownership pattern (reference-counted callback list with a "dead" flag) addresses this, though it adds complexity.

### Decision Guide for Callback Storage

| Approach | Owns callable | Heap alloc | Inlinable | Copyable | Best when |
|---|---|---|---|---|---|
| Function pointer | No | No | Rarely | Yes | No capture, C interop, embedded |
| Template param | Yes (by value) | No | Yes | Depends on type | Hot loops, generic algorithms |
| `std::function` | Yes | Maybe (SBO) | No | Yes | Heterogeneous callbacks, public API |
| `move_only_function` (C++23) | Yes | Maybe (SBO) | No | No | Move-only captures, one-shot callbacks |
| `function_ref` | No | No | Sometimes | Yes (trivial) | Borrowed callbacks, hidden impl |
| Heap + void* | Yes | Yes | No | Manual | C API interop |

The unifying principle is: **choose the storage strategy that matches the lifetime and ownership relationship between the callback and its invoker**. If the invoker never outlives the callback's scope, a non-owning reference (`function_ref` or raw reference) is the most efficient. If the invoker must hold the callback for an indeterminate duration, an owning wrapper (`std::function`, template value, or `move_only_function`) is necessary. The heap allocation and type erasure costs of `std::function` are the price of that ownership flexibility — pay it only where you need it.

---

## Stateful Lambdas and Closure Patterns

A stateful lambda is one that maintains mutable state across multiple invocations. The state is stored in the closure's data members — the captured variables — and persists for the lifetime of the lambda object. This transforms a lambda from a pure function (same input always produces same output) into an object with an identity, capable of remembering past calls and altering its behavior over time.

Stateful lambdas sit at the intersection of functional and object-oriented thinking: they combine the concise syntax of a lambda with the internal state of a functor. Understanding when and how to use them — and when to avoid them — is essential for writing lambdas that are correct, predictable, and maintainable.

### The Essential Property: Mutable Capture

Every stateful lambda relies on the `mutable` keyword. Without it, by-value captures are `const` and cannot be modified:

```cpp
// Error: cannot modify by-value capture in a const operator()
auto bad_counter = [count = 0]() { return ++count; };  // Error
```

The fix is explicit:

```cpp
auto counter = [count = 0]() mutable { return ++count; };
```

The `mutable` keyword is the syntactic signal that this lambda carries state. It should never be an afterthought — adding `mutable` changes the lambda's fundamental contract from "stateless and reusable" to "stateful and single-use" in certain contexts (e.g., it cannot be passed to algorithms that require a const callable). Every `mutable` lambda should prompt the question: "Does this need to be a lambda, or would a small functor class be clearer?"

### Pattern 1: Generators and Sequences

The simplest stateful lambda is a generator — a callable that produces a different value on each invocation:

```cpp
auto next_id = [id = 0]() mutable { return id++; };

std::cout << next_id();  // 0
std::cout << next_id();  // 1
std::cout << next_id();  // 2
```

The closure holds an `int id` that is incremented on each call. This is equivalent to:

```cpp
struct NextID {
    int id = 0;
    int operator()() { return id++; }
};
```

The lambda version is shorter and keeps the generator local to its use site. The functor version is reusable, testable, and nameable — a trade-off that mirrors the earlier discussion of generic lambdas vs. named function templates.

Sequence generators can be parameterized by capture:

```cpp
auto make_range = [](int start, int step) {
    return [start, step]() mutable {
        int current = start;
        start += step;
        return current;
    };
};

auto evens = make_range(0, 2);
std::cout << evens();  // 0
std::cout << evens();  // 2
std::cout << evens();  // 4
```

The outer lambda returns an inner stateful lambda. Each call to `make_range` creates an independent generator with its own state. This "lambda factory" pattern is a common way to create stateful callables without writing named classes.

A generator can be combined with `std::generate` or `std::generate_n` to populate containers:

```cpp
std::vector<int> ids(10);
auto next_id = [id = 0]() mutable { return id++; };
std::generate(ids.begin(), ids.end(), next_id);
// ids = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9}
```

The algorithm calls `next_id` once per element, each time retrieving and advancing the internal counter. The same pattern works with any stateful transformation.

### Pattern 2: Accumulators and Reducers

A stateful lambda can aggregate values across multiple calls:

```cpp
auto running_total = [sum = 0](int value) mutable {
    sum += value;
    return sum;
};

std::cout << running_total(5);   // 5
std::cout << running_total(3);   // 8
std::cout << running_total(2);   // 10
```

This is the lambda equivalent of `std::partial_sum`, but it stores the accumulated state in the closure rather than in an external variable. It is useful when the accumulation must be carried across calls that are not part of a single algorithm invocation — for instance, processing chunks of data as they arrive.

A more sophisticated accumulator might track multiple statistics:

```cpp
auto stats = [count = 0, sum = 0.0, min = std::numeric_limits<double>::max(), max = std::numeric_limits<double>::lowest()](double value) mutable {
    ++count;
    sum += value;
    if (value < min) min = value;
    if (value > max) max = value;
    return std::tuple{count, sum, min, max};
};
```

The capture list declares the initial state, and the body updates it on each call. The caller receives a snapshot of the accumulated statistics after each invocation.

### Pattern 3: Caching and Memoization

A stateful lambda can cache the result of an expensive computation, avoiding recomputation when the same input appears again:

```cpp
auto memoize = [cache = std::unordered_map<int, int>()](int n) mutable -> int {
    auto it = cache.find(n);
    if (it != cache.end()) return it->second;

    int result = expensive_computation(n);
    cache[n] = result;
    return result;
};
```

The `cache` map is a captured variable that persists across calls. On each invocation, the lambda checks the cache before computing. This is a simple memoization pattern — effective for pure functions called repeatedly with repeated arguments.

The cache can grow unbounded. A practical implementation might bound the cache size:

```cpp
auto memoize = [cache = std::unordered_map<int, int>(), max_size = 1000](int n) mutable -> int {
    auto it = cache.find(n);
    if (it != cache.end()) return it->second;

    int result = expensive_computation(n);
    if (cache.size() < max_size) {
        cache[n] = result;
    }
    return result;
};
```

For single-value caching (a lambda that remembers its previous call), the state is even simpler:

```cpp
auto with_previous = [prev = std::optional<int>()](int value) mutable {
    std::optional<int> old = prev;
    prev = value;
    return old;
};
```

On the first call, `prev` is empty and the lambda returns `std::nullopt`. On subsequent calls, it returns the value from the previous invocation. This is useful for detecting transitions or computing deltas.

### Pattern 4: The Overloaded Pattern

One of the most important stateful lambda patterns is not about mutable state at all — it is about using the **type** of the lambda as state. The `overloaded` pattern, popularized by `std::visit`, combines multiple lambdas into a single callable by inheriting from all of them:

```cpp
template <typename... Ts>
struct overloaded : Ts... {
    using Ts::operator()...;
};

// Deduction guide (C++17)
template <typename... Ts>
overloaded(Ts...) -> overloaded<Ts...>;
```

Usage:

```cpp
std::variant<int, std::string, double> v = "hello";

std::visit(overloaded{
    [](int i)       { std::cout << "int: " << i << "\n"; },
    [](const std::string& s) { std::cout << "str: " << s << "\n"; },
    [](double d)    { std::cout << "dbl: " << d << "\n"; }
}, v);
```

The `overloaded` struct inherits `operator()` from each lambda. When `std::visit` calls the visitor, overload resolution selects the best match among the inherited `operator()`s. A generic lambda fallback can be added as a catch-all:

```cpp
std::visit(overloaded{
    [](int i)       { /* handle int */ },
    [](auto)        { /* handle everything else */ }
}, v);
```

The `overloaded` pattern is a form of compile-time stateful composition: the "state" is the set of call operators inherited from the constituent lambdas. This pattern eliminates the need for manual visitor hierarchies and makes `std::variant` ergonomic enough for everyday use.

The same pattern can be extended to build composable visitors:

```cpp
auto int_handler = [](int i) { std::cout << "int: " << i; };
auto str_handler = [](const std::string& s) { std::cout << "str: " << s; };

auto visitor = overloaded{int_handler, str_handler};
std::visit(visitor, my_variant);
```

This composability is the pattern's key advantage over a switch-based approach: handlers can be defined separately, tested independently, and combined at the point of use.

### Pattern 5: Stateful Lambdas with Standard Algorithms — Side Effects

Passing a stateful lambda to a standard algorithm can be useful, but it requires care because algorithms may copy the callable internally. Consider:

```cpp
auto counter = [count = 0](int value) mutable {
    if (value > 0) ++count;
    return value > 0;
};

// How many positive values?
auto end = std::remove_if(data.begin(), data.end(), counter);
std::cout << counter.count;  // Probably 0 — we read a copy!
```

The algorithm may copy `counter` one or more times internally. Each copy has its own `count`, so the original lambda's count is not updated. The standard does not guarantee how many copies an algorithm makes of its callable — implementations vary.

The solution is to pass the lambda by reference using `std::ref`:

```cpp
auto counter = [count = 0](int value) mutable {
    if (value > 0) ++count;
    return value > 0;
};

auto end = std::remove_if(data.begin(), data.end(), std::ref(counter));
// The internal state 'count' is not accessible here. Use the capture-by-reference pattern instead.
```

`std::ref` creates a `reference_wrapper` that the algorithm copies — but the wrapper itself copies like a pointer, so all copies reference the same underlying lambda. The count accumulated by the algorithm is visible through the original lambda after the algorithm completes.

This pattern is essential when using stateful lambdas with any algorithm that may copy the callable — which is most of them. The C++ standard explicitly allows algorithms to copy callables, so `std::ref` is not a workaround for a particular implementation; it is a correctness requirement.

An alternative that avoids `std::ref` is to store the state externally and capture by reference:

```cpp
int count = 0;
auto counter = [&count](int value) {
    if (value > 0) ++count;
    return value > 0;
};
auto end = std::remove_if(data.begin(), data.end(), counter);
std::cout << count;  // Correct: all copies of counter reference the same count
```

This is often clearer than `std::ref` with a mutable lambda. The trade-off is that the state lives outside the lambda, which may be less encapsulated. Choose based on whether the state logically belongs to the lambda or to the surrounding scope.

### Pattern 6: Y-Combinator and Recursive Lambdas

A lambda cannot call itself by name because it has no name. The standard trick for recursive lambdas uses a generic lambda that takes itself as a parameter:

```cpp
auto factorial = [](auto self, int n) -> int {
    return n <= 1 ? 1 : n * self(self, n - 1);
};

int result = factorial(factorial, 5);  // 120
```

This is a manual Y-combinator. The lambda accepts a callable (`self`) as its first argument and passes `self` to recursive calls. The awkward part is the call site: `factorial(factorial, 5)`.

A more ergonomic version wraps the recursion:

```cpp
auto factorial = [](int n) {
    auto impl = [](auto self, int n) -> int {
        return n <= 1 ? 1 : n * self(self, n - 1);
    };
    return impl(impl, n);
};

std::cout << factorial(5);  // 120 — clean call site
```

The outer lambda captures the recursion machinery and exposes a clean `int -> int` interface. The inner lambda is the recursive core.

A generalization of this pattern is the `y_combinator` helper:

```cpp
template <typename F>
class y_combinator {
    F f_;
public:
    template <typename... Args>
    decltype(auto) operator()(Args&&... args) {
        return f_(*this, std::forward<Args>(args)...);
    }
};

template <typename F>
y_combinator(F) -> y_combinator<F>;

// Usage:
auto factorial = y_combinator{[](auto self, int n) -> int {
    return n <= 1 ? 1 : n * self(n - 1);
}};

std::cout << factorial(5);  // 120 — no self-passing at call site
```

The `y_combinator` passes itself to the lambda as `self`, so the lambda calls `self(n - 1)` without passing itself. This is the cleanest pattern for recursive lambdas, though it requires understanding that `self` is the combinator object, not the original lambda.

### Pattern 7: RAII Wrapper Lambdas — State as Resource

A stateful lambda can own a resource that is automatically released when the lambda is destroyed:

```cpp
auto file_guard = [file = fopen("log.txt", "w")]() mutable {
    if (file) {
        fprintf(file, "access\n");
    }
};

// When file_guard is destroyed, fclose is called automatically on file
// (assuming a custom deleter or unique_ptr wrapping — raw fopen leaks)
```

This example is intentionally flawed to make a point: `FILE*` captured by value will leak because the lambda's destructor does not call `fclose`. The correct pattern uses `std::unique_ptr` with a custom deleter:

```cpp
auto file_writer = [file = std::unique_ptr<FILE, decltype(&fclose)>(
    fopen("log.txt", "w"), &fclose
)](const std::string& line) mutable {
    if (file) fputs(line.c_str(), file.get());
};

// When file_writer is destroyed, unique_ptr calls fclose
```

The lambda owns a `unique_ptr` to a `FILE`. The resource is acquired at lambda construction and released at lambda destruction. This is an example of **RAII applied to closures** — the lambda becomes a self-contained resource guardian.

The same pattern works for any resource that needs RAII wrapping:

```cpp
auto scoped_mutex = [lock = std::unique_lock(mtx)]() {
    // The mutex is held while this lambda exists
    // Do work that requires the lock
};
```

### Pattern 8: Thread-Local Stateful Lambdas

When a stateful lambda is used concurrently from multiple threads, each thread must have its own copy of the state, or access to the shared state must be synchronized:

```cpp
// Thread-local generator: each thread gets its own counter
thread_local auto tls_counter = [id = 0]() mutable { return id++; };

// Each thread calling tls_counter() receives its own sequence:
// Thread A: 0, 1, 2, ...
// Thread B: 0, 1, 2, ... (independent)
```

Thread-local stateful lambdas are useful when each thread needs an independent resource — a random number generator, a connection pool handle, a sequence number — without mutex contention.

When state must be shared across threads, the state should live outside the lambda and be captured by reference with synchronization:

```cpp
std::mutex mtx;
int shared_count = 0;

auto safe_increment = [&]() {
    std::lock_guard lock(mtx);
    return ++shared_count;
};
```

Mutable state in a lambda passed to `std::thread` is a special case: the lambda is moved into the thread's storage, so the thread gets its own copy of the state unless references are used:

```cpp
int local = 0;
std::thread t([&local]() mutable {
    ++local;  // modifies the original local through the reference
});
t.join();
std::cout << local;  // 1
```

The mutable keyword here affects the reference capture's behavior — the lambda tracks changes to local through the reference. Without `&`, the thread would operate on its own copy.

### Stateful Lambdas vs. Hand-Written Functors

When does a stateful lambda become complex enough that a named functor class is better? The following signs suggest you should extract:

- **The lambda body exceeds 10–15 lines.** At this point, the lambda's brevity advantage is lost, and a named class provides better structure.
- **The state has invariants that must be maintained.** A functor class can have private members and a constructor that enforces preconditions. A lambda's captures are all public (in principle) and have no invariant enforcement.
- **The stateful lambda is used in multiple places.** A named functor can be defined once, tested, and reused. Copying the same stateful lambda to multiple sites duplicates the code and the bugs.
- **The lambda needs multiple overloads of `operator()`.** A hand-written functor can provide `const` and non-const overloads, or multiple signatures. A lambda has exactly one call signature.
- **The state is complex (multiple interdependent fields).** A functor class can name its members clearly and provide helper functions. A lambda's captured variables lack semantic naming beyond the variable names themselves.

```cpp
// When to extract: complex state with invariants
// Instead of this:
auto validator = [min = 0, max = 100, flags = 0u, errors = std::vector<std::string>{}](
    int value
) mutable {
    // 20+ lines of validation logic with multiple error conditions
};

// Write this:
class RangeValidator {
    int min_, max_;
    unsigned flags_;
    std::vector<std::string> errors_;
public:
    RangeValidator(int min, int max, unsigned flags = 0);
    bool operator()(int value);
    const std::vector<std::string>& errors() const;
};
```

The functor class provides a name that documents the abstraction, enforces invariants through its constructor, and can be unit-tested independently of any particular call site.

### Closure Identity and Equality

Stateful lambdas that are value-comparable require special handling because the generated closure type has no default `operator==`. Two instances of the same lambda type with the same captured values are not equal by default:

```cpp
auto make_counter = [](int start) {
    return [start]() mutable { return start++; };
};

auto a = make_counter(0);
auto b = make_counter(0);

// a == b would be a compilation error — no operator== for closures
```

C++20 added defaulted `operator==` for lambda closure types, but only when all captured types are equality-comparable. Even then, comparing stateful lambdas by value is fragile: the comparison checks the current captured values, not the future behavior.

In practice, if you need to compare callbacks for identity (to know whether a specific callback is already registered), use opaque tokens returned by the registration function, not the callbacks themselves:

```cpp
class Signal {
    std::vector<std::function<void()>> slots_;
public:
    using Token = size_t;

    Token connect(std::function<void()> slot) {
        slots_.push_back(std::move(slot));
        return slots_.size() - 1;  // simple token
    }

    void disconnect(Token token) {
        // mark slot for removal
    }
};
```

This avoids relying on the equality of closures, which is both underspecified and semantically questionable.

### Summary: When Stateful Lambdas Shine

Stateful lambdas excel in four specific scenarios:

1. **Local generators and counters** within a single function — concise, no external state, clear lifetime.
2. **Accumulators for data streams** where data arrives in chunks — the closure naturally holds the running state.
3. **Caching and memoization** of expensive pure computations — the cache lives exactly as long as the lambda.
4. **Ad-hoc visitor composition** via `overloaded` — combining multiple lambdas without a visitor hierarchy.

They should be avoided when:

- The state is complex enough to warrant a name and invariant enforcement.
- The lambda is used across multiple locations in the codebase.
- The lambda's state must be inspected or reset from outside (a named class can expose accessors).
- The lambda is passed to an algorithm that may copy it — use `std::ref` or external state.

The overarching principle is: **a stateful lambda is a functor that happens to be defined at its point of use**. Treat it with the same respect for state management, invariants, and lifetime that you would give a hand-written class. The lambda syntax is a convenience, not a license to disregard structure.
