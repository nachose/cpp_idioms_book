# Chapter 15: Type Manipulation

## Type manipulation utilities

Template metaprogramming in C++ is built on the ability to inspect, classify, and transform types at compile time. Type manipulation utilities are the atoms of this metaprogramming model: they take existing types as input and produce new, modified types as output, all without any runtime cost. Understanding them is essential because every higher-level technique in template metaprogramming—from SFINAE to policy-based design to concepts—ultimately composes these primitive operations.

The mental model is that of a compile-time function: given a type `T`, produce a related type `U`. The standard library exposes these operations as class templates that hold a `type` member alias, making them usable with `typename` in dependent contexts. The most fundamental are the `<type_traits>` header's transformation traits.

### Removing and adding qualifiers

The simplest type transformations strip or apply `const`, `volatile`, or reference qualifiers. Consider what happens when you write a template that receives types through generic code:

```cpp
template <typename T>
void process(T&& value) {
    // T might be int, int&, const int, const int&, etc.
    using CleanT = typename std::remove_cv<
        typename std::remove_reference<T>::type
    >::type;
    // CleanT is always int
}
```

The motivation for `remove_reference` and `remove_cv` arises from template argument deduction. A forwarding reference parameter `T&&` causes `T` to deduce to `int&` when passed an lvalue, or to `int` when passed an rvalue. Without stripping these qualifiers, any metaprogram that tries to compare or store the type would see all these variations as distinct, even though the underlying value type is the same.

C++14 introduced `_t` aliases that eliminate the `::type` suffix, making the code more readable:

```cpp
using CleanT = std::remove_cv_t<std::remove_reference_t<T>>;
```

The complementary `add_*` traits work in reverse. `std::add_const<int>` yields `const int`, and `std::add_lvalue_reference<int>` yields `int&`. These are most useful when building generic wrappers that must preserve or amplify the qualifiers of their argument types.

### Decay for function arguments

The `std::decay` trait models the type transformations that occur when an argument is passed by value to a function. Array-to-pointer decay and function-to-pointer decay are applied, and top-level cv-qualifiers are removed. This is what makes `std::decay_t<const char[4]>` produce `const char*`.

```cpp
// std::decay applies: array-to-pointer, function-to-pointer, and cv-removal
static_assert(std::is_same_v<
    std::decay_t<const char[4]>,
    const char*
>);
```

The mental model is that of "what type would this be if I passed it by value to a function?" This makes `decay` the natural choice when storing values in containers from a forwarding context, or when normalizing types before hashing or comparison.

### Conditional type selection

`std::conditional` is the compile-time ternary operator. Given a compile-time boolean and two types, it selects one or the other:

```cpp
template <typename T>
using SafeReference = typename std::conditional<
    std::is_fundamental<T>::value,
    T,
    const T&
>::type;
```

This pattern is widespread in generic libraries: when a trait is true, use one type; otherwise, use another. The limitation is that both branches must be valid types—`conditional` does not short-circuit, so both alternatives are instantiated even though only one is used. This can lead to hard errors in code that relies on SFINAE.

### Integral constants and type classification

The foundational building block for all type traits is `std::integral_constant`, which wraps a compile-time constant value as a type. The familiar `std::true_type` and `std::false_type` are simply aliases for `integral_constant<bool, true>` and `integral_constant<bool, false>`.

```cpp
template <typename T>
struct is_integral : std::false_type {};

template <>
struct is_integral<int> : std::true_type {};

template <>
struct is_integral<long> : std::true_type {};
```

Making a trait inherit from `true_type` or `false_type` rather than directly defining a `static constexpr bool value` is important because it enables tag dispatch: a function can accept `std::true_type` or `std::false_type` as a parameter, and overload resolution selects the appropriate version at compile time.

The standard library provides dozens of classification traits: `is_void`, `is_pointer`, `is_array`, `is_class`, `is_enum`, `is_function`, `is_member_pointer`, `is_reference`, and `is_object`, among others. Each is a specialization of `integral_constant` and can be used both for `::value` and as a dispatch tag.

### Combining traits: conjunction, disjunction, negation

When conditions grow complex, composing individual traits becomes unwieldy. C++17 introduced `std::conjunction`, `std::disjunction`, and `std::negation` to combine boolean traits:

```cpp
template <typename T>
using is_regular = std::conjunction<
    std::is_default_constructible<T>,
    std::is_copy_constructible<T>,
    std::is_copy_assignable<T>,
    std::is_destructible<T>
>;
```

`conjunction` short-circuits: once a trait evaluates to `false_type`, evaluation stops. This matters because later traits may be invalid for types that fail earlier checks. `disjunction` similarly short-circuits on the first `true_type`. `negation` simply inverts the result.

### The void_t detection idiom

A powerful utility for writing custom traits is `void_t`, which maps any type to `void`. Its definition is trivial:

```cpp
template <typename...>
using void_t = void;
```

Despite its simplicity, `void_t` enables a detection pattern that tests whether an expression is valid for a given type. Combined with SFINAE, it lets you ask questions like "does this type have a member called `foo`?" without relying on compiler extensions:

```cpp
template <typename T, typename = void>
struct has_foo : std::false_type {};

template <typename T>
struct has_foo<T, void_t<decltype(std::declval<T>().foo())>> : std::true_type {};
```

The second partial specialization is only viable when the expression `std::declval<T>().foo()` is well-formed. `void_t` transforms the (potentially complex) decltype into `void`, matching the default template parameter. This two-step pattern—primary template with `void` default, partial specialization with `void_t<...>`—is the backbone of custom type detection in modern C++.

### Type list utilities

Beyond individual transformations, type manipulation extends to operations on lists of types. A type list is simply a variadic template:

```cpp
template <typename... Ts>
struct type_list {};
```

Operations on type lists—like appending, prepending, finding the index of a type, or removing duplicates—are implemented through recursive template instantiations or, more efficiently in C++17, through fold expressions and constexpr if.

```cpp
// Length of a type list
template <typename> struct type_list_size;

template <typename... Ts>
struct type_list_size<type_list<Ts...>>
    : std::integral_constant<std::size_t, sizeof...(Ts)> {};

template <typename List>
inline constexpr std::size_t type_list_size_v = type_list_size<List>::value;
```

The key insight is that type lists are purely compile-time constructs. They do not correspond to any runtime data. Their purpose is to enable metaprogramming operations like iterating over template arguments, selecting types by index, or generating combinations of types for testing.

### Trade-offs and limits

Type manipulation utilities are zero-cost abstractions in the truest sense: they add no runtime instructions or memory overhead. However, they come with costs in other dimensions:

- **Compilation time**: Deeply nested type transformations can dramatically increase compilation time. Each `::type` alias triggers template instantiation, and the compiler must recursively process the chain of dependent types.

- **Diagnostic quality**: When a type manipulation fails—for example, attempting `remove_pointer` on a non-pointer type—the resulting error messages from template instantiation backtraces can be hundreds of lines long. Concepts in C++20 alleviate this by providing better error messages and early failure.

- **Mental overhead**: Reading code that chains multiple type transformations requires significant mental context switching. The `_t` aliases help, but deeply nested metaprograms remain harder to reason about than equivalent runtime code.

- **Limited vocabulary**: The standard library provides only the most commonly needed transformations. For specialized manipulations—such as replacing all occurrences of one type within a nested template—you must build your own utilities using the primitives described here.

Despite these limits, type manipulation utilities form the bedrock of all template metaprogramming in C++. Every technique in the chapters that follow—compile-time dispatch, recursive template computation, policy selection, and concept definition—builds on the ability to transform and classify types at compile time without runtime cost.

---

## Type introspection and traits

If type manipulation utilities transform types, type introspection traits ask questions about them. Introspection is the compile-time equivalent of `instanceof` or `typeof` in dynamic languages: given a type `T`, determine whether it has a certain property, supports a certain operation, or relates to another type in a specific way. The results are compile-time constants that guide template instantiation, overload resolution, and static assertions.

The mental model is that of a compile-time query function: `is_pointer<T>` asks "is `T` a pointer type?" and returns either `true_type` or `false_type`. More complex queries compose these atomic questions using the conjunction, disjunction, and negation utilities from the previous section. The entire type trait library in `<type_traits>` is built on this principle: each trait inherits from `integral_constant<bool, ...>`, making every answer available both as a `::value` and as a type suitable for tag dispatch.

### Classification traits

The first category of introspection traits classifies the fundamental nature of a type. These answer binary questions about what category a type belongs to in the C++ type system:

```cpp
static_assert(std::is_void_v<void>);
static_assert(std::is_null_pointer_v<decltype(nullptr)>);
static_assert(std::is_integral_v<int>);
static_assert(std::is_floating_point_v<double>);
static_assert(std::is_pointer_v<const char*>);
static_assert(std::is_array_v<int[4]>);
static_assert(std::is_class_v<std::string>);
static_assert(std::is_enum_v<enum class Color { Red }>);
static_assert(std::is_union_v<union MyUnion { int i; double d; }>);
```

These traits map straight to the C++ type taxonomy. `is_arithmetic` is `is_integral || is_floating_point`, and `is_fundamental` adds `is_void` and `is_null_pointer`. The hierarchy matters because it enables generic code to branch on type category: for example, an algorithm might use `memcpy` for trivially copyable types but element-wise copy for class types.

Understanding the precise boundaries of each category is important. `is_class` is true for `struct` and `class` types, including those that are also standard-layout or trivially copyable, but false for `union` and `enum`. `is_enum` is true for both scoped and unscoped enums but false for `enum class` underlying types like `int`. These distinctions directly affect how generic code can manipulate objects of unknown type.

### Property traits

Beyond category, introspection traits query specific properties of a type:

```cpp
static_assert(std::is_const_v<const int>);
static_assert(std::is_trivially_copyable_v<int>);
static_assert(std::is_trivially_destructible_v<std::string_view>);
static_assert(std::is_polymorphic_v<Base>);
static_assert(std::is_abstract_v<AbstractBase>);
static_assert(std::is_final_v<FinalClass>);
```

