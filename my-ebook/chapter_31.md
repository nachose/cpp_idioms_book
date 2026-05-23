# Chapter 31: Expression Templates

Expression templates are a C++ metaprogramming technique where arithmetic expressions are represented as types rather than computed values. When you write `a + b * c` with expression templates, the compiler builds a type such as `Add<Vec, Mul<Vec, Vec>>` instead of eagerly computing the result. The actual computation happens later, when the expression is assigned to a variable or otherwise evaluated.

The technique was pioneered by Todd Veldhuizen in the 1990s for the Blitz++ library and later adopted by Eigen, Boost.Lambda, Boost.Spirit, and numerous other libraries. At its core, expression templates solve a fundamental tension: operator overloading is eager (each `operator+` returns a result immediately), but optimal performance often requires fusing multiple operations into a single pass over data. Expression templates bridge this gap by making operators lazy: each operator returns a lightweight object that describes *what* to compute, deferring *how* to compute it.

This chapter explores the mechanism behind expression templates, their application to lazy evaluation, the operator overloading patterns they require, and advanced techniques for building expression tree systems.

---

## Expression Template Fundamentals

The motivation for expression templates begins with a simple problem. Consider a `Vector` class that supports arithmetic operations:

```cpp
class Vector {
    std::vector<double> data_;
public:
    explicit Vector(std::size_t n) : data_(n) {}

    Vector operator+(const Vector& rhs) const {
        Vector result(data_.size());
        for (std::size_t i = 0; i < data_.size(); ++i) {
            result.data_[i] = data_[i] + rhs.data_[i];
        }
        return result;
    }

    Vector operator*(double scalar) const {
        Vector result(data_.size());
        for (std::size_t i = 0; i < data_.size(); ++i) {
            result.data_[i] = data_[i] * scalar;
        }
        return result;
    }

    double& operator[](std::size_t i) { return data_[i]; }
    const double& operator[](std::size_t i) const { return data_[i]; }
    std::size_t size() const { return data_.size(); }
};
```

The expression `a * 2.0 + b` evaluates as follows:

1. `a.operator*(2.0)` creates a temporary `Vector` (one loop over all elements).
2. `temp.operator+(b)` creates another temporary `Vector` (a second loop).
3. The result is assigned to the target.

For large vectors, this means two memory allocations and two full traversals of the data. If the expression were `a * 2.0 + b * 3.0 + c`, the situation worsens: each binary operation produces a temporary, and the number of loops grows linearly with expression depth. The fundamental problem is that each operator evaluates eagerly, producing a fully materialized result before the next operation begins.

Expression templates eliminate the temporaries by making operators return lightweight proxy objects that represent the operation rather than its result:

```cpp
// Base class for all expression types (CRTP)
template<typename Derived>
class VecExpr {
public:
    double operator[](std::size_t i) const {
        return static_cast<const Derived&>(*this)[i];
    }
    std::size_t size() const {
        return static_cast<const Derived&>(*this).size();
    }
};

class Vector : public VecExpr<Vector> {
    std::vector<double> data_;
public:
    explicit Vector(std::size_t n) : data_(n) {}
    explicit Vector(std::initializer_list<double> il) : data_(il) {}

    double operator[](std::size_t i) const { return data_[i]; }
    double& operator[](std::size_t i) { return data_[i]; }
    std::size_t size() const { return data_.size(); }
};

// Represents a + b for any two expression types
template<typename LHS, typename RHS>
class VecAdd : public VecExpr<VecAdd<LHS, RHS>> {
    const LHS& lhs_;
    const RHS& rhs_;
public:
    VecAdd(const LHS& lhs, const RHS& rhs) : lhs_(lhs), rhs_(rhs) {}

    double operator[](std::size_t i) const {
        return lhs_[i] + rhs_[i];
    }
    std::size_t size() const {
        // Assumes lhs and rhs have compatible sizes
        return lhs_.size();
    }
};

// Represents a * scalar
template<typename LHS>
class VecScalarMul : public VecExpr<VecScalarMul<LHS>> {
    const LHS& lhs_;
    double scalar_;
public:
    VecScalarMul(const LHS& lhs, double s) : lhs_(lhs), scalar_(s) {}

    double operator[](std::size_t i) const {
        return lhs_[i] * scalar_;
    }
    std::size_t size() const {
        return lhs_.size();
    }
};
```

Now the operators return expression proxy objects instead of concrete `Vector` results:

```cpp
// operator+ returns VecAdd, not Vector
template<typename L, typename R>
VecAdd<L, R> operator+(const VecExpr<L>& lhs, const VecExpr<R>& rhs) {
    return VecAdd<L, R>(
        static_cast<const L&>(lhs),
        static_cast<const R&>(rhs)
    );
}

// operator* (scalar * vector)
template<typename L>
VecScalarMul<L> operator*(const VecExpr<L>& lhs, double scalar) {
    return VecScalarMul<L>(static_cast<const L&>(lhs), scalar);
}

// operator* (vector * scalar)
template<typename R>
VecScalarMul<R> operator*(double scalar, const VecExpr<R>& rhs) {
    return VecScalarMul<R>(static_cast<const R&>(rhs), scalar);
}
```

The expression `a * 2.0 + b` now produces a type like:

```
VecAdd<VecScalarMul<Vector>, Vector>
```

This type is a nested description of the computation. No vector arithmetic has been performed yet — the `VecAdd` and `VecScalarMul` objects just hold references to their operands. The computation happens only when we index into the expression:

```cpp
VecAdd<VecScalarMul<Vector>, Vector> expr = a * 2.0 + b;
double val = expr[5];  // Computes a[5] * 2.0 + b[5] on the fly
```

To make this useful, we add an assignment operator to `Vector` that accepts any `VecExpr`:

```cpp
class Vector : public VecExpr<Vector> {
    // ... as before ...
public:
    // Construct from any expression (eager evaluation)
    template<typename Expr>
    Vector(const VecExpr<Expr>& expr) {
        const auto& e = static_cast<const Expr&>(expr);
        data_.resize(e.size());
        for (std::size_t i = 0; i < data_.size(); ++i) {
            data_[i] = e[i];
        }
    }

    // Assign from any expression
    template<typename Expr>
    Vector& operator=(const VecExpr<Expr>& expr) {
        const auto& e = static_cast<const Expr&>(expr);
        data_.resize(e.size());
        for (std::size_t i = 0; i < data_.size(); ++i) {
            data_[i] = e[i];
        }
        return *this;
    }
};
```

Now the expression `a * 2.0 + b` evaluates in a single loop:

```cpp
Vector a = {1.0, 2.0, 3.0};
Vector b = {4.0, 5.0, 6.0};
Vector c = a * 2.0 + b;  // One loop, one allocation
// Equivalent to:
// for each i: c[i] = a[i] * 2.0 + b[i]
```

The key insight is: instead of evaluating each operator eagerly (which creates temporaries), the expression templates defer computation to the point of assignment, where the full expression tree is known and can be evaluated in a single fused pass. The compiler sees the entire computation `a[i] * 2.0 + b[i]` for each `i` and can optimize it as a single expression, potentially keeping values in registers across the entire computation.

This approach has important trade-offs. Expression templates eliminate temporaries and fuse loops, which can dramatically improve performance for large vectors and complex expressions. However, they increase compile time (each expression type is a distinct template instantiation), produce inscrutable error messages (a missing `operator*` might manifest as a template instantiation failure pages deep), and can generate larger binaries due to template specialization. For small vectors (e.g., fixed-size 3D vectors in graphics), the overhead of the expression proxy and the assignment loop may outweigh the benefits, and a simple eager implementation may be faster.

---

## Lazy Evaluation in Expressions

The fundamental mechanism of expression templates — representing operations as types — enables a broader pattern of lazy evaluation. Instead of computing results at each operator, the entire computation is deferred until the result is actually needed. This section explores what lazy evaluation means for expression templates, how it enables loop fusion, and when it becomes a liability.

### Deferred Computation

In the expression template model, computation is deferred along the entire chain of operations. Each operator simply constructs a new expression object that wraps its operands. No element-wise computation occurs until the expression is indexed or assigned:

```cpp
Vector a = {1, 2, 3}, b = {4, 5, 6}, c = {7, 8, 9};

// No computation happens here — just building the expression tree
auto expr = (a + b) * 2.0 - c;

// Computation happens now — one pass over all elements
Vector result = expr;
```

The expression `expr` has a type like:

```
VecSub<VecScalarMul<VecAdd<Vector, Vector>>, Vector>
```

This type captures the complete structure of the computation. The compiler knows the entire expression tree at compile time, which enables optimizations that would be impossible with eager evaluation.

