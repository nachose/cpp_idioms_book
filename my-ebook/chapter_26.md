# Chapter 26: Range and Views

C++20 introduced the Ranges library (`std::ranges`), the most significant change to how we work with sequences since the STL debuted in the 1990s. The old iterator-based approach required you to think in terms of pairs of iterators—`begin` and `end`—and to express operations as nested algorithm calls. Ranges let you think in terms of **sequences** themselves, composing operations with a clarity that was previously impossible.

The Ranges library has two interlocking parts: **range algorithms** (like `std::ranges::sort` that accept a range directly instead of iterator pairs) and **range adaptors** (like `std::views::filter` and `std::views::transform` that compose lazily). Together, they enable a **pipeline style** of programming—`data | filter | transform | sort`—that reads in the order of execution, not the order of nesting.

This chapter covers the four essential skills you need to use ranges effectively: using range-based algorithms, understanding lazy evaluation with views, building custom range adaptors, and composing pipelines.

---

## Range-Based Algorithms

The simplest entry point to the Ranges library is the algorithm set in `std::ranges`. These are not a replacement for the classic `<algorithm>` algorithms—they are a **superset** that adds convenience, safety, and expressiveness while remaining compatible with the existing iterator abstractions.

### Motivation: What Ranges Fix

The classic STL algorithms require two iterators to denote a sequence:

```cpp
std::vector<int> data = {3, 1, 4, 1, 5, 9, 2, 6};

auto it = std::find(data.begin(), data.end(), 5);
std::sort(data.begin(), data.end());

// What if you want to sort only the first half?
auto mid = data.begin() + data.size() / 2;
std::sort(data.begin(), mid);
```

Every call repeats `data.begin()` and `data.end()`. This is verbose, and it introduces a source of errors: what if you accidentally pass `data.begin()` from one container and `data.end()` from another? What if you pass iterators that belong to different containers entirely? The compiler cannot catch these mistakes.

Worse, some sequences don't have a simple "begin/end" pair. A null-terminated string `const char*` has no end iterator computed in advance—the end is computed by scanning. An input stream produces elements one at a time; there is no container. A generator like `iota` is infinite. The classic STL interface forces you to have the end ready before you start, which is fundamentally incompatible with lazy or infinite sequences.

Range algorithms solve both problems by accepting a **range object** that knows how to produce begin and end:

```cpp
#include <algorithm>
#include <ranges>

std::vector<int> data = {3, 1, 4, 1, 5, 9, 2, 6};

// Same algorithm, one argument instead of two.
auto it = std::ranges::find(data, 5);
std::ranges::sort(data);

// Sort the first half — no manual iterator arithmetic needed.
std::ranges::sort(std::views::take(data, data.size() / 2));
```

The range object encapsulates the begin/end logic. `data` (a `std::vector<int>`) is a range; `std::views::take(data, n)` is also a range. The algorithm doesn't care which kind of range it receives—it just calls `ranges::begin()` and `ranges::end()` on it. This abstraction is what makes composable pipelines possible.

A range is simply anything that satisfies the `std::ranges::range` concept: something that provides `begin()` and `end()` (or `begin()` and `sentinel()` for sentinel-terminated sequences). All standard containers are ranges. C-style arrays are ranges. `std::string` is a range. And, critically, **views** are also ranges, which enables composition.

### Constrained Algorithms

The `std::ranges` algorithms use C++20 concepts to provide better error messages and overload resolution. Where a classic algorithm like `std::sort` accepts any pair of random-access iterators and fails with a confusing template error if they are not, the range version is constrained:

```cpp
// Classic: error message involves pages of template instantiation backtrace.
std::sort(my_list.begin(), my_list.end());  // Error if my_list is std::list

// Ranges: clear error about the required concept.
std::ranges::sort(my_list);  // Error: 'std::sortable' not satisfied
```

The constraint says: "this algorithm requires a range whose iterator satisfies `std::sortable`." If the range does not provide random-access iterators (like `std::list`), the compiler reports the concept failure directly rather than deep in template instantiation.

Every constrained algorithm also works with iterator pairs when you need it, for backward compatibility. The constrained overloads use `std::invoke` internally, which means they work uniformly with member function pointers, lambdas, and callable objects without any special adapters.

### Projections: A New Idiom for Customizing Algorithm Behavior

One of the most practically useful additions in the Ranges library is **projections**. A projection is a unary callable that transforms each element before the algorithm operates on it. This eliminates a huge category of boilerplate code.

Suppose you have a `std::vector<Person>` and you want to sort by the `name` field. Classic C++ requires a custom comparator:

