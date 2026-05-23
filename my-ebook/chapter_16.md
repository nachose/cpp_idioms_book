# Chapter 16: Compile-Time Computation

## Template recursion patterns

Before C++11 introduced `constexpr`, the only way to perform nontrivial computation entirely at compile time was through recursive template instantiation. Even today, with powerful `constexpr` functions and `consteval`, template recursion remains essential for computations that involve types themselves—not just values. When the result of a compile-time computation is a type rather than a number, template recursion is the only tool available.

The mental model is that of structural recursion in functional programming. A template metafunction is defined in terms of itself with different template arguments, and one or more partial specializations serve as the base cases that terminate the recursion. Each instantiation of the template creates a new node in the compiler's internal template instantiation graph; the recursion depth is the number of nodes along the longest path before a base case is reached.

### Compile-time numeric computation

The canonical example is computing a factorial at compile time:

```cpp
template <unsigned int N>
struct Factorial {
    static constexpr unsigned long long value = N * Factorial<N - 1>::value;
};

template <>
struct Factorial<0> {
    static constexpr unsigned long long value = 1;
};

// Factorial<5>::value == 120, computed at compile time
```

The primary template defines the recursive step: `Factorial<N>` is `N` times `Factorial<N-1>`. The full specialization for `N = 0` terminates the recursion. The compiler instantiates `Factorial<5>`, which requires `Factorial<4>`, which requires `Factorial<3>`, and so on until `Factorial<0>` is reached. Each instantiation is a distinct type in the compiler's view, which is why template recursion depth is fundamentally limited: each level consumes compiler resources and contributes to the total instantiation depth.

The key insight is that the computation happens during type instantiation, not during execution. The `value` constant is a static data member initialized at compile time. The expression `Factorial<5>::value` is replaced by the compiler with the literal `120` in any context that expects a constant expression, such as array sizes or template arguments.

### Recursion depth limits

Compilers impose a limit on template instantiation depth, typically around 256 to 1024 levels, depending on the compiler and configuration. Exceeding this limit produces a hard error rather than a silent fallback. This is fundamentally different from runtime recursion, where stack depth is limited by available memory and can be extended by increasing stack size.

```cpp
// Likely exceeds compiler template recursion depth
constexpr auto result = Factorial<500>::value;
```

The limit exists because each template instantiation adds state to the compiler's internal data structures, and unbounded recursion could exhaust system memory during compilation. Three strategies exist for working within these limits:

1. **Restructure algorithms** to use divide-and-conquer recursion (logarithmic depth) rather than linear recursion
2. **Use `constexpr` functions** (C++14 and later) for purely numeric computations, which are not limited by template instantiation depth
3. **Increase the compiler's recursion limit** with `-ftemplate-depth=N` (GCC/Clang), though this only postpones the problem

For most practical metaprograms, a depth of 256 is sufficient. If you find yourself exceeding it, the computation is likely better expressed as a `constexpr` function anyway.

### Type-level recursion

Where template recursion truly shines is in type-level computation—operations that produce types rather than values. Variadic templates naturally lend themselves to recursive decomposition: process the first type, then recurse on the rest.

```cpp
// Find the type at a given index in a parameter pack
template <std::size_t I, typename... Ts>
struct TypeAtIndex;

// Base case: index 0, at least one type exists
template <typename T, typename... Rest>
struct TypeAtIndex<0, T, Rest...> {
    using type = T;
};

// Recursive case: decrement index, skip first type
template <std::size_t I, typename T, typename... Rest>
struct TypeAtIndex<I, T, Rest...> {
    using type = typename TypeAtIndex<I - 1, Rest...>::type;
};

static_assert(std::is_same_v<
    TypeAtIndex<2, int, double, char, float>::type,
    char
>);
```

The recursive case strips one type off the front and decreases the index by one. The base case matches when the index reaches zero. This pattern—a primary template declared but not defined, a recursive partial specialization, and a base-case partial specialization—reappears across virtually every type-level algorithm.

The same pattern can compute properties of parameter packs:

```cpp
template <typename... Ts>
struct MaxSize;

template <typename T>
struct MaxSize<T> {
    static constexpr std::size_t value = sizeof(T);
};

template <typename T, typename... Rest>
struct MaxSize<T, Rest...> {
    static constexpr std::size_t value =
        sizeof(T) > MaxSize<Rest...>::value
            ? sizeof(T)
            : MaxSize<Rest...>::value;
};

static_assert(MaxSize<int, double, char>::value == sizeof(double));
```

The base case (single type) trivially returns the size of that type. The recursive case compares the first type's size against the maximum of the remaining types. This linear recursion pattern is simple to write and reason about, but it instantiates `N` template specializations for `N` types.

### Compile-time control flow via specialization selection

