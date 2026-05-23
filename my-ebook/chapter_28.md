# Chapter 28: API Design

API design is the craft of defining how programmers interact with your code. A well-designed API makes the common case easy, the uncommon case possible, and the wrong thing difficult to express. A poorly designed API frustrates users, hides bugs behind misleading interfaces, and accumulates workarounds that ossify into technical debt.

This chapter covers four principles that together define what it means to design idiomatic C++ APIs. The first — the Rule of Least Surprise — is the governing meta-principle: an API should behave as its users intuitively expect, drawing on conventions from the standard library and from the wider C++ ecosystem. The second — Type Safety in APIs — shows how to use the type system to make illegal states unrepresentable and illegal operations uncompileable. The third — Builder and Fluent Interfaces — presents patterns for constructing complex objects with readable, composable initialization code. The fourth — Error Propagation Strategies — examines how to surface failures in a way that is impossible to ignore and easy to handle.

---

## Rule of Least Surprise

The Rule of Least Surprise (also called the Principle of Least Astonishment) states that a component should behave in a way that minimizes the cognitive burden on its users. The user should not have to read documentation to guess what a function does — the name, the signature, and the conventions of the surrounding ecosystem should make the behavior obvious.

This is not a matter of politeness or aesthetics. Surprising APIs produce bugs. When a function named `sort` rearranges a container, that is expected. When a function named `size` triggers a linear traversal, that is surprising and invites performance bugs. When a copy constructor actually shares state (the classic `auto_ptr` problem), that is surprising and invites use-after-free bugs. Each surprise is a defect waiting to happen, because the user will eventually forget the special case and treat the API as if it followed the rules.

### Consistency with Standard Library Conventions

The C++ standard library is the shared vocabulary of the language. Every C++ programmer knows that `.begin()` and `.end()` return iterators, that `.size()` returns the number of elements in constant time (since C++11 for containers), that `.empty()` is equivalent to `.size() == 0` but is guaranteed to be constant time even for containers that lack a `size` member, and that algorithms take iterator pairs as `(first, last)` with the last being exclusive.

Deviating from these conventions without good reason is a violation of the Rule of Least Surprise. Consider a custom container:

```cpp
// Surprising: non-standard naming, non-standard semantics.
class RingBuffer {
public:
    size_t count() const;           // why not size()?
    void put(int value);            // why not push_back?
    int get();                      // why not pop_front?
    void iterate(void(*cb)(int));   // why not begin/end?
};
```

A user encountering this API must learn a new vocabulary for operations they already know. The `iterate` callback mechanism prevents use of range-for, standard algorithms, and range adaptors — the entire ecosystem of C++ sequence processing is inaccessible. The cost is not just learning; it is lost interoperability.

The idiomatic version follows the standard conventions:

```cpp
class RingBuffer {
public:
    size_t size() const;
    bool empty() const;

    void push_back(int value);
    void pop_front();

    using iterator = /* ... */;
    iterator begin();
    iterator end();
};
```

Now the ring buffer works with range-for, `std::ranges` algorithms, and every tool that operates on a range. The user does not need to read documentation to guess how to use it — the API is self-explanatory because it follows the same contract as `std::deque`, `std::queue`, and every other sequence container.

The principle does not mean every API must mirror the standard library exactly. It means that when the standard library provides a well-known pattern for an operation, you should follow it unless you have a significant reason not to, and in that case you should document the deviation prominently. A `Matrix` class that uses `matrix(rows, cols)` for construction, `matrix.rows()` and `matrix.cols()` for dimensions, and `matrix(i, j)` for element access is not mimicking the standard library — it is following domain conventions. That is equally acceptable, because the user's expectation comes from the mathematical domain, not from the STL.

### Parameter Ordering Conventions

The standard library establishes clear patterns for parameter ordering:

- **Source first, destination second.** `std::copy(source_begin, source_end, dest_begin)` — the source comes before the destination. `std::ranges::copy(source_range, dest_begin)` follows the same convention.
- **Object first, operation arguments later.** `vec.insert(pos, value)` — the insertion position comes before the value. `vec.erase(first, last)` — the range comes before any additional policy.
- **Callbacks and comparators last.** `std::sort(begin, end, comp)`, `std::find_if(begin, end, pred)` — the operation's data comes first, the configurable behavior comes last.

Consider a custom `find_all` function that returns all positions where a predicate matches:

```cpp
// Surprising: callback is not the last parameter.
template <typename Range, typename Pred>
std::vector<size_t> find_all(Pred pred, const Range& range);
```

A user who writes `find_all(my_vec, is_even)` intending to search `my_vec` with predicate `is_even` will get a compilation error because the predicate is the first parameter but they passed it second. The user then checks the signature, adjusts the call, and mutters about the API designer. The standard-convention version:

```cpp
// Predictable: range first, callback last.
template <typename Range, typename Pred>
std::vector<size_t> find_all(const Range& range, Pred pred);
```

The principle is: **the thing being operated on comes first; the thing that customizes the operation comes last.** This matches the left-to-right reading order of "do this operation on this data with this configuration."

### Value Semantics and Surprising Behavior

C++ has value semantics by default: copying an object produces an independent clone. When an API deviates from this, the deviation must be obvious from the type system or the function signature.

The most infamous deviation in C++ history was `std::auto_ptr`, whose copy constructor transferred ownership instead of copying:

```cpp
std::auto_ptr<int> p1(new int(42));
std::auto_ptr<int> p2 = p1;    // p1 is now null!
*p1;                            // undefined behavior — surprising!
```

The assignment *looks* like a copy but is not. The type system gave no warning. The function signature — `auto_ptr(const auto_ptr&)` — looked exactly like a normal copy constructor. This violated the Rule of Least Surprise at the language level, and it is the primary reason `auto_ptr` was deprecated and replaced by `unique_ptr` (which makes the move explicit at the call site) and `shared_ptr` (which makes shared ownership explicit in the type).

The lesson for API design is: **never make a copy constructor or assignment operator do anything other than copy.** If your type cannot be copied, delete the copy operations (`Type(const Type&) = delete; Type& operator=(const Type&) = delete;`). If you want move semantics, provide a move constructor and mark it with `&&` at the call site. If you want shared ownership, require the user to wrap the type in `shared_ptr` explicitly. The type system should communicate the semantics.

A more subtle example is a class that *appears* to have value semantics but hides shared state:

```cpp
class String {
public:
    String(const char* s) : data_(new std::string(s)) {}
    // Default copy — shares the underlying string!?
private:
    std::shared_ptr<std::string> data_;
};
```

The default copy constructor copies the `shared_ptr`, producing two `String` objects that share the same underlying buffer. Modifying one appears to modify the other — a deep surprise for anyone expecting `std::string`-like value semantics. The fix is to implement the copy constructor to perform a deep copy, or to use `unique_ptr` (which forbids copying) and require explicit cloning.

The general rule: **if an object looks like a value (supports copying, assignment, comparison), it should behave like a value.** Each copy should be independent. If independence is expensive (a large matrix), consider making the type move-only (like `unique_ptr`) and providing a separate `clone()` method for explicit deep copying.

### Hidden Allocations and Side Effects

A function that looks cheap but allocates memory violates the Rule of Least Surprise. Consider a `merge` function for two sorted ranges:

```cpp
// Surprising: silently allocates a copy of the input.
std::vector<int> merge(const std::vector<int>& a, const std::vector<int>& b) {
    std::vector<int> result;
    result.reserve(a.size() + b.size());
    // merge into result ...
    return result;
}
```

This function is honest: its signature returns a new vector, so the allocation is expected. The problem arises when a function that *looks* like it operates in-place secretly allocates:

```cpp
class Bitmap {
public:
    void rotate(double degrees);
    // User expects: modifies *this in place.
    // Actual: allocates a new buffer, swaps, frees old.
};
```

The allocation is an implementation detail that leaks into performance. The user may call `rotate` in a tight loop expecting O(1) memory churn and instead trigger repeated heap allocations. The Rule of Least Surprise says: if the function modifies the object in place, it should not allocate unless it documents that it does. If allocation is unavoidable, consider a two-parameter design: `void rotate(double degrees, Allocator* alloc = {})` or a named alternative like `Bitmap rotate_copy(double degrees) const`.

The same principle applies to functions that acquire locks, open files, or start threads when the user does not expect it. A `getName()` const member function that acquires a mutex is surprising because `const` suggests thread-safe read-only access but the mutex acquisition introduces contention. The C++ standard library handles this with the `const`/non-`const` iterator split: `begin()` returns a `const_iterator` on a const container and an `iterator` on a non-const container, so the caller controls whether the operation is read-only or read-write.

### Operator Overloading and Expectations

Operator overloading is a powerful tool for making custom types feel like built-ins, but it is also a rich source of surprises. The cardinal rule: **operators should mean what users expect them to mean.**

`operator+` should be commutative, associative, and not modify its arguments. `operator+=` should modify the left-hand side and return a reference to it. `operator<` should establish a strict weak ordering (suitable for sorting and ordered containers). `operator==` should be an equivalence relation (reflexive, symmetric, transitive) and should be consistent with `operator<` if both are defined.

```cpp
// Good: + does not modify, += does, consistent semantics.
Matrix operator+(const Matrix& a, const Matrix& b);
Matrix& operator+=(Matrix& a, const Matrix& b);
```

A violation of these expectations creates bugs that are extremely hard to trace. Consider:

```cpp
// Surprising: operator+ modifies its left argument!
Vector& operator+(Vector& left, const Vector& right) {
    left.x += right.x;
    left.y += right.y;
    return left;
}
```

