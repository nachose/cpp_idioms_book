# Chapter 11: Function Composition

Function composition is a fundamental concept from mathematics and computer science that enables building complex operations from simpler ones. In C++, functional programming patterns have evolved significantly since C++11, with lambdas, the standard library algorithms, and modern features like ranges enabling elegant composition patterns. This chapter explores how to construct, combine, and apply functions as building blocks, enabling a more declarative programming style that expresses *what* to compute rather than *how* to compute it.

This chapter covers four related techniques: higher-order functions that accept or return other functions, monadic operations that wrap values and provide chainable transformations, function adapters that modify function behavior, and lazy evaluation patterns that defer computation until results are needed.

## Higher-Order Functions in C++

A higher-order function is a function that either takes other functions as arguments or returns a function as its result. This concept enables powerful abstraction patterns, allowing code to be written in terms of general operations that can be customized through function parameters.

### Functions as Parameters

The most common form of higher-order function passes functions as arguments to template functions or algorithms:

```cpp
#include <algorithm>
#include <vector>
#include <iostream>

// A function that takes a function as parameter
template<typename Func>
void applyTwice(std::vector<int>& values, Func transform) {
    for (auto& val : values) {
        val = transform(val);
        val = transform(val);  // Apply twice
    }
}

// Alternative: take function pointer explicitly
void applyFunction(std::vector<int>& values, int (*func)(int)) {
    for (auto& val : values) {
        val = func(val);
    }
}

int main() {
    std::vector<int> data = {1, 2, 3, 4, 5};

    // Using a lambda
    applyTwice(data, [](int x) { return x * 2; });

    // Using a function pointer
    applyFunction(data, [](int x) { return x + 1; });

    // Using std::transform with a lambda
    std::vector<int> result;
    std::transform(data.begin(), data.end(), std::back_inserter(result),
                   [](int x) { return x * x; });

    for (int v : result) {
        std::cout << v << " ";
    }
}
```

The key insight is that functions become data—passed around, stored, and invoked dynamically. This decoupling separates the algorithm (applyTwice) from the specific operation (transform), enabling reuse with different transformations.

### Functions as Return Values

Functions can also be returned from other functions, enabling factory functions that create specialized functions:

```cpp
#include <functional>

// Function returning a function
std::function<int(int)> makeMultiplier(int factor) {
    return [factor](int x) { return x * factor; };
}

// Template version avoiding std::function overhead
template<typename T>
auto makeAdder(T offset) {
    return [offset](T x) { return x + offset; };
}

// Function returning a function pointer
auto (*makeProcessor(bool fast))(int) {
    if (fast) {
        return [](int x) { return x * 2; };  // Fast path
    }
    return [](int x) { return x + 1; };      // Slow path
}

int main() {
    auto triple = makeMultiplier(3);
    auto addTen = makeAdder(10);

    std::cout << triple(5) << "\n";    // 15
    std::cout << addTen(5) << "\n";    // 15

    auto fastProc = makeProcessor(true);
    std::cout << fastProc(7) << "\n";  // 14
}
```

This pattern is useful for creating functions with pre-configured state, like factories for callbacks or event handlers.

### Generic Higher-Order Functions

Writing generic higher-order functions requires template parameters to accept any callable:

```cpp
#include <utility>

// Generic function that accepts any callable
template<typename Func, typename... Args>
decltype(auto) invoke(Func&& func, Args&&... args) {
    return std::forward<Func>(func)(std::forward<Args>(args)...);
}

// Generic function that accepts a predicate
template<typename Container, typename Predicate>
bool anyOf(const Container& c, Predicate pred) {
    for (const auto& elem : c) {
        if (pred(elem)) {
            return true;
        }
    }
    return false;
}

// Fold/reduce operation
template<typename Container, typename BinaryOp>
decltype(auto) fold(const Container& c, BinaryOp op) {
    auto it = std::begin(c);
    if (it == std::end(c)) {
        return std::decay_t<decltype(*it)>{};
    }

    auto result = *it;
    ++it;
    for (; it != std::end(c); ++it) {
        result = op(result, *it);
    }
    return result;
}

// Usage
int main() {
    std::vector<int> numbers = {1, 2, 3, 4, 5};

    // Check if any element is even
    bool hasEven = anyOf(numbers, [](int x) { return x % 2 == 0; });

    // Sum all elements
    int sum = fold(numbers, [](int a, int b) { return a + b; });

    // Find maximum
    int max = fold(numbers, [](int a, int b) { return a > b ? a : b; });

    std::cout << "Has even: " << hasEven << "\n";
    std::cout << "Sum: " << sum << "\n";
    std::cout << "Max: " << max << "\n";
}
```

Generic higher-order functions work with any callable—lambdas, function objects, member functions, and function pointers—through the unified call operator syntax.

### Capturing State in Higher-Order Functions

Lambdas can capture local variables, enabling higher-order functions that create stateful closures:

```cpp
#include <functional>

// Factory creating stateful functions
auto makeCounter() {
    int count = 0;
    return [count = 0]() mutable { return ++count; };
}

// Function creating a memorizing function
template<typename Func>
auto makeMemoized(Func&& func) {
    using ResultType = std::invoke_result_t<Func, int>;
    return [func = std::forward<Func>(func), cache = std::map<int, ResultType>{}] (int arg) mutable {
        if (cache.find(arg) == cache.end()) {
            cache[arg] = func(arg);
        }
        return cache[arg];
    };
}

// Stateful predicate
auto makeThresholder(int threshold) {
    return [threshold](int value) { return value >= threshold; };
}

int main() {
    auto counter = makeCounter();
    std::cout << counter() << "\n";  // 1
    std::cout << counter() << "\n";  // 2
    std::cout << counter() << "\n";  // 3

    auto fib = makeMemoized([](int n) {
        if (n <= 1) return n;
        return fib(n - 1) + fib(n - 2);
    });

    std::cout << fib(10) << "\n";  // 55 (computed once)

    auto isLarge = makeThresholder(100);
    std::cout << isLarge(50) << "\n";   // false
    std::cout << isLarge(150) << "\n";  // true
}
```

The mutable keyword is essential when the lambda modifies captured variables—without it, the lambda's operator() is const by default.

### Higher-Order Functions with Multiple Functions

Some higher-order functions accept multiple function arguments, enabling complex composition:

```cpp
#include <functional>

// Compose two functions: compose(f, g)(x) = f(g(x))
template<typename F, typename G>
auto compose(F&& f, G&& g) {
    return [f = std::forward<F>(f), g = std::forward<G>(g)](auto&& x) {
        return f(g(std::forward<decltype(x)>(x)));
    };
}

// Curry-like pattern
template<typename F>
auto curry(F&& f) {
    return [f = std::forward<F>(f)](auto a) {
        return [f, a](auto b) {
            return f(a, b);
        };
    };
}

// Binary function to unary function with fixed argument
template<typename F, typename T>
auto partial(F&& func, T&& arg) {
    return [func = std::forward<F>(func), arg = std::forward<T>(arg)](auto&&... args) {
        return func(arg, std::forward<decltype(args)>(args)...);
    };
}

// Usage
int main() {
    auto addOne = [](int x) { return x + 1; };
    auto doubleIt = [](int x) { return x * 2; };

    // compose: f(g(x)) - apply g first, then f
    auto addOneThenDouble = compose(doubleIt, addOne);
    std::cout << addOneThenDouble(3) << "\n";  // (3+1)*2 = 8

    // Partial application
    auto addFive = partial([](int a, int b) { return a + b; }, 5);
    std::cout << addFive(3) << "\n";  // 5 + 3 = 8

    // Using std::bind for partial application
    auto multiplyByThree = std::bind(std::multiplies<int>(), std::placeholders::_1, 3);
    std::cout << multiplyByThree(4) << "\n";  // 12
}
```

These patterns enable building complex transformations from simple, reusable components.

### Member Function Higher-Order Patterns

C++ provides special handling for member functions (including member function pointers and std::mem_fn):

```cpp
#include <functional>
#include <vector>
#include <string>

struct Person {
    std::string name;
    int age;

    std::string greet() const { return "Hello, I'm " + name; }
};

int main() {
    std::vector<Person> people = {
        {"Alice", 30},
        {"Bob", 25},
        {"Charlie", 35}
    };

    // Using std::mem_fn to create callable from member function
    auto greet = std::mem_fn(&Person::greet);

    // Using std::bind with member functions
    std::function<std::string(const Person&)> getName = std::bind(&Person::name, std::placeholders::_1);

    // Using std::mem_fn with member data
    auto getAge = std::mem_fn(&Person::age);

    // Transform using member functions
    std::vector<std::string> greetings;
    for (const auto& p : people) {
        greetings.push_back(greet(p));
    }

    for (const auto& g : greetings) {
        std::cout << g << "\n";
    }
}
```

The member function pointer syntax (`&Person::greet`) combined with `std::mem_fn` or `std::bind` enables treating member functions as first-class callable objects.

### Function References vs std::function

A key decision when writing higher-order functions is whether to use template parameters or `std::function`:

```cpp
// Template: accepts any callable, preserves type, enables inlining
template<typename Func>
void processTemplate(Func f) {
    f(42);
}

// std::function: type erasure, runtime polymorphism, heap allocation for large captures
void processFunction(std::function<void(int)> f) {
    f(42);
}

// Performance comparison for simple lambdas
void demonstrate() {
    auto lambda = [](int x) { return x * 2; };

    // Template: typically inlined, no allocation
    processTemplate(lambda);

    // std::function: may allocate, introduces indirection
    processFunction(lambda);

    // For stateful lambdas, std::function may allocate
    auto stateful = [counter = 0](int) mutable { return ++counter; };
    processFunction(stateful);  // May heap-allocate for the lambda
}
```

Prefer template parameters when the callable is a template argument—it's more efficient and enables compiler optimizations. Use `std::function` when type erasure is needed, such as when storing heterogeneous callables in a container or when the function signature must be part of a public interface.

### Summary

Higher-order functions are functions that accept functions as parameters or return functions. They enable abstraction by parameterizing behavior, separating the algorithm from the specific operation. Generic higher-order functions use templates to accept any callable. Closures capture state through lambda captures. Compose functions from simpler pieces using composition patterns. Choose between template parameters and std::function based on performance requirements and type erasure needs.

---

## Monadic Operations on Containers

Monadic operations transform containers by applying functions to their elements while preserving the container structure. The term "monad" comes from functional programming—a monad is a pattern that wraps a value and provides operations that work with the wrapped value while preserving the wrapper. In C++, containers like std::vector, std::optional, and std::variant exhibit monadic behavior through operations like map, flatMap (bind), and filter.

### Understanding Monads

A monad consists of three components: a type constructor (the wrapper), a unit function (wrapping a value), and a bind function (chain operations). For containers:

```cpp
// Container is the type constructor: vector<T>
// Unit wraps a value: make_from_iterator, single-element container
// Bind chains operations: flatMap/flatMap

// The monadic pattern:
template<typename T>
std::vector<T> unit(T value) {
    return std::vector<T>{value};
}

// map: (Container<T>, T -> U) -> Container<U>
template<typename T, typename Func>
auto map(const std::vector<T>& container, Func f) {
    std::vector<std::invoke_result_t<Func, T>> result;
    result.reserve(container.size());
    for (const auto& elem : container) {
        result.push_back(f(elem));
    }
    return result;
}

// flatMap/bind: (Container<T>, T -> Container<U>) -> Container<U>
template<typename T, typename Func>
auto flatMap(const std::vector<T>& container, Func f) {
    using ResultType = std::invoke_result_t<Func, T>;
    ResultType result;
    for (const auto& elem : container) {
        auto inner = f(elem);
        result.insert(result.end(), inner.begin(), inner.end());
    }
    return result;
}

int main() {
    std::vector<int> numbers = {1, 2, 3, 4, 5};

    // map: double each number
    auto doubled = map(numbers, [](int x) { return x * 2; });
    // {2, 4, 6, 8, 10}

    // flatMap: generate all pairs with another vector
    auto pairs = flatMap(numbers, [](int x) {
        std::vector<std::pair<int, int>> result;
        for (int y = 0; y < 3; ++y) {
            result.push_back({x, y});
        }
        return result;
    });
    // {(1,0), (1,1), (1,2), (2,0), (2,1), (2,2), ...}
}
```

The key difference between map and flatMap is that map transforms each element to a single value (preserving container size), while flatMap transforms each element to a container and flattens the results.

### Map on Containers

The map operation applies a function to each element, returning a new container with the transformed elements:

```cpp
#include <vector>
#include <iostream>
#include <string>
#include <sstream>

// Generic map implementation for containers
template<typename Container, typename Func>
auto mapContainer(const Container& c, Func f) {
    using T = std::decay_t<decltype(*std::begin(c))>;
    using U = std::invoke_result_t<Func, T>;

    std::vector<U> result;
    result.reserve(std::distance(std::begin(c), std::end(c)));

    for (const auto& elem : c) {
        result.push_back(f(elem));
    }
    return result;
}

// Using std::transform as the standard alternative
void demonstrateTransform() {
    std::vector<int> numbers = {1, 2, 3, 4, 5};

    // std::transform with lambda
    std::vector<int> squared;
    std::transform(numbers.begin(), numbers.end(), std::back_inserter(squared),
                   [](int x) { return x * x; });

    // Transform to different type
    std::vector<std::string> strings;
    std::transform(numbers.begin(), numbers.end(), std::back_inserter(strings),
                   [](int x) { return std::to_string(x); });

    for (const auto& s : strings) {
        std::cout << s << " ";
    }
}

int main() {
    std::vector<int> data = {1, 2, 3, 4, 5};

    // Using custom map
    auto result = mapContainer(data, [](int x) { return x * 3; });

    for (int v : result) {
        std::cout << v << " ";
    }
    std::cout << "\n";

    demonstrateTransform();
}
```

std::transform is the standard library's primary tool for map operations, but the custom implementation shows the underlying pattern.

### FlatMap/Bind Operations

FlatMap (also called flatMap, chain, or >>= in functional languages) applies a function that returns a container and flattens the results:

```cpp
#include <vector>
#include <iostream>
#include <optional>

// Flatten a container of containers
template<typename Container>
auto flatten(const Container& c) {
    using Inner = std::decay_t<decltype(*std::begin(c))>;
    using ValueType = std::decay_t<decltype(*std::begin(std::declval<Inner>()))>;

    std::vector<ValueType> result;
    for (const auto& inner : c) {
        for (const auto& elem : inner) {
            result.push_back(elem);
        }
    }
    return result;
}

// FlatMap: map then flatten
template<typename Container, typename Func>
auto flatMap(const Container& c, Func f) {
    return flatten(mapContainer(c, f));
}

// Practical example: finding all possible moves in a game
struct Position { int x, y; };

std::vector<Position> getValidMoves(Position p) {
    std::vector<Position> moves;
    // Add all 4-directional moves
    moves.push_back({p.x + 1, p.y});
    moves.push_back({p.x - 1, p.y});
    moves.push_back({p.x, p.y + 1});
    moves.push_back({p.x, p.y - 1});
    return moves;
}

std::vector<Position> getAllReachable(Position start, int depth) {
    if (depth == 0) {
        return {start};
    }

    auto moves = getValidMoves(start);
    std::vector<Position> result;

    for (const auto& move : moves) {
        auto reachable = getAllReachable(move, depth - 1);
        result.insert(result.end(), reachable.begin(), reachable.end());
    }

    return result;
}

int main() {
    auto all = getAllReachable({0, 0}, 2);
    for (const auto& p : all) {
        std::cout << "(" << p.x << "," << p.y << ") ";
    }
}
```

FlatMap is essential for expressing queries like "find all elements, then for each element find all related elements, then flatten".

### Filter (Where)

Filter (or "where" in some languages) selects elements that satisfy a predicate:

```cpp
#include <vector>
#include <iostream>
#include <algorithm>

template<typename Container, typename Predicate>
auto filter(const Container& c, Predicate pred) {
    using T = std::decay_t<decltype(*std::begin(c))>;

    std::vector<T> result;
    std::copy_if(c.begin(), c.end(), std::back_inserter(result), pred);
    return result;
}

// Chaining monadic operations
void demonstrateChaining() {
    std::vector<int> numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Pipeline: filter even numbers, then square them
    auto result = mapContainer(
        filter(numbers, [](int x) { return x % 2 == 0; }),
        [](int x) { return x * x; }
    );

    // Alternative: chain through accumulate
    auto pipeline = numbers
        | std::views::filter([](int x) { return x % 2 == 0; })
        | std::views::transform([](int x) { return x * x; });

    for (int v : result) {
        std::cout << v << " ";
    }
    std::cout << "\n";

    for (int v : pipeline) {
        std::cout << v << " ";
    }
}

int main() {
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Filter: keep only numbers greater than 5
    auto filtered = filter(data, [](int x) { return x > 5; });

    // Compose: filter then map
    auto transformed = mapContainer(filtered, [](int x) { return x * 2; });

    for (int v : transformed) {
        std::cout << v << " ";
    }
}
```

The pipeline pattern (using the | operator) provides a readable way to chain monadic operations.

### Reduce/Fold on Containers

Reduce (or fold) combines all elements into a single value using a binary operation:

```cpp
#include <numeric>
#include <vector>
#include <iostream>
#include <functional>

// Generic fold implementation
template<typename Container, typename Initial, typename BinaryOp>
auto fold(const Container& c, Initial init, BinaryOp op) {
    return std::accumulate(c.begin(), c.end(), init, op);
}

// Fold without initial value (uses first element as initial)
template<typename Container, typename BinaryOp>
auto fold1(const Container& c, BinaryOp op) {
    if (c.empty()) {
        throw std::runtime_error("Cannot fold empty container");
    }
    return std::accumulate(std::next(c.begin()), c.end(), *c.begin(), op);
}

// Group by operation
template<typename Container, typename KeyFunc>
auto groupBy(const Container& c, KeyFunc keyFunc) {
    using Key = std::invoke_result_t<KeyFunc, std::decay_t<decltype(*c.begin())>>;
    std::map<Key, std::vector<std::decay_t<decltype(*c.begin())>>> result;

    for (const auto& elem : c) {
        result[keyFunc(elem)].push_back(elem);
    }
    return result;
}

int main() {
    std::vector<int> numbers = {1, 2, 3, 4, 5};

    // Sum using fold
    int sum = fold(numbers, 0, std::plus<>{});
    std::cout << "Sum: " << sum << "\n";

    // Product using fold
    int product = fold(numbers, 1, std::multiplies<>{});
    std::cout << "Product: " << product << "\n";

    // Max using fold
    int max = fold1(numbers, [](int a, int b) { return a > b ? a : b; });
    std::cout << "Max: " << max << "\n";

    // Group words by length
    std::vector<std::string> words = {"one", "two", "three", "four", "five"};
    auto grouped = groupBy(words, [](const std::string& s) { return s.length(); });

    for (const auto& [len, ws] : grouped) {
        std::cout << "Length " << len << ": ";
        for (const auto& w : ws) {
            std::cout << w << " ";
        }
        std::cout << "\n";
    }
}
```

Fold is fundamental—it can implement map, filter, and many other operations. Understanding fold helps recognize when patterns can be simplified.