Template recursion is not limited to numeric or type computation. It can also model control flow by selecting different specializations based on compile-time conditions:

```cpp
template <typename T>
struct CheckAndProcess {
    static void doSomething() {
        // Default: do nothing
    }
};

template <typename T>
struct CheckAndProcess<T*> {
    static void doSomething() {
        // Pointer specialization: check for null
        std::cout << "is pointer\n";
    }
};
```

This is not recursion itself but a pattern that recursion enables: by decomposing a problem into smaller pieces and delegating each piece to the appropriate specialization, you can build compile-time algorithms that rival the expressiveness of runtime control flow.

### The cost model of template recursion

Each recursive template instantiation is independently compiled and checked for syntax errors, even if the result is never used in a runtime code path. This has implications for error detection:

```cpp
template <typename T>
struct Recursive {
    // If this body contains an error, it is diagnosed for EVERY instantiation
    static_assert(sizeof(T) > 0, "T must be complete");
};
```

A common pitfall is accidentally creating infinite recursion, which the compiler detects only when the depth limit is reached. Unlike runtime infinite recursion (which causes a stack overflow), template infinite recursion produces a compile error with a diagnostic listing all the instantiations in the chain. While this is safer than a runtime crash, the diagnostic can be hundreds of lines long and difficult to read.

Consider this bug:

```cpp
template <unsigned int N>
struct Buggy {
    static constexpr int value = Buggy<N - 1>::value;  // missing base case for N=0
};
```

The compiler will instantiate `Buggy<100>`, then `Buggy<99>`, then `Buggy<98>`, and so on until it exceeds the depth limit and produces an error. The diagnostic will contain all 100 instantiation sites, making the root cause visible but buried in noise.

### From template recursion to constexpr

C++14 relaxed the restrictions on `constexpr` functions, allowing loops, mutable local variables, and multiple statements. This made template recursion unnecessary for most numeric compile-time computations:

```cpp
// C++14 constexpr — no templates needed
constexpr unsigned long long factorial(unsigned int n) {
    unsigned long long result = 1;
    for (unsigned int i = 2; i <= n; ++i) {
        result *= i;
    }
    return result;
}
```

This version is simpler to write, easier to read, produces better compiler diagnostics, and is not subject to template recursion depth limits. It should be preferred for any computation that involves only values.

Template recursion remains necessary when:
1. **The result is a type**, not a value. `constexpr` functions return values, not types.
2. **The computation must produce a type alias**, such as finding the type at an index in a parameter pack.
3. **The computation involves template template parameters** that depend on recursive instantiation.
4. **The recursion drives partial specialization selection**, where different specializations define different member types or functions.

Trade-offs and limits

- **Readability**: Template recursion is harder to read than equivalent `constexpr` code. Each recursive step is a separate template definition, and the logic is spread across multiple declarations. Mentally simulating a recursive template instantiation requires tracking which partial specialization matches at each level.

- **Compilation time**: Each recursive instantiation adds to compilation time. A depth-100 recursion instantiates 100 separate types, each requiring name lookup, template argument substitution, and semantic analysis. For type-level computations there is no alternative, but for value computations `constexpr` functions compile faster because they do not generate intermediate types.

- **Error messages**: When a recursive template fails to match any specialization, the compiler lists all attempted specializations in the error message. For deeply nested recursion, this can produce diagnostics thousands of lines long. Concepts in C++20 mitigate this by providing earlier and clearer failure points.

- **Compiler portability**: The default template instantiation depth varies across compilers. Code that compiles with GCC at depth 512 may fail with MSVC at depth 256. Always document the minimum required template depth when using deep recursion.

- **Alternatives**: C++17's `if constexpr` can replace some type-level recursion by enabling recursive constexpr functions that operate on parameter packs. C++20's `consteval` and `constexpr` lambdas further reduce the need for template recursion in value computations.

Template recursion patterns are the oldest form of metaprogramming in C++, and while modern C++ has reduced their necessity for value computations, they remain irreplaceable for type-level algorithms. Understanding them is essential not only for writing type traits and type lists, but for developing an intuition about how the template instantiation mechanism works under the hood—an intuition that informs everything from error diagnosis to optimization of template-heavy code.

---

## Parameter packs and pack expansion

Parameter packs are the mechanism by which C++ templates accept a variable number of arguments. A parameter pack is not a single entity but a stand-in for zero or more actual template or function arguments. Pack expansion is the operation that unpacks these arguments into a consuming context. Together, they form the foundation of variadic templates, which are central to nearly every modern C++ template library.

The mental model is that of a compile-time list that the compiler expands in place. When you write `Ts...` in a template parameter list, you declare a pack. When you write `Ts...` in an expansion context, you instruct the compiler to repeat the surrounding pattern once for each type in the pack. The compiler does not create an intermediate container; it directly generates the expanded code as if you had written each element manually.

