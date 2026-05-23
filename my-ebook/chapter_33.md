# Chapter 33: Reflection and Introspection

Reflection — the ability of a program to examine and manipulate its own structure — is one of the few areas where C++ lags behind younger languages. Java's `java.lang.reflect`, C#'s `System.Reflection`, and Python's `type()` and `vars()` all provide runtime introspection that C++ deliberately avoids. The reason is philosophical: C++ values zero-cost abstraction and compile-time determinism. Paying a runtime cost for metadata that most programs never use is antithetical to the language's design.

But "limited reflection" is not "no reflection." C++ has always had considerable *compile-time* introspection through type traits and SFINAE, and the C++26 standard introduces a major step forward: a static reflection facility via `std::meta`. This chapter covers three approaches to reflection in C++: compile-time introspection through template metaprogramming, macro-based code inspection, and the practical problem that drives most real-world reflection needs — automatic serialization.

---

## Compile-Time Reflection Patterns

### What C++ has and what it lacks

Languages with full runtime reflection can query the name, layout, base classes, and members of any object at runtime using standardized APIs. C++ has nothing equivalent — there is no `obj.getMembers()` or `Type::getFields()`. The closest the language provides is `typeid`, which returns a `std::type_info` that can only compare equality and retrieve a human-readable name. That is deliberately minimal.

What C++ does provide is *compile-time* introspection: the ability to query properties of types during template instantiation, before the executable exists. This is the domain of `<type_traits>`, SFINAE, `decltype`, and the detection idiom.

### Type traits as a reflection library

The `<type_traits>` header is a corpus of compile-time queries:

```cpp
static_assert(std::is_class_v<MyType>);
static_assert(std::is_trivially_copyable_v<MyType>);
static_assert(std::is_constructible_v<MyType, int, double>);
static_assert(std::is_nothrow_move_assignable_v<MyType>);
```

Each trait is a predicate that answers one question about a type's properties. Composing them with logical trait operators yields conditional behavior:

```cpp
template <typename T>
void optimized_copy(T* dst, const T* src, std::size_t n) {
    if constexpr (std::is_trivially_copyable_v<T>) {
        std::memcpy(dst, src, n * sizeof(T));
    } else {
        for (std::size_t i = 0; i < n; ++i) {
            dst[i] = src[i];
        }
    }
}
```

Why use a trait instead of runtime detection? Because `std::is_trivially_copyable` is a property of the type, not of any particular value. The compiler knows it at compile time. The `if constexpr` branch that is not taken is discarded entirely — the `memcpy` call is never even compiled for non-trivial types. This is reflection as a compile-time gatekeeper.

The limits of trait-based reflection are quickly reached: traits can only answer yes/no questions that the committee has anticipated. They cannot enumerate the members of a struct, list its base classes, or iterate over its nested types.

### The detection idiom with `void_t`

What if you need to check whether a type has a member function named `.begin()` — but there is no trait for that? The detection idiom fills the gap. It relies on `void_t`, an alias template that always produces `void`, and uses it to drive SFINAE:

```cpp
template <typename T, typename = std::void_t<>>
struct has_begin : std::false_type {};

template <typename T>
struct has_begin<T, std::void_t<decltype(std::declval<T>().begin())>>
    : std::true_type {};

template <typename T, typename = void>
struct has_begin : std::false_type {};

template <typename T>
struct has_begin<T, void_t<decltype(std::declval<T>().begin())>>
    : std::true_type {};
```

The specialization is attempted only if the expression `std::declval<T>().begin()` is well-formed. If it compiles, the specialization is preferred over the primary template. If it fails, SFINAE discards the specialization and the primary template (which inherits `false_type`) is used.

This pattern — defining a void alias to enable partial specialization on expression validity — is the bedrock of ad-hoc type introspection in C++17 and earlier. It was formalized in C++20 as the Concepts TS and `requires` expressions, which are more readable but build on the same mechanism:

```cpp
template <typename T>
concept has_begin = requires(T t) {
    t.begin();
};
```

The required expression `t.begin()` fills the same role as the `decltype` in the `void_t` pattern. The improvement is readability: the concept spells out the requirement directly, without the machinery of trait specialization.

### Member detection without concepts

When concepts are unavailable, the detection idiom extends naturally to member types and nested aliases:

