# Chapter 12: Monads in C++

Monads are a concept from category theory that has found practical application in functional programming. At their core, monads provide a structured way to handle computation contexts—wrapping values, chaining operations, and managing effects. While the term "monad" can seem intimidating, C++ programmers have been using monadic patterns implicitly for years, particularly with `std::optional` and `std::variant`.

This chapter explores monadic patterns in C++, showing how to structure code that handles optionality, error propagation, and side effects in a clean, composable way. We focus on practical patterns rather than theoretical foundations, giving you tools you can apply immediately in your codebase.

---

## Maybe/Optional Monad

The Maybe monad, known in C++ as `std::optional`, provides a type-safe way to represent values that may or may not be present. Rather than using sentinel values like `-1` or `nullptr`, `std::optional` makes the possibility of absence explicit in the type system.

### Understanding the Optional Type

The motivation for `std::optional` stems from the problems with sentinel values. Consider a function that searches for an element in a collection. Using traditional approaches, you might return a pointer that could be null, or a special value like `-1` for indices. Both approaches share a fundamental flaw: the caller must remember to check for the absence case, and nothing enforces this check at compile time.

When you use `std::optional`, the return type itself communicates that the value might be absent. The compiler enforces handling of the empty case, reducing the chance of undefined behavior from dereferencing null values.

```cpp
#include <optional>
#include <vector>
#include <string>

std::optional<int> find_index(const std::vector<int>& vec, int target) {
    for (std::size_t i = 0; i < vec.size(); ++i) {
        if (vec[i] == target) {
            return static_cast<int>(i);
        }
    }
    return std::nullopt;  // Explicitly return "no value"
}
```

This function returns `std::optional<int>` rather than a raw index. Callers must handle both the "found" and "not found" cases explicitly.

### Chaining Operations with monad bind

One of the key patterns in monadic programming is chaining operations that might fail. Instead of checking for presence at each step, you can use `and_then` to chain operations that return optional types. This is the "bind" operation for the Maybe monad.

```cpp
struct User {
    int id;
    std::string name;
    std::optional<std::string> email;
};

struct DatabaseConnection {
    // Simulated database operations
};

std::optional<User> find_user(DatabaseConnection& db, int id);
std::optional<std::string> get_email_from_user(const User& user);
std::optional<std::string> find_user_email(DatabaseConnection& db, int user_id) {
    return find_user(db, user_id)
        .and_then(get_email_from_user);
}
```

The `and_then` method takes a function that transforms the contained value into another optional. If the first optional is empty, the chain short-circuits and returns empty without calling the function. If the value is present, the function is applied to it.

This approach eliminates nested `if` statements and makes the flow of optional values explicit. Each step in the chain declares what it returns, and the composition handles the empty case uniformly.

### Transforming Values with map

While `and_then` handles chaining optional-to-optional operations, `map` (or `transform`) handles converting the contained value to a different type without unwrapping the optional.

```cpp
std::optional<User> user = find_user(db, 123);

// Transform the user name to uppercase
std::optional<std::string> upper_name = user.map([](const User& u) {
    std::string result = u.name;
    std::transform(result.begin(), result.end(), result.begin(), ::toupper);
    return result;
});

// Transform to just the user ID (int to something else)
std::optional<bool> has_email = user.transform([](const User& u) {
    return u.email.has_value();
});
```

The key insight is that `map` wraps the return value of the transformation in an optional automatically. If the input optional is empty, `map` returns empty without executing the transformation function.

### Handling the Empty Case

When you need to provide a default value or execute side effects based on presence, you have several options. The `value_or` method returns the contained value or a default if empty.

```cpp
std::optional<int> age = user.transform([](const User& u) { return u.age; });

int display_age = age.value_or(0);  // Use 0 as default if age not set
```

For more complex logic, pattern matching with `has_value()` and direct access works, though it sacrifices some of the chainability that makes monadic code pleasant.

```cpp
if (auto& user = find_user(db, 42)) {
    std::cout << "Found user: " << user->name << "\n";
} else {
    std::cout << "User not found\n";
}
```

The choice between these approaches depends on context. Use `value_or` for simple defaults, and explicit checks when you need to handle the empty case with more complex logic.

### Trade-offs and Considerations