### Declaring parameter packs

A template parameter pack is declared by placing an ellipsis after the `typename` keyword (or the type) in the template parameter list:

```cpp
template <typename... Ts>   // Ts is a template parameter pack
class Tuple {};
```

A function parameter pack is declared by placing an ellipsis before the parameter name (or between the type and the name) in the function parameter list:

```cpp
template <typename... Ts>
void print(Ts... args);     // args is a function parameter pack
```

The two packs are related but distinct. `Ts` is a pack of types; `args` is a pack of values of those types. The number of elements in `args` is always the same as the number of elements in `Ts`, because one value of each type is expected.

### Pack expansion contexts

A pack can be expanded in several contexts. The simplest is in a function call, where the pattern is simply the pack name:

```cpp
template <typename... Ts>
void print_all(Ts... args) {
    // Pack expansion: expands to std::cout << arg1 << arg2 << ... << argN
    (std::cout << ... << args);
}
```

Each expansion context repeats the pattern that contains the pack. The pattern is everything that lexically contains the ellipsis. In the fold expression above, `args` is the pack and the pattern is just `args`. But the pattern can be arbitrarily complex.

```cpp
template <typename... Ts>
void process(Ts... args) {
    // Pattern: p(args)
    // Expands to: p(arg1), p(arg2), ..., p(argN)
    (p(args), ...);
}
```

Understanding where expansion can occur is critical. Pack expansion is allowed in:

1. **Template argument lists**: `Tuple<Ts...>`
2. **Function parameter lists**: `void f(Ts... args)`
3. **Initializer lists**: `int arr[] = {args...};`
4. **Base class specifiers**: `class Derived : public Bases... {};`
5. **Member initializer lists**: `Derived(Ts... args) : Bases(args)... {}`
6. **Using declarations**: `using Bases::foo...;`
7. **Lambda captures**: `[args...] {}`
8. **Fold expressions**: `(args + ...)`

Each context has its own rules about what patterns are valid. The most versatile expansion context is the initializer list, which can be used to expand packs in arbitrary order and with side effects before C++17 fold expressions were available.

### The comma-fold trick (pre-C++17)

Before C++17 introduced fold expressions, the standard technique for expanding a pack in a sequence of operations was the comma operator in an initializer list:

```cpp
template <typename... Ts>
void print_all(Ts... args) {
    int dummy[] = { (std::cout << args << " ", 0)... };
    // Expands to: { (cout << arg1 << " ", 0), (cout << arg2 << " ", 0), ... }
    (void)dummy;  // suppress unused variable warning
}
```

The pattern `(std::cout << args << " ", 0)` is expanded once per element. Each expansion evaluates the print expression and produces the integer `0`. The initializer list collects all the zeros. The `(void)dummy` cast suppresses the unused variable warning. This technique is reliable, portable, and works in C++11.

The comma-fold trick has no runtime overhead: the compiler sees the expanded code and optimizes away the unused array. Its only downside is that the expression `(expr, 0)` must be evaluable as a constant expression, which excludes some patterns that rely on non-constexpr operations.

### Expanding into base classes

Variadic base class expansion models mixin composition. Each type in a parameter pack becomes a base class of the current class:

```cpp
template <typename... Mixins>
class Composed : public Mixins... {
public:
    Composed(const Mixins&... mixins) : Mixins(mixins)... {}
};

// Composed<Loggable, Serializable, Clonable>
// inherits from Loggable, Serializable, and Clonable
```

The base class specifier `public Mixins...` expands to a comma-separated list of base classes. The member initializer `Mixins(mixins)...` expands to a comma-separated list of base-class constructor calls.

Combined with using-declarations, variadic base classes can compose interfaces:

```cpp
template <typename... Bases>
class Overloader : public Bases... {
public:
    using Bases::operator()...;
};

// Overloader combines multiple callable types into one
auto combined = Overloader<FuncA, FuncB, FuncC>{};
```

The `using Bases::operator()...;` declaration (C++17) expands to a using-declaration for each base, making all `operator()` overloads visible in the derived class. This is the mechanism behind `std::variant`'s visitor pattern and many polymorphic function wrapper implementations.

### Recursive pack processing without fold expressions

Even without fold expressions, parameter packs could be processed recursively by splitting off the first element:

```cpp
// Base case: no arguments
void print() {}

// Recursive case: print first argument, then recurse on rest
template <typename T, typename... Rest>
void print(const T& first, const Rest&... rest) {
    std::cout << first << " ";
    print(rest...);  // unpack rest as arguments to recursive call
}
```

