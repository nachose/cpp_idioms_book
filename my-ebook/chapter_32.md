# Chapter 32: Variadic Templates Patterns

Variadic templates, introduced in C++11, are the mechanism that lets a template accept an arbitrary number of arguments of arbitrary types. Their arrival transformed what was possible in C++ template metaprogramming: before them, variadic behavior required cumbersome recursion with overloads or preprocessor macros; after them, parameter packs, pack expansions, and fold expressions became the lingua franca of generic libraries. This chapter dissects the three essential patterns that every C++ programmer working with variadic templates must understand: constructing types from packs, manipulating packs at compile time, and implementing the canonical variadic container — `std::tuple`.

---

## Variadic Type Construction

### The parameter pack

A variadic template is declared with an _ellipsis_ (`...`) in the template parameter list:

```cpp
template <typename... Ts>
struct TypeList {};
```

Here, `Ts` is a _template parameter pack_. A pack can hold zero or more type arguments:

```cpp
TypeList<> empty;
TypeList<int, double, char> three;
```

The number of elements in a pack is obtained at compile time with `sizeof...`:

```cpp
template <typename... Ts>
constexpr std::size_t count = sizeof...(Ts);

static_assert(count<int, double, char> == 3);
static_assert(count<> == 0);
```

Why does `sizeof...` exist separately from `sizeof`? Because a pack is not a concrete type or object — it is a _compile-time list_ that exists only during template instantiation. The `sizeof...` operator is the only way to query its cardinality without first expanding it.

### Pack expansions

A pack becomes useful only when it is _expanded_. Expansion is triggered by placing `...` after a pattern that contains the pack name. The pattern is repeated for each element:

```cpp
template <typename... Ts>
void print_all(Ts... args) {        // function parameter pack
    (std::cout << ... << args);     // fold expression, C++17
}
```

The line `(std::cout << ... << args)` is a _unary right fold_. It expands to `((std::cout << arg1) << arg2) << arg3 ...`, printing each argument in order. Fold expressions (C++17) are the idiomatic way to operate on packs in value contexts; before C++17, recursion was the only option.

The pattern can be arbitrarily complex:

```cpp
template <typename... Ts>
void wrap_print(const Ts&... args) {
    ((std::cout << "[" << args << "] "), ...);
}
```

Here the pattern is `"[" << args << "] "`, and the comma fold `(expr, ...)` evaluates each expression in sequence. The result prints `[1] [hello] [3.14]` for input `(1, "hello", 3.14)`.

### Building types from packs

The most common type-construction pattern uses a pack to instantiate another variadic template:

```cpp
template <typename... Ts>
struct VariantWrapper {
    using type = std::variant<Ts...>;
};

using MyVariant = VariantWrapper<int, std::string, double>::type;
// MyVariant = std::variant<int, std::string, double>
```

This looks trivial, but it unlocks a key idea: packs can be _transformed_ before being used. With a metafunction applied to each element, you can build types that are derived from the input pack:

```cpp
template <typename T>
struct add_pointer {
    using type = std::add_pointer_t<T>;
};

template <typename... Ts>
struct PointerVariant {
    using type = std::variant<typename add_pointer<Ts>::type...>;
};

using PtrVar = PointerVariant<int, std::string>::type;
// PtrVar = std::variant<int*, std::string*>
```

The pattern `typename add_pointer<Ts>::type...` expands to `typename add_pointer<int>::type, typename add_pointer<std::string>::type`, which evaluates to `int*, std::string*`. This pattern — _mapping a metafunction over a pack_ — is the foundation of most variadic type construction.

### Recursive type construction

Before fold expressions (and still useful for complex cases), type construction was done recursively via partial specialization:

```cpp
template <typename... Ts>
struct Concat;   // primary template (undefined)

template <typename... Ts>
struct Concat<TypeList<Ts...>> {
    using type = TypeList<Ts...>;
};

// The recursive case is more involved and usually uses inheritance
// or alias templates. A practical concat:
template <typename... Lists>
struct ConcatHelper;

template <typename... Ts, typename... Us>
struct ConcatHelper<TypeList<Ts...>, TypeList<Us...>> {
    using type = TypeList<Ts..., Us...>;
};

template <typename... Ts>
using Concat_t = typename ConcatHelper<Ts...>::type;
```