```cpp
struct Person { std::string name; int age; };

std::vector<Person> people = { /* ... */ };

// Classic: write a lambda that compares the right field.
std::sort(people.begin(), people.end(), [](const Person& a, const Person& b) {
    return a.name < b.name;
});
```

With projections, you provide the projection separately from the comparison:

```cpp
std::ranges::sort(people, std::less{}, &Person::name);
```

The projection `&Person::name` is applied to each element before the comparison. The algorithm internally does: `std::invoke(comp, std::invoke(proj, a), std::invoke(proj, b))`. The projection can be a member pointer, a lambda, or any callable:

```cpp
// Sort by age, descending.
std::ranges::sort(people, std::greater{}, &Person::age);

// Find the first person whose name starts with 'A'.
auto it = std::ranges::find_if(people, [](const std::string& n) {
    return !n.empty() && n[0] == 'A';
}, &Person::name);

// Count people over 30.
auto count = std::ranges::count_if(people, [](int age) { return age > 30; }, &Person::age);
```

The projection is not just syntactic sugar—it changes how you reason about the algorithm. Instead of asking "how do I compare Person objects by name?" you ask "which field should the algorithm look at?" The comparison itself becomes generic (`std::less{}` works on any comparable type), and the projection provides the type-specific adaptation.

Projections compose. You can chain them with function composition to sort by more complex criteria:

```cpp
// Sort by the length of the name, then by name alphabetically.
std::ranges::sort(people, std::ranges::lexicographical_compare{}, 
    [](const Person& p) { return std::pair{p.name.size(), p.name}; });
```

The projection returns a pair; the algorithm compares pairs using `std::pair`'s built-in lexicographic comparison. This is the idiomatic C++20 way to express multi-key sorting: you project each element into a comparison key that encodes the sorting hierarchy.

### Sentinel-Based Algorithms

Classic STL iterators mark the end of a sequence with a specific iterator value (typically `end()`). This works when the end is known in advance. But many sequences have an end that is defined by a **condition** rather than a position:

- A null-terminated string ends when `*ptr == '\0'`.
- An input stream ends when extraction fails.
- A sequence of random numbers ends when a certain distribution threshold is crossed.

The Ranges library introduces **sentinels**—types that denote the end of a range by a predicate rather than a position. A sentinel-based range has `begin()` returning an iterator and `end()` returning a sentinel. The sentinel does not need to be the same type as the iterator; it just needs to be equality-comparable with the iterator.

```cpp
// A range that reads integers from stdin until EOF.
class InputStreamRange {
    int value_;
public:
    class Iterator {
        std::istream* stream_;
        int value_;
        bool consumed_ = false;

        void advance() {
            if (stream_ && !(*stream_ >> value_)) {
                stream_ = nullptr;  // mark as exhausted
            }
        }

    public:
        using difference_type = std::ptrdiff_t;
        using value_type = int;

        Iterator(std::istream* s) : stream_(s) { advance(); }
        Iterator& operator++() { advance(); return *this; }
        int operator*() const { return value_; }
        bool operator!=(std::default_sentinel_t) const {
            return stream_ != nullptr;
        }
    };

    Iterator begin() { return Iterator(&std::cin); }
    std::default_sentinel_t end() { return {}; }
};

// Usage:
for (int x : InputStreamRange()) {
    std::cout << x * 2 << "\n";
}
```

The sentinel type `std::default_sentinel_t` is empty—it carries no state. The iterator's `operator!=` against the sentinel checks whether the stream has been exhausted. This is the same mechanism that underlies `std::views::istream`, `std::views::iota` (where the sentinel is `std::unreachable_sentinel` for infinite ranges), and custom sentinel-defined views.

The practical impact of sentinels is that many more things become "ranges." A `const char*` is a range whose sentinel is the null terminator check. An infinite sequence like `std::views::iota(0)` is a range whose sentinel is `std::unreachable_sentinel`. This unification is what makes the ranges abstraction so powerful: if you can define begin and a way to detect the end, you have a range, regardless of how the underlying sequence is produced.

### Pipeable vs. Non-Pipeable Algorithm Calls

Range algorithms that return a range (like `std::ranges::transform` which returns the transformed range, or `std::ranges::copy` which returns an iterator) can be chained. But most algorithms that **mutate** a range in place (like `sort`) do not naturally compose in a pipeline because they operate by side effect. The idiomatic distinction is:

- **Mutating algorithms** (`sort`, `reverse`, `partition`, etc.) operate in-place and are used as direct calls: `std::ranges::sort(data)`.
- **Non-mutating algorithms** (`find`, `count`, `all_of`, etc.) inspect the range and return a result. They do not form pipelines either—they are terminal operations.
- **View operations** (`filter`, `transform`, `take`, etc.) are the building blocks of pipelines.