This technique works but has notable drawbacks:
- It requires a zero-argument overload for the base case
- Each recursion level is a separate function template instantiation, increasing compilation time
- The base case must be visible at the point of the recursive call, which can cause ordering issues
- It cannot process the pack in arbitrary order or with arbitrary patterns

C++17's `if constexpr` can eliminate the separate base-case overload:

```cpp
template <typename T, typename... Rest>
void print(const T& first, const Rest&... rest) {
    std::cout << first << " ";
    if constexpr (sizeof...(rest) > 0) {
        print(rest...);
    }
}
```

This is slightly cleaner but still incurs the compilation cost of recursive function template instantiation. Fold expressions (covered in the next section) are the preferred solution for most pack-processing needs.

### Pack indexing (C++26)

C++26 introduces pack indexing, allowing direct access to an individual element of a parameter pack without recursion. This eliminates the need for the `TypeAtIndex` pattern shown in the previous section:

```cpp
template <typename... Ts>
void process(Ts... args) {
    auto third = args...[2];  // direct access to third argument
    using ThirdType = Ts...[2];  // direct access to third type
}
```

Pack indexing makes many recursive type-level algorithms obsolete for the common case of random access. However, algorithms that need to iterate over all elements or compute aggregate properties (like summing sizes) still benefit from the recursive or fold-based approaches.

### sizeof... for pack queries

The `sizeof...` operator returns the number of elements in a pack as a compile-time constant:

```cpp
template <typename... Ts>
struct Count {
    static constexpr std::size_t value = sizeof...(Ts);
};

template <typename... Ts>
void print_size(Ts... args) {
    std::cout << "received " << sizeof...(args) << " arguments\n";
}
```

`sizeof...` is indispensable for controlling recursion and for static assertions that validate pack sizes:

```cpp
template <typename... Ts>
class FixedTuple {
    static_assert(sizeof...(Ts) > 0, "FixedTuple requires at least one type");
    static_assert(sizeof...(Ts) <= 10, "FixedTuple supports at most 10 types");
};
```

Unlike template recursion, `sizeof...` incurs no additional instantiation cost. It is a built-in operator evaluated directly by the compiler.

### Trade-offs and limits

Pack expansion is a compile-time operation with no runtime cost, but it has several constraints:

- **Order of evaluation**: In an initializer list, pack elements are evaluated left-to-right. In a function call, the order is unspecified. This matters when expansions have side effects:
  ```cpp
  // Left-to-right guaranteed in initializer list
  int dummy[] = { f(args)... };  // f(arg1), then f(arg2), then ...

  // Unspecified order in function call
  g(f(args)...);  // f may be called in any order
  ```

- **No partial expansion**: You cannot expand only part of a pack. The ellipsis expands the entire pattern containing the pack. To select a subset, you must use the recursive splitting technique or, in C++26, pack indexing.

- **No named expansion**: You cannot bind a pack to a name for repeated use. Each expansion consumes the pattern; there is no way to "store" an intermediate expanded result as a list of expressions.

- **Compilation time**: Each pack expansion generates additional code in the compiler's AST. A pack of 100 elements expanded in three different contexts produces 300 separate code fragments. For large packs, this can noticeably increase compilation time and binary size.

- **Diagnostic quality**: When a pack expansion fails, the error message repeats the failure for each element in the pack. A single type error in a pack of 50 types produces 50 identical or near-identical error messages. C++20 concepts mitigate this by failing at the constraint level before expansion.

Parameter packs and pack expansion transformed C++ template programming by eliminating the need for cumbersome workarounds like variadic macros or multiple overloads with different arities. Combined with fold expressions and the other compile-time computation tools, they make C++ templates a genuinely expressive metaprogramming language.

---

## Fold expressions

Fold expressions, introduced in C++17, provide a concise syntax for applying a binary operator over all elements of a parameter pack. They replace the recursive templates and comma-fold tricks that were necessary in C++11 and C++14, reducing pages of boilerplate to a single expression. A fold expression is the closest the template metaprogramming system comes to a `for` loop over a pack.

The mental model is that of reducing a list to a single value by repeatedly applying an operator. Given a pack `args` containing `{1, 2, 3, 4}`, the fold expression `(args + ...)` produces `((1 + 2) + 3) + 4` — a left-associative reduction. Each application of the operator combines one element with the accumulated result so far.

### The four fold forms

C++17 defines four forms of fold expressions, differing in associativity and whether an initial value is provided.

**Unary right fold**: `(pack op ...)` expands to `arg1 op (arg2 op (... op argN))`.

```cpp
template <typename... Ts>
auto sum(Ts... args) {
    return (args + ...);  // unary right fold
}

// sum(1, 2, 3, 4) computes 1 + (2 + (3 + 4)) == 10
```

**Unary left fold**: `(... op pack)` expands to `((arg1 op arg2) op ...) op argN`.