### Loop Fusion

The most important optimization enabled by lazy evaluation is loop fusion: combining multiple operations into a single pass over the data. In the expression `a + b + c`, eager evaluation requires two loops:

```
temp = a + b    →  loop 1: temp[i] = a[i] + b[i]
result = temp + c →  loop 2: result[i] = temp[i] + c[i]
```

With expression templates, a single loop suffices:

```
result = a + b + c  →  single loop: result[i] = a[i] + b[i] + c[i]
```

For expressions with many terms, the savings compound. An expression like `a + b + c + d + e + f` with eager evaluation requires five loops and four temporaries. With expression templates, it requires one loop and zero temporaries beyond the result.

The fused loop also improves cache utilization. Each temporary in the eager approach must be written to memory and then read back, consuming cache capacity and memory bandwidth. The expression template approach streams through the input vectors once, computing the final result directly. For large vectors that exceed cache size, this can mean the difference between memory-bound and compute-bound execution.

### The Assignment as Evaluation Point

The assignment operator or the constructor that accepts a `VecExpr` serves as the evaluation point — the moment when the deferred computation actually executes. This design creates an important distinction between two categories of operations:

- **Lazy operations**: arithmetic operators (`+`, `-`, `*`, etc.) that return expression proxies.
- **Eager operations**: assignment (`=`), construction from expression, and explicit evaluation methods that trigger the fused loop.

This distinction affects how users write code. Consider:

```cpp
Vector a = {1, 2, 3}, b = {4, 5, 6};
auto expr = a + b;          // expr is VecAdd<Vector, Vector>, not Vector
Vector c = expr;            // OK — triggers evaluation
auto d = expr;              // d is VecAdd<Vector, Vector>, not Vector!
```

The `auto` keyword captures the expression template type, not the evaluated result. This is a common source of confusion. If the user expects `auto d = a + b` to produce a `Vector`, they get an expression proxy instead, which holds references to `a` and `b`. If `a` and `b` are temporary objects, the expression proxy dangles:

```cpp
Vector getVector();

auto d = getVector() + getVector();  // Dangling references!
// d holds references to temporaries that are already destroyed
```

This pitfall is inherent to the lazy evaluation model. Libraries like Eigen mitigate it by using `Eigen::Matrix` types for the result, but the problem can never be fully eliminated while expression proxies hold references to operands. Users must be aware that `auto` with expression templates captures the expression type, not the computed result.

### When Lazy Evaluation Hurts

Lazy evaluation is not always beneficial. The costs include:

**Small vectors**: For fixed-size vectors with just two or three elements, the overhead of constructing expression proxy objects and the indirect access through `operator[]` may exceed the cost of simple eager computation. The optimizer may inline and eliminate the proxies, but this is not guaranteed.

**Complex control flow**: If the expression is used in a branch that rarely executes, the work of building the expression tree is wasted. For example:

```cpp
auto expr = a + b;                   // Builds the expression tree
if (rare_condition) {
    Vector result = expr;            // Only evaluates here
}
```