The optional monad works best when the absence of a value is a normal, expected condition rather than an error. For error conditions, `std::optional` doesn't communicate what went wrong—only that something is missing. This limitation leads to the Either monad pattern discussed in the next section.

Performance-wise, `std::optional` typically has the same size as a pointer plus one bit (for the empty flag), though this varies by implementation. Inlined operations like `has_value()` and `map` should have minimal overhead, making optional a zero-cost abstraction for most use cases.

One caution: avoid nesting optionals like `std::optional<std::optional<T>>`. This creates awkward chains and confuses the "no value" semantics. Instead, flatten to `std::optional<T>` or use a different monad transformation.

---

## Either Monad for Error Handling

While `std::optional` handles simple presence/absence, it provides no information about *why* a value is absent. For error handling, the Either monad—implemented in C++ via `std::variant` or custom types—lets you encode both success and failure cases in the type system, making error handling explicit and composable.

### The Either Concept

The Either type represents a value that is one of two possibilities: a "left" value (conventionally the error case) or a "right" value (conventionally the success case). The names come from the mathematical tradition, though you can think of it as "either success with value X or failure with reason Y."

```cpp
template<typename Left, typename Right>
class Either {
    Left left_value;
    Right right_value;
    bool is_left;
public:
    // Construction and access methods...
};
```

In practice, you'll more often use `std::variant<E, T>` where `E` represents the error type and `T` represents the success type. The standard library variant is essentially a tagged union that always holds exactly one of its alternatives.

### Implementing a Result Type

While `std::variant` works, many projects create a dedicated `Result<T, E>` type that provides a more convenient interface. This wrapper makes the Either pattern explicit and adds utility methods.

```cpp
template<typename T, typename E>
class Result {
    std::variant<T, E> data;
public:
    static Result ok(T value) {
        Result r;
        r.data = std::move(value);
        return r;
    }

    static Result err(E error) {
        Result r;
        r.data = std::move(error);
        return r;
    }

    bool is_ok() const {
        return std::holds_alternative<T>(data);
    }

    T& value() {
        return std::get<T>(data);
    }

    const E& error() const {
        return std::get<E>(data);
    }

    template<typename F>
    template<typename F>
    auto and_then(F&& f) -> decltype(f(std::declval<T>())) {
        if (is_ok()) {
            return f(value());
        }
        return decltype(f(std::declval<T>()))::err(error());
    }

    template<typename F>
    auto map(F&& f) -> Result<decltype(f(std::declval<T>())), E> {
        if (is_ok()) {
            return ok(f(value()));
        }
        return err(error());
    }
};
```

This implementation shows the key operations: `ok()` and `err()` for construction, `is_ok()` for checking, `and_then()` for chaining operations that might fail, and `map()` for transforming success values.

### Error Propagation Patterns

When chaining operations that can fail, the Either monad lets you propagate errors without explicit error checking at each step. Each function returns a Result, and the chain automatically short-circuits on error.

```cpp
Result<User, DatabaseError> find_user(int id);
Result<Email, NetworkError> fetch_email(const User& user);
Result<void, EmailError> send_welcome(const Email& email);

Result<void, std::variant<DatabaseError, NetworkError, EmailError>>
send_welcome_email(int user_id) {
    return find_user(user_id)
        .and_then(fetch_email)
        .and_then(send_welcome);
}
```

The return type uses `std::variant` to hold any of the possible error types. When any step in the chain fails, the error propagates automatically, and the final result contains the specific error that occurred.

This pattern has several advantages over exception-based error handling. The error type is part of the function signature, making it explicit what can go wrong. Errors can't silently propagate past the call site unless explicitly allowed. And the compiler ensures you handle errors or explicitly propagate them.

### Transforming Errors

Sometimes you need to convert between error types—for example, when a low-level error needs to be mapped to a higher-level domain error. The `map_error` operation transforms the error while keeping a successful value intact.

```cpp
Result<User, std::string> find_user_by_name(const std::string& name) {
    auto result = database.find(name);
    if (!result) {
        // Map database error to domain error
        return Result<User, std::string>::err(
            "User not found: " + name
        );
    }
    return Result<User, std::string>::ok(*result);
}
```

More sophisticated error handling might involve error codes that get enriched with context as they propagate up the call stack. The Either monad accommodates this by allowing the error type to accumulate information.

### Comparison with Exceptions