```cpp
template <typename... Ts>
auto sum_left(Ts... args) {
    return (... + args);  // unary left fold
}

// sum_left(1, 2, 3, 4) computes ((1 + 2) + 3) + 4 == 10
```

For associative operators like `+`, `*`, `&&`, and `||`, left and right folds produce the same result. For non-associative operators like subtraction or division, the difference matters:

```cpp
template <typename... Ts>
auto subtract_right(Ts... args) {
    return (args - ...);  // 1 - (2 - (3 - 4)) == -2
}

template <typename... Ts>
auto subtract_left(Ts... args) {
    return (... - args);  // ((1 - 2) - 3) - 4 == -8
}
```

Understanding which form you need is essential whenever the operator is not associative across all types in the pack.

**Binary right fold**: `(pack op ... op init)` expands to `arg1 op (arg2 op (... op (argN op init)))`.

```cpp
template <typename... Ts>
auto sum_with_default(Ts... args) {
    return (args + ... + 0);  // binary right fold with initial value 0
}

// sum_with_default() returns 0 (empty pack)
// sum_with_default(1, 2) returns 1 + (2 + 0) == 3
```

**Binary left fold**: `(init op ... op pack)` expands to `(((init op arg1) op arg2) op ...) op argN`.

```cpp
template <typename... Ts>
auto sum_with_default_left(Ts... args) {
    return (0 + ... + args);  // binary left fold with initial value 0
}

// sum_with_default_left() returns 0 (empty pack)
// sum_with_default_left(1, 2) returns ((0 + 1) + 2) == 3
```

The binary forms have a crucial advantage over the unary forms: they handle empty packs. A unary fold on an empty pack is a compile error, because there are no elements to fold and no initial value. A binary fold substitutes the initial value when the pack is empty.

### Operators valid in fold expressions

Not all operators work in fold expressions. The valid operators are: `+` `-` `*` `/` `%` `^` `&` `|` `<<` `>>` `+=` `-=` `*=` `/=` `%=` `^=` `&=` `|=` `<<=` `>>=` `==` `!=` `<` `>` `<=` `>=` `&&` `||` `,` `.*` `->*`.

Of these, the comma operator `,` and the logical operators `&&` and `||` are the most commonly used in practice because they naturally model iteration over a pack without requiring a meaningful accumulator type.

### Practical applications

Fold expressions shine in four common patterns.

**Checking that all elements satisfy a predicate:**

```cpp
template <typename... Ts>
bool all_true(Ts... args) {
    return (args && ...);  // unary right fold over &&
}

// all_true(true, true, false) returns false
// all_true() is ill-formed (empty pack)
```

With a binary fold, the empty case is handled:

```cpp
template <typename... Ts>
bool all_true(Ts... args) {
    return (true && ... && args);  // binary left fold, returns true for empty pack
}
```

**Calling a function for each element:**

```cpp
template <typename... Ts>
void for_each(Ts... args) {
    (p(args), ...);  // unary right fold over comma operator
}
```

The comma operator evaluates each `p(args)` left-to-right and discards the result. The last result becomes the value of the entire fold expression. This replaces the pre-C++17 initializer-list trick with a cleaner, idiomatic syntax.

**Streaming to an output stream:**

```cpp
template <typename... Ts>
void print(Ts... args) {
    (std::cout << ... << args);  // binary left fold over <<
}

// print(1, " hello ", 3.14) prints "1 hello 3.14"
```

The left fold `(std::cout << ... << args)` chains the stream operator left-to-right: `(((std::cout << 1) << " hello ") << 3.14)`. Each subexpression returns `std::cout`, so the chain continues. This is the most idiomatic way to implement variadic output in C++17.

**Matching any condition:**

```cpp
template <typename T, typename... Ts>
bool is_any_of(const T& value, const Ts&... candidates) {
    return ((value == candidates) || ...);  // unary right fold over ||
}

// is_any_of(3, 1, 5, 3, 9) returns true
```

The fold over `||` short-circuits: once a match is found, the remaining comparisons are not evaluated. This is a meaningful performance advantage over the recursive approach, where each comparison must be instantiated even if the result is known early.

### Fold expressions over types

Fold expressions work not only on values but on compile-time constants derived from types:

```cpp
template <typename... Ts>
struct MaxAlign {
    static constexpr std::size_t value = (alignof(Ts) > ...);
    // Wait — this computes (alignof(T1) > (alignof(T2) > (...)))
    // which is probably not what we want
};
```

This highlights a subtlety: the fold expands the expression containing the type, not the type itself. For the fold to produce sensible results, the packed expression must be binary and associative. Computing `std::max` of alignments is better done with a helper:

```cpp
template <typename... Ts>
struct MaxAlign {
    static constexpr std::size_t value = std::max({alignof(Ts)...});
    // Initializer list expansion: works correctly
};
```

The initializer list expansion `{alignof(Ts)...}` is often more appropriate than a fold when the operation is not naturally expressed as a reduction. This is a good reminder that fold expressions replaced one pattern of variadic processing but did not eliminate the need for other expansion contexts.

### Empty pack semantics and verification

Binary folds handle empty packs by using the initial value. Unary folds on empty packs are ill-formed and produce a compile error. This is a deliberate design choice that prevents silent misuse:

```cpp
template <typename... Ts>
auto multiply(Ts... args) {
    return (args * ...);  // compile error if pack is empty
}
```

If you want to support empty packs, you must either use a binary fold or provide a separate overload:

```cpp
template <typename... Ts>
auto multiply(Ts... args) {
    return (args * ... * 1);  // binary fold, returns 1 for empty pack
}
```

Guard against accidental empty-pack instantiation with a static assertion when the empty case is not meaningful:

```cpp
template <typename... Ts>
auto multiply(Ts... args) {
    static_assert(sizeof...(args) > 0, "multiply requires at least one argument");
    return (args * ...);
}
```

### Comparison with recursive approaches

Recursive pack processing instantiates a chain of function templates, one per element. Fold expressions produce a single expression tree that the compiler optimizes as a unit. For a pack of N elements:

| Aspect | Recursive | Fold expression |
|---|---|---|
| Template instantiations | N+1 function templates | 1 function template |
| Binary size | N copies of similar code | 1 optimized expression |
| Short-circuiting | No (all instantiations exist) | Yes (for `&&`, `||`, `,`) |
| Empty pack handling | Separate overload | Binary fold with init value |
| Readability | Verbose, error-prone | Concise, declarative |
| Compilation speed | Slower (more instantiations) | Faster |

Fold expressions are unambiguously superior in every dimension and should be the default choice for any operation that can be expressed as a reduction.

### Trade-offs and limits

- **Operator restriction**: Only the listed operators are valid. You cannot use custom functions or arbitrary callables directly in a fold. For complex per-element operations, fall back to comma folds (which can call any function as a side effect).

- **Evaluation order**: In a left fold, elements are evaluated left-to-right. In a right fold, the evaluation order is parenthesized right-to-left. For most operators, the operands can be evaluated in any order before the operator is applied. However, for the comma operator, &&, and ||, the sequencing rules of the operators themselves guarantee left-to-right evaluation in both left and right folds.

- **No break or early exit**: Unlike a loop, a fold expression cannot skip elements or exit early. Although `&&` and `||` short-circuit at the operator level, the compiler still generates the full expression tree. The elements that are not evaluated due to short-circuiting are determined at runtime based on prior results, not by compile-time selection.

- **Debugging**: Fold expressions are opaque in debug output. If a fold expression misbehaves, you cannot step through individual iterations. Expanding the fold manually in a debug build may be necessary for diagnosis.

- **Non-movable types**: If any element of the pack is a non-movable type and the fold operator invokes a move or copy, the fold may fail to compile. Recursive processing with explicit forwarding avoids this issue by constructing each step independently.

Despite these constraints, fold expressions are one of the most impactful additions in C++17 for template metaprogramming. They replace dozens of lines of recursive template code with a single line that is easier to write, read, and maintain. After fold expressions, the recursive patterns shown earlier in this chapter should be reserved for type-level computations where the result is a type rather than a value.

---

## Static assertions and constraints

Compile-time computation is only useful if the results can be used to enforce correctness. Static assertions and constraints are the mechanisms by which template metaprograms validate their inputs and guarantee their outputs. A template that silently produces wrong results for certain type arguments is worse than useless—it is a liability. The tools in this section turn compile-time checks into clear, immediate errors that fail early and explain precisely what went wrong.

The mental model distinguishes two phases of checking. **Static assertions** are unconditional: they check a compile-time boolean expression and, if it is false, halt compilation with a diagnostic. **Constraints** are conditional: they participate in overload resolution and template argument deduction, removing invalid candidates from consideration rather than producing an error. The former says "this template must never be instantiated with these arguments." The latter says "this template is not viable for these arguments—try another overload."

### Static assertions

The `static_assert` declaration evaluates a constant expression at compile time. If the expression is true, the declaration produces no code and has no runtime cost. If the expression is false, compilation stops with the provided diagnostic message.

```cpp
static_assert(sizeof(int) == 4, "This code requires 32-bit integers");
static_assert(std::is_arithmetic_v<T>, "T must be an arithmetic type");
```

The second form (without a message string) was added in C++17, but providing a descriptive message is always recommended because it becomes the primary diagnostic when the assertion fails.