The real power of range composition comes from **views**, which we turn to next.

---

## Lazy Evaluation with Views

A **view** is a lightweight range that **does not own** the data it represents. Views are composable, lazy, and constant-time to construct and copy. They are the heart of the C++20 ranges revolution because they let you describe data transformations without materializing intermediate results.

### The Core Idea: Lazy, Non-Owning

A view is a range whose `begin()` and `end()` return iterators that compute the view's elements on the fly. Applying `std::views::transform(v, f)` to a vector does **not** create a new vector of transformed values. It creates a view object that, when iterated, applies `f` to each element of `v` as it is accessed. The transformation happens lazily, one element at a time, during iteration.

```cpp
std::vector<int> data = {1, 2, 3, 4, 5, 6};

// No computation happens here — just view objects.
auto even_numbers = data | std::views::filter([](int n) { return n % 2 == 0; });
auto doubled = even_numbers | std::views::transform([](int n) { return n * 2; });

// Iteration triggers the computation:
for (int x : doubled) {
    std::cout << x << " ";  // 4 8 12
}
```

Each step in the pipeline is a view object. The pipeline `data | filter | transform` produces a single view type that, when iterated, walks through `data`, skips odd elements, and doubles what remains. No intermediate vectors are created. No memory is allocated beyond the view objects themselves.

This is fundamentally different from the classic approach:

```cpp
// Classic: each step materializes a full vector.
std::vector<int> even;
std::copy_if(data.begin(), data.end(), std::back_inserter(even), [](int n) { return n % 2 == 0; });

std::vector<int> doubled;
std::transform(even.begin(), even.end(), std::back_inserter(doubled), [](int n) { return n * 2; });
```

The classic approach allocates two additional vectors, iterates through `data` twice, and can exhaust memory if `data` is large. The view-based approach iterates once and allocates nothing.

### Ownership and Dangling

Because views do not own data, they become dangling if the underlying data is destroyed while the view is still in use:

```cpp
auto get_view() {
    std::vector<int> data = {1, 2, 3, 4, 5};
    return data | std::views::filter([](int n) { return n % 2 == 0; });
    // data is destroyed here — the returned view dangles!
}

// Using the returned view is undefined behavior.
for (int x : get_view()) {
    std::cout << x;  // Dangling reference: data is gone
}
```

The C++20 Ranges library attempts to mitigate this with **borrowed range** concepts and compile-time checks. Some views (like `std::views::iota`) are "borrowed" because they don't reference external data. Others (like `filter` and `transform` that wrap a range reference) are not borrowed because they depend on the underlying range's lifetime.

The practical rule is: **do not return a view that wraps a local container**. If you need to return a transformed sequence, either return the container directly (by value, accepting the copy) or ensure the source data outlives the view. Common patterns that avoid dangling:

```cpp
// Option 1: Accept a range by reference and return a view.
auto process(std::ranges::range auto&& data) {
    return data | std::views::filter(/* ... */) | std::views::transform(/* ... */);
}
// The caller owns the data; the view is safe.

// Option 2: Return a container (eager evaluation).
auto get_processed() {
    std::vector<int> data = {1, 2, 3, 4, 5};
    auto view = data | std::views::transform([](int n) { return n * 2; });
    return std::vector<int>(view.begin(), view.end());
    // Materializes the view into an owned vector.
}
```

Option 1 is preferred when the calling context owns the data. Option 2 is preferred when the function should own its result.

### Commonly Used Views

The standard library provides a rich set of views in `<ranges>`. The most important ones form the vocabulary of range composition:

**`std::views::filter(pred)`** — Selects elements for which `pred` returns true.

```cpp
auto evens = data | std::views::filter([](int n) { return n % 2 == 0; });
```

`filter` is one of the most used views. It wraps the underlying iterator: `operator++` advances the underlying iterator until the predicate is satisfied. If the predicate is expensive, calling it on every discarded element adds overhead. For this reason, `filter` is best used with cheap predicates or when the fraction of filtered-out elements is small.

**`std::views::transform(f)`** — Applies `f` to each element.

```cpp
auto squares = data | std::views::transform([](int n) { return n * n; });
```

`transform` is a pure mapping: every input element produces exactly one output element. The view's reference type is the return type of `f`, which may be a prvalue (a temporary). This has implications: you cannot bind a mutable reference from a `transform` view that returns by value. The C++23 `views::as_rvalue` view addresses this for move semantics.

**`std::views::take(n)` and `std::views::drop(n)`** — Limits or skips the first `n` elements.