The Either monad provides an alternative to exception-based error handling. Each approach has trade-offs that matter in different contexts.

Exceptions work well when errors are exceptional and should propagate implicitly. They separate the "happy path" from error handling, keeping normal code clean. However, exceptions can be hard to reason about—it's not always clear from the signature what might be thrown, and they interact poorly with asynchronous code.

The Either monad makes error handling explicit. The signature shows exactly what can go wrong. Errors compose naturally with monadic operations. And there's no performance overhead from stack unwinding.

The choice depends on your context. For library code that can't make assumptions about the caller, Either provides better guarantees. For application code where exceptions are acceptable, exceptions may be simpler. Many modern C++ projects use Either for recoverable errors while reserving exceptions for truly exceptional situations.

---

## IO Monad Concepts

The IO monad represents computations that interact with the outside world. In purely functional languages, IO is explicit—functions that perform input/output return an IO type rather than performing effects directly. C++ doesn't enforce this separation, but understanding the IO monad helps design interfaces that make side effects explicit and composable.

### Making Effects Explicit

In C++, there's nothing stopping any function from reading from stdin, writing to files, or modifying global state. This flexibility is both a strength and a weakness. When side effects are implicit, reasoning about code behavior becomes difficult.

The IO monad concept suggests making effects explicit in the type system. Rather than a function that "does something," we have a function that "produces an IO action" which, when executed, performs the effect.

```cpp
class IOString {
public:
    virtual ~IOString() = default;
    virtual std::string execute() const = 0;
};

class PrintLine : public IOString {
    std::string message;
public:
    explicit PrintLine(std::string msg) : message(std::move(msg)) {}

    std::string execute() const override {
        std::cout << message << "\n";
        return message;
    }
};

class ReadLine : public IOString {
public:
    std::string execute() const override {
        std::string line;
        std::getline(std::cin, line);
        return line;
    }
};
```

This approach wraps IO operations in types that describe the action. The actual side effects only occur when you explicitly "run" the IO action.

### Composing IO Actions

The monadic bind operation for IO allows chaining IO actions where each step can use the result of the previous step. This is similar to the Either monad's `and_then`, but the contained type is an IO action rather than a plain value.

```cpp
template<typename T>
class IO {
    std::function<T()> action;
public:
    explicit IO(std::function<T()> a) : action(std::move(a)) {}

    T run() const { return action(); }

    template<typename F>
    auto and_then(F&& f) const -> IO<decltype(f(std::declval<T>()).run())> {
        return IO<decltype(f(std::declval<T>()).run())>(
            [this, &f]() {
                T result = this->run();
                return f(result).run();
            }
        );
    }

    template<typename F>
    IO<F> map(F&& f) const {
        return IO<F>([this, &f]() { return f(this->run()); });
    }
};
```

This simplified implementation wraps a function that performs the actual IO. The `and_then` method chains IO actions, running the first and passing its result to the next.

### Practical Application

While full IO monad implementation is uncommon in C++, the underlying concepts appear in design patterns throughout modern C++ libraries. Task-based async libraries like `std::future` and custom async frameworks embody the idea of describing computation separately from execution.

The concept matters most in library design. When you create functions that perform IO, consider whether the side effect should be explicit in the type. For pure functions that happen to do IO, consider whether splitting the "describe the operation" phase from the "execute the operation" phase would improve the caller's control.

```cpp
// Imperative style - IO happens immediately
void save_to_file(const std::string& path, const std::string& data) {
    std::ofstream file(path);
    file << data;
}

// IO monad style - action is described, not executed
auto save_action = [](const std::string& path, const std::string& data) {
    return IO<void>([=]() {
        std::ofstream file(path);
        file << data;
    });
};

// Caller decides when to execute
auto save = save_action("config.txt", "content");
save.run();
```

The second style gives the caller more control—they can defer execution, execute it multiple times, or compose it with other IO actions. For many applications, this additional flexibility isn't worth the complexity, but for libraries and frameworks, it can be valuable.

---

## Monadic Bind and Lift Operations

The bind operation (often called `flatMap`, `chain`, or `>>=`) and the lift operation are fundamental to working with monadic types. Understanding these operations helps you write generic code that works with any monad and makes the patterns we've discussed in this chapter more explicit.

### Understanding Bind

