# Chapter 10: Tag Dispatch and SFINAE

Tag dispatch and SFINAE are two fundamental techniques for achieving compile-time polymorphism in C++. Tag dispatch uses empty marker types (tags) to select between function overloads based on type properties. SFINAE (Substitution Failure Is Not An Error) enables template functions to be excluded from overload resolution based on type constraints. Together, these techniques form the backbone of modern C++ metaprogramming, allowing developers to write generic code that behaves differently depending on the properties of the types it operates on.

This chapter covers four related techniques: tag-based function overload resolution for selecting implementations based on type categories, enable_if and conditional compilation for template selection, type traits and detection idioms for introspecting type properties at compile time, and compile-time introspection for examining type characteristics and enabling or disabling code paths based on those characteristics.

## Tag-Based Function Overload Resolution

Tag dispatch is a technique where empty marker types (tags) are used to select between function overloads. The caller doesn't pass the tag directly; instead, the tag is derived from type properties. This enables compile-time selection of the most appropriate implementation based on type characteristics.

### Understanding Tag Dispatch

The core idea is simple but powerful: instead of writing one function that handles multiple cases, you write multiple overloaded functions, each tagged with a different type. A helper function extracts the appropriate tag from the type and forwards to the correct overload:

```cpp
// Tag types define categories
struct InputIteratorTag {};
struct ForwardIteratorTag : InputIteratorTag {};
struct BidirectionalIteratorTag : ForwardIteratorTag {};
struct RandomAccessIteratorTag : BidirectionalIteratorTag {};

// Implementation for each category
template<typename Iterator>
void advanceImpl(Iterator& it, typename std::iterator_traits<Iterator>::difference_type n,
                 RandomAccessIteratorTag) {
    it += n;  // Random access: O(1)
}

template<typename Iterator>
void advanceImpl(Iterator& it, typename std::iterator_traits<Iterator>::difference_type n,
                 BidirectionalIteratorTag) {
    if (n >= 0) {
        while (n--) ++it;
    } else {
        while (n++) --it;
    }
}

template<typename Iterator>
void advanceImpl(Iterator& it, typename std::iterator_traits<Iterator>::difference_type n,
                 InputIteratorTag) {
    // Only forward movement, O(n)
    while (n--) ++it;
}

// Dispatch function that selects the tag
template<typename Iterator>
void advance(Iterator& it, typename std::iterator_traits<Iterator>::difference_type n) {
    using tag = typename std::iterator_traits<Iterator>::iterator_category;
    advanceImpl(it, n, tag{});
}
```

The key insight is that `std::iterator_traits<Iterator>::iterator_category` is a tag type that identifies the iterator's capabilities. The `advance` function extracts this tag and passes it as a parameter to `advanceImpl`, which has overloads for each tag type. The compiler selects the most specific matching overload through standard overload resolution.

### Tag Hierarchy and Inheritance

The tag types form a hierarchy using inheritance. This allows more specific implementations to override less specific ones while maintaining a fallback:

```cpp
struct MonomorphicTag {};
struct PolymorphicTag : MonomorphicTag {};

template<typename T>
void processImpl(const T& obj, MonomorphicTag) {
    std::cout << "Processing monomorphic type\n";
}

template<typename T>
void processImpl(const T& obj, PolymorphicTag) {
    std::cout << "Processing polymorphic type\n";
}

template<typename T>
void process(const T& obj) {
    using Tag = std::conditional_t<std::is_polymorphic_v<T>,
                                    PolymorphicTag,
                                    MonomorphicTag>;
    processImpl(obj, Tag{});
}

class Base {};
class Derived : Base {};

int main() {
    process(42);           // MonomorphicTag - int is not polymorphic
    process(Base{});       // MonomorphicTag - not polymorphic
    process(Derived{});     // PolymorphicTag - has virtual functions (implicitly)
}
```

This pattern is used extensively in the standard library. `std::iterator_traits` defines the iterator category tags, `std::is_integral`, `std::is_floating_point` and similar type traits use this pattern, and `std::decay_t`, `std::remove_reference_t` use tag dispatch internally.

### Tag Dispatch for Type Categories

Tag dispatch naturally handles different type categories, similar to how the standard library distinguishes iterators:

```cpp
struct ArrayPointerTag {};
struct PointerTag {};
struct IteratorTag {};

template<typename T>
auto getDataImpl(T* ptr, ArrayPointerTag) -> T(*)[] {
    return ptr;
}

template<typename T>
T* getDataImpl(T* ptr, PointerTag) {
    return ptr;
}

template<typename T>
typename std::iterator_traits<T>::pointer getDataImpl(T& it, IteratorTag) {
    return std::addressof(*it);
}

template<typename T>
auto getData(T&& arg) {
    if constexpr (std::is_array_v<std::remove_reference_t<T>>) {
        using Tag = ArrayPointerTag;
    } else if constexpr (std::is_pointer_v<std::remove_reference_t<T>>) {
        using Tag = PointerTag;
    } else {
        using Tag = IteratorTag;
    }
    return getDataImpl(std::addressof(arg), Tag{});
}
```