```cpp
auto first_10 = data | std::views::take(10);
auto after_5 = data | std::views::drop(5);
auto middle = data | std::views::drop(5) | std::views::take(3);
```

`take` and `drop` are especially useful with infinite ranges:

```cpp
// The first 10 positive even numbers.
auto first_10_evens = std::views::iota(1) 
    | std::views::filter([](int n) { return n % 2 == 0; })
    | std::views::take(10);
```

Without `take`, iterating over `iota(1)` would be infinite. The `take(10)` makes the pipeline finite.

**`std::views::reverse`** — Iterates a bidirectional range in reverse.

```cpp
for (int x : data | std::views::reverse) {
    std::cout << x;  // last to first
}
```

This is equivalent to `rbegin`/`rend` iteration but expressed as a composable view.

**`std::views::elements<N>`** — Extracts the Nth element from a tuple-like range.

```cpp
std::vector<std::pair<int, std::string>> pairs = {{1, "one"}, {2, "two"}};
auto just_strings = pairs | std::views::elements<1>;
// {"one", "two"}
```

**`std::views::keys` and `std::views::values`** — Shorthand for `elements<0>` and `elements<1>`, designed for associative containers and ranges of pairs.

```cpp
std::map<int, std::string> m = {{1, "one"}, {2, "two"}};
auto keys = m | std::views::keys;     // {1, 2}
auto values = m | std::views::values; // {"one", "two"}
```

These views are the idiomatic way to iterate over maps without structured bindings in a pipeline.

**`std::views::split(delim)` and `std::views::lazy_split(delim)`** — Splits a range into subranges.

```cpp
std::string csv = "a,b,c,d";
for (auto token : csv | std::views::split(',')) {
    std::cout << std::string_view(token) << " ";
}
// Prints: a b c d
```

`split` and `lazy_split` differ in whether they materialize the delimiter search eagerly. For most use cases, `split` is sufficient. Both produce subranges, not strings—you must convert to `std::string_view` or `std::string` for printing or storage.

**`std::views::join`** — Flattens a range of ranges into a single range.

```cpp
std::vector<std::vector<int>> nested = {{1, 2}, {3, 4, 5}, {6}};
auto flat = nested | std::views::join;
// {1, 2, 3, 4, 5, 6}
```

`join` handles the awkward case of iterating over a range whose elements are themselves ranges. It hides the nested iteration structure.

**C++23 views** (included in the standard already): `std::views::zip` (iterate multiple ranges in lockstep), `std::views::enumerate` (index each element), `std::views::adjacent<N>` (sliding window of N consecutive elements), `std::views::chunk(N)` (contiguous blocks of N elements), `std::views::stride(N)` (every Nth element). These extend the composition vocabulary significantly.

### The `auto` Deduction Trap with Views

A common mistake is capturing a view with `auto`, which copies the view. For most views, copying is cheap (views are cheap to copy by design), so this is not an issue. But `std::views::filter` has a subtlety: its iterators may store a pointer to the filter's predicate, and copying the view copies the predicate pointer. If the predicate is a lambda with captures, copying the view is safe as long as the lambda's captures remain valid.

More importantly, if you write:

```cpp
auto view = data | std::views::filter(pred);
```

The `auto` copies the view object. This is usually fine. But if the view was created from a temporary range or a prvalue expression, the copy may reference data that no longer exists. The general rule is: **store views only when you are certain the underlying ranges outlive the view**. For short-lived compositions within a single expression, no storage is needed.

### Performance Characteristics of Views

Views eliminate the memory allocation and multiple-pass overhead of manual eager pipelines. But they introduce their own costs:

- **Iterator indirection.** A `filter` iterator wraps the underlying iterator and checks the predicate on every increment. This is a branch that the CPU must predict. For short sequences or sparse filters, the branch predictor handles it well. For long sequences where most elements pass the filter, the overhead is the cost of one branch per element.
- **Deeply nested views.** A view of a view of a view (e.g., `data | transform | filter | take`) produces an iterator type that unwraps multiple layers on each dereference and increment. The compiler usually inlines these layers away — the "abstraction penalty" is zero in optimized builds. In debug builds, however, deeply nested views can be significantly slower than hand-written loops.
- **No parallel execution.** Views compose lazily and serially. You cannot parallelize a range pipeline the way you can with `std::for_each(std::execution::par, ...)`. If you need data parallelism, materialize into a container and use parallel algorithms.

The general guidance: **use views freely for transforms and filters; if you measure a performance problem, profile the view code specifically**. In the vast majority of cases, views are as fast as hand-written loops in optimized builds, and they are much more maintainable.