Now `v1 + v2` silently modifies `v1`. The user who writes `auto v3 = v1 + v2;` expects `v1` to remain unchanged. The result is a subtle mutation bug.

Another common surprise is overloading operators for unrelated semantics. `operator<<` for stream insertion is a well-established convention; `operator<<` for a matrix library that means "multiply" is surprising. `operator/` for a URI library that means "append path component" (`uri / "path"`) is a defensible domain-specific use, but it requires documentation and a strong convention. The same applies to `operator|` for range adaptors — it succeeds because the domain (pipeline composition) is clearly defined and the standard library established the convention.

The safest approach: **only overload an operator when at least one operand is a user-defined type, the operation is unambiguous, and the operator's conventional meaning maps cleanly to your domain.** When in doubt, use a named function.

### Const-Correctness Surprises

An API that is not const-correct violates the Rule of Least Surprise because it forces users into awkward workarounds. A `getValue` function that cannot be called on a const object, even though it logically does not modify the object, forces the user to cast away const or to store the object as non-const when it should be const:

```cpp
class Config {
public:
    std::string& get_value(const std::string& key);
    // Returns a non-const reference — cannot be called on const Config.
    // Even if the user only wants to read the value.
};
```

The fix is to provide const and non-const overloads, or to return by const reference or by value:

```cpp
class Config {
public:
    const std::string& get_value(const std::string& key) const;
    std::string& get_value(const std::string& key);
};
```

The reverse surprise is equally problematic: a member function marked `const` that modifies a data member through a pointer or reference, or uses `mutable` for caching or synchronization. While `mutable` has legitimate uses (caching, mutexes), it should be reserved for members whose mutation does not change the observable state of the object. A `const` function that logs access, updates a cache, or modifies a shared counter is transparent to the caller only if the caller cannot observe the mutation's effects.

### Implicit Conversions and Surprises

A single-argument constructor (or a constructor with all-but-one default arguments) defines an implicit conversion. This is sometimes convenient and sometimes disastrous:

```cpp
class Path {
public:
    Path(const char* s);  // implicit conversion from const char*
};

void open_file(const Path& p);

open_file("data.txt");  // works — implicit conversion
```

This is probably fine: converting a string literal to a `Path` is intuitive. But consider:

```cpp
class Database {
public:
    Database(int connection_pool_size);
    // Implicit conversion from int!
};

void process(Database db);

process(42);  // compiles — but what does this mean?
```

The user who writes `process(42)` probably meant something else. The implicit conversion silently creates a `Database` with 42 connections, which is unlikely to be what the caller intended. The fix is to mark the constructor `explicit`:

```cpp
explicit Database(int connection_pool_size);
// Now: process(42) is an error.
// process(Database(42)) is explicit and clear.
```

The principle: **make constructors `explicit` unless the implicit conversion is truly natural and lossless.** A `StringView(const char*)` constructor can be implicit because converting a string literal to a non-owning view is natural and lossless. A `Database(int)` constructor should be explicit because the meaning of the integer is not obvious from context.

The same applies to conversion operators. A `std::vector<bool>::reference` that implicitly converts to `bool` is natural. A custom `Status` class that implicitly converts to `int` (losing the error code semantics) is surprising:

```cpp
class Status {
public:
    explicit operator bool() const { return success_; }
    // explicit: the user must write static_cast<bool>(status) or
    // use it in a boolean context (if (status) { ... }).
};
```

Making the conversion explicit prevents accidental use of a `Status` value as an integer, which would lose the error code information.

### Exception Safety Promises

A function that throws an unexpected exception violates the Rule of Least Surprise. Consider:

```cpp
class Logger {
public:
    void write(const std::string& message);
    // User expects: basic exception guarantee (strong, if they check the docs).
    // Actual: may throw std::bad_alloc on every call.
};
```

If the user calls `write` from a destructor, the unexpected exception causes `std::terminate`. If they call it from a transaction rollback handler, the rollback itself fails, compounding the error. The fix is either to make the function `noexcept` (which guarantees it will not throw, forcing any errors to be handled internally) or to document the exceptions clearly.

The standard library follows a convention: `noexcept` on operations that cannot fail (destructors, `swap`, `size`, `empty`), and clear exception documentation for operations that can. Your API should do the same. A function that allocates memory can throw `std::bad_alloc` — that is expected. A function that reads a file can throw `std::ios_base::failure` — that is expected. A function named `get_value` that throws an unknown exception when the key is missing is surprising; it should return an `std::optional` or use `std::expected` (C++23) instead.

### Summary of the Rule

The Rule of Least Surprise is not a single prescriptive rule but a collection of conventions that, taken together, make an API predictable. The key heuristics:

- **Follow standard library conventions** for naming, parameter ordering, and semantics unless you have a strong reason not to.
- **Respect value semantics** — copy means independent copy, move means transfer, and the type system should communicate the difference.
- **Avoid hidden costs** — a function should not silently allocate, lock, or block unless its name and signature warn the user.
- **Overload operators conservatively** — follow conventional semantics or use named functions.
- **Be const-correct** — mark functions const when they do not modify the object's observable state, and provide const/non-const overloads when needed.
- **Mark constructors `explicit`** unless the implicit conversion is natural and lossless.
- **Document exception contracts** — make noexcept promises where appropriate, and do not throw from unexpected places.

These conventions are not restrictive — they are liberating. When every API in a project follows the same rules, users stop needing to check documentation for every call. They develop intuitions that transfer from one component to the next. The time saved accumulates across every line of code written against the API.

### Exercises

1. **Identify surprises.** Find an open-source C++ library you use or have used. Identify three APIs that violate the Rule of Least Surprise. For each, describe what a reasonable user would expect and what the API actually does. How would you fix each one?

2. **Conversion audit.** Review a codebase for single-argument constructors and conversion operators. Which ones should be marked `explicit`? Justify each decision.

3. **Parameter ordering.** Design an API for a `TextFormatter` class that takes a string, a width, a fill character, and an alignment mode. Discuss two different parameter orderings. Which one is least surprising, and why?

4. **Const audit.** Take a class with several getter methods. Are all of them const-correct? For any that are not, does the non-constness reveal a design issue (e.g., lazy initialization that should be explicit), or is it simply an oversight?

5. **Operator design.** You are designing a `BigInteger` class. Which operators would you overload? Which would you explicitly choose *not* to overload? What conventions would you follow for division and modulo with negative numbers?

---

## Type Safety in APIs

Type safety is the practice of using the type system to make illegal states unrepresentable and illegal operations uncompileable. Every type that the compiler can enforce is a constraint that the programmer does not have to remember, document, or test. A type-safe API shifts the burden of correctness from runtime checks and documentation to compile-time enforcement, where errors are caught earlier and cannot be forgotten.

The principle is sometimes called "making invalid states unrepresentable" or "pushing bugs from runtime to compile time." Each time you replace a runtime check with a type distinction, you eliminate an entire class of errors. The compiler becomes your first line of defense.

### The Problem: Stringly-Typed APIs

The most common violation of type safety is the "stringly-typed" API — one that uses strings, integers, or other generic types to represent domain concepts that have specific meaning:

```cpp
// Type-unsafe: the arguments are just strings.
void connect_to_db(const std::string& host,
                   const std::string& port,
                   const std::string& username,
                   const std::string& password);
```

What happens if the user accidentally swaps host and port, or username and password? The compiler cannot tell — they are all the same type. The error manifests only at runtime, when the connection fails or the authentication is rejected. Worse, the error may not be immediately detectable: swapping `host` and `username` might succeed against a different database, leaking data to the wrong server.

The type-safe version introduces distinct types for each concept:

```cpp
struct Host { std::string value; };
struct Port { std::string value; };
struct Username { std::string value; };
struct Password { std::string value; };

void connect_to_db(Host host, Port port, Username username, Password password);

// Usage:
connect_to_db(Host{"db.example.com"}, Port{"5432"},
              Username{"admin"}, Password{"s3cret"});
// The compiler rejects:
// connect_to_db(Host{"db.example.com"}, Port{"5432"},
//               Password{"s3cret"}, Username{"admin"});
```

Now the user cannot accidentally swap arguments of different domain concepts. The compiler enforces the mapping. The cost is a few lines of wrapper types and slightly more verbose call sites. The benefit is a compile-time guarantee that arguments of different domains cannot be interchanged.

For internal APIs used in a single codebase, the wrappers can be lightweight structs with an `auto`-deduced `.value` member. For public APIs, consider adding `explicit` constructors to prevent unintended implicit conversions from raw strings, and provide `operator std::string_view()` if users need to access the underlying value for printing or logging.

### Strong Typedefs and Opaque Wrappers

The pattern of wrapping a built-in type to give it a distinct identity is called a **strong typedef** (or newtype pattern). Unlike a simple `typedef` or `using` alias, which creates an alias for the same type, a strong typedef creates a new type that is distinct from its underlying representation:

```cpp
// Weak alias: Meter and Pixel are still int.
using Meter = int;
using Pixel = int;

Meter distance = 100;
Pixel width = 200;
// This compiles — but it should not:
Meter m = width;  // assignment from incompatible dimension
```

A strong typedef prevents this:

```cpp
template <typename T, typename Tag>
class StrongType {
public:
    explicit StrongType(T value) : value_(std::move(value)) {}
    const T& value() const { return value_; }
    T& value() { return value_; }

private:
    T value_;
};

using Meter = StrongType<int, struct MeterTag>;
using Pixel = StrongType<int, struct PixelTag>;

Meter distance(100);
Pixel width(200);
// Meter m = width;  // Error: no implicit conversion
// distance + width; // Error: no operator+ defined across types
```