This demonstrates how tag dispatch can select different implementations based on type categories—arrays, raw pointers, or iterators each get handled by their appropriate implementation.

### Tag Dispatch vs SFINAE

Tag dispatch and SFINAE solve similar problems but with different trade-offs. Tag dispatch requires explicit tag types but is more readable and supports inheritance-based fallbacks. SFINAE happens implicitly during template argument substitution but can produce confusing error messages. Many implementations use both: tag dispatch for the public interface and SFINAE internally.

### Tag Dispatch with Multiple Parameters

More complex dispatch scenarios involve multiple tag parameters:

```cpp
struct ValueCategory {};
struct ReferenceCategory {};
struct PointerCategory {};

template<typename T>
auto processImpl(const T& val, ValueCategory) -> void {
    std::cout << "Processing by value: " << val << "\n";
}

template<typename T>
auto processImpl(T& ref, ReferenceCategory) -> void {
    std::cout << "Processing by reference\n";
}

template<typename T>
auto processImpl(T* ptr, PointerCategory) -> void {
    std::cout << "Processing pointer: " << *ptr << "\n";
}

template<typename T>
void process(T&& arg) {
    using Td = std::remove_cvref_t<T>;

    if constexpr (std::is_pointer_v<Td>) {
        processImpl(arg, PointerCategory{});
    } else if constexpr (std::is_reference_v<Td>) {
        processImpl(arg, ReferenceCategory{});
    } else {
        processImpl(arg, ValueCategory{});
    }
}
```

This enables handling value, reference, and pointer types differently based on their category.

### Tag Dispatch in the Standard Library

The standard library uses tag dispatch extensively. The `std::advance` function uses iterator category tags to choose between O(1) and O(n) implementations. The `std::distance` function similarly chooses efficient algorithms based on iterator category. The `std::uninitialized_copy` and related algorithms use tag dispatch to select between trivial and non-trivial copy semantics.

### Summary

Tag dispatch is a powerful technique for compile-time function selection. It uses marker types (tags) to differentiate between type categories, with inheritance providing fallback behavior. The pattern is readable, produces clear error messages, and is widely used in the standard library. The key insight is that tag selection can be automated through type traits, making the dispatching transparent to users.

---

## Enable_if and Conditional Compilation

The `std::enable_if` family of utilities provides a mechanism for enabling or disabling template overloads based on compile-time conditions. Combined with SFINAE, this enables selective inclusion of function templates in overload resolution. This section explores `enable_if`, its variants, and common patterns for conditional compilation.

### Understanding std::enable_if

`std::enable_if` is a type trait that takes a boolean condition and a type. If the condition is true, it defines a member type equal to the second argument (defaulting to `void`). If false, the type is not defined, causing substitution failure:

```cpp
template<typename T>
typename std::enable_if<std::is_integral_v<T>, T>::type
add(T a, T b) {
    return a + b;  // Only enabled for integral types
}

add(1, 2);    // OK - int is integral
add(1.0, 2.0); // Error - double is not integral
```

The return type uses SFINAE: when `std::is_integral_v<T>` is false, the `enable_if` has no `type` member, causing substitution failure. The function is simply removed from the candidate set rather than causing a hard error.

### Enable_if in Multiple Locations

`enable_if` can appear in several positions within a function template: as a return type, as a parameter type, as a template parameter, or in the function body. Each has trade-offs:

```cpp
// Return type position (most common for SFINAE)
template<typename T>
typename std::enable_if_t<std::is_integral_v<T>, T>
square(T n) {
    return n * n;
}

// Template parameter position (useful for class templates)
template<typename T,
         typename = std::enable_if_t<std::is_integral_v<T>>>
class IntegralWrapper {
    T value;
};

// Additional parameter position (often used with default arguments)
template<typename T,
         typename std::enable_if_t<std::is_integral_v<T, int> = 0>>
void process(T value) {}

// In function body (less common, uses static_assert or if constexpr)
template<typename T>
void processBody(T value) {
    if constexpr (std::is_integral_v<T>) {
        // Implementation for integral types
    } else {
        static_assert(false, "Not supported");
    }
}
```

The return type position is often preferred for free functions because it keeps the constraint visible and is widely understood. The template parameter position is preferred for class templates and when multiple overloads need the same constraint.