```cpp
template <typename T, typename = void>
struct has_value_type : std::false_type {};

template <typename T>
struct has_value_type<T,
    void_t<typename T::value_type>> : std::true_type {};
```

And to member data:

```cpp
template <typename T, typename = void>
struct has_first : std::false_type {};

template <typename T>
struct has_first<T,
    void_t<decltype(std::declval<T>().first)>> : std::true_type {};
```

Each detection is a standalone trait. When many detections are needed together, the traits can be composed with `std::conjunction` or folded into a single `requires` clause. The pattern scales poorly with the number of members — you write one trait per member — but the underlying insight remains powerful: the compiler *can* tell you whether a type has a particular member; the trait just formalizes the question.

### C++26 static reflection (`std::meta`)

The C++26 standard introduces a language-level reflection facility based on the `^` operator and the `std::meta` namespace. It is a compile-time system: reflection values are `consteval` and produce `std::meta::info` objects that are not available at runtime — they are used to generate code, not to inspect data.

```cpp
#include <meta>

enum class Color { Red, Green, Blue };

consteval {
    // std::meta::info representing the enum type
    std::meta::info enum_info = ^Color;

    // iterate over enumerators
    for (std::meta::info member : std::meta::members_of(enum_info)) {
        std::meta::info name = std::meta::name_of(member);
        // name can be used in a consteval context
    }
}
```

The `^` operator applied to a type or expression yields a `std::meta::info` object. Functions like `std::meta::members_of`, `std::meta::name_of`, `std::meta::type_of`, `std::meta::size_of`, and `std::meta::is_class` then query that info object.

This is fundamentally different from type traits: traits answer a single question per template instantiation. Reflection with `std::meta` allows iteration, selection, and code generation. For example, generating `std::string to_string(Color)` without hand-writing each case:

```cpp
consteval {
    std::meta::info enum_info = ^Color;
    std::vector<std::meta::info> enumerators =
        std::meta::members_of(enum_info);

    // generate a switch statement
    std::string out = "std::string to_string(Color c) {\n  switch (c) {\n";
    for (auto e : enumerators) {
        out += "    case " + std::string(std::meta::name_of(e)) + ": "
             + "return \"" + std::string(std::meta::name_of(e)) + "\";\n";
    }
    out += "  }\n  return \"(unknown)\";\n}";
    // inject out as source code at compile time
}
```

This code runs at compile time, producing the function body as a string, which is then spliced into the program. The `for` loop over `enumerators` is a `consteval` loop — it is evaluated entirely by the compiler, not by the final executable.

The limits of `std::meta` are practical rather than theoretical: it is a large new facility, compiler support is maturing, and idiomatic patterns around it are still emerging. It will not replace `type_traits` — the traits are simpler and sufficient for most single-property queries — but it will eliminate the need for macro-based code generation and external code generators for many reflection tasks.

---

## Reflection with Macros

Before `std::meta`, and still widely used today, C++ programmers turn to the preprocessor when they need to enumerate or inspect code structure. Macros offer a way to define information once and expand it in multiple contexts — exactly what reflection provides in other languages, albeit with significant trade-offs.

### The preprocessor as a reflection tool

The C preprocessor provides two operators that make code generation possible:

- `#` — stringification: converts a macro argument into a string literal.
- `##` — token pasting: concatenates two tokens to form a new token.

Combined with `__FILE__` (current filename), `__LINE__` (current line), and `__FUNCTION__` (current function name), these allow limited self-inspection:

```cpp
#define LOG(msg) \
    std::cout << __FILE__ << ":" << __LINE__ << " " << __FUNCTION__ \
              << ": " << msg << std::endl;
```

This pattern is primitive compared to true reflection, but it demonstrates the principle: the preprocessor has access to source-level metadata that the language proper does not expose.

### X macros

The X macro is the preprocessor's most powerful pattern for reflection-like code generation. It works by defining a list macro once and then expanding it inside multiple `#define` contexts:

```cpp
// Define the list once
#define COLOR_LIST \
    X(Red)   \
    X(Green) \
    X(Blue)

// First expansion: enum definition
enum class Color {
    #define X(name) name,
    COLOR_LIST
    #undef X
};

// Second expansion: string conversion
std::string to_string(Color c) {
    switch (c) {
        #define X(name) case Color::name: return #name;
        COLOR_LIST
        #undef X
    }
    return "(unknown)";
}

// Third expansion: stream operator
std::ostream& operator<<(std::ostream& os, Color c) {
    switch (c) {
        #define X(name) case Color::name: os << #name; break;
        COLOR_LIST
        #undef X
    }
    return os;
}
```

Each expansion of `COLOR_LIST` redefines what `X(name)` does. The `#undef` ensures the macro is reset for the next expansion. The result is a *single source of truth*: adding a new color requires editing only `COLOR_LIST`, and the enum, string conversion, and streaming are updated simultaneously.

This is the same guarantee that runtime reflection provides in other languages — "add a field, and all introspection code sees it" — but achieved through textual substitution rather than runtime metadata. The pattern extends to struct field definitions:

```cpp
#define PERSON_FIELDS \
    X(std::string, name) \
    X(int, age)          \
    X(double, height)

struct Person {
    #define X(type, name) type name;
    PERSON_FIELDS
    #undef X
};

template <typename Visitor>
void visit_person(Person& p, Visitor&& v) {
    #define X(type, name) v(#name, p.name);
    PERSON_FIELDS
    #undef X
}
```

The `visit_person` function now provides a reflection-like interface: it applies a visitor to each field of the struct. A serializer can be written against this visitor:

```cpp
nlohmann::json to_json(Person& p) {
    nlohmann::json j;
    visit_person(p, [&](const char* name, auto& field) {
        j[name] = field;
    });
    return j;
}
```

The X macro pattern gives each struct a *structure definition* that is a single source of truth, from which multiple code paths are mechanically generated. It is reliable, predictable, and requires no external tools.

### Limitations of X macros

X macros come with significant costs. Errors during macro expansion produce impenetrable compiler diagnostics — the error message refers to the expanded text, not to the macro definition, so a mistake in `PERSON_FIELDS` might appear as a failure inside `visit_person` with no hint that the cause is the data definition. Debugging is difficult because the preprocessor operates before the compiler, and stepping through macro expansions in a debugger is not practical.

Macros also ignore scope, namespaces, and access control. An X macro defined in a header file expands wherever the header is included. The `#undef` pattern is essential to prevent cross-contamination, but it is a manual discipline that is easy to neglect.

Finally, X macros produce code bloat for large data sets. Each expansion of the list creates a complete copy of the pattern. If the list is long and the expansion is used in many contexts, the compiler may generate substantial code from each source location.

### Boost.Preprocessor for complex code generation

For situations requiring loops, sequences, and conditional expansion beyond what simple X macros provide, Boost.Preprocessor offers a library of preprocessor metafunctions:

```cpp
#include <boost/preprocessor.hpp>

#define ENUM_WITH_STRINGS(Name, Values) \
    enum class Name { BOOST_PP_SEQ_ENUM(Values) }; \
    inline std::string to_string(Name v) { \
        switch (v) { \
            BOOST_PP_SEQ_FOR_EACH(ENUM_CASE, Name, Values) \
        } \
        return "(unknown)"; \
    }

#define ENUM_CASE(r, Enum, Value) \
    case Enum::Value: return BOOST_PP_STRINGIZE(Value);

ENUM_WITH_STRINGS(Color, (Red)(Green)(Blue))
```

`BOOST_PP_SEQ_ENUM` converts `(Red)(Green)(Blue)` to `Red, Green, Blue`. `BOOST_PP_SEQ_FOR_EACH` applies `ENUM_CASE` to each element, producing three case statements. The result is the same as the X macro version, but the intermediate macros are standardized and composable.

Boost.Preprocessor pushes the preprocessor to its limits — sequences, tuples, lists, arithmetic, and iteration are all simulated within the preprocessor's recursion and token-replacement rules. It works but imposes a high cognitive load. Every `BOOST_PP` macro is a recursion-limiting workaround; hitting the preprocessor's recursion depth (typically 256) produces cryptic failures.

---

## Automatic Serialization

The most common real-world use of reflection in any language is serialization: converting objects to and from bytes, JSON, XML, or binary formats. Without built-in reflection, C++ programmers must choose from several imperfect approaches.

### Why serialization is hard