This works but is verbose. Modern C++ reduces the need for recursion by providing two alternatives: fold expressions (for value packs) and `using` declarations with pack expansion (for type packs). However, recursion is still the correct tool when the operation on the pack depends on a structural property, such as "split after the first element" or "filter elements satisfying a predicate."

### Fold expressions for type construction (C++17)

Fold expressions operate on values, not on types directly. But you can use lambdas and `decltype` to bridge the gap:

```cpp
template <typename... Ts>
struct HeadType;

template <typename T, typename... Rest>
struct HeadType<T, Rest...> {
    using type = T;
};
```

This extraction pattern — partially specializing on the first element and the rest — is the variadic equivalent of `car` and `cdr` from Lisp. It is used throughout tuple-like type manipulation and is especially relevant to the tuple implementation later in this chapter.

---

The power of variadic type construction lies in the interplay between packs and partial specialization. A pack can be destructured (first element + rest), expanded into another template, or transformed element-wise via a metafunction. These three operations — _map_, _filter_, and _fold_ at the type level — are the building blocks of all advanced variadic C++.

---

## Parameter Pack Manipulation

Having a pack is one thing; manipulating it — indexing into it, filtering it, transforming it, splitting it — is another. This section covers the techniques that make packs programmable.

### Index sequences and pack indexing

A fundamental limitation of parameter packs is that they do not support direct element access. You cannot write `Ts[2]` or `Ts::at<2>`. The standard solution is `std::index_sequence` and its companion `std::make_index_sequence`, which generate a compile-time sequence `0, 1, 2, ..., N-1`:

```cpp
template <typename... Ts>
void print_all(const Ts&... args) {
    print_each(std::index_sequence_for<Ts...>{}, args...);
}

template <typename... Ts, std::size_t... Is>
void print_each(std::index_sequence<Is...>, const Ts&... args) {
    ((std::cout << Is << ": " << args << "\n"), ...);
}
```

Why go through the indirection of an index sequence? Because packs can only be expanded in certain contexts. An index sequence gives you a second pack `Is...` of `std::size_t` constants that can be used in combination with the original pack. This is the idiomatic way to access the _position_ of each element in a pack.

C++26 adds _pack indexing_ directly: `Ts...[I]` retrieves the `I`-th type in a pack. When widely available, this will eliminate many uses of index sequences. Until then, `std::tuple_element_t<I, std::tuple<Ts...>>` serves the same purpose at the cost of instantiating a `tuple` specialization.

### Type filtering with conditional

A common operation is keeping only those types from a pack that satisfy a predicate:

```cpp
template <typename... Ts>
struct FilterIntegral {
    template <typename T>
    using Predicate = std::is_integral<T>;

    // Recursive split
    template <typename... Accum>
    struct Impl;

    template <typename T, typename... Rest, typename... Accum>
    struct Impl<T, Rest..., Accum...> {
        using type = typename std::conditional_t<
            Predicate<T>::value,
            typename Impl<Rest..., Accum..., T>::type,
            typename Impl<Rest..., Accum...>::type
        >;
    };

    template <typename... Accum>
    struct Impl<Accum...> {
        using type = TypeList<Accum...>;
    };

    using type = typename Impl<Ts...>::type;
};
```

This recursive implementation is verbose, but the pattern is essential: each step examines the first type `T`, conditionally appends it to `Accum`, and recurses on `Rest`. The base case (empty pack) returns `Accum`. This is the type-level equivalent of `std::copy_if`.

In practice, type filtering is often delegated to a helper like `mp_filter` from Boost.Mp11 or a hand-rolled `Filter` alias. The key insight is not the verbosity of the implementation but the fact that type-level iteration is inherently recursive — there is no `for` loop at compile time.

### Transforming a pack with alias templates

Transformation applies a unary metafunction to each element:

```cpp
template <typename T>
using make_pointer = T*;

template <template <typename> class F, typename... Ts>
struct Transform;

template <template <typename> class F, typename... Ts>
struct Transform<F, TypeList<Ts...>> {
    using type = TypeList<F<Ts>...>;
};

using PtrList = Transform<make_pointer, TypeList<int, double, char>>::type;
// TypeList<int*, double*, char*>
```

The pattern `F<Ts>...` is the simplest and most elegant form of type-level map. It works with any alias template that takes one type and produces one type. When the metafunction is more complex (e.g., conditional), wrapping it in an alias keeps the expansion readable.

### Zip operations on multiple packs

To combine two packs element-wise, you need an index sequence:

```cpp
template <typename... Ts, typename... Us, std::size_t... Is>
auto zip_impl(const std::tuple<Ts...>& t, const std::tuple<Us...>& u,
              std::index_sequence<Is...>) {
    return std::make_tuple(
        std::pair<std::tuple_element_t<Is, std::tuple<Ts...>>,
                  std::tuple_element_t<Is, std::tuple<Us...>>>{
            std::get<Is>(t), std::get<Is>(u)
        }...
    );
}
```

This produces a tuple of pairs, where each pair holds the corresponding elements from the two input tuples. The `Is...` pack drives the element-wise access. The limitation — both packs must have the same length — is an invariant that should be enforced with a `static_assert`.

### Pack concatenation and splitting

Concatenating two type lists is simply `TypeList<Ts..., Us...>`. Splitting, however, requires recursion or index-based partitioning:

```cpp
template <typename... Ts>
struct Split;

template <typename T, typename... Rest>
struct Split<T, Rest...> {
    using first = T;
    using rest  = TypeList<Rest...>;
};
```

This split — separating head from tail — is the cornerstone of recursive variadic algorithms. It appears in tuple implementations, variant visitors, recursive fold algorithms, and type-level search.

---

The ability to index, filter, transform, zip, and split parameter packs transforms them from a syntactic curiosity into a genuine compile-time programming language. The mental model is simple: packs are linked lists of types. Recursion on head/tail gives you iteration; alias template expansion gives you map; `std::conditional` gives you filter. Everything else is built on these primitives.

---

## Tuple Implementation

`std::tuple` is the canonical example of variadic template design. It holds an arbitrary number of values of arbitrary types, provides compile-time indexed access via `std::get`, and supports decomposition via structured bindings. Understanding how a tuple is implemented — even in simplified form — ties together every concept in this chapter.

### Recursive inheritance-based tuple

The classic tuple uses recursive inheritance. Each level of recursion stores one element and inherits from the tuple of the remaining elements:

```cpp
template <typename... Ts>
class tuple;   // primary template, not defined

template <>
class tuple<> {
    // base case: empty tuple
};

template <typename T, typename... Rest>
class tuple<T, Rest...> : private tuple<Rest...> {
public:
    tuple() = default;

    tuple(const T& head, const Rest&... tail)
        : tuple<Rest...>(tail...), head_(head) {}

    T& head() { return head_; }
    const T& head() const { return head_; }

    using base_type = tuple<Rest...>;
    base_type& tail() { return *this; }
    const base_type& tail() const { return *this; }

private:
    T head_;
};
```

Why inheritance instead of composition? Because inheriting from `tuple<Rest...>` enables the _empty base optimization_ (EBO). When `Rest...` contains only empty types (such as a `tuple<>` with no data members), the compiler is permitted to eliminate the base class subobject entirely, consuming no space. With composition, `tuple<Rest...>` would always occupy at least one byte, even when empty. This is why `std::tuple` uses inheritance: zero-overhead abstraction for empty tuples.

A private base class also means the tuple class hierarchy is not intended for polymorphism. You never cast to a base — you access it through `std::get`, which uses template specialization to navigate the inheritance chain.

### Element access via `std::get`

How does `std::get<I>(tuple)` retrieve the `I`-th element from a recursive tuple? It uses partial specialization on the index:

```cpp
template <std::size_t I, typename... Ts>
struct tuple_element;

template <typename T, typename... Rest>
struct tuple_element<0, tuple<T, Rest...>> {
    using type = T;
    using tuple_type = tuple<T, Rest...>;
};

template <std::size_t I, typename T, typename... Rest>
struct tuple_element<I, tuple<T, Rest...>> {
    using type = typename tuple_element<I - 1, tuple<Rest...>>::type;
    using tuple_type = typename tuple_element<I - 1, tuple<Rest...>>::tuple_type;
};

template <std::size_t I, typename... Ts>
decltype(auto) get(tuple<Ts...>& t) {
    using elem_t = typename tuple_element<I, tuple<Ts...>>::tuple_type;
    return static_cast<elem_t&>(t).head();
}
```

The algorithm: `get<0>` returns `head()` of the outermost tuple. `get<1>` recurses to `tuple_element<0, tuple<Rest...>>`, which matches the base case and returns `head()` of the second-level tuple. Each recursive step strips one type from the pack. The cast `static_cast<elem_t&>(t)` navigates the inheritance hierarchy: because `tuple<T, Rest...>` inherits from `tuple<Rest...>`, a downcast to the appropriate base class exposes the correct `head_`.

This recursive technique is efficient — the `get` call compiles to a simple member access with constant offset — but it produces deep template instantiations for large tuples. Some implementations use a flat internal storage layout to avoid deep nesting.

### Flat tuple with pack expansion (C++17)

A flat tuple uses a struct with a member for each type, avoiding recursive inheritance:

```cpp
template <typename... Ts>
struct flat_tuple {
    static_assert(sizeof...(Ts) > 0, "flat_tuple requires at least one element");

    template <std::size_t I>
    decltype(auto) get() {
        return storage_.template get<I>();
    }

private:
    struct Storage {
        Ts... values_;   // not valid C++, pack in member is illegal
    } storage_;
};
```

The problem: C++ prohibits a pack expansion in a member declaration (except through an intermediate template). The workaround is to inherit from a pack expansion:

```cpp
template <typename... Ts>
struct flat_tuple : Ts... {
    // inherits from each type individually
};
```

But this fails when `Ts` contains non-class types (like `int`) or when two types are the same (duplicate base class). The solution uses the _element holder_ pattern:

```cpp
template <std::size_t I, typename T>
struct tuple_element_holder {
    T value;
};

template <typename... Ts, std::size_t... Is>
struct flat_tuple : tuple_element_holder<Is, Ts>... {
    // inherits from each holder using its unique index
};
```

Because each base class has a unique index `I`, there is no ambiguity even when types repeat. This flat approach is used by some production tuple implementations (e.g., EASTL). It requires a pack of indices — generated by `std::index_sequence` — alongside the type pack:

```cpp
template <typename... Ts, std::size_t... Is>
struct flat_tuple_impl : tuple_element_holder<Is, Ts>... {
    flat_tuple_impl(Ts... args)
        : tuple_element_holder<Is, Ts>(std::forward<Ts>(args))... {}
};
```

The flat approach avoids deep template recursion and produces fewer instantiations than the recursive inheritance approach. Its main drawback is that it requires the index sequence as part of the template signature, which complicates the interface slightly.

### `std::apply` and tuple algorithms

C++17 introduced `std::apply`, which calls a function with the elements of a tuple as arguments:

```cpp
template <typename F, typename... Ts, std::size_t... Is>
decltype(auto) apply_impl(F&& f, std::tuple<Ts...>& t,
                          std::index_sequence<Is...>) {
    return std::invoke(std::forward<F>(f), std::get<Is>(t)...);
}

template <typename F, typename... Ts>
decltype(auto) apply(F&& f, std::tuple<Ts...>& t) {
    return apply_impl(
        std::forward<F>(f), t,
        std::make_index_sequence<sizeof...(Ts)>{}
    );
}
```

The pattern: create an index sequence matching the tuple size, expand `std::get<Is>(t)...` to produce the arguments in order. This is the canonical use of index sequences with tuple — it demonstrates how the two packs (types and indices) collaborate.