### Enable_if_t and Void_t Shorthands

C++14 introduced `std::enable_if_t` as a shorthand for `typename std::enable_if<...>::type`, and C++17 added `std::void_t` for transforming types:

```cpp
// C++14 style
template<typename T>
std::enable_if_t<std::is_integral_v<T>, T> square(T n) {
    return n * n;
}

// Using void_t for more complex conditions
template<typename, typename = void>
struct has_value_type : std::false_type {};

template<typename T>
struct has_value_type<T, std::void_t<typename T::value_type>> : std::true_type {};

template<typename T>
std::enable_if_t<has_value_type<T>::value>
process(const T& container) {
    // Only enabled if T has value_type
}
```

The `void_t` trick transforms "has a member" into a boolean condition by causing substitution failure when the member doesn't exist.

### Conditional Overload Selection

A common pattern uses `enable_if` to provide multiple overloads with different constraints:

```cpp
template<typename T>
std::enable_if_t<std::is_integral_v<T>>
serialize(std::ostream& os, const T& value) {
    os << "int:" << value;
}

template<typename T>
std::enable_if_t<std::is_floating_point_v<T>>
serialize(std::ostream& os, const T& value) {
    os << "float:" << value;
}

template<typename T>
std::enable_if_t<std::is_class_v<T> && !std::is_pointer_v<T>>
serialize(std::ostream& os, const T& value) {
    os << "complex:" << value;  // Assumes operator<< exists
}

serialize(std::cout, 42);        // Calls integral overload
serialize(std::cout, 3.14);      // Calls floating point overload
serialize(std::cout, std::string("hello"));  // Calls class overload
```

This pattern enables completely different implementations for different type categories, with the compiler selecting the appropriate overload based on the constraints.

### Enable_if with Multiple Constraints

Complex constraints can combine multiple conditions using logical operators:

```cpp
// Using && for conjunction
template<typename T>
std::enable_if_t<std::is_integral_v<T> && (sizeof(T) >= 4), void>
processLargeInteger(T value) {
    // Only enabled for 4+ byte integers
}

// Using std::conjunction for cleaner code (C++17)
template<typename T>
std::enable_if_t<std::conjunction_v<std::is_integral<T>, std::is_signed<T>>, void>
processSignedInteger(T value) {
    // Only enabled for signed integral types
}

// Disjunction (OR)
template<typename T>
std::enable_if_t<std::disjunction_v<std::is_integral<T>, std::is_floating_point<T>>, void>
processNumeric(T value) {
    // Enabled for integral OR floating point
}
```

C++17's `std::conjunction` and `std::disjunction` provide short-circuit evaluation, avoiding evaluation of unnecessary conditions.

### SFINAE-Friendly Type Traits

Not all type traits are SFINAE-friendly. A SFINAE-friendly trait is one that, when applied to an invalid type, causes substitution failure rather than a hard error. The standard library type traits are generally SFINAE-friendly, but custom traits may not be:

```cpp
// Not SFINAE-friendly - hard error on incomplete types
template<typename T>
struct BadTrait {
    static constexpr bool value = sizeof(T) > 4;  // Hard error if T is incomplete
};

// SFINAE-friendly - uses void_t to defer evaluation
template<typename T, typename = void>
struct GoodTrait : std::false_type {};

template<typename T>
struct GoodTrait<T, std::void_t<decltype(sizeof(T))>> : std::integral_constant<bool, (sizeof(T) > 4)> {};
```

The second version uses SFINAE properly: when `sizeof(T)` is invalid, the specialization is simply not used rather than causing an error.

### Enable_if in Class Templates

`enable_if` works with class templates but requires care with partial specializations:

```cpp
template<typename T, typename = void>
class Serializer {
public:
    static void serialize(std::ostream& os, const T& value) {
        os << "generic";
    }
};

// Specialization for types with serialize() method
template<typename T>
class Serializer<T, std::void_t<decltype(std::declval<T>().serialize(std::declval<std::ostream&>()))>> {
public:
    static void serialize(std::ostream& os, const T& value) {
        value.serialize(os);
    }
};
```

This pattern enables different serialization strategies based on what capabilities the type supports.

### Common SFINAE Patterns

Several idiomatic patterns emerge from combining `enable_if` with type traits:

```cpp
// Enable only for pointers
template<typename T>
std::enable_if_t<std::is_pointer_v<T>, T>
dereference(T ptr) {
    return *ptr;
}

// Enable only for containers with size()
template<typename Container>
std::enable_if_t<std::is_same_v<decltype(std::declval<Container>().size()), std::size_t>, std::size_t>
getSize(const Container& c) {
    return c.size();
}

// Enable only for noexcept move constructors
template<typename T>
std::enable_if_t<std::is_nothrow_move_constructible_v<T>, void>
claim(T&& value) {
    // Safe to throw away original
}
```