In a language with reflection, serialization is automatic: the framework iterates over the object's fields, retrieves their names and values, and writes them. In C++, the framework has no way to enumerate fields. Every serializer must be told, one type at a time, which fields to include and how to access them.

The challenge is also one of *type erasure*. A serializer that accepts `const T&` and writes it to JSON must somehow iterate over the members of `T`, but the template parameter `T` provides no member list. The iteration must be encoded explicitly for each `T`.

### Visitor-based serialization

A visitor pattern decouples the struct definition from the serialization logic. The struct provides a `visit` function that calls a visitor for each field. The visitor is a generic callback; the serializer implements the callback for its format:

```cpp
template <typename Visitor>
void visit(const Person& p, Visitor&& v) {
    v("name",   p.name);
    v("age",    p.age);
    v("height", p.height);
}

nlohmann::json to_json(const Person& p) {
    nlohmann::json j;
    visit(p, [&](const char* name, const auto& value) {
        j[name] = value;
    });
    return j;
}
```

The `visit` function is the explicit encoding of the struct's fields. It must be written once per type, but it can be reused for any format — JSON, XML, binary, or human-readable. Adding a new format requires no changes to the struct, only a new visitor.

The cost is maintenance. When a field is added to `Person`, the `visit` function must be updated. If it is not, the serializer silently omits the field. There is no compile-time error and no reflection-like guarantee of completeness.

### Boost.Fusion adaptation

Boost.Fusion provides macros that adapt a struct for use with its metaprogramming infrastructure, providing a `for_each`-based visitor:

```cpp
#include <boost/fusion/adapted.hpp>
#include <boost/fusion/include/for_each.hpp>

BOOST_FUSION_ADAPT_STRUCT(
    Person,
    (std::string, name)
    (int, age)
    (double, height)
)

struct json_serializer {
    nlohmann::json& j;
    template <typename T>
    void operator()(const char* name, const T& value) const {
        j[name] = value;
    }
};

nlohmann::json to_json(const Person& p) {
    nlohmann::json j;
    boost::fusion::for_each(p, json_serializer{j});
    return j;
}
```

`BOOST_FUSION_ADAPT_STRUCT` generates a compile-time description of the struct's members, making the struct behave like a tuple. `boost::fusion::for_each` iterates over the members and applies the visitor. The macro is the single source of truth — updating the macro updates all visitors automatically.

The trade-off is that `BOOST_FUSION_ADAPT_STRUCT` is itself a macro, with all the debugging and name-collision issues discussed earlier. It also imposes a dependency on Boost.Fusion, which is a large library to include for serialization alone.

### X-macro serialization

The earlier X macro approach for structs is essentially the same pattern as Boost.Fusion adaptation, but hand-rolled:

```cpp
#define PERSON_FIELDS \
    X(std::string, name) \
    X(int, age)

struct Person {
    #define X(type, name) type name;
    PERSON_FIELDS
    #undef X
};

#define TO_JSON_HELPER(type, name) \
    j[#name] = p.name;

nlohmann::json to_json(const Person& p) {
    nlohmann::json j;
    PERSON_FIELDS
    return j;
}

#undef TO_JSON_HELPER
```

This avoids the Boost dependency and keeps the field list local. Multiple serialization formats are supported by defining different helper macros for each format:

```cpp
#define TO_XML_HELPER(type, name) \
    xml.append_child(#name).append_child(pugi::node_pcdata) \
       .set_value(std::to_string(p.name).c_str());
```

The principle is the same as Fusion's — one list, many expansions — but implemented with the language's own preprocessor.

### Template-based serialization for tuple-like types

For types that are already tuples (such as `std::tuple` or types adapted with `BOOST_FUSION_ADAPT_STRUCT`), serialization can be written generically:

```cpp
template <typename Tuple, std::size_t... Is>
nlohmann::json tuple_to_json_impl(const Tuple& t,
                                   std::index_sequence<Is...>) {
    nlohmann::json arr = nlohmann::json::array();
    ((arr.push_back(std::get<Is>(t))), ...);
    return arr;
}

template <typename... Ts>
nlohmann::json tuple_to_json(const std::tuple<Ts...>& t) {
    return tuple_to_json_impl(t,
        std::make_index_sequence<sizeof...(Ts)>{});
}
```