The bind operation takes a monadic value `M<A>` and a function `A -> M<B>`, producing `M<B>`. The key characteristic is that the function returns a monad, not a plain value. Bind "unwraps" the value, applies the function, and rewraps the result.

```cpp
// Generic bind signature (conceptual)
template<typename M, typename F>
auto bind(M m, F f) -> /* resulting monad type */;

// For std::optional
std::optional<int> opt = /* ... */;
auto result = opt.and_then([](int x) -> std::optional<int> {
    return x > 0 ? std::make_optional(x * 2) : std::nullopt;
});
```

The "flat" in `flatMap` comes from the fact that the function returns a monad, so we avoid nesting like `M<M<A>>`. If we used `map` instead of `and_then`, we'd get `std::optional<std::optional<int>>`, which is rarely what we want.

### Understanding Lift

The lift operation (often called `map`) takes a regular function `A -> B` and "lifts" it to work with monadic values. The function is applied to the contained value, and the result is wrapped in the monad.

```cpp
// Generic lift signature (conceptual)
template<typename M, typename F>
auto lift(M m, F f) -> M< /* result type of f */ >;

// For std::optional
std::optional<int> opt = /* ... */;
auto result = opt.map([](int x) { return x * 2; });
```

The difference between bind and lift is fundamental: lift applies a pure function to a monadic value, while bind applies a function that returns a monadic value. Use lift when transforming contained values, use bind when chaining operations that produce monads.

### Custom Monads in C++

Creating custom monadic types follows a consistent pattern. You implement the constructor, the bind operation, and usually lift as well. Here's a sketch of a simple Result monad showing these concepts:

```cpp
template<typename T, typename E>
class Result {
    std::variant<T, E> value;
public:
    // Constructors
    static Result success(T v) { Result r; r.value = v; return r; }
    static Result failure(E e) { Result r; r.value = e; return r; }

    // Bind (>>=)
    template<typename F>
    auto operator>>=(F&& f) const {
        if (std::holds_alternative<T>(value)) {
            return f(std::get<T>(value));
        }
        return Resultfailure(std::get<E>(value));
    }

    // Lift
    template<typename F>
    auto fmap(F&& f) const {
        if (std::holds_alternative<T>(value)) {
            return Result::success(f(std::get<T>(value)));
        }
        return Result::failure(std::get<E>(value));
    }
};
```

With these operations defined, you can chain operations using operator `>>=` (the classic Haskell bind operator), creating readable pipelines of operations that may fail.

### Monadic Laws

Well-behaved monads should satisfy three laws, even though C++ doesn't enforce them:

**Left identity**: `return a >>= f` is equivalent to `f(a)` — wrapping a value and then binding produces the same as applying the function directly.

**Right identity**: `m >>= return` is equivalent to `m` — binding a monad to the return function produces the original monad.

**Associativity**: `(m >>= f) >>= g` is equivalent to `m >>= (lambda x: f(x) >>= g)` — the grouping of bind operations doesn't matter.

These laws ensure that monadic operations compose predictably. When you implement custom monads, keeping these laws in mind helps create intuitive behavior.

---

## Summary

The monad pattern provides a structured approach to handling optionality, errors, and effects in C++. While the theoretical foundation comes from category theory, practical application focuses on three key operations: `and_then` (bind) for chaining operations, `map` (lift) for transforming contained values, and explicit construction of the monadic type.

The Maybe/Optional monad, embodied by `std::optional`, handles the case where a value may or may not be present. Use it when absence is a normal, expected condition.

The Either monad, typically implemented with `std::variant` or a custom Result type, handles errors with explicit error types. Use it when callers need to know why an operation failed.

The IO monad makes side effects explicit in the type system. While full implementation is rare in C++, the concept influences async libraries and library design.

These patterns complement modern C++ features. Ranges work with optionals and variants. Coroutines can co_await monadic types. And the type system ensures you handle edge cases at compile time rather than runtime.

### Exercises

1. Implement a function that uses `std::optional::and_then` to navigate a nested structure, like finding a field within an optional struct within an optional container.

2. Create a simple Result type and implement the three main operations: `ok()`, `err()`, and `and_then()`. Use it to parse a configuration with multiple validation steps.

3. Refactor a function that uses exceptions to instead return a Result, making the error cases explicit in the type signature.

4. Write a small program demonstrating IO actions that are described but not executed until explicitly run, showing the separation of description and execution.