These patterns enable compile-time selection between implementations based on type properties.

### Enable_if vs if constexpr

C++17's `if constexpr` provides an alternative to SFINAE for conditional compilation within a single function:

```cpp
// SFINAE approach - different functions
template<typename T>
std::enable_if_t<std::is_integral_v<T>> process(const T& value) {
    // Integral implementation
}

template<typename T>
std::enable_if_t<!std::is_integral_v<T>> process(const T& value) {
    // Non-integral implementation
}

// if constexpr approach - single function
template<typename T>
void process(const T& value) {
    if constexpr (std::is_integral_v<T>) {
        // Integral implementation
    } else {
        // Non-integral implementation
    }
}
```

The trade-off is that `if constexpr` keeps everything in one function but compiles both branches (discarding at compile time), while SFINAE only compiles the selected version. Use SFINAE when you want to avoid compiling invalid code paths, and `if constexpr` when the branches are logically part of the same function.

### Summary

`std::enable_if` enables selective template instantiation through SFINAE. Use it in return types, template parameters, or additional function parameters to constrain which types a template applies to. Combine with type traits for complex conditions, and prefer SFINAE-friendly type traits. Consider `if constexpr` as an alternative when a single function body with conditional paths is clearer.

---

## Type Traits and Detection Idioms

Type traits are templates that provide information about type properties at compile time. The C++ standard library provides a rich set of type traits covering type categories, type relationships, property queries, and capability detection. This section explores the standard type traits, how to create custom traits, and detection idioms for introspecting type capabilities.

### Primary Type Categories

The most fundamental traits query type categories. These form the foundation for most type-based dispatch:

```cpp
static_assert(std::is_integral_v<int>);
static_assert(std::is_floating_point_v<double>);
static_assert(std::is_array_v<int[5]>);
static_assert(std::is_enum_v<enum class Color>);
static_assert(std::is_class_v<std::string>);
static_assert(std::is_union_v<some_union>);
static_assert(std::is_function_v(void(int)));
static_assert(std::is_pointer_v<int*>);
```

These traits provide boolean constants that can be used in `enable_if` conditions or `if constexpr` statements. They're the building blocks for more complex type queries.

### Type Relationships

Type relationships compare two types, useful for detecting implicit conversions or exact matches:

```cpp
static_assert(std::is_same_v<int, int>);              // Same type
static_assert(std::is_same_v<int, const int> == false);  // Different types
static_assert(std::is_base_of_v<Base, Derived>);    // Inheritance
static_assert(std::is_convertible_v<int, double>);  // Implicit conversion
static_assert(std::is_trivially_copyable_v<int>);  // Trivial copy
static_assert(!std::is_volatile_v<const int>);      // Not volatile
```

These relationships enable sophisticated type constraints, such as ensuring a derived class is passed to a function or that a type can be implicitly converted.

### Composite Type Queries

Beyond single types, composite queries combine conditions for specific patterns:

```cpp
template<typename T>
constexpr bool is_string_v = std::is_same_v<T, std::string> ||
                             std::is_same_v<T, std::string_view> ||
                             std::is_same_v<T, const char*> ||
                             std::is_same_v<T, char*>;

template<typename T>
constexpr bool is_numeric_v = std::is_integral_v<T> ||
                              std::is_floating_point_v<T>;

template<typename T>
constexpr bool is_smart_ptr_v = std::is_same_v<T, std::unique_ptr<typename T::element_type>> ||
                                 std::is_same_v<T, std::shared_ptr<typename T::element_type>> ||
                                 std::is_same_v<T, std::weak_ptr<typename T::element_type>>;
```

These composite traits provide readable names for common type patterns.

### Type Properties

Type properties query characteristics beyond category:

```cpp
static_assert(std::is_const_v<const int>);
static_assert(std::is_trivial_v<int>);              // Trivial type
static_assert(std::is_trivially_destructible_v<int>);
static_assert(std::is_standard_layout_v<struct A>);
static_assert(std::is_pod_v<int>);                  // Trivial + standard layout
static_assert(std::is_literal_type_v<int>);       // Can be in constexpr
static_assert(std::is_aggregate_v<std::array<int, 5>>);  // Aggregate
```

These properties inform what operations are safe and efficient, guiding algorithm selection.

### SFINAE-Based Detection

For custom capabilities that standard traits don't cover, detection idioms use SFINAE to check for members and operations:

```cpp
// Detect if type has a specific member
template<typename, typename = void>
struct has_size_member : std::false_type {};

template<typename T>
struct has_size_member<T, std::void_t<decltype(std::declval<T>().size())>> : std::true_type {};

// Detect if type supports an operation
template<typename, typename = void>
struct has_begin : std::false_type {};

template<typename T>
struct has_begin<T, std::void_t<decltype(std::declval<T>().begin())>> : std::true_type {};

// Detect if expression is valid
template<typename T>
struct can_add {
private:
    template<typename U>
    static auto test(int) -> decltype(std::declval<U>() + std::declval<U>(), std::true_type{});
    template<typename U>
    static std::false_type test(...);
public:
    static constexpr bool value = decltype(test<T>(0))::value;
};

static_assert(has_size_member<std::vector<int>>::value);  // true
static_assert(has_size_member<std::string>::value);       // true
static_assert(has_size_member<int>::value);               // false
```

The key is using `decltype` with the expression being tested. If the expression is invalid, substitution failure occurs and the primary template (which defaults to `false_type`) is selected.

### Detection with Multiple Conditions

More sophisticated detection can check multiple operations at once:

```cpp
template<typename T>
struct is_container {
private:
    template<typename U>
    static auto test(int) -> decltype(
        std::declval<U>().begin(),
        std::declval<U>().end(),
        std::declval<U>().size(),
        std::true_type{}
    );

    template<typename U>
    static std::false_type test(...);

public:
    static constexpr bool value = decltype(test<T>(0))::value;
};

template<typename T>
struct is_range {
private:
    template<typename U>
    static auto test(int) -> decltype(
        std::begin(std::declval<U>()),
        std::end(std::declval<U>()),
        std::true_type{}
    );

    template<typename U>
    static std::false_type test(...);

public:
    static constexpr bool value = decltype(test<T>(0))::value;
};
```

This detects containers by checking for `begin()`, `end()`, and `size()` members, and ranges by checking for `std::begin`/`std::end` support.

### Detection with Return Type

Checking return types enables detecting more specific capabilities:

```cpp
template<typename T>
struct has_value_type {
private:
    template<typename U>
    static auto test(int) -> std::void_t<typename U::value_type, decltype(U::value_type{})>;
    template<typename U>
    static void test(...);

public:
    static constexpr bool value = !std::is_same_v<void, decltype(test<T>(0))>;
};

template<typename T, typename = void>
struct value_type_of {
    using type = void;
};

template<typename T>
struct value_type_of<T, std::void_t<typename T::value_type>> {
    using type = typename T::value_type;
};

// Usage
static_assert(has_value_type<std::vector<int>>::value);  // true
using vt = value_type_of<std::vector<int>>::type;       // int
```

This pattern both detects presence and extracts the type when present.

### Void_t for Universal Detection

The `void_t` pattern (also called "void trick") transforms type conditions into SFINAE-friendly checks:

```cpp
template<typename...>
using void_t = void;

// Check for nested type
template<typename T, typename = void>
struct has_value_type : std::false_type {};

template<typename T>
struct has_value_type<T, void_t<typename T::value_type>> : std::true_type {};

// Check for member
template<typename T, typename = void>
struct has_data : std::false_type {};

template<typename T>
struct has_data<T, void_t<decltype(std::declval<T>().data())>> : std::true_type {};

// Check for noexcept
template<typename T, typename = void>
struct is_nothrow_swappable : std::false_type {};

template<typename T>
struct is_nothrow_swappable<T, void_t<decltype(std::swap(std::declval<T&>(), std::declval<T&>()))>>
    : std::bool_constant<noexcept(std::swap(std::declval<T&>(), std::declval<T&>()))> {};
```

The `void_t` alias maps any type sequence to `void`, but importantly, it causes substitution failure to be SFINAE-friendly rather than a hard error.

### Detection with C++20 Concepts

C++20 concepts provide a more readable syntax for the same detection:

```cpp
template<typename T>
concept Container = requires(T t) {
    typename T::value_type;
    t.begin();
    t.end();
    t.size();
};

template<typename T>
concept Numeric = std::integral_v<T> || std::floating_point_v<T>;

// Usage
template<Container C>
std::size_t size(const C& c) {
    return c.size();
}

template<Numeric N>
N square(N n) {
    return n * n;
}
```

While C++20 concepts are cleaner, understanding the underlying detection idiom remains valuable for pre-C++20 code and for understanding how concepts work under the hood.

### Conditional Type Selection

Beyond boolean traits, type traits can transform types:

```cpp
// Conditional type based on condition
template<bool Condition, typename TrueType, typename FalseType>
struct conditional { using type = TrueType; };

template<typename TrueType, typename FalseType>
struct conditional<false, TrueType, FalseType> { using type = FalseType; };

template<bool Condition, typename TrueType, typename FalseType>
using conditional_t = typename conditional<Condition, TrueType, FalseType>::type;

// Example: choose iterator category
template<typename Iterator>
using iterator_category_t = conditional_t<
    std::is_pointer_v<Iterator>,
    std::random_access_iterator_tag,
    typename std::iterator_traits<Iterator>::iterator_category
>;

// Remove qualifiers
template<typename T>
using remove_cv_t = typename std::remove_cv<T>::type;
template<typename T>
using remove_reference_t = typename std::remove_reference<T>::type;
template<typename T>
using add_pointer_t = typename std::add_pointer<T>::type;
```

The type transformation traits enable flexible generic programming by selecting types based on compile-time conditions.

### Custom Type Traits

Creating custom type traits follows a consistent pattern:

```cpp
// Trait for detecting if type is a smart pointer
template<typename T>
struct is_smart_pointer : std::false_type {};

template<typename T>
struct is_smart_pointer<std::unique_ptr<T>> : std::true_type {};

template<typename T>
struct is_smart_pointer<std::shared_ptr<T>> : std::true_type {};

template<typename T>
struct is_smart_pointer<std::weak_ptr<T>> : std::true_type {};

template<typename T>
inline constexpr bool is_smart_pointer_v = is_smart_pointer<std::remove_cv_t<T>>::value;

// Trait for extracting element type from smart pointers
template<typename T, bool = is_smart_pointer_v<T>>
struct element_type {
    using type = T;
};

template<typename T>
struct element_type<std::unique_ptr<T>, true> {
    using type = T;
};

template<typename T>
struct element_type<std::shared_ptr<T>, true> {
    using type = T;
};

template<typename T>
using element_type_t = typename element_type<T>::type;
```

Following the standard library pattern (inheriting from `std::true_type` or `std::false_type`) ensures consistency and enables `inline constexpr` variables in C++17+.

### Summary

Type traits provide compile-time type introspection. Use primary type categories (`is_integral`, `is_floating_point`, etc.) for basic classification. Use type relationships (`is_same`, `is_base_of`, `is_convertible`) for comparing types. Use detection idioms with `void_t` to check for arbitrary capabilities. Create custom traits following the `std::true_type`/`std::false_type` pattern. C++20 concepts provide cleaner syntax for the same capabilities.

---

## Compile-Time Introspection

Compile-time introspection enables examining type properties and making decisions based on those properties at compile time. This goes beyond simple traits to include detecting capabilities, implementing constraints, and generating type-specific code. This section explores techniques for introspecting types and implementing compile-time decisions.

### Detecting Type Capabilities

The foundation of introspection is detecting what operations a type supports:

```cpp
// Check for operator[]
template<typename T, typename = void>
struct has_subscript : std::false_type {};

template<typename T>
struct has_subscript<T, std::void_t<decltype(std::declval<T>()[0])>> : std::true_type {};

// Check for hash() method
template<typename T, typename = void>
struct has_hash : std::false_type {};

template<typename T>
struct has_hash<T, std::void_t<decltype(std::declval<T>().hash())>> : std::true_type {};

template<typename T>
inline constexpr bool has_subscript_v = has_subscript<T>::value;
template<typename T>
inline constexpr bool has_hash_v = has_hash<T>::value;

// Usage
static_assert(has_subscript_v<std::vector<int>>);  // true
static_assert(has_subscript_v<std::string>);      // true
static_assert(!has_subscript_v<int>);              // false
static_assert(has_hash_v<std::string>);            // true
```

This pattern enables generic code to adapt based on what operations the target type supports.

### Detecting noexcept Specifications

Understanding which operations are noexcept enables different handling:

```cpp
template<typename T>
struct is_nothrow_default_constructible {
    static constexpr bool value = std::is_nothrow_default_constructible_v<T>;
};

template<typename T>
struct is_nothrow_move_constructible {
    static constexpr bool value = std::is_nothrow_move_constructible_v<T>;
};

template<typename T>
constexpr bool is_nothrow_relocatable_v = std::is_trivially_destructible_v<T> &&
                                          std::is_trivially_move_constructible_v<T>;

// Enable optimization for nothrow-movable types
template<typename T>
std::enable_if_t<std::is_nothrow_move_constructible_v<T>, std::unique_ptr<T>>
cloneUnique(std::unique_ptr<T> ptr) {
    if (ptr) return std::make_unique<T>(std::move(*ptr));
    return nullptr;
}
```

Detecting noexcept properties guides optimization decisions and error handling strategies.

### Introspecting Class Members

Detecting and accessing class members enables generic access patterns:

```cpp
// Detect if class has a specific member
template<typename T, typename Member, typename = void>
struct has_member : std::false_type {};

template<typename T, typename Member>
struct has_member<T, Member, std::void_t<Member T::*>> : std::true_type {};

struct A { int x; };
struct B { };

static_assert(has_member<A, int>::value);  // true
static_assert(has_member<B, int>::value);  // false

// Detect member function signature
template<typename T, typename Return, typename... Args>
struct has_member_function {
private:
    template<typename U>
    static auto test(int) -> std::is_same<decltype(std::declval<U>().execute(std::declval<Args>()...)), Return>;
    template<typename U>
    static std::false_type test(...);

public:
    static constexpr bool value = test<T>(0)::value;
};

class Handler {
public:
    int execute(int, double) { return 0; }
};

static_assert(has_member_function<Handler, int, int, double>::value);
```

This enables sophisticated generic programming that adapts to class member structure.

### Type List Introspection

For complex type manipulation, type lists enable compile-time collection operations:

```cpp
// Simple type list
template<typename... Ts>
struct TypeList {};

template<typename List>
struct Size;

template<typename... Ts>
struct Size<TypeList<Ts...>> : std::integral_constant<std::size_t, sizeof...(Ts)> {};

// Access element by index
template<std::size_t I, typename List>
struct TypeAt;

template<std::size_t I, typename Head, typename... Tail>
struct TypeAt<I, TypeList<Head, Tail...>>
    : TypeAt<I - 1, TypeList<Tail...>> {};

template<typename Head, typename... Tail>
struct TypeAt<0, TypeList<Head, Tail...>> {
    using type = Head;
};

// Find index of type
template<typename List, typename T>
struct IndexOf;

template<typename T>
struct IndexOf<TypeList<>, T> : std::integral_constant<std::size_t, -1> {};

template<typename Head, typename... Tail>
struct IndexOf<TypeList<Head, Tail...>, T>
    : std::conditional_t<std::is_same_v<Head, T>,
                         std::integral_constant<std::size_t, 0>,
                         std::integral_constant<std::size_t, IndexOf<TypeList<Tail...>, T>::value + 1>> {};

// Usage
using MyList = TypeList<int, double, char, std::string>;
static_assert(Size<MyList>::value == 4);
static_assert(std::is_same_v<TypeAt<2, MyList>::type, char>);
static_assert(IndexOf<MyList, double>::value == 1);
```

Type lists enable compile-time algorithms over type sequences, the foundation of many metaprogramming techniques.

### Compile-Time Branching

Combining introspection with conditional compilation enables compile-time branching:

```cpp
template<typename T>
void process(const T& value) {
    if constexpr (std::is_integral_v<T>) {
        std::cout << "Integer: " << value << "\n";
        if constexpr (std::is_signed_v<T>) {
            std::cout << "  Signed\n";
        } else {
            std::cout << "  Unsigned\n";
        }
    } else if constexpr (std::is_floating_point_v<T>) {
        std::cout << "Floating: " << value << "\n";
    } else if constexpr (has_to_string_v<T>) {
        std::cout << value.toString() << "\n";
    } else {
        std::cout << "Other: <no display>\n";
    }
}

// Conditional based on property
template<typename T>
auto compute(T a, T b) {
    if constexpr (std::is_integral_v<T>) {
        // Integer arithmetic
        return a + b;
    } else if constexpr (requires(T x) { x + x; }) {
        // Has operator+ (C++20 requires expression)
        return a + b;
    } else {
        return T{};
    }
}
```

The `if constexpr` statement performs compile-time branching, with branches that don't match being discarded rather than compiled.

### SFINAE for Function Selection

Detecting function existence enables different implementation strategies:

```cpp
// Try to use ADL, fallback to member function
template<typename T>
auto toString(const T& value)
    -> decltype(std::to_string(std::declval<T>())) {
    return std::to_string(value);
}

template<typename T>
auto toString(const T& value)
    -> decltype(value.toString()) {
    return value.toString();
}

template<typename T>
std::string toString(const T& value) {
    return std::string("fallback");
}
```

This pattern provides multiple implementations, each enabled only when its dependency is available.

### Introspection for Serialization

A practical application is generic serialization that adapts to type capabilities:

```cpp
template<typename T, typename = void>
struct Serializer {
    static void serialize(std::ostream& os, const T& value) {
        os << value;  // Uses operator<<
    }
};

template<typename T>
struct Serializer<T, std::void_t<decltype(std::declval<T>().serialize(std::declval<std::ostream&>()))>> {
    static void serialize(std::ostream& os, const T& value) {
        value.serialize(os);  // Uses member function
    }
};

template<typename T>
void serialize(std::ostream& os, const T& value) {
    Serializer<T>::serialize(os, value);
}
```