### Optional as a Monad

std::optional provides monadic operations that handle absence elegantly:

```cpp
#include <optional>
#include <iostream>
#include <string>

// Map on optional: transform if present, preserve absence
template<typename T, typename Func>
std::optional<std::invoke_result_t<Func, T>> mapOptional(
    const std::optional<T>& opt, Func f) {
    if (opt.has_value()) {
        return f(opt.value());
    }
    return std::nullopt;
}

// FlatMap on optional: chain optional-returning functions
template<typename T, typename Func>
auto flatMapOptional(const std::optional<T>& opt, Func f) {
    if (opt.has_value()) {
        return f(opt.value());
    }
    return std::invoke_result_t<Func, T>{};
}

// Chaining optional operations
struct User {
    std::string name;
    std::optional<std::string> email;
};

std::optional<std::string> getEmail(const User& user) {
    return user.email;
}

std::optional<std::string> getDomain(const std::string& email) {
    auto pos = email.find('@');
    if (pos != std::string::npos) {
        return email.substr(pos + 1);
    }
    return std::nullopt;
}

int main() {
    User user1 = {"Alice", "alice@example.com"};
    User user2 = {"Bob", std::nullopt};
    User user3 = {"Charlie", "charlie@invalid"};

    // Chain: get user email domain, safely handling absence
    auto getDomainSafe = [](const User& u) -> std::optional<std::string> {
        if (!u.email) return std::nullopt;
        return getDomain(*u.email);
    };

    std::cout << getDomainSafe(user1).value_or("none") << "\n";  // example.com
    std::cout << getDomainSafe(user2).value_or("none") << "\n";  // none
    std::cout << getDomainSafe(user3).value_or("none") << "\n";  // none

    // Using C++17's optional::and_then (monadic bind)
    std::cout << user1.email.and_then(getDomain).value_or("none") << "\n";
}
```

Optional monads eliminate nested if-checks for presence, making the code express the happy path clearly.

### Result/Either Monad Pattern