Building on `apply`, you can implement `tuple_for_each` and `tuple_transform`:

```cpp
template <typename... Ts, typename F>
void tuple_for_each(std::tuple<Ts...>& t, F&& f) {
    std::apply([&](auto&... args) {
        (f(args), ...);
    }, t);
}

template <typename... Ts, typename F>
auto tuple_transform(std::tuple<Ts...>& t, F&& f) {
    return std::apply([&](auto&... args) {
        return std::tuple<decltype(f(args))...>{ f(args)... };
    }, t);
}
```

The comma fold `(f(args), ...)` inside the lambda evaluates `f` for each element in order. The second example uses `decltype(f(args))...` to deduce the result types. Both patterns leverage pack expansion in lambda capture and return statements.

### Structured bindings and tuple-like types

Structured bindings (C++17) work with any type that satisfies the _tuple-like_ protocol: the type must specialize `std::tuple_size`, `std::tuple_element`, and provide a `get<I>()` member or ADL-eligible `get<I>(t)`. This is exactly the interface a tuple exposes:

```cpp
template <>
struct std::tuple_size<tuple<int, double, char>> {
    static constexpr std::size_t value = 3;
};

template <std::size_t I>
struct std::tuple_element<I, tuple<int, double, char>> {
    using type = ...;   // as shown earlier
};
```

Implementing this protocol for a custom type (such as a struct or a fixed-size array) enables structured bindings without any changes to the client code. The standard library's `std::array`, for example, provides these specializations, allowing:

```cpp
std::array<int, 3> arr = {1, 2, 3};
auto [a, b, c] = arr;   // works because array has tuple-like protocol
```

This is the payoff of understanding the tuple implementation: the same patterns — pack expansion, index sequences, partial specialization — are reused throughout the standard library. Writing a custom tuple-like type is a matter of providing `tuple_size`, `tuple_element`, and `get`.

---

The tuple is more than a container. It is a demonstration of every variadic template pattern in a single coherent design: pack declaration, recursive or flat inheritance, index-based access, structured binding protocol, and algorithm composition via `apply`. Mastering the tuple means mastering variadic templates.

---

## Chapter Summary

Variadic templates are the backbone of modern C++ generic programming. The three patterns in this chapter build on each other:

- **Variadic type construction** introduces packs and their expansion. The key operations — expanding a pack into another template, applying a metafunction to each element, and destructuring a pack via partial specialization — form the foundation of type-level programming.

- **Parameter pack manipulation** adds control structures: indexing via `std::index_sequence`, filtering via `std::conditional` and recursion, transformation via alias template expansion, and splitting via head/tail decomposition. These operations turn packs from passive lists into programmable compile-time data structures.

- **Tuple implementation** demonstrates how these patterns compose. Whether recursive (classic) or flat (index-based), a tuple is a concrete application of pack expansion, index sequences, and partial specialization. It also serves as the protocol for structured bindings, connecting variadic templates to a widely used language feature.

Together, these patterns equip you to design variadic interfaces — not just containers, but also visitors, type erasure wrappers, function decorators, and policy combinators — that match the expressive power of the standard library.

---

## Exercises

1. **Type-level `std::is_any_of`** — Write a variadic trait `is_any_of<T, Ts...>` that derives from `std::true_type` if `T` matches any type in `Ts...`, and `std::false_type` otherwise.

2. **Tuples of references** — Implement a simplified version of `std::forward_as_tuple`, which creates a `tuple` of forwarding references to its arguments.

3. **Tuple zip** — Write a function `tuple_zip` that takes two tuples of equal length and returns a tuple of `std::pair`s, each pair containing corresponding elements from the two input tuples.

4. **Apply to vector** — Implement a function that takes a tuple of functions and a single argument, and returns a tuple of the results of applying each function to the argument. For example, `apply_all(std::make_tuple(square, negate), 5)` returns `(25, -5)`.

5. **Flat tuple from scratch** — Build a flat tuple using the `tuple_element_holder` approach described in this chapter. Ensure it supports `std::get`, `std::tuple_size`, and `std::tuple_element` so that structured bindings work.