The tag type (the incomplete struct `MeterTag`) ensures that `StrongType<int, MeterTag>` and `StrongType<int, PixelTag>` are distinct types even though they both wrap `int`. Each tag struct is declared but never defined — its only purpose is to give the compiler a unique type ID.

The Boost library provides `BOOST_STRONG_TYPEDEF` for this pattern, and the C++ standard library has `std::chrono::duration` and `std::chrono::time_point` as the most prominent standard examples of strong typedefs with unit safety.

The cost of strong typedefs is ergonomic: you cannot use the wrapped type's operators without providing them explicitly. You must decide which operations to support: comparison, arithmetic, streaming. Each missing operation is a compilation error for the user. This is by design — the strong typedef forces you to think about what operations are actually valid for the domain concept. `Meter + Meter` is valid; `Meter * Meter` produces `SquareMeter`, not `Meter`. The strong typedef makes you model this correctly instead of accidentally using `int` arithmetic.

### Making Illegal States Unrepresentable

The most powerful application of type safety is designing types so that certain invalid states cannot be constructed at all. This is the principle behind `std::optional<T>` (a value that may or may not be present), `std::variant<A, B>` (a value that is exactly one of several types), and `std::unique_ptr<T>` (a value that is either null or uniquely owns a resource). Each of these types encodes a constraint in the type system that previously had to be documented or checked at runtime.

Consider a `User` class with an email field:

```cpp
// Runtime enforcement: check every time the value is used.
class User {
public:
    void set_email(const std::string& email) {
        if (!is_valid_email(email)) {
            throw std::invalid_argument("invalid email");
        }
        email_ = email;
    }

    const std::string& email() const { return email_; }

private:
    std::string email_;  // May or may not be a valid email.
};

// Caller must handle the failure:
try {
    user.set_email("not-an-email");
} catch (const std::invalid_argument&) {
    // handle error
}
```

The problem is that `User::email_` is a `std::string`, which can hold any string, including invalid ones. The invariant (valid email) is not enforced by the type — it is enforced by runtime checks that can be bypassed if someone sets the member directly or constructs the object without calling `set_email`.

The type-safe approach creates an `Email` type that guarantees validity:

```cpp
class Email {
public:
    explicit Email(std::string s) : value_(std::move(s)) {
        if (!is_valid_email(value_)) {
            throw std::invalid_argument("invalid email address");
        }
    }

    const std::string& value() const { return value_; }

private:
    std::string value_;
};

class User {
public:
    User(std::string name, Email email)
        : name_(std::move(name)), email_(std::move(email)) {}

    const Email& email() const { return email_; }

private:
    std::string name_;
    Email email_;  // Guaranteed valid by its type.
};
```

Now `User::email_` cannot hold an invalid email — it is physically impossible because `Email` rejects invalid values in its constructor. Any code that receives an `Email` object can rely on its validity without checking. The invariant is enforced at the boundary (construction) and never needs to be re-checked.

This pattern — **parse, don't validate** — is a powerful design technique from the functional programming world that translates directly to C++. Instead of accepting a generic type and validating it (which must be done at every use), you accept a specific type whose constructor guarantees validity. The validation happens once, at the type boundary. Every subsequent use is automatically safe.

The pattern applies broadly:

```cpp
// Instead of:
void process_age(int age);  // Is 0 valid? Is -1 valid? Is 200 valid?
// Use:
class Age {
public:
    explicit Age(int years) : years_(years) {
        if (years < 0 || years > 150) {
            throw std::out_of_range("age out of range");
        }
    }
    int years() const { return years_; }
private:
    int years_;
};

void process_age(Age age);  // No validation needed: the type guarantees it.
```

The cost is one extra type per domain concept. The benefit is that validation is centralized, the type documents its constraints, and every function that accepts the type inherits the guarantee for free.

### Enum Classes vs. Unconstrained Integers

Plain `enum` types in C++ have a well-known type-safety weakness: they implicitly convert to `int`, and `int` implicitly converts to them:

```cpp
enum Color { Red, Green, Blue };
enum Shape { Circle, Square, Triangle };

Color c = 42;     // Compiles — unconstrained integer!
Shape s = Circle; // Compiles — cross-enum assignment!
if (c == s) { }   // Compiles — comparing Color and Shape!
```

Each of these is a type-safety failure. The compiler does not prevent using an arbitrary integer where a `Color` is expected, or mixing two different enum types. C++11's `enum class` fixes all of these:

```cpp
enum class Color { Red, Green, Blue };
enum class Shape { Circle, Square, Triangle };

Color c = 42;            // Error: no implicit conversion from int
Shape s = Color::Red;    // Error: Color is not Shape
if (c == s) { }          // Error: different types
```

The rule for API design is: **always use `enum class` instead of plain `enum`** unless you have a specific, documented reason to need implicit conversion to `int` (such as bitmask flags where the enum values need to be combined with `|`, in which case you should explicitly define the operators).

For bitmask use cases, the standard pattern is:

```cpp
enum class Permissions : uint32_t {
    Read  = 1 << 0,
    Write = 1 << 1,
    Exec  = 1 << 2,
};

// Define bitwise operators for the enum class.
constexpr Permissions operator|(Permissions a, Permissions b) {
    return static_cast<Permissions>(
        static_cast<uint32_t>(a) | static_cast<uint32_t>(b)
    );
}

// Usage:
Permissions p = Permissions::Read | Permissions::Write;
```

This preserves type safety (you cannot pass an arbitrary `uint32_t` where `Permissions` is expected) while allowing the bitwise operations that the domain requires.

### Parameter Objects for Complex Functions

A function with many parameters of the same type is a type-safety failure waiting to happen, regardless of strong typedefs. Consider:

```cpp
// Seven parameters, many of the same type.
void configure_engine(bool enable_physics, bool enable_audio, bool enable_networking,
                      int max_players, int tick_rate, int port,
                      const std::string& server_name);
```

A call like `configure_engine(true, false, true, 32, 60, 25565, "My Server")` is nearly unreadable. The user must count parameters and match them to the declaration. It is trivial to swap the two `bool` parameters or the three `int` parameters.

The fix is to introduce a parameter object — a struct that groups related configuration:

```cpp
struct EngineConfig {
    struct Features {
        bool physics     = true;
        bool audio       = true;
        bool networking  = true;
    };

    struct Network {
        int  port       = 25565;
        bool use_tls    = false;
    };

    Features    features;
    Network     network;
    int         max_players = 32;
    int         tick_rate   = 60;
    std::string server_name = "default";
};

void configure_engine(const EngineConfig& config);

// Usage:
configure_engine({
    .features = { .physics = true, .audio = true, .networking = true },
    .network  = { .port = 25565 },
    .max_players = 32,
    .tick_rate   = 60,
    .server_name = "My Server",
});
```

The parameter object improves type safety in two ways. First, named field initialization (C++20 designated initializers) makes each value's meaning visible at the call site. Second, the struct's default values mean the caller only specifies what differs from the defaults — reducing the number of arguments that can be misplaced.

For C++17 and earlier, which do not have designated initializers, the pattern uses a builder or named-argument idiom (covered in the next section). But even without syntactic sugar, a plain struct with sensible defaults is safer than seven positional parameters.

### Unit Safety with std::chrono

The C++11 `std::chrono` library is the standard library's most thorough example of type-safe API design. It demonstrates every principle in this section: strong typedefs (each duration is a distinct type), unit safety (you cannot add seconds and milliseconds without explicit conversion), and making illegal states unrepresentable (a `time_point` does not expose its raw representation unless you ask for it).

Before `std::chrono`, the typical API was:

```cpp
// Type-unsafe: both durations are plain integers.
void wait_for(int milliseconds);
void set_timeout(int seconds);

// User can easily swap units:
wait_for(1000);            // Is this milliseconds? Seconds? Microseconds?
set_timeout(300000);       // Same ambiguity — and a mistake is not caught.
```

With `std::chrono`, the type encodes the unit:

```cpp
void wait_for(std::chrono::milliseconds ms);
void set_timeout(std::chrono::seconds s);

// The type system enforces correctness:
wait_for(std::chrono::milliseconds(1000));
wait_for(std::chrono::seconds(1));          // Still OK — implicit conversion
// wait_for(1000);                          // Error: ambiguous
```