Property traits are useful for optimization and safety checks. `is_trivially_copyable` tells you whether it is safe to copy the object with `memcpy`. `is_polymorphic` tells you whether the type has a vtable. `is_abstract` tells you whether the type can be instantiated.

A common pattern is using these in static assertions to enforce constraints:

```cpp
template <typename T>
void optimized_copy(T* dst, const T* src, std::size_t count) {
    static_assert(std::is_trivially_copyable_v<T>,
                  "optimized_copy requires trivially copyable types");
    std::memcpy(dst, src, count * sizeof(T));
}
```

The static assertion provides a clear error message when the template is instantiated with an unsuitable type, rather than producing a confusing template backtrace from `memcpy` or—worse—silently invoking undefined behavior.

### Relationship traits

Some of the most powerful introspection traits query relationships between two types:

```cpp
static_assert(std::is_same_v<int, int>);
static_assert(std::is_base_of_v<Base, Derived>);
static_assert(std::is_convertible_v<Derived*, Base*>);
static_assert(std::is_assignable_v<int&, long>);
static_assert(std::is_constructible_v<std::string, const char*>);
```

`is_same` is the strictest relationship: two types must be identical. `is_base_of` checks inheritance, including both public and private bases. `is_convertible` checks whether an implicit conversion exists, which is broader than inheritance and includes user-defined conversion operators.

`is_assignable` and `is_constructible` are the most general: they check whether an expression `declval<LHS>() = declval<RHS>()` is well-formed. Their variants—`is_trivially_assignable`, `is_nothrow_assignable`—also check exception guarantees. Beware that these traits evaluate the expression purely syntactically; they do not check semantic requirements like postconditions.

### Using decltype and std::declval for expression introspection

The most flexible introspection tool does not come from `<type_traits>` at all. It is the combination of `decltype` and `std::declval`, which together let you ask "what would be the type of this expression without actually executing it?"

```cpp
using result_type = decltype(std::declval<A>() + std::declval<B>());
```

`std::declval<T>()` is a function that is never defined; it exists only to be used in unevaluated contexts like `decltype`, `sizeof`, and `noexcept`. It produces an rvalue reference to `T`, making it possible to ask about the return type of an expression even when `T` has no default constructor or cannot be instantiated at all.

This pattern is the foundation of modern detection idioms. Combined with `void_t` and SFINAE, it enables introspection that goes far beyond what the standard trait library provides. The `std::is_detected` utility (proposed but not yet standardized; available in Library Fundamentals TS v2) generalizes this into a composable form:

```cpp
// Check if type T has a .size() member that returns something convertible to size_t
template <typename T>
using size_type = decltype(std::declval<T>().size());

template <typename T>
using has_size = std::is_detected_convertible<std::size_t, size_type, T>;
```

Without the detection idiom, you would need a separate partial specialization for each expression you want to test. The detection pattern turns this into a single, reusable utility.

### Invocable traits

C++17 introduced `std::is_invocable` and its variants, which check whether a callable can be invoked with given argument types:

```cpp
template <typename F, typename... Args>
using is_callable = std::is_invocable<F, Args...>;

void example(F&& f, auto&&... args) {
    static_assert(std::is_invocable_v<decltype(f), decltype(args)...>,
                  "Function cannot be called with these arguments");
    std::invoke(std::forward<F>(f), std::forward<decltype(args)>(args)...);
}
```

`is_invocable` is more powerful than it may first appear. It works with function pointers, member function pointers (including the implied `this` parameter), lambdas, and `std::function`. `is_nothrow_invocable` additionally checks the noexcept specification of the call. The `invoke_result` trait retrieves the return type of the invocation.

These traits are essential for writing generic wrappers that must forward calls while preserving type safety. A logging wrapper, for example, can inspect the invocable's signature at compile time and produce a static error if the arguments do not match.

### The _v helper aliases

Every standard trait that provides a `::value` member has a corresponding `_v` alias template (C++14 and later):

```cpp
template <typename T>\ninline constexpr bool is_integral_v = std::is_integral<T>::value;
```

The `_v` suffix may seem trivial, but it significantly improves readability. Compare:

```cpp
// Without _v
if constexpr (std::is_integral<T>::value) { /* ... */ }

// With _v
if constexpr (std::is_integral_v<T>) { /* ... */ }
```

More importantly, `_v` aliases avoid the `typename` keyword entirely and make compositions with `conjunction`/`disjunction` read more naturally. Every trait discussed in this section has a `_v` counterpart, and you should prefer them for all new code.

### Composing introspection for real-world constraints

Purely academic trait usage checks a single property. Real code composes multiple traits to express precise constraints. Consider a serialization function that requires its argument to be a non-polymorphic, trivially copyable class type:

```cpp
template <typename T>
using is_plain_data = std::conjunction<
    std::is_class<T>,
    std::is_trivially_copyable<T>,
    std::negation<std::is_polymorphic<T>>
>;

template <typename T>
void serialize_binary(const T& value) {
    static_assert(is_plain_data<T>::value,
                  "Binary serialization requires a plain data type");
    write_bytes(&value, sizeof(T));
}
```