---

## Custom Range Adaptors

When the standard views do not cover your domain, you can write your own. A custom range adaptor is a function or object that takes a range and returns a view. Writing one requires understanding the view interface, the adaptor object pattern, and the pipe operator mechanics.

### The Anatomy of a View

Every view is a class that:

1. Stores a pointer or reference to the underlying range (or, for owning views, a copy of the data).
2. Provides a `begin()` and `end()` that return custom iterators.
3. Satisfies the `std::ranges::view` concept (move-constructible, constant-time destruction, constant-time copy or move).
4. (Optionally) Is pipeable with `operator|`.

As a running example, we will build a `take_while_view` that takes elements from a range as long as a predicate holds, then stops. This is similar to `std::views::take_while` (which exists in C++20), but we will build it from scratch to illustrate the anatomy.

```cpp
template <std::ranges::view V, std::predicate<std::ranges::range_reference_t<V>> Pred>
class take_while_view : public std::ranges::view_interface<take_while_view<V, Pred>> {
    V base_;
    Pred pred_;

public:
    take_while_view() = default;
    take_while_view(V base, Pred pred) : base_(std::move(base)), pred_(std::move(pred)) {}

    class iterator {
        std::ranges::iterator_t<V> current_;
        std::ranges::sentinel_t<V> sentinel_;
        Pred* pred_;  // pointer to the predicate stored in the view

    public:
        using iterator_concept = std::forward_iterator_tag;
        using value_type = std::ranges::range_value_t<V>;
        using difference_type = std::ranges::range_difference_t<V>;

        iterator() = default;
        iterator(std::ranges::iterator_t<V> current, std::ranges::sentinel_t<V> sentinel, Pred* pred)
            : current_(current), sentinel_(sentinel), pred_(pred) {}

        auto operator*() const { return *current_; }

        auto operator*() const { return *current_; } 

        iterator& operator++() { 
            ++current_; 
            return *this; 
        } 

        bool operator==(const iterator& other) const { 
            return current_ == other.current_; 
        } 

        bool operator==(std::default_sentinel_t) const { 
            return current_ == sentinel_ || !(*pred_)(*current_); 
        }
    };

    iterator begin() { return iterator(std::ranges::begin(base_), std::ranges::end(base_), &pred_); }
    std::ranges::sentinel_t<V> end() { return std::ranges::end(base_); }
};
```

This is a simplified view that works for demonstration. The key details:

- It inherits from `std::ranges::view_interface`, which provides useful member functions like `empty()`, `data()`, `size()`, and `operator bool` based on the iterators we provide.
- The iterator stores a pointer to the predicate (or holds a copy). For simplicity here, we use a pointer; a production implementation might use `std::optional<Pred>` or store the predicate in the iterator directly.
- `begin()` returns our custom iterator. `end()` returns the underlying range's sentinel — we do not need a custom sentinel because the termination condition is already checked in the iterator's dereference logic (the caller must not dereference past the point where the predicate fails, which `std::ranges::take_while` enforces more carefully than shown).

### Making a View Pipeable

To make `take_while_view` work with the `|` operator, we need a **range adaptor object** — a function object that handles the syntax `range | adaptor(args...)`.

```cpp
namespace detail {
    struct take_while_adaptor {
        template <std::predicate Pred>
        constexpr auto operator()(Pred pred) const {
        template <std::predicate Pred>
        constexpr auto operator()(Pred pred) const {
            return [pred = std::move(pred)](auto&& range) {
                return take_while_view<std::views::all_t<decltype(range)>, Pred>(
                    std::views::all(std::forward<decltype(range)>(range)), pred);
            };
        }
        }

        template <std::ranges::viewable_range R, std::predicate Pred>
        constexpr auto operator()(R&& r, Pred pred) const {
            return take_while_view<std::views::all_t<R>, Pred>(
                std::views::all(std::forward<R>(r)), std::move(pred));
        }
    };
}

// The pipe operator overload.
template <std::ranges::viewable_range R, std::predicate Pred>
constexpr auto operator|(R&& r, detail::take_while_adaptor adaptor) {
    // This requires more work to pass the predicate through — see below.
}

inline constexpr detail::take_while_adaptor take_while;
```

This pattern — a function object with two `operator()` overloads — is the standard way to create range adaptors. When you write `range | adaptor(args...)`, the compiler looks for a pipe operator that accepts a range on the left and the adaptor object on the right. The standard library's adaptors follow this pattern internally.

In practice, writing the full pipeable adaptor from scratch is error-prone. The idiomatic approach is to use **`std::ranges::range_adaptor_closure`** (since C++23) or a helper like `ranges::views::transform`'s internal machinery. For C++20, a common approach is to build on top of existing adaptors or to use a helper library like `range-v3`.