Static assertions are the simplest and most direct way to enforce template preconditions. They are evaluated after template arguments are substituted, so they can inspect the concrete types involved:

```cpp
template <typename T>
class FixedVector {
    static_assert(std::is_nothrow_move_constructible_v<T>,
                  "FixedVector requires nothrow move constructible types");
    static_assert(std::is_trivially_destructible_v<T>,
                  "FixedVector requires trivially destructible types");
    // ...
};
```

The key advantage of `static_assert` over runtime assertions is that the check happens at compile time, before any code is generated. A `static_assert` failure in a template prevents the template from being instantiated at all, which means no binary code is emitted for the invalid specialization. This is strictly better than discovering the problem at runtime through an assertion failure or undefined behavior.

### Placement strategies for static assertions

The placement of a `static_assert` in a template determines when the check is evaluated. This matters because template classes are instantiated lazily: member functions are only instantiated when they are odr-used.

```cpp
template <typename T>
class Container {
    static_assert(std::is_default_constructible_v<T>,
                  "T must be default constructible");  // (1) checked at class instantiation

    void push_back(const T& value) {
        static_assert(std::is_copy_constructible_v<T>,
                      "T must be copy constructible");  // (2) checked only when push_back is used
    }
};
```

Assertion (1) fires as soon as the class template is instantiated with a non-default-constructible type. Assertion (2) fires only if `push_back` is actually called. This selective instantiation is deliberate: a type that is not copy-constructible might still be usable with `Container` if the user never calls `push_back`. Placing assertions at the member level rather than the class level preserves this flexibility.

A common pattern is to place a comprehensive set of static assertions in a single `static_assert` at the class level as a form of documentation, while placing more specialized checks in individual member functions:

```cpp
template <typename T>
class SortedVector {
    static_assert(std::is_integral_v<T> || std::is_floating_point_v<T>,
                  "SortedVector only supports arithmetic types");
    static_assert(!std::is_const_v<T>,
                  "SortedVector does not support const types");

    void insert(T value) {
        static_assert(std::is_move_constructible_v<T>,
                      "insert requires move constructible types");
        // ...
    }
};
```

### Using static_assert with type traits

The combination of `static_assert` and type traits enables precise requirement specifications:

```cpp
template <typename Iter, typename T>
void safe_copy(Iter first, Iter last, T* output) {
    static_assert(std::is_pointer_v<Iter> || std::is_same_v<
        typename std::iterator_traits<Iter>::iterator_category,
        std::random_access_iterator_tag
    >, "safe_copy requires random access iterators");

    static_assert(std::is_trivially_copyable_v<
        typename std::iterator_traits<Iter>::value_type
    >, "safe_copy requires trivially copyable elements");

    std::memcpy(output, first, (last - first) * sizeof(T));
}
```

This pattern documents the template's requirements in executable form. A user who attempts to call `safe_copy` with an input iterator sees an immediate, specific error message rather than a confusing failure deep inside `std::memcpy`.

The limitation is that static assertions produce hard errors. They cannot redirect overload resolution to another template. For that, you need constraints.

### C++20 concepts and the requires clause

Concepts, introduced in C++20, elevate type constraints from a library convention to a language feature. A concept is a named predicate on template arguments that can be evaluated at compile time and used to constrain templates:

```cpp
template <typename T>
concept Arithmetic = std::is_arithmetic_v<T>;

template <typename T>
concept Hashable = requires(T value) {
    { std::hash<T>{}(value) } -> std::convertible_to<std::size_t>;
};

template <Arithmetic T>
T multiply(T a, T b) {
    return a * b;
}
```

The `Arithmetic` concept above behaves like a `static_assert` with better error messages. The `Hashable` concept goes further: the `requires` expression checks that the expression `std::hash<T>{}(value)` is valid and that its return type is convertible to `std::size_t`. This is the compile-time equivalent of asking "does this expression compile?" and using the answer as a constraint.

### The requires expression

The `requires` expression is the most powerful part of the concepts system. It allows you to check arbitrary compile-time conditions about types, including the validity of expressions:

```cpp
template <typename T>
concept Serializable = requires(T value, std::ostream& os) {
    { os << value } -> std::same_as<std::ostream&>;
    { value.serialize() } -> std::convertible_to<std::vector<char>>;
    requires std::is_trivially_copyable_v<T>;
};
```

A `requires` expression evaluates to a compile-time `bool`. It contains a sequence of requirements:

1. **Simple requirements**: `os << value` — checks that the expression is valid
2. **Type requirements**: `typename T::value_type` — checks that a type exists
3. **Compound requirements**: `{ os << value } -> std::same_as<std::ostream&>` — checks validity and return type
4. **Nested requirements**: `requires std::is_trivially_copyable_v<T>` — checks that a constant expression is true