This composition illustrates the typical pattern: start with a category check (`is_class` to exclude primitives and pointers), add a property check (`is_trivially_copyable` for safety), and then exclude undesirable subcategories (`is_polymorphic` because virtual tables complicate binary layout).

### Trade-offs and limits

Type introspection happens entirely at compile time with zero runtime overhead. The costs, however, are not zero:

- **Compiler resource usage**: Each static_assert and each trait instantiation consumes compiler resources. Hundreds of trait evaluations in a single translation unit are typical, but thousands in a deeply nested template library can slow compilation noticeably.

- **Limited expressiveness**: Standard traits can only query what the standard committee has anticipated. You cannot directly ask "does this type have a public member named `data` that is a contiguous iterator?" without building the detection idiom yourself. C++20 concepts alleviate this by providing a language-level syntax for expressing type constraints, but the introspection machinery remains trait-based underneath.

- **False positives and negatives**: Trait results are conservative by necessity. `is_trivially_copyable` may be true for a type that has mutable state requiring deep copy, and `is_nothrow_constructible` may be true for a function that the compiler can prove will not throw, even if the author intended it to be noexcept. Semantic intent is invisible to the type system.

- **ABI implications**: Adding or removing traits from a type (such as declaring a virtual function, which changes `is_polymorphic`) can change the trait's value across translation units, potentially causing ODR violations if not consistently defined.

Type introspection traits, despite these limits, are the lens through which template metaprograms understand their inputs. Without them, generic code would be blind to the properties of the types it operates on, and every template would have to assume the worst case. The ability to inspect types at compile time is what makes the C++ template system more than a simple macro processor: it gives templates the power to adapt their behavior to the characteristics of their arguments while maintaining zero-cost abstraction guarantees.

## Template specialization strategies

Template specialization is the mechanism by which a generic template definition is replaced with an alternative definition for specific template arguments. It is the foundation of all type-directed metaprogramming in C++. Every technique in this book that selects behavior based on types—from `enable_if` to tag dispatch to policy selection—ultimately relies on the specialization rules of the language.

The mental model distinguishes three levels of template definition. The **primary template** provides the default implementation. **Explicit specializations** (also called full specializations) provide an implementation for a specific set of template arguments, matching exactly. **Partial specializations** provide an implementation for a family of arguments that satisfy a certain pattern, available only for class templates and variable templates—not for function templates. This asymmetry between class and function templates is one of the most important constraints to understand about the specialization system.

Understanding why function templates cannot be partially specialized is essential. The language disallows it because function template overloading already provides a more flexible mechanism: when multiple function templates match a call, the compiler selects the best match through overload resolution rather than specialization ordering. This design avoids the complex partial ordering rules that would be needed for function template partial specializations. A function template with the same name but different template parameters is a separate overload, not a partial specialization, and overload resolution handles the selection.

### Primary template design

The primary template serves as the fallback. The skill in template specialization lies in designing this fallback so that specializations are natural to write and express. Two principles guide effective primary template design.

First, the primary template should be as minimal as possible. If a type trait asks a question, the primary template should default to the conservative answer (typically `false_type`). This makes specialization additive rather than subtractive: you specialize for types that have the property, and everything else automatically gets the safe default.

```cpp
// Primary template: conservative default
template <typename T, typename = void>
struct has_serialize : std::false_type {};

// Specialization: types that support serialize()
template <typename T>
struct has_serialize<T, std::void_t<decltype(std::declval<T>().serialize())>>
    : std::true_type {};
```

Second, the primary template's interface determines what specializations must provide. If the primary template defines member functions, every specialization must define them. If the primary template is completely empty—providing only a `type` alias or a `value` constant—specializations need only provide that single member.

```cpp
// Primary template: no members, just a declaration
template <typename T>
struct Storage;

// Specialization for int
template <>
struct Storage<int> {
    int data;
    void serialize() { /* ... */ }
};

// Specialization for double
template <>
struct Storage<double> {
    double data;
    void serialize() { /* ... */ }
};
```

An empty primary template enforces that every specialization defines its own interface independently. This is useful when specializations have fundamentally different layouts, but it also means there is no shared contract enforced by the compiler.

### Full (explicit) specialization

A full specialization provides an implementation for a specific, concrete set of template arguments:

```cpp
template <typename T>
struct TypeInfo {
    static constexpr const char* name = "unknown";
};

template <>
struct TypeInfo<int> {
    static constexpr const char* name = "int";
};

template <>
struct TypeInfo<double> {
    static constexpr const char* name = "double";
};
```

Full specializations are all-or-nothing: they replace the entire template definition. This makes them suitable when the specialized version has a completely different implementation, but unsuitable when only a small aspect of the behavior needs to change.

For function templates, full specialization works but interacts with overload resolution in subtle ways. A full specialization of a function template does not participate in overload resolution; it is selected only after overload resolution chooses the primary template. This means that a full specialization can never be a better match than another overload, which confuses many developers.