With eager evaluation, `a + b` would be computed only when needed. With expression templates, the expression tree is always constructed (building the tree is cheap — it's just reference storage), but the evaluation loop happens only in the branch. This is usually fine, but the expression proxy types are always instantiated, increasing compile time.

**Non-trivial element access**: If the expression operands themselves involve computation (e.g., reading from a file or generating random numbers), lazy evaluation means that computation happens at assignment time, which may be unexpected:

```cpp
RandomVector rng(seed);
Vector a = {1, 2, 3};
auto expr = a + rng.nextNormal(0.0, 1.0);
// rng.nextNormal is called once per element during the assignment loop
Vector result = expr;
```

This is correct — the random numbers should be generated element-by-element, not once at the point of `operator+`. But it changes the semantics: the expression captures a reference to `rng`, and the random sequence is consumed during assignment. If `rng` is modified between building the expression and evaluating it, the result changes.

**Debugging complexity**: Lazy evaluation makes single-stepping through arithmetic code difficult. Instead of tracing through `operator+`, `operator*`, and assignment in sequence, the debugger shows template instantiation internals and indirect calls through CRTP bases. Techniques like `__attribute__((noinline))` on the evaluation loop can help, but the debugging experience remains worse than with eager code.

These trade-offs make expression templates most valuable for large arrays (thousands of elements or more), SIMD-optimized computations, and scenarios where memory bandwidth is the bottleneck. For small-scale computation, eager evaluation remains simpler and often faster.

---

## Operator Overloading Patterns

Expression templates require careful operator overloading design. The operators must return expression proxy objects rather than computed values, and they must compose correctly with each other. This section covers the patterns used to build expression template operator overloads.

### Returning Expression Proxies

The defining characteristic of expression template operators is that they return proxy types, not concrete types:

```cpp
template<typename L, typename R>
VecAdd<L, R> operator+(const VecExpr<L>& lhs, const VecExpr<R>& rhs) {
    return VecAdd<L, R>(
        static_cast<const L&>(lhs),
        static_cast<const R&>(rhs)
    );
}
```

This function template accepts any two types derived from `VecExpr` and returns a `VecAdd` that holds references to both operands. The function itself is lightweight — it just creates the proxy object — and the compiler typically inlines it entirely.

The challenge is ensuring that all possible operand combinations are covered. A complete set of overloads for a numeric vector library might include:

```cpp
// vector + vector
template<typename L, typename R>
VecAdd<L, R> operator+(const VecExpr<L>&, const VecExpr<R>&);

// vector - vector
template<typename L, typename R>
VecSub<L, R> operator-(const VecExpr<L>&, const VecExpr<R>&);

// scalar * vector
template<typename R>
VecScalarMul<R> operator*(double, const VecExpr<R>&);

// vector * scalar
template<typename L>
VecScalarMul<L> operator*(const VecExpr<L>&, double);

// vector / scalar
template<typename L>
VecScalarDiv<L> operator/(const VecExpr<L>&, double);
```

Each operator follows the same pattern: accept `VecExpr<L>&` (or value types for scalars), return a new expression proxy type.

### Composing Expressions of Different Types

A key strength of expression templates is that they compose expressions involving different concrete types, as long as those types derive from the common `VecExpr` base. For example, if we have a `SparseVector` and a `DenseVector`, both deriving from `VecExpr`, then `sparse + dense` produces a `VecAdd<SparseVector, DenseVector>`, which can be assigned to either a `DenseVector` or a `SparseVector` (depending on which assignment operator is available).

This composability requires that all expression types support a common interface — in our case, `operator[]` and `size()`. The CRTP base enforces this interface but does not mandate a specific storage layout. The evaluation loop in the assignment operator only needs element access:

```cpp
template<typename Expr>
Vector& Vector::operator=(const VecExpr<Expr>& expr) {
    const auto& e = static_cast<const Expr&>(expr);
    data_.resize(e.size());
    for (std::size_t i = 0; i < data_.size(); ++i) {
        data_[i] = e[i];  // Calls operator[] through the expression tree
    }
    return *this;
}
```

The single line `data_[i] = e[i]` invokes the full chain of CRTP calls: `VecAdd::operator[]` calls `VecScalarMul::operator[]` which calls `Vector::operator[]`. The inliner typically collapses this into a single expression like `data_[i] = a[i] * 2.0 + b[i]`.

### Binary Operations Between Expressions and Scalars

Handling mixed operations between expressions and scalars requires care. The scalar must be wrapped or passed directly to the expression proxy. Our earlier approach used a separate `VecScalarMul` expression type that stores a `double`:

```cpp
template<typename LHS>
class VecScalarMul : public VecExpr<VecScalarMul<LHS>> {
    const LHS& lhs_;
    double scalar_;
public:
    VecScalarMul(const LHS& lhs, double s) : lhs_(lhs), scalar_(s) {}
    double operator[](std::size_t i) const { return lhs_[i] * scalar_; }
    std::size_t size() const { return lhs_.size(); }
};
```

An alternative is to treat scalars as expressions over a constant value:

```cpp
class ScalarExpr : public VecExpr<ScalarExpr> {
    double value_;
public:
    explicit ScalarExpr(double v) : value_(v) {}
    double operator[](std::size_t) const { return value_; }
    std::size_t size() const { return 0; }  // size is determined by other operand
};
```

Then `scalar * vector` becomes `VecMul<ScalarExpr, Vector>`, eliminating the need for a separate `VecScalarMul` type. The size mismatch must be handled in the evaluation: when the expression is assigned to a concrete vector, the size comes from the concrete target, and indexing into the `ScalarExpr` returns the constant regardless of index.

This unified approach reduces the number of expression types but introduces the complexity of handling size in mixed-type expressions. Libraries like Eigen use a combination of both approaches, with dedicated scalar operations where they improve code generation.

### Handling Mixed-Precision Operations

When expression operands have different value types (e.g., `float` vector + `double` vector), the expression template must decide the result type. The standard approach is to use `decltype` or a traits class to determine the common type:

```cpp
template<typename T, typename U>
struct CommonType {
    using type = decltype(std::declval<T>() + std::declval<U>());
};

template<typename LHS, typename RHS>
class VecAdd : public VecExpr<VecAdd<LHS, RHS>> {
    using value_type = typename CommonType<
        typename LHS::value_type,
        typename RHS::value_type
    >::type;

    value_type operator[](std::size_t i) const {
        return static_cast<value_type>(lhs_[i]) + static_cast<value_type>(rhs_[i]);
    }
};
```

This requires each expression type to define a `value_type` typedef. The expression template then promotes operands as needed, following C++'s usual arithmetic conversions. The cost is compile-time complexity: each mixed-type expression instantiates additional template machinery for the type computation.

### Common Pitfalls in Operator Overloading

**Non-const reference parameters**: Operators must take their operands by const reference (or by value for scalars). Taking by non-const reference prevents binding to temporaries, which breaks common patterns like `getVector() + another`.

**Return type deduction**: With `auto` return types, operators can inadvertently return an evaluation result instead of an expression proxy:

```cpp
// BAD: evaluates eagerly
template<typename L, typename R>
auto operator+(const L& lhs, const R& rhs) {
    return Vector(lhs) + Vector(rhs);  // Converts to Vector first
}
```

The solution is to explicitly specify the return type or ensure the return expression preserves lazy evaluation.

**Namespace pollution**: Operators defined in global namespace or large namespaces can accidentally participate in overload resolution for unrelated types. Libraries like Eigen define operators in their own namespace and rely on ADL or explicit qualification. However, ADL only works if at least one operand is from the same namespace, which means users must use `using namespace Eigen;` or call operators through qualified names.

**Type deduction failures**: Template operators with multiple template parameters may fail to deduce when both operands require implicit conversion. For example, if `Vector` has a converting constructor from `VecExpr`, the expression `a + b` might try to convert both `a` and `b` to `Vector` before calling `operator+`, defeating expression templates. This is prevented by ensuring the operators are defined before the conversion constructors and that they match more precisely.

---

## Advanced Expression Template Techniques

The basic expression template pattern — representing operations as types and deferring evaluation — extends to several advanced use cases beyond simple vector arithmetic.

### Compile-Time Expression Trees

Expression templates naturally form a compile-time tree structure. Each node in the tree is a distinct C++ type, and the tree structure encodes the full computation. This enables compile-time traversal and transformation of the expression:

```cpp
// Traits to determine expression properties at compile time
template<typename Expr>
struct ExprTraits {
    static constexpr bool is_constant = false;
    static constexpr bool is_unary = false;
    static constexpr bool is_binary = false;
};

template<>
struct ExprTraits<ScalarExpr> {
    static constexpr bool is_constant = true;
};

template<typename L, typename R>
struct ExprTraits<VecAdd<L, R>> {
    static constexpr bool is_binary = true;
    using left_type = L;
    using right_type = R;
};
```

These traits enable optimization passes at compile time. For example, the expression `a * 0.0` can be simplified to a zero vector without any element-wise computation:

```cpp
template<typename LHS>
class VecScalarMul : public VecExpr<VecScalarMul<LHS>> {
    // ...
public:
    // Return a simplified expression when scalar is zero
    auto optimized() const {
        if constexpr (std::is_same_v<LHS, ScalarExpr>) {
            return ScalarExpr(lhs_[0] * scalar_);
        } else if (scalar_ == 0.0) {
            return ScalarExpr(0.0);
        } else {
            return *this;
        }
    }
};
```

The `if constexpr` branches are evaluated at compile time for type-level simplifications. The runtime `scalar_ == 0.0` check catches value-level simplifications at the cost of a branch in the expression construction.

### Evaluation Strategies

Beyond the simple element-by-element assignment expression templates support different evaluation strategies:

**Block evaluation**: Instead of computing one element at a time, the expression is computed in blocks that fit in cache:

```cpp
template<typename Expr>
void evaluate_blocked(Vector& result, const Expr& expr, std::size_t block_size = 64) {
    for (std::size_t i = 0; i < result.size(); i += block_size) {
        std::size_t end = std::min(i + block_size, result.size());
        for (std::size_t j = i; j < end; ++j) {
            result[j] = expr[j];
        }
    }
}
```

**SIMD evaluation**: On platforms with SIMD instruction sets, the expression can be evaluated in vector registers:

```cpp
template<typename Expr>
void evaluate_simd(Vector& result, const Expr& expr) {
    #if defined(__AVX2__)
    constexpr std::size_t simd_width = 256 / (8 * sizeof(double));  // 4 doubles
    for (std::size_t i = 0; i < result.size(); i += simd_width) {
        // Load, compute, and store in SIMD registers
        // Compiler auto-vectorization often handles this
        for (std::size_t j = 0; j < simd_width; ++j) {
            result[i + j] = expr[i + j];
        }
    }
    #endif
}
```

Modern compilers auto-vectorize the simple element loop for basic expression types, but complex or irregular expressions may require explicit SIMD intrinsics. Libraries like Eigen use a sophisticated evaluator hierarchy that selects the best evaluation strategy based on the expression type and available hardware.

**Parallel evaluation**: Multi-threaded evaluation splits the expression across threads:

```cpp
template<typename Expr>
void evaluate_parallel(Vector& result, const Expr& expr) {
    std::size_t chunk_size = result.size() / std::thread::hardware_concurrency();
    std::vector<std::thread> threads;
    for (std::size_t start = 0; start < result.size(); start += chunk_size) {
        std::size_t end = std::min(start + chunk_size, result.size());
        threads.emplace_back([&result, &expr, start, end]() {
            for (std::size_t i = start; i < end; ++i) {
                result[i] = expr[i];
            }
        });
    }
    for (auto& t : threads) t.join();
}
```

The evaluation strategy can be selected at compile time through traits on the expression type, or at runtime through a strategy parameter. Eigen, for instance, uses a `eval` method on expressions that dispatches to specialized evaluators determined by the expression's properties.

### Expression Templates and Ranges

C++20 ranges and views provide a lazy evaluation model similar to expression templates, but standardized and composable with the standard library:

```cpp
#include <ranges>
#include <vector>

namespace rv = std::views;

std::vector<int> a = {1, 2, 3, 4, 5};
std::vector<int> b = {6, 7, 8, 9, 10};

auto result = rv::zip_transform(
    [](int x, int y) { return x * 2 + y; },
    a, b
);  // Lazy range, no computation yet

for (int v : result) {
    // Computation happens here, one element at a time
}
```

The key difference between ranges and expression templates is generality: ranges work with any sequence-producing operation, while expression templates are optimized for numeric computations. Ranges provide `view` types that are analogous to expression proxies — they hold references to their source ranges and produce elements on demand.

Expression templates can interoperate with ranges by providing range-like interfaces:

```cpp
template<typename LHS, typename RHS>
class VecAdd : public VecExpr<VecAdd<LHS, RHS>> {
    // ...
public:
    auto begin() const { return Iterator<VecAdd>(*this, 0); }
    auto end() const { return Iterator<VecAdd>(*this, size()); }

    // C++20 range capability
    friend auto ranges::range_access_t(const VecAdd& expr)
        -> std::ranges::ref_view<const VecAdd>;
};
```

A full range adapter wrapping expression template types allows expression templates to participate in pipeline compositions like `expr | std::views::take(5) | std::views::transform(...)`, bridging the two lazy evaluation worlds.

### Constant Folding and Expression Rewriting

Advanced expression template libraries perform compile-time expression rewriting. The expression `(a + b) + (a + b)` can be recognized as `2 * (a + b)` and simplified:

```cpp
// Define transformation rules
template<typename L, typename R>
struct ExprOptimizer {
    // Identity: x + 0 = x
    static auto optimize(const VecAdd<L, R>& expr) {
        if constexpr (is_zero_constant<L>()) {
            return R(expr);  // Strip the zero
        } else if constexpr (is_zero_constant<R>()) {
            return L(expr);  // Strip the zero
        }
        return expr;  // No optimization
    }

    // Common subexpression detection could be done here
    // (typically at a higher level than individual expression types)
};
```

True common subexpression elimination requires expression graphs rather than trees (since a subexpression may be referenced multiple times) and is usually handled at a higher level — either through explicit variable naming by the user or through a graph-based IR that the expression template system constructs during evaluation.

### Comparison with Macros and Lambdas

Before expression templates, C++ programmers used preprocessor macros to achieve loop fusion:

```cpp
#define FOR_EACH(i, n, expr) \
    for (std::size_t i = 0; i < n; ++i) { expr; }

FOR_EACH(i, n, result[i] = a[i] * 2.0 + b[i]);
```

Macros have no type safety, no composability (you cannot pass a macro expression as a function argument), and no debugging support. Expression templates provide the same fusion benefit with full type safety and composability.

Lambdas provide an alternative lazy evaluation mechanism:

```cpp
auto operation = [&](std::size_t i) { return a[i] * 2.0 + b[i]; };
for (std::size_t i = 0; i < n; ++i) {
    result[i] = operation(i);
}
```

Lambdas, like expression templates, defer computation until called. They are simpler to write and understand, but they don't compose as naturally — composing `operation1` and `operation2` into `operation1 + operation2` requires explicit lambda wrapping, whereas expression templates compose automatically through operator overloading. For simple use cases, lambdas are preferable; for building large expression systems, expression templates remain the better tool.

---

## Summary

Expression templates are a C++ technique that represents arithmetic expressions as types, deferring computation until assignment. This deferral enables loop fusion — combining multiple operations into a single pass over data — which eliminates temporaries and improves memory bandwidth utilization.

The fundamental mechanism has three parts:

- A CRTP base class defines the expression interface, typically element access and size.
- Operator overloads return expression proxy objects that hold references to their operands, describing _what_ to compute rather than computing eagerly.
- Assignment operators or constructors serve as evaluation points, running a fused loop that computes the final result.

**Expression template fundamentals** cover the core mechanism: representing operations as types, the CRTP base pattern, and how lazy evaluation eliminates temporaries. The key trade-off is compile-time complexity against runtime performance.

**Lazy evaluation in expressions** explains how deferring computation enables loop fusion, the role of assignment as the evaluation point, and when lazy evaluation is harmful (small vectors, complex control flow, non-trivial element access).

**Operator overloading patterns** covers the design of operators that return expression proxies, composing expressions of different types, handling scalar operands, mixed precision, and common pitfalls like dangling references from `auto` deduction.

**Advanced expression template techniques** explores compile-time expression trees, evaluation strategies (blocked, SIMD, parallel), integration with C++20 ranges, and constant folding.

Expression templates are most valuable for large numeric arrays, SIMD-optimized computations, and library code where users compose complex expressions. Their costs — increased compile time, complex error messages, debugging difficulty — make them inappropriate for small-scale computation or general-purpose code where eager evaluation or simple lambdas suffice. When applied judiciously, however, they deliver the zero-overhead abstraction that C++ promises.

### Exercises

1. **Unary Expression**: Extend the expression template system with a `VecNegate` expression that represents element-wise negation (`-vec`). Implement the unary `operator-` overload. What changes are needed to the `VecExpr` base class to support unary operations?

2. **Dot Product Expression**: Implement a `DotProduct` expression that computes the dot product of two vector expressions lazily. The dot product should return a scalar, not a vector. How does this differ from the element-wise expressions in this chapter? What evaluation strategy makes sense for dot products?

3. **Lifetime Safety**: Add a `VecExpr::evaluate()` method that returns a concrete `Vector`. This gives users a way to materialize the expression without assignment. Then create a wrapper `ExprGuard` that holds vector operands by value, preventing dangling references when expressions involve temporaries. Show how `ExprGuard<a + b>` differs from plain `a + b`.

4. **Custom Evaluation Strategy**: Implement a `evaluate_with_policy` function that accepts the expression and a tag type (`Sequential`, `SIMD`, or `Parallel`) to select the evaluation strategy at compile time. Use `if constexpr` to dispatch to the appropriate loop implementation. Measure the performance difference for vectors of size 10, 1000, and 1,000,000.

5. **Expression with Ternary Operations**: Extend the system to support a conditional expression: `where(mask, a, b)` that selects elements from `a` where `mask` is true and from `b` otherwise. Implement `VecCondition` as an expression type. Discuss how branching in the evaluation loop affects SIMD vectorization.

6. **Integration with C++20 Ranges**: Create a range adapter that wraps a `VecExpr` and exposes it as a C++20 range. Then implement a `sum` algorithm that uses `std::ranges::fold_left` to compute the total of the expression. Compare the assembly output with the manual loop implementation using Compiler Explorer.