The `requires` expression is the conceptual successor to the `void_t` detection idiom. It achieves the same result—checking whether an expression is well-formed—with clearer syntax and better error messages. Any detection idiom can be rewritten as a concept:

```cpp
// Detection idiom version
template <typename T, typename = void>
struct has_size : std::false_type {};

template <typename T>
struct has_size<T, std::void_t<decltype(std::declval<T>().size())>>
    : std::true_type {};

// Concept version
template <typename T>
concept has_size = requires(T value) {
    { value.size() } -> std::convertible_to<std::size_t>;
};
```

The concept version is shorter, more readable, and produces better diagnostics when it fails.

### Constraining templates with requires clauses

The `requires` clause can appear in several positions, each with different effects:

```cpp
// 1. After template parameter list (most common)
template <typename T>
    requires std::integral<T> || std::floating_point<T>
T square(T value);

// 2. Using abbreviated syntax (C++20)
void process(std::integral auto value);

// 3. As a trailing requires clause
template <typename T>
void process(T value) requires std::integral<T>;

// 4. In a requires clause after a concept introduction
template <std::integral T>
T factorial(T n);
```

Positions 1 and 2 are the most common. Position 3 is useful when the constraint depends on multiple template parameters or on the function signature. Position 4 is syntactic sugar for position 1 with a concept.

The critical difference between `static_assert` and a `requires` clause is that `requires` participates in overload resolution. When a constrained template's requirements are not met, the template is simply removed from the candidate set, and another overload may be selected. A `static_assert` always produces an error.

```cpp
template <typename T>
    requires std::integral<T>
T increment(T value) {
    return value + 1;
}

template <typename T>
    requires std::floating_point<T>
T increment(T value) {
    return value + 0.5;
}

// increment(3) uses the integral version
// increment(3.0) uses the floating-point version
// increment("hello") produces "no matching function" error
```

With `static_assert`, both overloads would be candidates, and the one with the matching assertion would be selected. The other would produce a hard error. With `requires`, the non-matching overload is silently removed from consideration, and only the matching one participates in overload resolution.

### Combining static_assert and concepts

Static assertions and concepts are complementary, not mutually exclusive. A common pattern is to use `static_assert` inside a constrained template to document additional requirements that go beyond what the concept checks:

```cpp
template <std::ranges::input_range Range>
void process_range(Range&& range) {
    static_assert(std::is_nothrow_destructible_v<
        std::ranges::range_value_t<Range>
    >, "Elements must be nothrow destructible");

    for (auto&& elem : range) {
        // ...
    }
}
```

The concept `std::ranges::input_range` constrains the template parameter, ensuring that only types that model an input range are considered. The `static_assert` inside the function body adds a refinement that is checked only when the template is instantiated. This separation keeps concepts focused on interface requirements and static assertions focused on implementation requirements.

### C++20 constraints and if constexpr

Constraints also work with `if constexpr` to create compile-time branches that depend on type capabilities:

```cpp
template <typename T>
void serialize(const T& value) {
    if constexpr (std::ranges::range<T>) {
        for (const auto& elem : value) {
            serialize(elem);
        }
    } else if constexpr (requires { value.serialize(); }) {
        value.serialize();
    } else {
        std::cout << value;
    }
}
```

The `requires` expression inside `if constexpr` checks whether a particular expression is valid for the given type, without requiring the type to satisfy a named concept. This is useful for ad-hoc capability checks that do not warrant a named concept.

### Trade-offs and limits

- **Static assertions** are the simplest tool and work in all C++ versions from C++11 onward. Their limit is that they produce hard errors and cannot participate in overload resolution. They are best used for requirements that must always be satisfied and for which an alternative overload does not exist.

- **Concepts** provide better error messages, participate in overload resolution, and express intent more clearly. Their limits are that they require C++20 and that not all compilers have complete C++20 concept support in all contexts. They also add complexity: a concept must be defined, named, and used consistently across a codebase.

- **requires expressions** within concepts are powerful but can be slow to compile when they contain many requirements. Each requirement is a separate compile-time check, and complex concepts with dozens of requirements can add measurable compilation time.

- **Over-constraining** is a trap. A template that requires more than it needs is less reusable. The principle of least constraint says: require only what the template actually uses, and let other templates add their own constraints.

- **Under-constraining** is equally dangerous. A template that accepts types it cannot handle produces confusing error messages deep in its implementation, far from the call site where the invalid type was passed.

The best practice is to start with static assertions during development, because they are simple and produce clear errors. As the template matures and its requirements stabilize, convert the preconditions into concepts. This migration path—from static assertions to concepts—ensures that the constraints are well-understood before they are formalized, and that the concept definitions capture the actual requirements rather than imagined ones.

---

*End of Chapter 16*