```cpp
template <typename T>
void process(T value);            // (1) primary template

template <>
void process<int>(int value);     // (2) explicit specialization of (1)

void process(int value);          // (3) non-template overload

// process(42) calls (3), not (2), because (3) is preferred over (1)
```

The preferred strategy when function-level specialization is needed is to delegate to a class template that performs the specialization:

```cpp
template <typename T>
struct ProcessImpl {
    static void apply(T value) { /* generic */ }
};

template <>
struct ProcessImpl<int> {
    static void apply(int value) { /* int-specific */ }
};

template <typename T>
void process(T value) {
    ProcessImpl<T>::apply(value);
}
```

This pattern—sometimes called the "specialization helper" or "shim" pattern—works because class templates support both full and partial specialization, and the function template simply forwards to the class.

### Partial specialization

Partial specialization is the most powerful tool in the specialization toolbox. A partial specialization matches a subset of possible template arguments based on a pattern, rather than a single concrete type.

```cpp
// Primary template
template <typename T>
struct IsPointer : std::false_type {};

// Partial specialization: matches any pointer type
template <typename T>
struct IsPointer<T*> : std::true_type {};
```

The pattern can involve multiple template parameters, nested templates, and non-type parameters:

```cpp
// Primary template
template <typename T, typename U>
struct IsSame : std::false_type {};

// Partial specialization: matches when both types are the same
template <typename T>
struct IsSame<T, T> : std::true_type {};

// Partial specialization: match std::vector of any type
template <typename T, typename A>
struct IsVector<std::vector<T, A>> : std::true_type {};
```

The compiler matches partial specializations through a process called partial ordering. When multiple partial specializations match a given set of arguments, the compiler selects the most specialized one—the one that accepts a strict subset of the arguments accepted by the others. If no specialization is more specialized than the others, the program is ambiguous and compilation fails.

```cpp
template <typename T>
struct Foo;              // primary

template <typename T>
struct Foo<T*> {};       // (1) matches pointers

template <typename T>
struct Foo<const T> {};  // (2) matches const-qualified

// Foo<const int*> matches both (1) and (2) — ambiguous!
```

Understanding partial ordering is essential for writing correct specialization hierarchies. The rules are complex, but the practical intuition is: if a type that matches specialization A can always be transformed to also match specialization B, then B is more general and A is more specialized. The compiler prefers the more specialized one.

### Specializing for type categories with enable_if

Partial specialization works naturally with `enable_if` to specialize for types that satisfy a boolean condition:

```cpp
template <typename T, typename = void>
struct SmartPrinter {
    static void print(const T& value) {
        std::cout << value;
    }
};

// Specialization for types that have a .toString() member
template <typename T>
struct SmartPrinter<T, std::enable_if_t<
    std::is_detected_v<has_toString, T>
>> {
    static void print(const T& value) {
        std::cout << value.toString();
    }
};

// Specialization for iterable containers
template <typename T>
struct SmartPrinter<T, std::enable_if_t<
    std::is_detected_v<has_begin_end, T> &&
    !std::is_same_v<T, std::string>
>> {
    static void print(const T& container) {
        std::cout << "[";
        for (const auto& elem : container) {
            SmartPrinter<decltype(elem)>::print(elem);
        }
        std::cout << "]";
    }
};
```

This pattern uses the `void_t` technique seen in the previous section: the primary template takes a second defaulted `void` parameter, and partial specializations constrain it by substituting `enable_if_t<condition>` in place of `void`. Only when the condition is true does the substitution succeed and the specialization becomes viable.

### Tag dispatch as an alternative

When specialization is needed for function templates, tag dispatch often provides a cleaner solution than the helper-class pattern. Instead of specializing a class, you define overloads that accept different tag types:

```cpp
struct integral_tag {};
struct floating_tag {};
struct other_tag {};

template <typename T>
void process_impl(T value, integral_tag) {
    std::cout << "integral: " << value << "\n";
}

template <typename T>
void process_impl(T value, floating_tag) {
    std::cout << "floating: " << value << "\n";
}

template <typename T>
void process_impl(T value, other_tag) {
    std::cout << "other\n";
}

template <typename T>
void process(T value) {
    using tag = std::conditional_t<
        std::is_integral_v<T>, integral_tag,
        std::conditional_t<
            std::is_floating_point_v<T>, floating_tag,
            other_tag
        >
    >;
    process_impl(value, tag{});
}
```

The advantage of tag dispatch over specialization helpers is that it uses ordinary overload resolution, which is well-understood and produces better compiler diagnostics. The disadvantage is that the dispatch logic is explicit at the call site rather than implicit in the template matching rules.

### if constexpr as a simpler alternative (C++17)

For many specialization needs, C++17's `if constexpr` eliminates the need for separate specializations entirely. Instead of defining multiple template definitions, you define one and branch at compile time:

```cpp
template <typename T>
void process(T value) {
    if constexpr (std::is_integral_v<T>) {
        std::cout << "integral: " << value << "\n";
    } else if constexpr (std::is_floating_point_v<T>) {
        std::cout << "floating: " << value << "\n";
    } else {
        std::cout << "other\n";
    }
}
```