### A Simpler Approach: Wrapping Existing Views

Most custom range adaptors do not need a full view implementation. You can often compose existing standard views:

```cpp
// A custom adaptor that squares each element.
constexpr auto squared = std::views::transform([](auto x) { return x * x; });

// Usage:
auto result = data | squared | std::views::take(5);
```

This is a **partial composition** — `squared` is not a view itself but a pre-configured adaptor that can be used in a pipeline. This pattern is the simplest way to create reusable "custom view" logic:

```cpp
// A reusable "only positive" filter.
constexpr auto positives = std::views::filter([](auto x) { return x > 0; });

// A "running total" view built from transform and cached state.
// (See note on stateful transforms below.)
```

The limitation is that this does not create a named view type — `squared` is just `std::views::transform` with a bound lambda. If you need the view to be a distinct type (for overloading, for documentation, or for template specialization), you need the full view class as shown earlier.

### When to Write a Full Custom View

Writing a full custom view class is warranted when:

- The view's iteration logic cannot be expressed as a composition of existing views. For example, a "chunk" view that groups elements into blocks of N requires managing an internal counter and iterator state.
- The view needs to maintain state across element access (beyond what a simple `transform` with a stateful lambda provides — though stateful lambdas in views are fragile because views are often copied).
- The view serves as a vocabulary type in your library's public API and needs a documented name and behavior.

In most other cases, a named adaptor built from existing standard views is sufficient and easier to maintain.

### Stateful Views: A Word of Caution

Views are expected to be cheap to copy. If your view's iterator holds a reference to mutable state in the view object, copying the view creates multiple iterators that reference different copies of the state — leading to subtle bugs:

```cpp
// Dangerous: stateful predicate captured in a view.
auto bad_view = data | std::views::filter([seen = std::set<int>{}](int x) mutable {
    return seen.insert(x).second;  // keep only first occurrence of each value
});

// Two iterations produce different results:
for (int x : bad_view) { /* ... */ }  // first iteration — inserts into seen
for (int x : bad_view) { /* ... */ }  // second iteration — seen is already populated!
```

The first iteration populates `seen`; the second iteration sees a different state. This is almost never what you want. The standard views are designed to be **stateless with respect to iteration** — a view may be iterated multiple times and produce the same result each time (assuming the underlying range is unchanged).

If you need stateful views, either:

1. Materialize into a container first, then iterate the container.
2. Use a **range generator** (a coroutine — see Chapter 27) that encapsulates state naturally without the view contract.

The range adaptor contract assumes idempotent views. Breaking that contract leads to bugs that are hard to diagnose.

---

## Pipeline Composition

The pipe operator `|` is the syntactic innovation that makes range programming feel like a declarative pipeline. Understanding how it works, when to use it, and what its limits are is essential for writing idiomatic range code.

### How the Pipe Operator Works

The expression `data | adaptor | adaptor` is left-associative: it parses as `(data | adaptor) | adaptor`. Each `|` call:

1. Takes the range on the left (which may already be a view).
2. Applies the adaptor's transformation, returning a new view.
3. The result becomes the left operand of the next `|`.

The implementation is approximately:

```cpp
// Roughly how operator| works for range adaptors:
template <std::ranges::viewable_range R, typename Adaptor>
    requires requires { Adaptor{}(std::declval<R>()); }
auto operator|(R&& r, Adaptor adaptor) {
    return adaptor(std::forward<R>(r));
}
```

The adaptor object is a function object (like `std::views::filter{std::less{}}` or a bound adaptor with `std::bind_back`). The pipe operator is simply function application in infix notation. The adaptor object knows how to construct the appropriate view from the input range.

The key design property is that `|` does not add overhead beyond the adaptor's own view construction. There is no virtual dispatch, no heap allocation, no hidden cost. The pipeline is entirely a compile-time composition of types.

### Pipeline Readability: Reverse vs. Nested Notation

Compare the pipeline style to the equivalent nested calls:

```cpp
// Pipeline: reads left to right, top to bottom.
auto result = data 
    | std::views::filter(pred)
    | std::views::transform(f)
    | std::views::take(10);

// Nested: reads inside-out, right to left.
auto result = std::views::take(
    std::views::transform(
        std::views::filter(data, pred),
        f),
    10);
```

The pipeline version makes the execution order match the reading order. Data enters at the top (`data`), flows through `filter`, then `transform`, then `take`. In the nested version, you must read from the innermost call outward: first `filter`, then `transform`, then `take` — but the order of arguments is reversed compared to the logical data flow.