This enables heterogeneous serialization strategies based on what the type supports.

### Introspecting Function Signatures

Detecting function signatures enables sophisticated generic callbacks:

```cpp
template<typename Func>
struct FunctionTraits;

template<typename R, typename... Args>
struct FunctionTraits<R(Args...)> {
    using return_type = R;
    using argument_types = TypeList<Args...>;
    static constexpr std::size_t arity = sizeof...(Args);
};

template<typename R, typename... Args>
struct FunctionTraits<R(*)(Args...)> : FunctionTraits<R(Args...)> {};

template<typename C, typename R, typename... Args>
struct FunctionTraits<R(C::*)(Args...)> : FunctionTraits<R(Args...)> {};

// Usage
using FuncPtr = int(*)(double, char);
static_assert(FunctionTraits<FuncPtr>::arity == 2);
static_assert(std::is_same_v<typename FunctionTraits<FuncPtr>::return_type, int>);
```

Function traits enable generic libraries to understand and manipulate function types.

### Introspection for Type Erasure

Type erasure uses introspection to handle heterogeneous types uniformly:

```cpp
template<typename T>
constexpr std::size_t estimated_size() {
    if constexpr (std::is_trivially_destructible_v<T>) {
        return sizeof(T);
    } else {
        return sizeof(T) + 16;  // Extra for destructor
    }
}

template<typename T>
constexpr bool is_cache_friendly() {
    return std::is_standard_layout_v<T> &&
           std::is_trivially_copyable_v<T>;
}
```

These introspections guide the design of type-erased wrappers.

### Detecting Implicit Conversions

Understanding possible conversions enables safe generic programming:

```cpp
template<typename From, typename To>
struct is_explicitly_convertible {
private:
    template<typename U>
    static auto test(int) -> std::is_same<decltype(static_cast<To>(std::declval<U>())), To>;
    template<typename U>
    static std::false_type test(...);

public:
    static constexpr bool value = test<From>(0)::value;
};

template<typename From, typename To>
inline constexpr bool is_explicitly_convertible_v = is_explicitly_convertible<From, To>::value;

// Enable conversion only where explicit
template<typename To, typename From>
std::enable_if_t<is_explicitly_convertible_v<From, To>, To>
convert(const From& value) {
    return static_cast<To>(value);
}
```

This enables safe generic conversion functions.

### Summary

Compile-time introspection enables examining type properties and making decisions at compile time. Detect capabilities using `void_t` with `decltype`. Use `if constexpr` for conditional compilation based on detected properties. Create traits for reusable introspection logic. Combine introspection with SFINAE for selective function overloads. The key insight is that most type information can be queried at compile time, enabling static polymorphism without runtime overhead.

---

## Summary

This chapter explored four interrelated techniques for compile-time polymorphism in C++. Tag dispatch uses marker types (tags) to select between function overloads based on type properties, with inheritance providing fallback behavior. `std::enable_if` enables or disables template instantiation through SFINAE, allowing selective compilation based on type constraints. Type traits provide compile-time queries for type categories, relationships, and properties. Compile-time introspection combines these techniques to examine type capabilities and make compile-time decisions.

These techniques form the foundation of modern C++ metaprogramming. They're used extensively in the standard library (iterator traits, type traits, algorithms) and in modern libraries (Boost,Ranges, Eigen). The combination of tag dispatch and SFINAE enables zero-overhead abstractions that adapt to types at compile time while remaining readable and maintainable.

The key insight is that C++ provides powerful compile-time computation capabilities. Rather than runtime type information and virtual dispatch, we can use template instantiation and compile-time selection to achieve polymorphic behavior. This trades flexibility for performance—types must be known at compile time—but enables optimizations that runtime polymorphism cannot match.

### Exercises

1. **Tag Dispatch Implementation**: Implement a `advance` function that uses tag dispatch to provide O(1) advancement for random access iterators, O(n) for bidirectional iterators, and throws an exception for input iterators that don't support multi-pass.

2. **Enable_if Selection**: Write a `concatenate` function that accepts strings and vectors of arithmetic types, using `enable_if` to select between overloads and ensure type safety.

3. **Custom Type Traits**: Create a type trait `is_callable` that detects whether a type can be invoked as a function with any arguments, using SFINAE with `decltype`.

4. **Serialization Detection**: Implement a generic `serialize` function that uses introspection to call `serialize()` member function if available, fall back to `operator<<` if defined, or produce a compile error otherwise.

5. **Compile-Time Introspection**: Build a type list implementation that supports filtering types based on a predicate trait, and demonstrate it by filtering a list of types to only integral types.