This is dramatically simpler than any specialization strategy. The compiler discards the non-taken branches at compile time, so there is no runtime overhead. However, `if constexpr` works within a single function body; it cannot change the type of data members or the set of member functions defined. When the specialization must affect the structure of a type (for example, adding or removing data members based on a trait), class template partial specialization remains the only option.

### Choosing the right strategy

The decision tree for selecting a specialization strategy follows the nature of what needs to change:

| Goal | Strategy |
|---|---|
| Change return type or behavior per type | `if constexpr` (C++17) |
| Add/remove members per type | Class template partial specialization |
| Select function overload per category | Tag dispatch |
| Hide implementation details from users | Helper class with full specialization |
| Conditionally enable/disable an overload | `enable_if` / concepts |
| Customize behavior for user-defined types | Traits class specialization |

`if constexpr` should be the first consideration because it is the simplest and most readable. Partial specialization should be used when the type's structure must change. Tag dispatch should be used when working with function templates in pre-C++17 code or when the dispatch criteria are complex. Full specialization of function templates should be avoided in favor of any of the alternatives.

### Trade-offs and limits

Template specialization strategies differ in their maintainability, diagnostic quality, and compilation cost:

- **`if constexpr`** produces the best diagnostics because the compiler sees a single function with clear branches. It has the lowest compilation cost. Its limits are that it cannot change the structure of a class or the set of available member functions.

- **Partial specialization** is the most flexible but has the highest complexity. Partial ordering rules are subtle, and mistakes can produce silent fallback to the primary template or hard-to-debug ambiguity errors. Compilation time increases with the number of specializations and the depth of the template matching.

- **Tag dispatch** separates concerns cleanly but requires manual tag selection at each call site. It scales poorly when many category dimensions interact, because the number of tags grows combinatorially.

- **Full specialization of function templates** should generally be avoided. It violates the principle of least surprise because specializations do not participate in overload resolution. Every case where a function template specialization seems necessary can be better served by one of the other strategies.

The broader trade-off is between compile-time selection and runtime selection. Template specialization strategies push decisions to compile time, which is almost always the right choice for performance. But compile-time selection requires knowing all types at compile time, which is impossible when types are determined dynamically—for example, when loading plugins or deserializing polymorphic objects. In those cases, runtime dispatch through virtual functions or type-erased wrappers is the appropriate tool, and the specialization strategies discussed in this section do not apply.

## Template Argument Deduction

Template argument deduction is the mechanism by which the compiler determines the template parameters of a function or class template from the types of its arguments — without the programmer explicitly writing them. It is the engine behind almost every convenient C++ feature: `auto`, `std::make_unique`, range-for, generic lambdas, and CTAD (Class Template Argument Deduction). Understanding its rules is essential because it determines what a template *sees*, and therefore how it behaves.

### How deduction works: the compiler's view

When you write `f(expr)`, the compiler inspects what `T` must be for the function parameter type to match the argument type:

```cpp
template <typename T>
void f(T arg);

f(42);        // T = int
f(3.14);      // T = double
f("hello");   // T = const char*
```

The compiler builds a system of type equations: the parameter type is `T`, the argument type is `int`, therefore `T = int`. This matching is structural — it considers the form of the parameter, not just its raw type.

When the parameter is a reference, deduction must account for the reference:

```cpp
template <typename T>
void g(T& arg);

int x = 42;
const int cx = 42;

g(x);         // T = int,        arg is int&
g(cx);        // T = const int,  arg is const int&
g(42);        // Error: cannot bind int& to rvalue
```

The key observation: when the parameter is `T&`, the compiler strips the reference from the argument type and matches the referenced type against `T`. A non-const lvalue reference parameter cannot bind to a const lvalue or to an rvalue. This is the same rule as function parameter binding — template deduction does not relax it.

### Forwarding references and reference collapsing

A forwarding reference — written `T&&` where `T` is a deduced template parameter — has special deduction rules:

```cpp
template <typename T>
void forwarder(T&& arg);

int x = 42;
forwarder(x);       // T = int&,  arg is int&      (lvalue)
forwarder(42);      // T = int,   arg is int&&     (rvalue)
```

When the argument is an lvalue of type `A`, `T` deduces to `A&`. When the argument is an rvalue, `T` deduces to `A`. The difference is critical: in the lvalue case, the parameter becomes `int& &`, which collapses to `int&` per the reference collapsing rules.

Reference collapsing is the set of four rules that determine what happens when a reference to a reference appears:

| Original type | Collapsed to |
|---------------|-------------|
| `T& &`  | `T&`  |
| `T& &&` | `T&`  |
| `T&& &` | `T&`  |
| `T&& &&`| `T&&` |

The rule is simple: if either reference is an lvalue reference, the result is an lvalue reference. Only when both are rvalue references does the result remain an rvalue reference.

This is why `auto&&` works as a universal reference in range-for:

```cpp
for (auto&& element : container) {
    // element binds to both lvalues and rvalues from the container
}
```