This serializes a tuple as a JSON array (losing field names). For named fields, the tuple must carry metadata — field name strings — which typically requires the struct-adaptation macros above.

### External serialization frameworks

Several external tools solve the reflection problem by generating C++ code from an IDL (Interface Definition Language):

- **Protocol Buffers** (protobuf): define `.proto` files, codegen produces C++ classes with built-in serialization.
- **FlatBuffers**: define `.fbs` files, codegen produces zero-copy serialization.
- **Cap'n Proto**: similar to FlatBuffers, with a focus on speed.
- **Apache Thrift**: multi-language serialization and RPC.

These tools bypass C++'s lack of reflection entirely by having codegen write the code that C++ cannot. The generated classes include `SerializeToString`, `ParseFromString`, `DebugString`, and field accessors. The trade-off is a build-system dependency on the codegen tool and the impedance mismatch between hand-written C++ types and generated types — a `Person` defined in protobuf is not the same type as a hand-written `Person`, and converting between them requires glue code.

### Choosing a serialization approach

The choice depends on the project's priorities:

- **Minimal dependencies** — Hand-written visitor functions. Maintainable for small numbers of types. Scales poorly.
- **Single format, many types** — X macros or Boost.Fusion adaptation. The macro is the single source of truth; serialization is automatic for any type that uses the macro.
- **Multiple formats, many types** — X macros with format-specific helper macros. Same source list drives JSON, XML, binary outputs.
- **Cross-language or performance-critical** — External codegen (protobuf, FlatBuffers). The reflection problem is solved at the codegen level, and the serialized format is standard and versioned.
- **Ad-hoc, small-scale** — Manual `operator<<` and `operator>>`. Direct, explicit, and zero abstraction cost.

None of these approaches is as convenient as Java's reflection or Python's `pickle`. All of them require discipline — the visitor function must be kept in sync with the struct, the X macro must be updated, or the `.proto` file must be regenerated. In return, they produce serialization code that is efficient, predictable, and free of runtime metadata.

---

## Chapter Summary

Reflection in C++ is not a single feature but a spectrum of techniques spanning compile-time introspection, macro-based code generation, and external tooling.

- **Compile-time type traits** provide queryable properties of types and are sufficient for conditional compilation and constrained templates. The detection idiom extends traits to arbitrary member expressions. C++26's `std::meta` expands this to full compile-time iteration and code generation, promising to eliminate many preprocessor use cases.

- **Macro-based reflection** uses X macros and Boost.Preprocessor to generate code from a single data definition. The approach is proven and dependency-free, but carries significant debugging and maintenance costs.

- **Serialization** is the driving application for most reflection needs. The available approaches — visitor functions, adaptation macros, X macros, and external codegen — each balance convenience, performance, and maintainability differently.

C++ will never have Java-style runtime reflection. The language's commitment to zero-cost abstraction and deterministic layout makes runtime metadata an optional extra rather than a built-in feature. But the combination of compile-time traits, `std::meta`, and disciplined macro usage provides the introspection capabilities that most programs actually need — at the cost of more deliberate design.

---

## Exercises

1. **Detection trait for a member function** — Write a trait `has_reserve<T>` that detects whether `T` has a member function `.reserve(std::size_t)`. Use both the `void_t` pattern and a C++20 `requires` expression.

2. **X-macro enum with flags** — Define an X-macro list of flag names. Generate an `enum class Flags` with powers-of-two values, a `to_string` function, and an `operator|` overload. Ensure adding a new flag updates all generated code.

3. **Tuple serializer** — Write a generic function `to_json` that accepts a `std::tuple` and returns a `nlohmann::json` array. Then extend it to produce an object (key-value pairs) by accepting an array of field name strings as a template argument.

4. **Visit struct with `std::meta` (C++26)** — Using the `std::meta` reflection facilities, write a `consteval` function that generates a visitor for a struct's members. The visitor should print each field name and value. (If your compiler does not support `std::meta`, sketch the solution as pseudocode.)

5. **Comparison** — Implement the same serialization task — writing a `Person` struct to JSON — using three different approaches: hand-written visitor, X macro, and Boost.Fusion adaptation. Compare the lines of code per type, the ease of adding a new field, and the quality of compiler error messages when a field type is not serializable.