This difference matters more as the pipeline grows. A pipeline with five or six stages is still readable. The same logic in nested form becomes deeply indented and hard to parse.

### Terminal Operations: Breaking the Pipeline

A pipeline produces a view. To extract concrete results, you need a **terminal operation** — something that consumes the view and produces a value or fills a container. Common terminal operations:

**Iteration:**

```cpp
for (int x : data | views::filter(pred) | views::transform(f)) {
    // x is computed here — lazy evaluation.
}
```

**Container construction:**

```cpp
// Materialize into a vector.
std::vector<int> result(
    data | views::filter(pred) | views::transform(f) | views::take(10)
);
```

The `std::vector` constructor accepts an iterator pair. The view provides them. This is the idiomatic way to convert a lazy pipeline into an eager container.

**Algorithm termination:**

```cpp
// Find the first matching element.
auto it = std::ranges::find_if(
    data | views::filter(pred) | views::transform(f),
    some_condition
);
```

Range algorithms accept views as their range argument. The algorithm triggers lazy iteration until it finds a match, then stops — it does not materialize the entire pipeline.

**Reduction:**

```cpp
auto sum = std::ranges::fold_left(
    data | views::filter(pred) | views::transform(f),
    0, std::plus{}
);
// C++23 fold algorithms.
```

### Eager vs. Lazy: When to Materialize

Views are lazy, but laziness is not always the best choice. Three situations favor eager materialization:

**1. Multiple passes.** If you need to iterate the same transformed data twice, a view recomputes the transformation on each pass. Materializing into a container computes it once:

```cpp
// Lazy: filter and transform run twice.
auto view = data | views::filter(pred) | views::transform(f);
for (int x : view) { /* first pass */ }
for (int x : view) { /* second pass — filter and transform run again */ }

// Eager: done once.
std::vector<int> materialized(view.begin(), view.end());
for (int x : materialized) { /* first pass */ }
for (int x : materialized) { /* second pass — no recomputation */ }
```

**2. Long-lived result.** If the pipeline result outlives the function that created it, and the underlying data may be destroyed, materialize:

```cpp
std::vector<int> get_processed() {
    std::vector<int> data = get_data();
    auto view = data | views::filter(pred) | views::transform(f);
    return std::vector<int>(view.begin(), view.end());
    // Safe: the returned vector owns the data.
}
```

**3. Debugging.** View types are compiler-generated and nearly unreadable in debugger output. Materializing into a container makes the state inspectable:

```cpp
auto view = data | views::filter(pred);  // type: what the compiler generates
std::vector<int> debug_view(view.begin(), view.end());
// debug_view is a plain vector, trivially inspectable.
```

### Pipeline Short-Circuiting

One of the elegant properties of lazy pipelines is that they **short-circuit** when combined with algorithms that stop early:

```cpp
// Does this iterate the entire range?
auto first_good = std::ranges::find_if(
    data | views::transform(expensive_transform) | views::filter(cheap_filter),
    is_perfect
);
```

No. The pipeline produces elements one at a time. `find_if` asks for elements from the pipeline until `is_perfect` returns true. Each element goes through `expensive_transform` and `cheap_filter` exactly once, and as soon as `is_perfect` matches, no more elements are produced.

This is the same efficiency you would get from a hand-written loop that breaks early:

```cpp
auto it = data.begin();
while (it != data.end()) {
    auto transformed = expensive_transform(*it);
    if (cheap_filter(transformed) && is_perfect(transformed)) {
        break;
    }
    ++it;
}
```

The pipeline version is more declarative and harder to get wrong. The compiler generates equivalent code in optimized builds.

### Composing Views with Side Effects

A common pitfall is putting side effects inside a view transformation:

```cpp
int call_count = 0;
auto logging_transform = std::views::transform([&call_count](int x) {
    ++call_count;  // side effect
    std::cout << "processing " << x << "\n";  // side effect
    return x * 2;
});

auto view = data | logging_transform | std::views::take(3);
```

How many times is `call_count` incremented? The answer depends on how `view` is iterated. If iterated once, it is incremented up to 3 times (or fewer if data has fewer than 3 elements). But if `view` is copied and iterated again, it is incremented again for each element. The side effect is tied to the iteration, not to the view creation — and because iteration can happen multiple times, the side effects compound.

The principle is: **view operations should be pure functions of the input.** If you need side effects, materialize the pipeline into a container and apply side effects to the container, or use `std::ranges::for_each` as a terminal operation.

### Pipeline Debugging Strategies

When a pipeline does not produce the expected result, the lazy nature of views makes debugging harder than debugging a loop. Three strategies help:

**1. Materialize intermediate stages.** Insert `std::views::common` (to get a `begin`/`end` pair of the same type) and construct a small vector at each stage:

```cpp
auto stage1 = data | views::filter(pred);
// std::vector<int> dbg1(stage1.begin(), stage1.end());  // uncomment to inspect

auto stage2 = stage1 | views::transform(f);
// std::vector<int> dbg2(stage2.begin(), stage2.end());

auto stage3 = stage2 | views::take(10);
```

**2. Add logging adaptors.** Create a `tap` view (not in the standard library but trivial to write) that logs each element as it passes through:

```cpp
auto tap = [](const char* label) {
    return std::views::transform([label](auto x) {
        std::cout << label << ": " << x << "\n";
        return x;
    });
};

auto result = data | tap("input") | views::filter(pred) | tap("filtered") | views::transform(f);
```

**3. Reduce the pipeline.** Start with just the first stage, verify it, then add stages one at a time. This isolates which stage introduces the bug.

### Pipeline Composition Summary

The following table shows the four main roles in a range pipeline:

| Role | Examples | Behavior |
|---|---|---|
| Source | `std::vector`, `std::array`, `std::views::iota`, `std::views::istream` | Provides elements. May be owning (container) or non-owning (view). |
| Adaptor | `filter`, `transform`, `take`, `drop`, `reverse`, `split` | Transforms the element stream. Lazy, non-owning. |
| Composition | `operator\|` | Connects adaptors left-to-right, creating a compound view type. |
| Terminal | `for`, vector constructor, `std::ranges::find_if`, `std::ranges::fold_left` | Consumes the view, produces a concrete result. |

The pipeline style is not a replacement for all loops. It excels when the transformation is a sequence of independent steps applied to each element. It is less suitable when:

- The algorithm requires access to previous results in a non-trivial way (though `views::adjacent` and `views::slide` help in C++23).
- The algorithm is stateful and must be iterated exactly once in a specific way (coroutines are a better fit here — see Chapter 27).
- The algorithm needs to terminate early based on data from later in the sequence (you need random access for that, not a lazy pipeline).

But for the common case of "filter some elements, transform them, take a subset," the pipeline style is clearer, safer, and often faster than the equivalent loop.

---

## Summary

The C++20 Ranges library changes how we write code that operates on sequences. The key ideas to carry forward:

- **Range algorithms** accept a range (single argument) instead of an iterator pair. They support projections, which separate the "what to compare" from "how to compare," and sentinels, which allow sequences whose end is defined by a condition rather than a position.

- **Views are lazy and non-owning.** They compose transformations without materializing intermediate results. The standard library provides a rich vocabulary of views: `filter`, `transform`, `take`, `drop`, `reverse`, `split`, `join`, `keys`, `values`, and more in C++23.

- **Custom views** are built by writing a view class and a range adaptor object. For most practical needs, composing standard views is sufficient — the full custom view is only needed when the iteration logic fundamentally cannot be expressed with existing primitives.

- **Pipeline composition** with `|` makes data transformations read in execution order. Pipelines are best for stateless, element-by-element transformations. They short-circuit naturally with algorithms that stop early.

The Ranges library is not the final word on sequence processing — coroutines (Chapter 27) add another dimension by allowing generators and async sequences. But ranges handle the vast majority of data transformation tasks with a clarity that the old iterator-pair APIs could never achieve. The investment in learning them pays back in every subsequent project.

### Exercises

1. **Basic pipeline.** Given a `std::vector<int>`, write a pipeline that filters odd numbers, squares the remainder, and takes the first 5. Compare the result with a manual loop.

2. **Projections with custom types.** Define `struct Employee { std::string name; int salary; int department_id; };` and a `std::vector<Employee>`. Write a range algorithm that finds the highest-paid employee in department 3, using projections.

3. **Custom adaptor.** Write a custom adaptor `drop_last(n)` that returns a view of all but the last `n` elements of a range. (Hint: you will need to know the size of the range. For sized ranges, this is straightforward; for forward ranges, it requires two passes or a buffer.)

4. **Performance comparison.** Generate a `std::vector<int>` of 10 million elements. Compare the runtime of:
   - A pipeline: `data | filter(pred) | transform(f)` iterated in a for loop.
   - A manual loop that filters and transforms in one pass.
   - A classic eager approach: copy_if into a vector, then transform into another vector.
   Run the comparison in both debug and optimized (O2) builds. What do you observe about the relative performance?

5. **Dangling detection.** Write a function that returns a view of the first 5 elements of a local `std::vector<int>`. Compile it. What does the compiler warn about? How would you fix it?