The forwarding reference pattern, combined with `std::forward`, produces what is called *perfect forwarding* — the ability to forward an argument's value category unchanged:

```cpp
template <typename T>
void wrapper(T&& arg) {
    target(std::forward<T>(arg));
}
```

When `T = int&`, `std::forward<T>` returns an lvalue reference. When `T = int`, it returns an rvalue reference. The original value category is preserved through the forwarding chain.

### Array and function decay

When a function parameter is `T` (by value), arrays and functions decay to pointers, just as they do in non-template C:

```cpp
template <typename T>
void by_value(T arg);

template <typename T>
void by_reference(T& arg);

int arr[5];
by_value(arr);        // T = int*,  arg is int*  (array decays)
by_reference(arr);    // T = int[5], arg is int(&)[5]  (no decay)
```

The by-reference version preserves the complete array type, including its size. This is the technique behind `std::size` and C++17's `std::data` — they take a reference to an array so they can deduce its extent:

```cpp
template <typename T, std::size_t N>
constexpr std::size_t array_size(T (&)[N]) noexcept {
    return N;
}
```

Function pointers follow the same pattern:

```cpp
void func(double);

by_value(func);       // T = void(*)(double)
by_reference(func);   // T = void(&)(double)
```

### CV-qualifier deduction

When the parameter is `T` (by value), top-level `const` and `volatile` on the argument are ignored during deduction — an `int` and a `const int` produce the same `T = int`:

```cpp
template <typename T>
void by_value(T arg);

const int cx = 42;
by_value(cx);         // T = int (const is stripped)

template <typename T>
void by_const_ref(const T& arg);

by_const_ref(cx);     // T = int,  arg is const int&
```

When the parameter is `const T&`, the `const` is part of the parameter type, not the deduced template argument. `T` deduces to the non-const type, and the function parameter becomes `const T&`.

This distinction matters when using `std::is_same` or other type traits inside the template:

```cpp
template <typename T>
void inspect(T arg) {
    static_assert(std::is_same_v<T, int>);  // succeeds
    static_assert(std::is_const_v<T>);      // false — const was stripped
}
```

### Non-deduced contexts

Certain positions in a template parameter are *non-deduced*: the compiler will not attempt to deduce `T` from them, and the template argument must be provided explicitly or taken from a default. The most common non-deduced contexts are:

**The left side of `::`**

```cpp
template <typename T>
void f(typename T::value_type arg);  // T cannot be deduced from arg
```

The compiler cannot reverse-engineer `T` from `T::value_type` because many types may have a member `value_type` the same type as the argument. The pattern is used when the intent is for `T` to be deduced from other parameters and then used to qualify this parameter.

**A nested template parameter**

```cpp
template <typename T>
void g(std::vector<T> arg);  // T is deduced from the vector element type
```

This *is* a deduced context — `T` is not nested inside `std::vector` as a non-deduced position; it is a template argument of `std::vector`. The compiler can deduce `T` from `std::vector<int>` in the argument. But:

```cpp
template <typename T>
void h(typename std::vector<T>::iterator it);  // T is NOT deduced
```

Here `T` is inside a qualified name (`std::vector<T>::iterator`), making it non-deduced.

**Non-type parameters that depend on a deduced type**

```cpp
template <typename T, T value>
void f();   // value cannot be used to deduce T
```

`T` cannot be deduced from the value of a non-type parameter.

**Default arguments**

Default template arguments are not used for deduction:

```cpp
template <typename T = int>
void f(T arg);

f(42.0);   // T = double from deduction, NOT int from default
```

The default is used only when deduction fails or when the template argument is explicitly omitted and deduction does not apply (which cannot happen for function templates, but can for class templates).

### Class Template Argument Deduction (CTAD)

C++17 introduced deduction guides that allow class template arguments to be deduced from constructor arguments:

```cpp
template <typename T>
class Box {
public:
    Box(T value) : value_(value) {}
private:
    T value_;
};

Box b(42);       // Box<int>, CTAD deduces T = int
Box b2(3.14);    // Box<double>, CTAD deduces T = double
```

CTAD works through *implicit deduction guides*: for each constructor of the class template, the compiler generates a synthetic function template that mirrors the constructor's signature and deduces the template parameters. The standard library examples include `std::pair`, `std::tuple`, and `std::optional`:

```cpp
std::pair p(1, 2.0);                  // std::pair<int, double>
std::tuple t(1, "hello", 3.14);       // std::tuple<int, const char*, double>
std::optional o(42);                  // std::optional<int>
std::mutex mtx;
std::lock_guard lk(mtx);              // std::lock_guard<std::mutex>
```

**Explicit deduction guides** override the implicit ones:

```cpp
template <typename T>
class StringOrNumber {
public:
    StringOrNumber(const T& val);
};

// Deduction guide: const char* constructs StringOrNumber<std::string>
StringOrNumber(const char*) -> StringOrNumber<std::string>;

StringOrNumber s("hello");  // StringOrNumber<std::string>, not StringOrNumber<const char*>
StringOrNumber n(42);       // StringOrNumber<int>, uses implicit guide
```