Error handling can use a Result type (similar to Haskell's Either) that represents either a success value or an error:

```cpp
#include <variant>
#include <optional>
#include <iostream>
#include <string>

template<typename T, typename E>
class Result {
    std::variant<T, E> value;

public:
    static Result success(T v) { Result r; r.value = std::move(v); return r; }
    static Result failure(E e) { Result r; r.value = std::move(e); return r; }

    bool isSuccess() const { return std::holds_alternative<T>(value); }
    bool isFailure() const { return std::holds_alternative<E>(value); }

    T& get() { return std::get<T>(value); }
    const E& error() const { return std::get<E>(value); }

    // Map: transform success value
    template<typename Func>
    auto map(Func f) -> Result<std::invoke_result_t<Func, T>, E> {
        if (isSuccess()) {
            return Result<std::invoke_result_t<Func, T>, E>::success(f(get()));
        }
        return Result<std::invoke_result_t<Func, T>, E>::failure(error());
    }

    // FlatMap: chain operations that might fail
    template<typename Func>
    auto flatMap(Func f) -> std::invoke_result_t<Func, T> {
        if (isSuccess()) {
            return f(get());
        }
        return f(E{});  // Propagate error type
        return std::invoke_result_t<Func, T>::failure(error());
};

// Using Result for error handling
Result<int, std::string> parseInt(const std::string& s) {
    try {
        return Result<int, std::string>::success(std::stoi(s));
    } catch (...) {
        return Result<int, std::string>::failure("Invalid integer");
    }
}

Result<double, std::string> divide(int a, int b) {
    if (b == 0) {
        return Result<double, std::string>::failure("Division by zero");
    }
    return Result<double, std::string>::success(static_cast<double>(a) / b);
}

int main() {
    // Chain of operations that can fail
    auto result = parseInt("42")
        .map([](int x) { return x * 2; })
        .map([](int x) { return x + 1; });

    if (result.isSuccess()) {
        std::cout << "Result: " << result.get() << "\n";
    }

    // Propagate errors
    auto failResult = parseInt("not-a-number")
        .flatMap([](int) { return divide(10, 0); });

    if (failResult.isFailure()) {
        std::cout << "Error: " << failResult.error() << "\n";
    }
}
```

This pattern makes error handling explicit in the type system—functions that can fail return Result types, and callers must handle both success and failure cases.

### Summary

Monadic operations provide a consistent interface for transforming containers. Map applies a function to each element, returning a container of results. FlatMap applies a function that returns a container and flattens the results. Filter selects elements matching a predicate. Fold/reduce combines all elements into a single value. Optional provides monadic operations for handling absence. Result types handle error cases monadically. Together, these operations enable a declarative, pipeline-based programming style.

---

## Function Adapters and Composition

Function adapters modify or combine functions to create new functions. They enable building complex operations from simple, reusable components. C++ provides several function adapters in the standard library, and we can create custom adapters for specific needs.

### Function Pointer Adapters

C++ provides adapters for function pointers through std::bind and function objects:

```cpp
#include <functional>
#include <iostream>

void printSum(int a, int b) {
    std::cout << a << " + " << b << " = " << (a + b) << "\n";
}

int main() {
    // Bind specific arguments
    auto printFivePlus = std::bind(printSum, 5, std::placeholders::_1);
    printFivePlus(3);  // 5 + 3 = 8

    // Bind in different positions
    auto printPlusFive = std::bind(printSum, std::placeholders::_1, 5);
    printPlusFive(3);  // 3 + 5 = 8

    // Reorder arguments
    auto printReversed = std::bind(printSum, std::placeholders::_2, std::placeholders::_1);
    printReversed(3, 5);  // 5 + 3 = 8

    // Bind to member functions
    struct Counter {
        int count = 0;
        void increment(int n) { count += n; }
    };

    Counter c;
    auto incrementByThree = std::bind(&Counter::increment, &c, 3);
    incrementByThree();
    std::cout << "Count: " << c.count << "\n";
}
```

std::bind creates new function objects by binding some arguments to specific values, leaving others as placeholders for later specification.

### Negation Adapters

Negation adapters invert the result of predicates:

```cpp
#include <algorithm>
#include <vector>
#include <functional>
#include <iostream>

int main() {
    std::vector<int> numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // std::not_fn (C++17) negates a predicate
    auto isEven = [](int x) { return x % 2 == 0; };
    auto isOdd = std::not_fn(isEven);

    std::vector<int> oddNumbers;
    std::copy_if(numbers.begin(), numbers.end(), std::back_inserter(oddNumbers), isOdd);

    // Using std::not1 for unary predicates (deprecated in C++17 in favor of not_fn)
    // auto oldStyleNot = std::not1(std::ptr_fun(isEven));

    for (int n : oddNumbers) {
        std::cout << n << " ";
    }
    std::cout << "\n";

    // Compose predicates with logical operations
    auto isPositive = [](int x) { return x > 0; };
    auto isLessThanHundred = [](int x) { return x < 100; };

    auto isValid = [isPositive, isLessThanHundred](int x) {
        return isPositive(x) && isLessThanHundred(x);
    };

    // Or use std::logical_and with std::binder1st
    auto boundAnd = std::logical_and<bool>();
    // Modern approach: compose inline
    auto combined = [isPositive, isLessThanHundred](int x) { return isPositive(x) && isLessThanHundred(x); };
}
```

Negation is essential for inverting conditions, like finding elements that don't match a predicate.

### Member Function Adapters

Member function adapters convert member functions to callable objects that work with algorithms:

```cpp
#include <functional>
#include <vector>
#include <string>
#include <iostream>

struct Person {
    std::string name;
    int age;

    void print() const {
        std::cout << name << " (" << age << ")\n";
    }

    std::string getDescription() const {
        return name + " is " + std::to_string(age) + " years old";
    }
};

int main() {
    std::vector<Person> people = {
        {"Alice", 30},
        {"Bob", 25},
        {"Charlie", 35}
    };

    // std::mem_fn creates a callable from a member function
    auto printPerson = std::mem_fn(&Person::print);

    for (const auto& p : people) {
        printPerson(p);
    }

    // Use with std::transform
    std::vector<std::string> descriptions;
    auto getDesc = std::mem_fn(&Person::getDescription);
    std::transform(people.begin(), people.end(), std::back_inserter(descriptions), getDesc);

    for (const auto& d : descriptions) {
        std::cout << d << "\n";
    }

    // std::bind with member functions
    auto printAlice = std::bind(&Person::print, std::placeholders::_1);
    printAlice(people[0]);  // Alice (30)

    // Binding to a specific object
    auto printPerson2 = std::bind(&Person::print, &people[1]);
    printPerson2();  // Bob (25)
}
```

Member function adapters enable using member functions with algorithms by handling the implicit `this` parameter.

### Composition Adapters

Creating composed functions enables building complex operations from simple ones:

```cpp
#include <functional>
#include <iostream>
#include <utility>

// Function composition: f after g = f(g(x))
template<typename F, typename G>
auto compose(F f, G g) {
    return [f, g](auto x) {
        return f(g(x));
    };
}

// Compose multiple functions (right to left evaluation)
template<typename... Funcs>
auto composeAll(Funcs... funcs) {
    return [funcs...](auto x) {
        return ((funcs(x) + ...));  // Fold expression - adds all results
    };
}

// Pipelines: apply functions in sequence
template<typename... Funcs>
auto pipeline(Funcs... funcs) {
    return [funcs...](auto x) {
        auto result = x;
        ((result = funcs(result)), ...);
        return result;
    };
}

// Generic function composition with type preservation
template<typename F, typename G>
auto operator>>(F f, G g) {
    return compose(g, f);  // f >> g means apply f, then g
}

int main() {
    auto addOne = [](int x) { return x + 1; };
    auto square = [](int x) { return x * x; };
    auto doubleIt = [](int x) { return x * 2; };

    // Compose: square after addOne
    auto squareOfAddOne = compose(square, addOne);
    std::cout << squareOfAddOne(3) << "\n";  // (3+1)^2 = 16

    // Pipeline: apply in sequence
    auto transform = pipeline(addOne, square, doubleIt);
    std::cout << transform(3) << "\n";  // ((3+1)^2)*2 = 32

    // Operator syntax
    auto result = (addOne >> square >> doubleIt)(3);
    std::cout << result << "\n";  // 32

    // Compose multiple
    auto multi = composeAll(addOne, square, doubleIt);
    std::cout << multi(2) << "\n";  // 2+1+4+8 = 15
}
```

Composition adapters enable building reusable transformations that can be combined flexibly.

### Callable Wrappers

std::function provides type erasure for callable objects:

```cpp
#include <functional>
#include <vector>
#include <iostream>

// Store heterogeneous callables
class CallbackManager {
    std::vector<std::function<void()>> callbacks;

public:
    void add(std::function<void()> cb) {
        callbacks.push_back(std::move(cb));
    }

    void executeAll() {
        for (auto& cb : callbacks) {
            cb();
        }
    }
};

int main() {
    // Store different callable types in a container
    std::vector<std::function<int(int)>> operations;

    operations.push_back([](int x) { return x * 2; });
    operations.push_back([](int x) { return x + 10; });
    operations.push_back([](int x) { return x * x; });

    for (const auto& op : operations) {
        std::cout << op(5) << " ";
    }
    std::cout << "\n";

    // Polymorphic callable interface
    CallbackManager mgr;
    mgr.add([]() { std::cout << "First callback\n"; });
    mgr.add([]() { std::cout << "Second callback\n"; });

    int captured = 42;
    mgr.add([captured]() { std::cout << "Third with captured: " << captured << "\n"; });

    mgr.executeAll();
}
```

std::function enables storing and invoking heterogeneous callable objects with a unified interface.

### Placeholder Adapters

std::placeholders provide named parameters for partial application:

```cpp
#include <functional>
#include <iostream>

void process(int a, int b, int c) {
    std::cout << "a=" << a << " b=" << b << " c=" << c << "\n";
}

int main() {
    // Partial application: bind some arguments
    auto partial1 = std::bind(process, 1, std::placeholders::_1, std::placeholders::_2);
    partial1(2, 3);  // a=1 b=2 c=3

    auto partial2 = std::bind(process, std::placeholders::_2, 99, std::placeholders::_1);
    partial2(5, 10);  // a=10 b=99 c=5

    // Reorder arguments
    auto reorder = std::bind(process, std::placeholders::_3, std::placeholders::_1, std::placeholders::_2);
    reorder(1, 2, 3);  // a=3 b=1 c=2

    // Bind member functions
    struct Calculator {
        int add(int a, int b) { return a + b; }
        int multiply(int a, int b) { return a * b; }
    };

    Calculator calc;
    auto addToCalc = std::bind(&Calculator::add, &calc, std::placeholders::_1, 100);
    std::cout << addToCalc(5) << "\n";  // 105

    auto multiplyWithCalc = std::bind(&Calculator::multiply, std::placeholders::_1, std::placeholders::_2);
    std::cout << multiplyWithCalc(6, 7) << "\n";  // 42
}
```

Placeholders enable flexible reordering and partial application of function arguments.

### Adaptor Patterns in the Standard Library

The standard library provides several function adaptors through the iterator and algorithm headers:

```cpp
#include <iterator>
#include <algorithm>
#include <vector>
#include <iostream>

int main() {
    std::vector<int> v1 = {1, 2, 3};
    std::vector<int> v2 = {4, 5, 6};

    // Insert iterators for output
    std::vector<int> result;
    std::transform(v1.begin(), v1.end(), std::back_inserter(result), [](int x) { return x * 2; });

    // Reverse iterators
    std::vector<int> reversed(v1.rbegin(), v1.rend());

    // Move iterators
    std::vector<std::unique_ptr<int>> sources;
    sources.push_back(std::make_unique<int>(1));
    sources.push_back(std::make_unique<int>(2));

    std::vector<std::unique_ptr<int>> destinations;
    std::move(sources.begin(), sources.end(), std::back_inserter(destinations));

    // Stream iterators
    std::vector<int> input = {1, 2, 3, 4, 5};
    std::copy(input.begin(), input.end(), std::ostream_iterator<int>(std::cout, " "));
    std::cout << "\n";

    // Reading from input
    std::vector<int> fromInput;
    std::copy(std::istream_iterator<int>(std::cin),
              std::istream_iterator<int>(),
              std::back_inserter(fromInput));
}
```

Iterator adaptors transform the way iterators work, enabling different traversal patterns and I/O integration.

### Custom Function Adapters

Creating custom adapters extends the composition capabilities:

```cpp
#include <functional>
#include <iostream>
#include <vector>

// Tap adapter: apply function and return original value
template<typename Func>
auto tap(Func f) {
    return [f](auto&& value) -> decltype(auto) {
        f(std::forward<decltype(value)>(value));
        return std::forward<decltype(value)>(value);
    };
}

// Memoize: cache function results
template<typename Func>
auto memoize(Func func) {
    std::map<std::invoke_result_t<Func, int>, std::invoke_result_t<Func, int>> cache;
    return [func, &cache](int arg) mutable {
        if (cache.find(arg) == cache.end()) {
            cache[arg] = func(arg);
        }
        return cache[arg];
    };
}

// Retry: call function multiple times on failure
template<typename Func>
auto retry(int times, Func func) {
    return [times, func]() {
        for (int i = 0; i < times; ++i) {
            try {
                return func();
            } catch (...) {
                if (i == times - 1) throw;
            }
        }
        throw std::runtime_error("All retries failed");
    };
}

// Debounce: delay calls (conceptual - needs async)
template<typename Func>
auto debounce(int ms, Func func) {
    return [ms, func](auto&&... args) {
        // In practice, this would use timers
        static_cast<void>(ms);
        func(std::forward<decltype(args)>(args)...);
    };
}

int main() {
    // Tap: debug and continue
    std::vector<int> data = {1, 2, 3};
    auto processed = [&data]() {
        std::vector<int> result;
        for (int x : data) {
            result.push_back(x * 2);
            // Tap to debug: print each step
            tap([](int v) { std::cout << "Processing: " << v << "\n"; })(v);
        }
        return result;
    }();

    // Memoize: cache expensive computation
    auto fib = memoize([](int n) {
        if (n <= 1) return n;
        return fib(n - 1) + fib(n - 2);
    });

    std::cout << fib(20) << "\n";  // Computes once, cached

    // Pipeline with tap
    auto pipeline = [](int x) { return x + 1; }
        >> tap([](int x) { std::cout << "After +1: " << x << "\n"; })
        >> [](int x) { return x * 2; }
        >> tap([](int x) { std::cout << "After *2: " << x << "\n"; });

    std::cout << "Result: " << pipeline(5) << "\n";
}
```

Custom adapters enable domain-specific composition patterns that extend the standard library's capabilities.

### Summary

Function adapters modify or combine functions. std::bind provides argument binding and reordering. std::not_fn negates predicates. std::mem_fn creates callables from member functions. Composition creates new functions from existing ones. std::function provides type erasure for heterogeneous callables. Placeholders enable partial application. Custom adapters extend composition for specific domains. Together, these patterns enable flexible function building from reusable components.

---

## Lazy Evaluation Patterns

Lazy evaluation defers computation until its result is actually needed. This approach can improve performance by avoiding unnecessary work, enable infinite data structures, and provide better resource management. C++ supports lazy evaluation through expression templates, ranges, and custom implementations.

### Understanding Lazy vs Eager Evaluation

Eager evaluation computes results immediately, while lazy evaluation defers computation until required:

```cpp
#include <vector>
#include <iostream>

// Eager: compute immediately
std::vector<int> eagerFilter(const std::vector<int>& data, std::function<bool(int)> pred) {
    std::vector<int> result;
    for (int x : data) {
        if (pred(x)) {
            result.push_back(x);
        }
    }
    return result;
}

// Lazy: return a description of what to compute
template<typename Container, typename Predicate>
class LazyFilter {
    const Container& source;
    Predicate pred;

public:
    LazyFilter(const Container& c, Predicate p) : source(c), pred(p) {}

    // Computation happens here - when iterated
    class Iterator {
    public:
        using iterator_category = std::input_iterator_tag;
        using value_type = int;
        using difference_type = std::ptrdiff_t;
        using pointer = const int*;
        using reference = int;

        Iterator& operator++() {
            do {
                ++it_;
            } while (it_ != end_ && !pred_(*it_));
            return *this;
        }

        int operator*() const { return *it_; }
        bool operator!=(const Iterator& other) const { return it_ != other.it_; }

    private:
        typename Container::const_iterator it_, end_;
        Predicate pred_;
    };

    Iterator begin() const {
        auto it = source.begin();
        while (it != source.end() && !pred(*it)) ++it;
        return {it, source.end(), pred};
    }

    Iterator end() const {
        return {source.end(), source.end(), pred};
    }
};

int main() {
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Eager: entire result computed immediately
    auto eagerResult = eagerFilter(data, [](int x) { return x % 2 == 0; });

    // Lazy: only compute when iterated
    LazyFilter lazyResult(data, [](int x) { return x % 2 == 0; });

    // The lazy computation only runs when we iterate
    for (int x : lazyResult) {
        std::cout << x << " ";
    }
}
```

Lazy evaluation postpones computation, which can save work when only part of the result is needed or when the result is never used.

### Lazy Ranges (C++20)

C++20 introduces ranges that provide lazy evaluation:

```cpp
#include <ranges>
#include <vector>
#include <iostream>

int main() {
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Lazy pipeline - nothing computed yet
    auto pipeline = data
        | std::views::filter([](int x) { return x % 2 == 0; })
        | std::views::transform([](int x) { return x * x; })
        | std::views::take(3);

    // Still lazy - only iterated when consumed
    for (int x : pipeline) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    // Infinite range - only possible with lazy evaluation
    auto integers = std::views::iota(1);
    auto evenIntegers = integers | std::views::filter([](int x) { return x % 2 == 0; });
    auto firstTen = evenIntegers | std::views::take(10);

    for (int x : firstTen) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    // Chained transformations - all lazy
    auto result = std::views::iota(1)
        | std::views::transform([](int x) { return x * x; })
        | std::views::filter([](int x) { return x < 100; });

    for (int x : result) {
        std::cout << x << " ";
    }
}
```

C++20 ranges enable expressive, lazy pipelines that don't compute until iterated, and can represent infinite sequences.

### Custom Lazy Generators

Creating custom lazy generators enables domain-specific lazy evaluation:

```cpp
#include <functional>
#include <iostream>
#include <optional>

template<typename T>
class Generator {
public:
    using ValueType = T;

private:
    std::function<std::optional<T>()> generator_;

public:
    explicit Generator(std::function<std::optional<T>()> gen)
        : generator_(std::move(gen)) {}

    class Iterator {
    public:
        using iterator_category = std::input_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using pointer = const T*;
        using reference = T;

        explicit Iterator(std::function<std::optional<T>()>* gen)
            : generator_(gen), current_(gen ? (*gen)() : std::nullopt) {}

        reference operator*() { return *current_; }
        pointer operator->() { return &*current_; }

        Iterator& operator++() {
            if (generator_) {
                current_ = (*generator_)();
            }
            return *this;
        }

        bool operator!=(const Iterator&) const {
            return current_.has_value();
        }

    private:
        std::function<std::optional<T>()>* generator_;
        std::optional<T> current_;
    };

    Iterator begin() { return Iterator(&generator_); }
    Iterator end() { return Iterator(nullptr); }
};

// Fibonacci generator
Generator<int> fibonacci() {
    int a = 0, b = 1;
    return Generator<int>([&a, &b]() -> std::optional<int> {
        int current = a;
        int next = a + b;
        a = b;
        b = next;
        return current;
    });
}

// Range generator
Generator<int> range(int start, int end) {
    int current = start;
    return Generator<int>([&current, end]() -> std::optional<int> {
        if (current >= end) return std::nullopt;
        return current++;
    });
}

int main() {
    // First 10 Fibonacci numbers
    for (int x : fibonacci() | std::views::take(10)) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    // Numbers 1 to 10
    for (int x : range(1, 11)) {
        std::cout << x << " ";
    }
    std::cout << "\n";
}
```

Custom generators enable creating lazy sequences for any domain, deferring computation until values are requested.

### Expression Templates

Expression templates defer operations by building an expression tree that evaluates on demand:

```cpp
#include <vector>
#include <iostream>

// Expression template base
template<typename E>
class Expression {
public:
    double evaluate() const {
        return static_cast<const E&>(*this).evaluate();
    }
};

// Terminal value
class Constant : public Expression<Constant> {
    double value_;
public:
    explicit Constant(double v) : value_(v) {}
    double evaluate() const { return value_; }
};

// Variable reference
template<typename T>
class Variable : public Expression<Variable<T>> {
    const T& ref_;
public:
    explicit Variable(const T& r) : ref_(r) {}
    double evaluate() const { return ref_; }
};

// Addition expression
template<typename L, typename R>
class Add : public Expression<Add<L, R>> {
    const L& left_;
    const R& right_;
public:
    Add(const L& l, const R& r) : left_(l), right_(r) {}
    double evaluate() const { return left_.evaluate() + right_.evaluate(); }
};

// Multiplication expression
template<typename L, typename R>
class Multiply : public Expression<Multiply<L, R>> {
    const L& left_;
    const R& right_;
public:
    Multiply(const L& l, const R& r) : left_(l), right_(r) {}
    double evaluate() const { return left_.evaluate() * right_.evaluate(); }
};

// Operators
template<typename L, typename R>
Add<L, R> operator+(const Expression<L>& l, const Expression<R>& r) {
    return Add<L, R>(static_cast<const L&>(l), static_cast<const R&>(r));
}

template<typename L, typename R>
Multiply<L, R> operator*(const Expression<L>& l, const Expression<R>& r) {
    return Multiply<L, R>(static_cast<const L&>(l), static_cast<const R&>(r));
}

int main() {
    double x = 3.0;
    double y = 4.0;

    // Build expression lazily: (x + 2) * (y - 1)
    auto expr = (Variable<double>(x) + Constant(2)) * (Variable<double>(y) - Constant(1));

    // Evaluate - computation happens now
    double result = expr.evaluate();
    std::cout << "Result: " << result << "\n";  // (3+2)*(4-1) = 15

    // Modify x - expression still references x
    x = 5.0;
    result = expr.evaluate();
    std::cout << "Result after x=5: " << result << "\n";  // (5+2)*(4-1) = 21
}
```

Expression templates enable building complex computations lazily, deferring evaluation until the result is actually needed, and recomputing when dependencies change.

### Lazy Evaluation with std::optional

std::optional can model computations that might not produce a value:

```cpp
#include <optional>
#include <iostream>
#include <vector>

template<typename T>
class Lazy {
    std::optional<T> value_;
    std::function<T()> factory_;

public:
    explicit Lazy(std::function<T()> f) : factory_(std::move(f)) {}

    T& get() {
        if (!value_) {
            value_ = factory_();
        }
        return *value_;
    }

    const T& get() const {
        if (!value_) {
            value_ = factory_();
        }
        return *value_;
    }

    operator T() { return get(); }
};

// Lazy expensive computation
Lazy<int> lazyCompute() {
    return Lazy<int>([]() {
        std::cout << "Computing...\n";
        int sum = 0;
        for (int i = 0; i < 1000000; ++i) sum += i;
        return sum;
    });
}

int main() {
    auto lazy = lazyCompute();

    std::cout << "Before first access\n";
    std::cout << "Value: " << lazy.get() << "\n";
    std::cout << "After first access\n";

    std::cout << "Value again: " << lazy.get() << "\n";
    // Does not recompute - cached
}
```

Lazy wrappers defer expensive computations until needed and cache results to avoid recomputation.

### Infinite Data Structures

Lazy evaluation enables infinite data structures that are computed on demand:

```cpp
#include <iostream>
#include <vector>
#include <functional>

template<typename T>
class Stream {
    T head_;
    std::function<Stream<T>()> tail_;
    bool tailEvaluated_ = false;
    Stream<T>* tailCache_ = nullptr;

public:
    Stream(T head, std::function<Stream<T>()> tail)
        : head_(head), tail_(std::move(tail)) {}

    T head() const { return head_; }

    Stream<T>& tail() {
        if (!tailEvaluated_) {
            tailCache_ = new Stream<T>(tail_());
            tailEvaluated_ = true;
        }
        return *tailCache_;
    }

    const Stream<T>& tail() const { return const_cast<Stream*>(this)->tail(); }

    // Take first n elements
    std::vector<T> take(int n) const {
        std::vector<T> result;
        const Stream<T>* current = this;
        for (int i = 0; i < n && current; ++i) {
            result.push_back(current->head());
            current = &current->tail();
        }
        return result;
    }
};

// Infinite stream of integers
Stream<int> integers(int start) {
    return Stream<int>(start, [start]() {
        return integers(start + 1);
    });
}

// Infinite stream with transformation
Stream<int> map(Stream<int> s, std::function<int(int)> f) {
    return Stream<int>(f(s.head()), [s = std::move(s), f]() mutable {
        return map(s.tail(), f);
    });
}

// Filter lazy stream
Stream<int> filter(Stream<int> s, std::function<bool(int)> pred) {
    while (!pred(s.head())) {
        s = s.tail();
    }
    return Stream<int>(s.head(), [s = std::move(s), pred]() mutable {
        return filter(s.tail(), pred);
    });
}

int main() {
    // Infinite stream starting at 1
    auto nums = integers(1);

    // First 10 numbers
    auto first10 = nums.take(10);
    for (int x : first10) std::cout << x << " ";
    std::cout << "\n";

    // First 10 even numbers
    auto evens = filter(integers(1), [](int x) { return x % 2 == 0; });
    auto first10evens = evens.take(10);
    for (int x : first10evens) std::cout << x << " ";
    std::cout << "\n";

    // First 10 squares
    auto squares = map(integers(1), [](int x) { return x * x; });
    auto first10squares = squares.take(10);
    for (int x : first10squares) std::cout << x << " ";
    std::cout << "\n";
}
```

Infinite streams are only possible with lazy evaluation—they would require infinite memory with eager evaluation.

### Performance Considerations

Lazy evaluation has trade-offs that affect performance:

```cpp
#include <chrono>
#include <iostream>
#include <vector>
#include <ranges>

void demonstratePerformance() {
    // Lazy: only does what's needed
    auto start = std::chrono::high_resolution_clock::now();

    auto result = std::views::iota(1, 1000000)
        | std::views::filter([](int x) { return x % 2 == 0; })
        | std::views::transform([](int x) { return x * x; })
        | std::views::take(10);

    // Only 10 elements computed
    for (int x : result) {
        std::cout << x << " ";
    }

    auto end = std::chrono::high_resolution_clock::now();
    std::cout << "\nLazy: " << std::chrono::duration_cast<std::chrono::microseconds>(end - start).count() << "us\n";

    // Eager: computes everything
    start = std::chrono::high_resolution_clock::now();

    std::vector<int> eager;
    for (int i = 1; i < 1000000; ++i) {
        if (i % 2 == 0) {
            eager.push_back(i * i);
        }
    }
    eager.resize(10);

    for (int x : eager) {
        std::cout << x << " ";
    }

    end = std::chrono::high_resolution_clock::now();
    std::cout << "\nEager: " << std::chrono::duration_cast<std::chrono::microseconds>(end - start).count() << "us\n";
}

// Advantages of lazy:
// - Don't compute unused values
// - Can work with infinite sequences
// - Better memory for large/dynamic data

// Disadvantages of lazy:
// - Overhead of lazy wrapper/closure
// - Harder to debug (stack traces less clear)
// - Potential for memory leaks if references held
// - Cache-friendly for sequential access vs random

int main() {
    demonstratePerformance();
}
```

Lazy evaluation optimizes for cases where not all data is needed, while eager evaluation optimizes for sequential access and simplicity.

### Summary

Lazy evaluation defers computation until results are needed. C++20 ranges provide standard lazy pipelines. Custom generators enable domain-specific lazy sequences. Expression templates build deferred computation trees. Lazy wrappers cache expensive operations. Infinite data structures require lazy evaluation. Consider performance trade-offs when choosing lazy vs eager—lazy saves work when results are partially consumed, while eager is simpler and often faster for complete consumption.

---

## Summary

This chapter explored four related functional programming patterns in C++. Higher-order functions accept functions as parameters or return functions, enabling flexible abstraction and reusable algorithms. Monadic operations transform containers through map, flatMap, filter, and fold, providing a declarative pipeline style. Function adapters modify or combine functions through binding, composition, and type erasure. Lazy evaluation defers computation until needed, enabling infinite data structures and efficient partial computation.

Together, these patterns enable a functional programming style in C++ that expresses *what* to compute rather than *how*. They compose well—higher-order functions accept adapters, monadic operations work with lazy ranges, and composed functions can themselves be lazy. Modern C++ (C++17 and C++20) provides extensive support through lambdas, std::function, std::bind, std::optional, ranges, and concepts.

The key insight is that functional patterns complement rather than replace imperative C++. Use them where they provide clarity and safety—algorithms, data transformations, and composition logic—while retaining C++'s strengths for low-level work. The functional style excels at expressing complex transformations elegantly, while C++'s value semantics and RAII provide the performance and resource management needed for systems programming.

### Exercises

1. **Higher-Order Functions**: Implement a generic `retry` higher-order function that calls a function up to N times until it succeeds or throws an exception on final failure.

2. **Monadic Operations**: Implement a monadic `flatMap` for `std::optional` that chains optional-returning functions, handling the case when any step returns `std::nullopt`.

3. **Function Composition**: Create a `compose` function that composes multiple functions of the same type, and demonstrate building a complex transformation pipeline.

4. **Lazy Evaluation**: Implement an infinite lazy Fibonacci stream using the generator pattern, with `take(n)` to retrieve the first N elements.

5. **Range Adaptors**: Using C++20 ranges (or implementing equivalent lazy range views), create a pipeline that generates the first 100 prime numbers starting from 1.