The user cannot pass a duration in the wrong unit because the type tells the compiler what unit to expect. If the user has a duration in a different unit, they must explicitly convert (or rely on `std::chrono`'s implicit conversion, which is safe because it goes from finer to coarser granularity — `seconds` to `milliseconds` is allowed, but the reverse requires `duration_cast`).

When designing your own APIs, consider whether any numeric parameter represents a quantity with a unit. If so, `std::chrono` is the model — and for non-time quantities (distances, masses, velocities), the same strong-typedef pattern applies.

### Non-Null Pointers and Reference Semantics

A raw pointer in C++ can be null. This is a type-safety problem because functions that accept pointers must document whether null is allowed, and callers must remember to check:

```cpp
// Does this function accept null?
void process_data(const int* data, size_t size);

// The caller does not know without reading documentation.
int* ptr = maybe_get_data();  // may be null
if (ptr) {
    process_data(ptr, 100);   // must check — but what if someone forgets?
}
```

The type-safe approach uses the type system to distinguish "nullable" from "non-null" references:

```cpp
// Non-null: use a reference.
void process_data(std::span<const int> data);
// Or:
void process_data(const std::vector<int>& data);

// Nullable: use a pointer.
void process_data_optional(const int* data, size_t size);
```

A `const&` or `std::span` cannot be null. By using a reference instead of a pointer, you encode the non-null invariant in the type. The caller cannot accidentally pass null, and the function does not need to check.

For cases where you need a nullable reference (an optional output parameter), C++17's `std::optional<T&>` (proposed but not yet standardized) or a non-owning pointer with clear documentation is the fallback. The guideline from the C++ Core Guidelines is: **use `T*` to denote "pointer to single object that may be null" and `T&` to denote "reference to single object that is never null."** The `gsl::not_null<T>` wrapper from the Guidelines Support Library makes the non-null guarantee explicit even for pointer types:

```cpp
#include <gsl/pointers>

void process_data(gsl::not_null<const int*> data, size_t size);
// The caller must check before calling, but the function knows it is never null.
```

This does not eliminate the null check entirely — the caller must still check before dereferencing. But it moves the responsibility to the single boundary where the pointer enters the non-null zone, rather than distributing it across every function that receives the pointer.

### Phantom Types for Distinguishing Identical Representations

Sometimes you have multiple concepts that share the same underlying representation but should not be interchangeable. A database library might have `TableId` and `RowId`, both of which are integers:

```cpp
// Unsafe: both are int.
void delete_row(int table_id, int row_id);
// What if the user swaps the arguments?
```

Strong typedefs solve this, but there is a more lightweight alternative called **phantom types** — template types where one or more template parameters do not appear in the type's representation but serve only to distinguish different instantiations:

```cpp
template <typename Tag>
class Id {
public:
    explicit Id(int64_t value) : value_(value) {}
    int64_t value() const { return value_; }
private:
    int64_t value_;
};

// Tags — never defined, only used as type discriminators.
struct TableTag {};
struct RowTag {};
struct UserTag {};

using TableId = Id<TableTag>;
using RowId   = Id<RowTag>;
using UserId  = Id<UserTag>;

// Now these are distinct types even though they all store int64_t.
void delete_row(TableId table_id, RowId row_id);
// delete_row(RowId(42), TableId(1));  // Error: wrong order
```

The phantom tag `TableTag` appears only as a template parameter — it is never instantiated, never stored, and has no runtime cost. Its only purpose is to give the compiler a way to distinguish `Id<TableTag>` from `Id<RowTag>`. The compiler generates zero code for the tag; it exists purely for type checking.

This pattern is widely used in the standard library. `std::chrono::duration<int64_t, std::ratio<1, 1000>>` and `std::chrono::duration<int64_t, std::ratio<1, 1>>` have the same representation (`int64_t`) but are different types because of the period parameter — which is a phantom type parameter.

### Compile-Time Enforcement vs. Runtime Checks

Type safety is not an all-or-nothing property. Every API has a spectrum of enforcement:

| Enforcement level | Mechanism | Error timing | Example |
|---|---|---|---|
| Compile-time | Type system, `static_assert`, concepts | At build | `std::is_integral_v<T>` constraint |
| Initialization-time | Constructor validation | At object creation | `Email` constructor throws on invalid input |
| Use-time | Precondition check | At each operation | `vector::at(size_t)` throws on out-of-range |
| Postcondition | Return value check | After operation | `fopen` returns null on failure |

The goal of type-safe API design is to move as many checks as possible **upward** — from use-time to initialization-time, from initialization-time to compile-time. Each level you climb eliminates an entire class of bugs.

Concepts (C++20) provide the strongest level of enforcement:

```cpp
template <typename T>
concept SortableContainer = std::ranges::contiguous_range<T>
    && std::sortable<std::ranges::iterator_t<T>>;

template <SortableContainer Cont>
void sort_and_process(Cont& container) {
    std::ranges::sort(container);
    // process...
}
```

If a caller passes a type that does not satisfy `SortableContainer`, the compilation fails with a clear error message before any code is generated. This is the gold standard of type safety: the bug never reaches the developer's runtime testing.

The investment in type safety pays off proportionally to the API's usage frequency. An internal function called in three places does not need the same level of protection as a public API called in hundreds of locations. The cost of the strong typedefs, parameter objects, and validation constructors should be weighed against the cost of debugging the errors they prevent.

### Summary of Type Safety Principles

- **Use strong typedefs** to distinguish domain concepts that share the same representation. A simple struct wrapper or template-based newtype prevents argument-swapping bugs at compile time.
- **Make illegal states unrepresentable** by moving validation into type constructors. Once a value is constructed, its invariants are guaranteed.
- **Use `enum class`** instead of plain `enum` to prevent implicit conversion to `int` and cross-enum mixing.
- **Replace long parameter lists with parameter objects** that use named fields and sensible defaults.
- **Use the type system to distinguish nullable from non-null.** References and `std::span` for non-null; raw pointers for nullable.
- **Use phantom types** when multiple concepts share the same representation but should remain distinct.
- **Use `std::chrono` as a model** for any quantity that has a unit — let the type encode the measurement dimension.
- **Push enforcement upward** — prefer compile-time constraints over runtime checks, and initialization-time validation over use-time checks.

The next section — Builder and Fluent Interfaces — shows how to combine type safety with readability for complex object construction.

### Exercises

1. **Stringly-typed audit.** Find a function in your codebase that takes three or more parameters of the same type (e.g., multiple `std::string` arguments). Introduce strong typedefs for each parameter. How many lines of code changed? Did the refactoring reveal any latent bugs?

2. **Making illegal states unrepresentable.** Design a `PositiveInteger` type that can only hold values greater than zero. Use it as a parameter type for a function that accepts array indices, ages, or page numbers. What operations does the type need? Should it support arithmetic?

3. **Enum class migration.** Take a plain `enum` used in your codebase and convert it to `enum class`. Which call sites required changes? Did you choose to define any operators on the new `enum class`?

4. **Unit safety.** Design a `Distance` strong typedef that distinguishes `Meters`, `Feet`, and `Kilometers`. Provide `operator+`, `operator-`, and conversion functions between units. Should `Meters + Feet` compile? If so, what should the result type be?

5. **Parameter object design.** Redesign the following API using a parameter object:

   ```cpp
   void send_message(const std::string& to, const std::string& from,
                     const std::string& subject, const std::string& body,
                     bool urgent, bool encrypt, int retry_count);
   ```

   Discuss what defaults make sense and whether any of the string parameters should be strong typedefs.

6. **Phantom types.** Implement a `Unit<T, Tag>` template where `T` is the numeric representation and `Tag` distinguishes different physical dimensions (Length, Mass, Time). Demonstrate that `Unit<double, LengthTag>` and `Unit<double, MassTag>` cannot be assigned to each other. Add `operator+` only for same-tag units.

---

## Builder and Fluent Interfaces

A fluent interface is an API design style where method calls can be chained because each method returns a reference (or a new object) that the next call can operate on. The term was coined by Eric Evans and Martin Fowler in 2005 to describe APIs that read like domain-specific languages, using method chaining to sequence operations in a natural reading order.

The Builder pattern is the most common application of fluent design in C++. It solves a specific problem: constructing objects that require many parameters, optional parameters, or complex validation before the object is considered valid. Where the Rule of Least Surprise governs naming and conventions, and Type Safety governs representation, the builder governs construction — the process of assembling a valid object step by step.

### The Telescoping Constructor Problem

A class with many optional parameters often ends up with a "telescoping" set of constructors:

```cpp
class Pizza {
public:
    Pizza();
    Pizza(Size size);
    Pizza(Size size, Crust crust);
    Pizza(Size size, Crust crust, std::vector<Topping> toppings);
    Pizza(Size size, Crust crust, std::vector<Topping> toppings,
          bool extra_cheese);
    Pizza(Size size, Crust crust, std::vector<Topping> toppings,
          bool extra_cheese, bool gluten_free);
    // ...
};
```

Each constructor adds one parameter. As the number of parameters grows, the number of constructors explodes combinatorially. The user must pick the right constructor, pass parameters in the right order, and remember default values. Swapping two `bool` parameters (like `extra_cheese` and `gluten_free`) is not caught by the compiler.

The telescoping constructor pattern also fails when many parameters have sensible defaults but the caller wants to override only one. To set `gluten_free = true` while accepting defaults for everything else, the caller must write `Pizza(Size::Medium, Crust::Regular, {}, false, true)` — writing out four values they do not care about.

The builder pattern solves all of these problems.

### Classic Builder (GoF)

The Gang of Four Builder pattern separates the construction of a complex object from its representation. The classic form uses a director and a builder interface:

```cpp
// Product.
class Pizza {
public:
    enum class Size { Small, Medium, Large };
    enum class Crust { Thin, Regular, DeepDish };
    struct Topping { std::string name; };

    Pizza(Size size, Crust crust, std::vector<Topping> toppings,
          bool extra_cheese, bool gluten_free);

    // ...
};

// Builder interface.
class PizzaBuilder {
public:
    virtual ~PizzaBuilder() = default;
    virtual void set_size(Size size) = 0;
    virtual void set_crust(Crust crust) = 0;
    virtual void add_topping(std::string name) = 0;
    virtual void set_extra_cheese(bool enabled) = 0;
    virtual void set_gluten_free(bool enabled) = 0;
    virtual Pizza build() = 0;
};

// Director — knows the construction sequence for a specific recipe.
class MargheritaDirector {
public:
    Pizza make(PizzaBuilder& builder) {
        builder.set_size(Pizza::Size::Medium);
        builder.set_crust(Pizza::Crust::Thin);
        builder.add_topping("mozzarella");
        builder.add_topping("tomato sauce");
        builder.add_topping("basil");
        builder.set_extra_cheese(true);
        return builder.build();
    }
};

// Concrete builder.
class ConcretePizzaBuilder : public PizzaBuilder {
    Size size_ = Size::Medium;
    Crust crust_ = Crust::Regular;
    std::vector<Pizza::Topping> toppings_;
    bool extra_cheese_ = false;
    bool gluten_free_ = false;

public:
    void set_size(Size size) override { size_ = size; }
    void set_crust(Crust crust) override { crust_ = crust; }
    void add_topping(std::string name) override {
        toppings_.push_back({std::move(name)});
    }
    void set_extra_cheese(bool enabled) override { extra_cheese_ = enabled; }
    void set_gluten_free(bool enabled) override { gluten_free_ = enabled; }
    Pizza build() override {
        return Pizza(size_, crust_, std::move(toppings_),
                     extra_cheese_, gluten_free_);
    }
};
```

This form is useful when there are multiple concrete builders that construct different representations of the same product (e.g., `JsonPizzaBuilder` produces JSON, `HtmlPizzaBuilder` produces HTML, `ConcretePizzaBuilder` produces a `Pizza` object). The director encapsulates the recipe, and the builder encapsulates the construction technique.

In practice, builder interfaces with virtual functions are rare in modern C++. The polymorphic builder is more common in Java and C# frameworks. In C++, the builder is usually a single concrete class that uses method chaining for a fluent API.

### Fluent Builder (Method Chaining)

The fluent builder drops the virtual interface and the director in favor of method chaining — each setter returns a reference to the builder itself:

```cpp
class Pizza {
public:
    enum class Size { Small, Medium, Large };
    enum class Crust { Thin, Regular, DeepDish };
    struct Topping { std::string name; };

    // ...

    class Builder {
    public:
        Builder& size(Size s) { size_ = s; return *this; }
        Builder& crust(Crust c) { crust_ = c; return *this; }
        Builder& add_topping(std::string name) {
            toppings_.push_back({std::move(name)});
            return *this;
        }
        Builder& extra_cheese(bool enabled = true) {
            extra_cheese_ = enabled;
            return *this;
        }
        Builder& gluten_free(bool enabled = true) {
            gluten_free_ = enabled;
            return *this;
        }

        Pizza build() {
            // Validate before constructing.
            if (toppings_.empty()) {
                throw std::invalid_argument("pizza must have at least one topping");
            }
            return Pizza(size_, crust_, std::move(toppings_),
                         extra_cheese_, gluten_free_);
        }

    private:
        Size size_ = Size::Medium;
        Crust crust_ = Crust::Regular;
        std::vector<Topping> toppings_;
        bool extra_cheese_ = false;
        bool gluten_free_ = false;
    };

private:
    Pizza() = default;  // Only the builder can construct.
    friend class Builder;

    // ...
};

// Usage:
Pizza pizza = Pizza::Builder()
    .size(Pizza::Size::Large)
    .crust(Pizza::Crust::Thin)
    .add_topping("pepperoni")
    .add_topping("mushrooms")
    .extra_cheese()
    .build();
```

The fluent builder has several advantages over telescoping constructors:

- **Named parameters.** Each value is labeled at the call site. The reader sees `.size(Large)` and `.crust(Thin)` instead of counting positional arguments.
- **Selective overrides.** The caller sets only what differs from the defaults. `.extra_cheese()` without touching size, crust, or toppings is a single method call.
- **Validation at build time.** The `build()` method validates the complete configuration before constructing the product. Partial state is never exposed because the product is only created when `build()` succeeds.
- **Immutability.** The `Pizza` class can have a private constructor and no setters, making it immutable after construction. The builder accumulates state, then produces an immutable result.

The idiom is to nest the `Builder` class inside the product class, make the product's constructors private, and declare `Builder` as a friend. This ensures that the only way to create a product is through the builder, which enforces all invariants.

### Builder with Move Semantics

When the builder accumulates expensive resources (like `std::vector` or `std::string` members), copying the builder becomes costly. The builder should be move-only or, at minimum, move the accumulated state into the product during `build()`:

```cpp
class Pizza::Builder {
public:
    Builder() = default;

    // Move-only builder.
    Builder(Builder&&) = default;
    Builder& operator=(Builder&&) = default;

    Builder& add_topping(std::string name) {
        toppings_.push_back(std::move(name));
        return *this;
    }

    Pizza build() {
        // Validate...
        return Pizza(size_, crust_, std::move(toppings_),
                     extra_cheese_, gluten_free_);
        // toppings_ is now empty — moved into the Pizza.
    }

    // ...
};
```

After `build()`, the builder is in a moved-from state and should not be used. This is acceptable because the builder is typically a temporary:

```cpp
auto pizza = Pizza::Builder()
    .size(Pizza::Size::Large)
    .add_topping("pepperoni")
    .build();
// The builder temporary is destroyed after .build().
```

If the user needs to keep the builder around (e.g., to create variations of a base configuration), they should not call `build()` on it more than once, or should provide a `clone()` method that copies the accumulated state.

### Builder with Compile-Time Enforcement (Stepped Builder)

A common complaint about the fluent builder is that it moves validation to `build()` — a runtime check. For parameters that are truly required, you can use a **stepped builder** that enforces the presence of required fields at compile time using phantom types:

```cpp
template <bool HasSize, bool HasCrust>
class PizzaBuilder {
public:
    // Can only call size() if size has not been set yet.
    auto size(Pizza::Size s) const {
        return PizzaBuilder<true, HasCrust>{*this, s};
    }

    // Can only call crust() if crust has not been set yet.
    auto crust(Pizza::Crust c) const {
        return PizzaBuilder<HasSize, true>{*this, c};
    }

    // build() is only available when all required fields are set.
    Pizza build() requires (HasSize && HasCrust) {
        return Pizza(size_, crust_);
    }

private:
    Pizza::Size size_;
    Pizza::Crust crust_;
};

// The starting type: both flags false.
using PizzaBuilderStart = PizzaBuilder<false, false>;

// Usage:
auto pizza = PizzaBuilderStart{}
    .size(Pizza::Size::Large)
    .crust(Pizza::Crust::Thin)
    .build();

// .crust().build() without .size() would fail to compile
// because PizzaBuilder<false, true>::build() is constrained away.
```

Each call to `size()` or `crust()` returns a new type that records which fields have been set as boolean template parameters. The `build()` method is constrained (via `requires`) to only be callable when all required fields are present. If the user forgets to set a required field, the program does not compile.

This pattern is sometimes called a **type-safe builder** or **phased builder**. It is useful in public APIs where forgetting a required parameter would be a common mistake. The trade-off is that the builder's type changes with each method call, which can confuse users who try to store the builder in an `auto` variable and use it multiple times. The builder is essentially a compile-time state machine.

For most C++ APIs, the runtime-validated builder (checking in `build()`) is sufficient. The stepped builder is reserved for high-stakes APIs where compile-time enforcement of required parameters is worth the complexity.

### Builder for Immutable Objects

One of the strongest motivations for the builder pattern is constructing immutable objects. An immutable object (all fields `const`, no setters) cannot be constructed incrementally — the constructor must receive all values at once. If the object requires many parameters, the constructor either telescopes or takes a parameter object.

The builder provides a middle ground: incremental accumulation during construction, followed by a single immutable product:

```cpp
class HttpRequest {
public:
    // Immutable: all fields are const.
    const std::string method;
    const std::string url;
    const std::map<std::string, std::string> headers;
    const std::vector<char> body;

    class Builder {
    public:
        Builder& method(std::string m) { method_ = std::move(m); return *this; }
        Builder& url(std::string u) { url_ = std::move(u); return *this; }
        Builder& header(std::string key, std::string value) {
            headers_.emplace(std::move(key), std::move(value));
            return *this;
        }
        Builder& body(std::vector<char> b) { body_ = std::move(b); return *this; }

        HttpRequest build() {
            if (method_.empty() || url_.empty()) {
                throw std::invalid_argument("method and url are required");
            }
            return HttpRequest(std::move(method_), std::move(url_),
                               std::move(headers_), std::move(body_));
        }

    private:
        std::string method_ = "GET";
        std::string url_;
        std::map<std::string, std::string> headers_;
        std::vector<char> body_;
    };

private:
    HttpRequest(std::string method, std::string url,
                std::map<std::string, std::string> headers,
                std::vector<char> body)
        : method(std::move(method)), url(std::move(url))
        , headers(std::move(headers)), body(std::move(body)) {}
};
```

The `HttpRequest` object has four `const` public members — no setters, no mutability after construction. The builder handles the incremental setup. This design makes `HttpRequest` trivially thread-safe (immutable objects need no synchronization) and easy to reason about.

### Fluent Interfaces Beyond Builders

Method chaining is useful outside the builder pattern. Any API that performs a sequence of operations on the same subject can benefit from fluency:

**Query builders:**

```cpp
auto results = db.query("SELECT * FROM users")
    .where("age > ?", 18)
    .where("status = 'active'")
    .order_by("name")
    .limit(10)
    .execute();
```

Each call returns a new or modified query object that accumulates constraints. The `execute()` terminal operation consumes the query and produces results.

**Stream manipulators (before C++20 ranges):**

```cpp
auto result = make_stream(values)
    | filter([](int x) { return x > 0; })
    | transform([](int x) { return x * 2; })
    | take(5);
```

The pipe operator `|` is method chaining in infix notation. The range adaptors are a non‑member fluent interface.

**Test assertions:**

```cpp
EXPECT_THAT(result, AllOf(Gt(0), Lt(100)));
// Fluent matchers compose naturally.
```

The Google Test matcher library uses fluency to compose assertions from small matcher objects.

**Logger configuration:**

```cpp
Logger::configure()
    .level(LogLevel::Debug)
    .output_file("app.log")
    .format("[%t] %m")
    .rotate_daily()
    .apply();
```

The terminal operation `apply()` atomically applies the configuration.

The common pattern in all these examples is: intermediate methods return an object of the same type (or a related type in the same hierarchy), and a terminal method consumes the accumulated state. The terminal method is what distinguishes a fluent interface from simple chaining — without it, every intermediate step would be a valid final state, which often makes no sense.

### Named Parameter Idiom (C++17 and Earlier)

Before designated initializers (C++20), C++ had no way to name constructor arguments at the call site. The named parameter idiom fills this gap using a lightweight builder-like pattern without a separate `build()` step:

```cpp
class Window {
public:
    // Named parameter setters, each returning a reference.
    Window& title(const std::string& t) { title_ = t; return *this; }
    Window& width(int w) { width_ = w; return *this; }
    Window& height(int h) { height_ = h; return *this; }
    Window& resizable(bool r) { resizable_ = r; return *this; }

    void show() {
        // Create and display the window using accumulated state.
    }

private:
    std::string title_ = "Untitled";
    int width_ = 800;
    int height_ = 600;
    bool resizable_ = true;
};

// Usage:
Window().title("My App").width(1024).height(768).show();
```

Here the `Window` class is itself the builder. Each setter returns `*this`, so calls chain. The `show()` method is the terminal operation. This approach is simpler than a nested Builder class because there is no separate product — the object under construction is the product itself.

The drawback is that the Window object exists in partially-constructed states during the chain. If `show()` calls a virtual function or accesses a resource before all parameters are set, the object may be in an invalid intermediate state. The nested Builder pattern avoids this because the product is only created after all parameters are accumulated.

Use the named parameter idiom directly on the class when construction is cheap, the object is used immediately, and there is no risk of using the object before configuration is complete. Use a separate Builder class when the product should be immutable, when validation requires the full parameter set, or when construction involves expensive resource acquisition.

### Trade-Offs and When to Use a Builder

The builder pattern adds code. A nested builder class with method chaining, validation, and move semantics can be two to three times longer than the product class itself. The cost is worth it when:

- **The object has many optional parameters** with sensible defaults. The builder lets callers specify only what they care about.
- **The object requires validation that depends on multiple parameters.** A single-parameter setter cannot validate cross-field constraints; the builder's `build()` method can.
- **The object should be immutable.** The builder is the only way to support incremental construction for an immutable type.
- **The construction involves resource acquisition** that should happen atomically. The builder accumulates lightweight handles; `build()` acquires the resources.
- **The API is a public interface** used by many callers. The builder's named methods serve as self-documenting API surface.

The builder is not worth it when:

- **The object has three or fewer parameters.** A plain constructor or aggregate initialization is simpler.
- **All parameters are required.** A single constructor with all parameters is clearer than forcing the user through a builder chain.
- **The object is created in a hot loop.** The builder's method calls and temporary state add overhead (though the compiler often inlines it away; profile first).
- **The API is internal to a single translation unit.** The maintenance cost of the builder outweighs the benefit for a handful of call sites.

The decision framework:

| Situation | Recommended approach |
|---|---|
| 1-3 parameters, all required | Constructor or aggregate init |
| 1-3 parameters, some optional | Default arguments in constructor |
| 4+ parameters, most optional | Fluent builder |
| Immutable product with many fields | Fluent builder |
| Cross-field validation needed | Fluent builder with validation in `build()` |
| Compile-time enforcement of required fields | Stepped builder (phantom types) |
| C++20, struct-like object | Designated initializers + default member init |
| Internal API, few call sites | Parameter object struct |
| One-off construction, no reuse | Inline aggregate or constructor |

### Summary of Builder and Fluent Interface Principles

- **Use method chaining** (`return *this`) to enable a fluent reading order: the code reads left to right, top to bottom, in the order of operations.
- **Provide sensible defaults** for every optional parameter. The default-constructed builder should produce a valid default product.
- **Validate in `build()`**, not in individual setters. Cross-field constraints need the full parameter set.
- **Move, don't copy**, in terminal operations. `build()` should steal the builder's resources, leaving the builder in a valid but unspecified state.
- **Nest the Builder inside the product class** and make the product's constructors private, so the builder is the only way to create the product.
- **Use a terminal method** (`build()`, `show()`, `execute()`, `apply()`) to mark the end of the fluent chain and produce the final result or side effect.
- **Prefer the nested Builder pattern over the named parameter idiom** when the product should be immutable or when construction is expensive.

### Exercises

1. **Builder refactoring.** Take a class with a telescoping constructor pattern (four or more constructors) and replace it with a fluent builder. Measure the change in lines of code. How does the caller code change?

2. **Immutable HTTP request.** Design an immutable `HttpResponse` class with status code, headers, and body. Implement a fluent builder. Ensure that `build()` validates that the status code is in a valid range and that required headers (like `Content-Type`) are present.

3. **Builder with cross-field validation.** A `Date` class has day, month, and year fields. Implement a builder that rejects invalid date combinations in `build()` (e.g., February 30). Should the builder also validate in individual setters, or is `build()` enough?

4. **Stepped builder.** Implement a stepped builder for a `DatabaseConnection` class that requires `host`, `port`, `username`, and `password` before `connect()` can be called. Use phantom types (boolean template parameters) to enforce that all four are set at compile time.

5. **Fluent query builder.** Design a minimal SQL query builder that supports `SELECT`, `FROM`, `WHERE`, `ORDER BY`, and `LIMIT`. The `SELECT` and `FROM` methods should be required before `execute()`; `WHERE`, `ORDER BY`, and `LIMIT` should be optional. The `execute()` method should return a `std::string` containing the assembled SQL.

6. **Builder vs parameter object.** Take the `EngineConfig` parameter object from the Type Safety exercises and rewrite it as a fluent builder. Compare the call sites. Which version do you find more readable? Which version enforces invariants more strictly? Discuss the trade-offs.

---

## Error Propagation Strategies

Error propagation is the mechanism by which a function signals to its caller that it could not deliver its promised result. It is one of the most consequential decisions in API design because the choice ripples through every call site, every test, and every maintenance change.

C++ offers more error propagation mechanisms than almost any other language: return codes, exceptions, `std::optional`, `std::expected` (C++23), out parameters, callbacks, termination handlers, and error-state objects. Choosing among them requires understanding the calling context, the performance requirements, the ABI constraints, and the semantic nature of the failure itself.

The sections that follow present each mechanism, its idiomatic use cases, its trade-offs, and a framework for deciding which one to use in a given API.

### The Landscape of Error Propagation

Before examining individual mechanisms, it is useful to see the full landscape. Every error propagation strategy can be characterized along three axes:

- **How the error is represented.** An exception is a special control-flow path. A return code is a value in the function's normal return channel. An out parameter writes to a caller-provided location. A callback invokes a separate function.
- **What the caller must do to handle the error.** Exceptions can be ignored (the stack unwinds until a handler is found, or `std::terminate` is called). Return codes can be ignored silently. `std::expected` forces the caller to check — the error is part of the type. Callbacks must be provided at the call site.
- **The performance characteristics.** Exceptions have zero normal-path cost but significant cold-path cost. Return codes have a branch on every call. `std::expected` has a branch on every access.

The following table summarizes the strategies:

| Strategy | Error representation | Caller must handle? | Normal-path cost | Cold-path cost | Best for |
|---|---|---|---|---|---|
| Exception | Separate control flow | No (can let propagate) | Zero (if no `throw`) | High (unwind + stack walk) | Exceptional conditions |
| Error code | Return value | No (can ignore) | Branch + move | Branch + move | Expected failures, C interop |
| `std::optional` | Return value | Partial (must check before use) | Branch + move | Branch + move | "No value" is not an error |
| `std::expected` | Return value | Yes (compile-time type) | Branch + move | Branch + move | Recoverable errors with typed info |
| Out parameter | Side channel | No | Pointer write | Pointer write | Performance-critical, legacy |
| Callback | Function call | Yes (must provide) | Branch (if optional) | Callback invocation | Async operations |
| Termination | Abort | No | Never returns | Never returns | Unrecoverable invariants |

Each row has legitimate uses. The challenge is matching the mechanism to the semantics of the failure.

### Exceptions: When and How

Exceptions are C++'s native error propagation mechanism. They have two properties that no other mechanism provides: **separation of normal and error paths** (the error handling code does not clutter the normal flow) and **automatic propagation** (intermediate functions do not need to explicitly forward errors).

```cpp
// The normal path is clean — no error checks between steps.
void process_user_data(const std::string& path) {
    auto data = read_file(path);           // may throw
    auto parsed = parse_json(data);        // may throw
    auto validated = validate(parsed);     // may throw
    store(validated);                      // may throw
}
```

The reader sees only the happy path. Every function can throw, and the exception propagates through any number of stack frames until it finds a handler. Intermediate functions need no error-handling code unless they need to translate, augment, or recover from the error.

This property is powerful, but it comes with constraints:

**Exceptions must be used for truly exceptional conditions.** If a failure is an expected outcome (file not found, network timeout, validation failure), exceptions make the control flow hard to reason about because the reader cannot tell which functions throw without checking the documentation or the source. The C++ Core Guidelines (and most C++ style guides) recommend using exceptions only for errors that the caller cannot reasonably be expected to handle at every call site.

**Exception safety guarantees must be documented.** Every function that throws (or calls a function that throws) makes one of four guarantees:

| Guarantee | Meaning | Example |
|---|---|---|
| No‑throw | Function never throws | Destructors, `swap`, `size()` |
| Strong | If throw, state is rolled back | `vector::push_back` (if copy fails, vector is unchanged) |
| Basic | If throw, no resources leak, invariants hold | Most mutating operations |
| None | If throw, object may be in an invalid state | Rare; only in low‑level code |

The caller depends on these guarantees. If a function documents the strong guarantee but actually provides only the basic guarantee, the caller's error recovery code may produce incorrect results. The `noexcept` specifier enforces the no-throw guarantee at compile time — if a `noexcept` function throws, `std::terminate` is called.

**Exceptions are unsuitable at ABI boundaries.** Exception handling mechanisms are implementation-defined (the Itanium C++ ABI specifies one scheme, MSVC uses another). Passing exceptions across shared library boundaries requires careful setup and is often avoided entirely. Libraries that cross ABI boundaries typically use error codes or `std::expected` instead.

**Exceptions have non-trivial cold-path cost.** When an exception is thrown, the runtime must unwind the stack, run destructors, and match handlers. This can be thousands of instructions. For expected errors that happen frequently, this cost is prohibitive.

The idiomatic rule is: **use exceptions for errors that the caller cannot reasonably handle at the point of call, and that occur rarely relative to the success path.** Use another mechanism for errors that the caller is expected to handle immediately and that occur frequently.

### Error Codes: Return Values with Semantic Information

Error codes communicate failure through the function's return channel. The classic C pattern returns an `int` and writes results through out parameters. The C++ improvement is `std::error_code`, which carries both a numeric code and a reference to an error category (domain), enabling rich error information without sacrificing efficiency:

```cpp
#include <system_error>

enum class FileError {
    NotFound = 1,
    PermissionDenied,
    Corrupted,
};

class FileErrorCategory : public std::error_category {
public:
    const char* name() const noexcept override { return "file"; }
    std::string message(int ev) const override {
        switch (static_cast<FileError>(ev)) {
        case FileError::NotFound:       return "file not found";
        case FileError::PermissionDenied: return "permission denied";
        case FileError::Corrupted:      return "file corrupted";
        default:                        return "unknown file error";
        }
    }
};

const FileErrorCategory file_error_category{};

std::error_code make_error_code(FileError e) {
    return {static_cast<int>(e), file_error_category};
}

// Make it work with std::error_code's implicit conversion.
namespace std {
    template <> struct is_error_code_enum<FileError> : true_type {};
}

// Usage in an API.
std::error_code read_config(const std::string& path, Config& out) {
    // On failure:
    if (!file_exists(path)) {
        return FileError::NotFound;
    }
    // On success:
    return {};  // default-constructed error_code means "no error"
}

// Caller:
Config cfg;
if (auto ec = read_config("config.json", cfg)) {
    // ec.message() provides a human-readable string.
    // ec.category().name() identifies the domain.
    std::cerr << "Error: " << ec.message() << "\n";
    return;
}
```

The advantage of `std::error_code` over a plain `int` is that it carries domain information. A function that returns `std::error_code` can produce errors from multiple domains (file I/O, network, parsing), and the caller can distinguish them without guessing. The `std::error_code` also composes naturally with `std::expected`.

The disadvantage is that the caller can ignore the return value. A caller that writes `read_config("config.json", cfg);` without checking the error code silently proceeds with uninitialized data. This is the fundamental weakness of error codes: they rely on programmer discipline.

For this reason, error codes are best used in:
- **C interop layers**, where C APIs already use error codes.
- **Hot paths**, where exception overhead is unacceptable and the caller handles errors immediately.
- **ABI boundaries**, where exception mechanisms cannot be relied upon.
- **Systems programming**, where every failure path must be explicit and auditable.

### std::optional: Absence as a Normal Outcome

`std::optional<T>` represents a value that may or may not be present. It is not an error-handling mechanism per se — it is a way to encode "no value" as a normal outcome:

```cpp
std::optional<User> find_user_by_id(Database& db, int64_t id) {
    auto result = db.query("SELECT * FROM users WHERE id = ?", id);
    if (result.empty()) {
        return std::nullopt;  // Not found — not an error.
    }
    return User{result[0]};
}

// Caller:
auto user = find_user_by_id(db, 42);
if (user) {
    process(*user);
} else {
    // User does not exist — handle gracefully.
}
```

Use `std::optional` when:
- The absence of a value is a normal, expected outcome (a map lookup, a search, a cache query).
- The caller has a sensible default or alternative path when the value is absent.
- The error condition can be fully described by "the thing does not exist" (no additional error code is needed).

Do not use `std::optional` when:
- The failure requires additional information (why was the value not found?).
- The failure is exceptional and should propagate across multiple stack frames.
- The caller needs to distinguish between different failure modes.

The `std::optional` API supports monadic operations since C++23 (`and_then`, `transform`, `or_else`) that let you chain operations that may or may not produce values:

```cpp
auto city = find_user_by_id(db, 42)
    .and_then([](User u) { return u.address(); })
    .transform([](Address a) { return a.city(); })
    .value_or("Unknown");
```

Each step returns `std::nullopt` if the previous step returned `std::nullopt`, short-circuiting the chain. This composes operations without nested `if` checks.

### std::expected: Value-or-Error with Type Safety

`std::expected<T, E>` (C++23, available in `std::experimental` in earlier versions, or via the proposed `tl::expected` reference implementation) represents either a value of type `T` or an error of type `E`. It is like `std::optional` but with attached error information:

```cpp
#include <expected>

enum class ParseError { InvalidSyntax, UnexpectedToken, Overflow };

std::expected<Config, ParseError> parse_config(std::string_view text) {
    if (text.empty()) {
        return std::unexpected(ParseError::InvalidSyntax);
    }
    // Parse...
    return Config{/* ... */};
}

// Caller must acknowledge the error:
auto result = parse_config(input);
if (result) {
    Config& cfg = *result;
    use(cfg);
} else {
    switch (result.error()) {
    case ParseError::InvalidSyntax:
        // Handle syntax error.
        break;
    // ...
    }
}
```

The key difference from error codes is that the caller **cannot use the value without acknowledging the possibility of an error**. The `expected<T, E>` type does not implicitly convert to `T`. The caller must explicitly check (via `operator bool` or `.has_value()`) or use one of the monadic operations. This eliminates the "forgotten error code" class of bugs.

`std::expected` supports the same monadic operations as `std::optional`:

```cpp
auto result = parse_config(input)
    .and_then(validate_config)
    .transform(apply_defaults)
    .or_else([](ParseError e) -> std::expected<Config, ParseError> {
        // Attempt recovery.
        return Config::defaults();
    });
```

The monadic chain lets you compose fallible operations without nested error checks. If any step returns `std::unexpected`, the chain short-circuits and the error propagates to the final result.

`std::expected` is the recommended default for recoverable errors in new C++ code (C++23 and later) because it combines the explicitness of error codes with the type safety that error codes lack. It is suitable for:

- **Functions that can fail in expected ways** (network timeouts, validation failures, I/O errors).
- **APIs where every failure must be handled** or explicitly propagated.
- **Code that needs to compose multiple fallible operations** in a pipeline.

The downsides are:
- **Every call site checks.** This makes the happy path more verbose than exceptions.
- **Propagation must be explicit.** Unlike exceptions (which propagate automatically), `expected` must be returned and checked at each level, or propagated via `.and_then()`. This can be verbose in deeply nested call stacks.
- **Move-only errors.** If `E` is move-only (like `std::unique_ptr<ErrorInfo>`), using `expected` requires care.

### Out Parameters: The Legacy Pattern

An out parameter is a non-const reference or pointer through which the function writes its result:

```cpp
bool parse_int(const std::string& s, int& out) {
    char* end = nullptr;
    long val = std::strtol(s.c_str(), &end, 10);
    if (*end != '\0') {
        return false;
    }
    out = static_cast<int>(val);
    return true;
}
```

Out parameters were common in C++98 and earlier, but they have several well-known problems:

- **The caller must construct a default value** before calling. For types without sensible default states, this is awkward or impossible.
- **Exception safety is tricky.** If the function writes to the out parameter and then throws, the output is partially written — the caller cannot rely on the result.
- **Readability suffers.** `parse_int("42", result)` does not communicate the direction of data flow as clearly as `auto result = parse_int("42")`.
- **Argument ordering errors.** When multiple out parameters have the same type, the caller can swap them without the compiler complaining.

Modern C++ idioms prefer return values over out parameters. Return-value optimization (RVO) and guaranteed copy elision (C++17) eliminate the copy overhead that once motivated out parameters for large types. If the type is move-only, move it out of the function:

```cpp
// Modern: return by value (RVO elides the copy).
std::optional<int> parse_int(const std::string& s);
// Or:
std::expected<int, ParseError> parse_int(const std::string& s);
```

The only remaining legitimate use of out parameters is:
- **Pre-allocated buffers**, where the caller owns the memory and the function fills it.
- **Performance-critical loops** where the allocation in every return-by-value would be too expensive (though in practice, RVO eliminates this cost for most types).
- **C interop**, where the C API requires a pointer-to-pointer or pointer-to-buffer pattern.

### Error Callbacks

For asynchronous APIs, the caller cannot receive a return value because the function returns before the operation completes. The idiomatic C++ pattern for async error propagation is to pass a callback:

```cpp
template <typename SuccessCb, typename ErrorCb>
void fetch_data(std::string url,
                SuccessCb on_success,
                ErrorCb on_error) {
    // Start async operation...
    // When done, call on_success(data) or on_error(error).
}

// Usage:
fetch_data("https://api.example.com/data",
    [](const std::vector<char>& data) {
        // Handle success.
    },
    [](std::error_code ec) {
        // Handle error.
    });
```

The separation of success and error callbacks is clearer than a single callback with an error code parameter, because the two paths are handled by different functions. The error callback type can be `std::function<void(std::error_code)>`, and the success callback can be `std::function<void(Data)>`, making it impossible for the caller to accidentally mix the two paths.

For coroutine-based APIs (see Chapter 27), the error propagation is implicit — the coroutine either returns a value or throws an exception at the co_await point:

```cpp
// Coroutine-based async API.
Task<Data> fetch_data(std::string url) {
    auto response = co_await http_client.get(url);
    if (response.status != 200) {
        throw HttpError{response.status};
    }
    co_return response.body;
}

// The caller's error handling is identical to synchronous code:
try {
    Data data = co_await fetch_data("https://...");
    // Use data.
} catch (const HttpError& e) {
    // Handle error.
}
```

Coroutines combine the readability of synchronous exception handling with the efficiency of asynchronous execution. This is the direction the C++ ecosystem is moving for async error propagation.

### Two-Phase Construction and Factory Functions

Constructors have a special relationship with error propagation. A constructor cannot return an error — it can only complete successfully or throw. This creates a tension when object construction may fail in expected ways (a file cannot be opened, a network connection cannot be established).

The anti-pattern is **two-phase construction**: a default constructor followed by an `init()` or `open()` function that returns an error code:

```cpp
// Anti-pattern: two-phase construction.
class DatabaseConnection {
public:
    DatabaseConnection() = default;  // Creates an invalid object.
    bool connect(const std::string& connection_string);  // Returns false on failure.
    void query(const std::string& sql);  // Undefined behavior if connect() failed.
};
```

The problem is that the object exists in an invalid state between construction and `connect()`. Every method must check whether the object has been initialized, adding branches and complexity. The user can accidentally call `query()` on an unconnected object.

The idiomatic alternatives are:

**1. Throwing constructor.** The constructor throws if it cannot acquire the resource. The object is never created in an invalid state:

```cpp
class DatabaseConnection {
public:
    explicit DatabaseConnection(const std::string& connection_string)
        : handle_(open_connection(connection_string))
    {
        if (!handle_) {
            throw std::runtime_error("failed to connect to database");
        }
    }

    void query(const std::string& sql) {
        // handle_ is guaranteed valid.
    }

private:
    ConnectionHandle handle_;
};
```

The disadvantage is that exceptions cannot be used at ABI boundaries or in hot paths.

**2. Factory function returning `expected`.** A static factory function performs the construction and returns an error on failure:

```cpp
class DatabaseConnection {
public:
    static std::expected<DatabaseConnection, std::error_code>
    create(const std::string& connection_string) {
        auto handle = open_connection(connection_string);
        if (!handle) {
            return std::unexpected(make_error_code(Error::ConnectionFailed));
        }
        return DatabaseConnection(std::move(handle));
    }

    void query(const std::string& sql) {
        // handle_ is guaranteed valid.
    }

private:
    explicit DatabaseConnection(ConnectionHandle handle)
        : handle_(std::move(handle)) {}

    ConnectionHandle handle_;
};

// Usage:
auto conn = DatabaseConnection::create("db:localhost");
if (conn) {
    conn->query("SELECT 1");
}
```

The factory function keeps the constructor private, so the only way to create a `DatabaseConnection` is through `create()`, which returns a properly initialized object or an error. No invalid state is possible.

**3. Builder pattern (from the previous section).** The builder accumulates configuration, and `build()` returns an `expected` or throws:

```cpp
auto conn = DatabaseConnection::Builder()
    .host("localhost")
    .port(5432)
    .credentials("admin", "s3cret")
    .build();  // Returns expected<DatabaseConnection, error_code>
```

The factory function approach is the most common for objects whose construction may fail. It combines the safety of `std::expected` with the guarantee that every constructed object is valid.

### Error Propagation at ABI Boundaries

When a library is distributed as a shared object (`.so` or `.dll`), the boundary between the library and its callers is an **ABI boundary**. Exceptions cannot safely cross ABI boundaries unless both sides use the same compiler, the same standard library, and the same exception handling ABI. In practice, this means exceptions are unusable across shared libraries on most platforms.

The standard solution for ABI-safe error propagation is `std::error_code`:

```cpp
// Public API exported from a shared library.
extern "C" EXPORT_SYMBOL
std::error_code library_initialize(const LibraryConfig* config);
```

The `std::error_code` type has a stable ABI (it is just an `int` and a pointer), so it can cross shared library boundaries safely. The error category pointer must point to a statically-allocated category object that is available at link time.

For C++20 modules, the situation is similar: modules do not solve the ABI compatibility problem because exceptions still depend on the runtime library. `std::expected` has the same issue if `E` is a complex type that depends on the standard library's layout.

### Termination for Unrecoverable Errors

Some errors are not recoverable. A violated precondition, a failed invariant check, or a detected memory corruption cannot be handled meaningfully — the program is already in an undefined state. For these, the idiomatic response is `std::terminate` or `std::abort`:

```cpp
void check_invariant(bool condition) {
    if (!condition) {
        std::cerr << "FATAL: invariant violated\n";
        std::terminate();
    }
}
```

Termination should be reserved for conditions where:
- Continuing would cause data corruption or security vulnerabilities.
- The error is a programming bug (assertion failure, null pointer dereference), not a runtime condition.
- Recovery is impossible because the program state is undefined.

User-facing errors (file not found, network timeout, invalid input) should never call `std::terminate`. Programming errors (null pointer passed where non-null was required, invalid enum value) are candidates for termination, but even those can be handled more gracefully with the contract facilities in C++26 (or with custom termination handlers that write crash dumps).

### Choosing the Right Strategy

No single strategy is correct for every API. The decision depends on the nature of the failure, the calling context, and the performance requirements. The following decision tree summarizes the idiomatic choices:

**Is the error a programming bug (precondition violation, invariant failure)?**
- Yes → Use `assert` (debug builds) or `std::terminate` (release builds for truly unrecoverable cases). The error indicates a bug in the caller, and handling it gracefully only hides the bug.

**Can the operation fail in practice, and is the failure an expected outcome?**
- Yes → Is the absence of a value sufficient to describe the failure?
  - Yes → Use `std::optional<T>`. Example: map lookup, cache query, search.
  - No → Do you need to cross an ABI boundary?
    - Yes → Use `std::error_code`. Example: shared library API, plugin interface.
    - No → Does the caller need to handle the error immediately at every call site?
      - Yes → Use `std::expected<T, E>`. Example: parsing, validation, I/O.
      - No → Use exceptions. Example: resource acquisition, algorithm failure.

**Is the operation asynchronous?**
- Yes → Use callbacks (with separate success/error handlers) or coroutines (with exceptions or `expected`).

**Is the operation in a hot path (called millions of times per second)?**
- Yes → Use `std::error_code` or `std::expected` with a trivially copyable error type. Avoid exceptions entirely.

### Summary of Error Propagation Principles

- **Match the mechanism to the semantics.** Exceptions for exceptional conditions, `std::optional` for absent values, `std::expected` for recoverable errors with information, error codes for ABI boundaries and hot paths, termination for unrecoverable bugs.
- **Never use two-phase construction.** A constructor should either fully initialize the object or throw. If the constructor cannot throw (ABI constraints), use a factory function returning `std::expected`.
- **Document exception safety guarantees.** Every function that may throw should document which guarantee it provides (no‑throw, strong, basic, none).
- **Prefer return values over out parameters.** RVO and guaranteed copy elision make return-by-value efficient. Out parameters are only justified for pre-allocated buffers and C interop.
- **Use `std::error_code` for ABI boundaries.** It is the only portable error mechanism across shared libraries.
- **Propagate errors explicitly in async code.** Callbacks with separate success/error handlers are clearer than a single callback with an error code. Coroutines provide the best of both worlds — synchronous-looking code with async error handling.
- **Terminate on unrecoverable errors.** Do not try to handle corrupted state gracefully — abort and restart.

The three sections of this chapter — the Rule of Least Surprise, Type Safety in APIs, Builder and Fluent Interfaces, and Error Propagation Strategies — are not independent. They reinforce each other. A type-safe API with fluent construction and consistent error semantics is an API that users trust. Each principle reduces the cognitive load on the caller, and together they define what it means to design a C++ API that feels right.

### Exercises

1. **Exception vs expected audit.** Find a function in your codebase that uses exceptions for a frequently-occurring error (e.g., file not found, network timeout). Refactor it to use `std::expected` instead. Compare the call sites before and after. What changed in readability? What changed in performance?

2. **Factory function design.** A `TempFile` class creates a temporary file in its constructor and deletes it in its destructor. The constructor may fail (disk full, permission denied). Redesign it using:
   a. A throwing constructor.
   b. A factory function returning `std::expected<TempFile, std::error_code>`.
   Discuss the trade-offs.

3. **Error code categories.** Implement an `std::error_category` for a domain of your choice (e.g., a graphics library, a networking library, a compression library). Ensure it integrates with `std::error_code` so that your error enum values can be implicitly converted to `std::error_code`.

4. **Monadic error handling.** Given three functions that return `std::expected`:

   ```cpp
   std::expected<A, Error> step1();
   std::expected<B, Error> step2(A);
   std::expected<C, Error> step3(B);
   ```

   Write code that calls all three in sequence using `and_then`, propagating errors automatically. Then write the equivalent code using exceptions. Compare the two versions.

5. **Async error handling.** Design an API for an async image downloader. The caller provides a URL and receives a callback when the download completes. Design the callback interface. Should you use separate success/error callbacks, a single callback with an `expected` parameter, or a coroutine? Justify your choice.

6. **Two-phase construction refactoring.** Find an example of two-phase construction in your codebase (a default constructor followed by an `init()` or `open()` method). Refactor it to use either a throwing constructor or a factory function. What safety guarantees did the refactoring add?