Deduction guides are function-like declarations with a trailing return type that specifies which class specialization the deduced arguments should produce.

**Limitations of CTAD**:

CTAD does not work when the class template has no constructors whose parameter types model the template parameters:

```cpp
template <typename T>
class Wrapper {
public:
    Wrapper(typename T::value_type val);  // T cannot be deduced
};

// Wrapper w(42);  // Error: T is non-deduced
```

CTAD also fails for aggregates before C++20. In C++17, aggregate types with user-provided constructors were needed for CTAD. C++20 added *aggregate CTAD*:

```cpp
template <typename T>
struct Point { T x; T y; };

Point p{1, 2};   // C++20: Point<int>, aggregate CTAD works
```

### `auto` and `decltype(auto)` deduction

`auto` uses the same rules as template argument deduction, with one crucial difference: `auto` in a declaration behaves as if it were the parameter of an implicit function template. Thus:

```cpp
auto x = 42;          // auto = int, x is int
const auto& rx = x;   // auto = int, rx is const int&
auto&& uref = x;      // auto = int&, uref is int& (forwarding reference)
auto&& uref2 = 42;    // auto = int,  uref2 is int&&
```

The forwarding reference deduction applies to `auto&&` — it is the same `T&&` pattern applied to the implicit template parameter.

`decltype(auto)` differs from `auto` in one important way: it deduces the type using `decltype` of the initializer expression rather than template argument deduction rules. This means:

```cpp
int x = 42;
int& ref = x;

auto a = ref;              // a is int (auto strips reference)
decltype(auto) da = ref;   // da is int& (decltype(ref) is int&)
```

The difference is critical when writing forwarding wrappers:

```cpp
template <typename F, typename... Args>
decltype(auto) invoke(F&& f, Args&&... args) {
    return std::invoke(std::forward<F>(f), std::forward<Args>(args)...);
}
```

Using `decltype(auto)` preserves the value category of the return value — if `std::invoke` returns an lvalue reference, `decltype(auto)` deduces to `int&` rather than `int`. Using `auto` would copy the result.

### Common deduction pitfalls

**Pitfall 1: initializer lists are not deduced**

```cpp
template <typename T>
void f(T arg);

f({1, 2, 3});   // Error: cannot deduce T from initializer list
f(std::vector{1, 2, 3});  // OK: vector<int> deduced, T = vector<int>
```

Brace-enclosed initializer lists are a special case that does not participate in template argument deduction.

**Pitfall 2: `const` and reference confusion with forwarding**

```cpp
template <typename T>
void forwarder(T&& arg) {
    // T may be int, int&, const int, const int&, etc.
    target(std::forward<T>(arg));
}

const int cx = 42;
forwarder(cx);          // T = const int&,  arg is const int&
forwarder(std::move(cx)); // T = const int,  arg is const int&&
```

The forwarding reference preserves the const qualification. If `target` expects a non-const reference, the code will not compile — and correctly so, because forwarding a const argument as non-const would violate const-correctness.

**Pitfall 3: `auto` deducing to a pointer when an array was expected**

```cpp
auto arr = "hello";   // arr is const char*, not const char[6]
auto& arr_ref = "hello";  // arr_ref is const char(&)[6]
```

The decay rule applies to `auto` by value the same way it applies to `T` by value.

**Pitfall 4: overload resolution and forwarding references**

A forwarding reference `T&&` is a greedy match — it accepts any argument, lvalue or rvalue. When overloaded with a `const T&` version:

```cpp
template <typename T>
void process(T&& arg);          // (1)

template <typename T>
void process(const T& arg);     // (2)

int x = 42;
process(x);      // calls (1) with T = int&  (greedy)
process(42);     // calls (1) with T = int   (greedy)
const int cx = 42;
process(cx);     // calls (1) with T = const int&  (greedy)
```

Overload (1) is preferred for all non-const and const lvalues and for all rvalues because it is more specialized. Overload (2) is only selected when (1) is not viable. This is why constrained templates or SFINAE are needed to restrict forwarding references to specific use cases.

### Summary

Template argument deduction is the bridge between generic code and concrete types. The rules are not arbitrary — they mirror the language's existing parameter binding rules (reference collapsing, const stripping, array decay) and are consistent with how the compiler already treats function parameters. The key mental model:

- **By-value parameters** strip top-level qualifiers and decay arrays/functions.
- **By-reference parameters** preserve qualifiers and array bounds.
- **Forwarding references** encode the argument's value category in the deduced type.
- **Non-deduced contexts** prevent the compiler from guessing types that cannot be uniquely inferred.
- **CTAD** applies the same rules to class constructors, eliminating redundant type annotations.
- **`auto` and `decltype(auto)`** mirror template deduction with the same rules, except that `decltype(auto)` preserves the reference- and cv-qualification of the expression itself.

Understanding deduction is not academic — every `auto`, every `make_unique`, every range-for, and every generic lambda depends on these rules. Debugging a failed deduction almost always means figuring out which case the compiler could not match, and the rules in this section are the map for that search.
