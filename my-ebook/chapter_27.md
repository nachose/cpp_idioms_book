# Chapter 27: Coroutines and Async

C++20 introduced coroutines — a language feature for writing resumable functions that can suspend execution at a point, yield a value (or an await signal), and later resume from where they left off. Coroutines are not a library feature like `std::future` or `std::thread`; they are a **language mechanism** that library authors build on. The standard library provides minimal coroutine support (`std::coroutine_handle`, `std::suspend_always`, `std::suspend_never`), leaving the semantics of suspension, resumption, and value propagation to library-level types like generators, tasks, and awaitables.

This makes coroutines unusually flexible — and unusually complex. Unlike most C++ features, coroutines require you to understand a **protocol**: a set of conventions between the compiler, your types, and the runtime. This chapter covers the fundamentals of that protocol, then builds up to generators, awaitable types, and task-based async patterns.

---

## Coroutine Fundamentals

A coroutine is any function that contains one of three keywords: `co_await`, `co_return`, or `co_yield`. The presence of these keywords changes how the compiler compiles the function. Instead of producing a normal function that runs to completion on a single call, the compiler transforms the function into a **state machine** whose state is stored in a heap-allocated **coroutine frame**.

### Motivation: What Problem Do Coroutines Solve?

Before coroutines, writing code that could pause and resume required one of several approaches, each with significant drawbacks:

**Callbacks** invert control flow. A function that needs to wait for an asynchronous result accepts a callback that it invokes when the result is ready. The problem is that logic that would naturally be expressed sequentially — do A, wait, do B with the result, wait, do C — becomes a deeply nested chain of callbacks, known colloquially as "callback hell":

```cpp
// Callback style: nesting obscures the sequential intent.
fetch_data([](Data d) {
    process(d, [](Result r) {
        save(r, []() {
            notify("done");
        });
    });
});
```

Each nesting level adds indentation, separates the dependent operations, and makes error handling awkward (every callback must handle errors independently).

**Threads** preserve sequential logic but introduce their own costs. Each thread consumes significant stack memory (typically 1-8 MB on desktop systems), context switching is expensive, and synchronization between threads requires locks or atomic operations that are easy to get wrong:

```cpp
// Thread style: sequential but heavyweight.
std::thread t([&] {
    Data d = fetch_data();   // blocks the thread
    Result r = process(d);   // still on the same thread
    save(r);
    notify("done");
});
t.join();
```

For I/O-bound work where most of the time is spent waiting (on network, disk, user input), dedicating an OS thread per operation is wasteful. A thousand concurrent operations would require a thousand threads — infeasible on most systems.

**State machines** avoid both problems but require manual implementation. You encode each suspension point as a state in an explicit enum, and the function body becomes a switch statement that jumps to the right state on each call:

```cpp
// State machine style: efficient but manual.
struct FetchProcessSave {
    enum State { START, FETCHING, PROCESSING, SAVING, DONE };
    State state = START;
    Data data;
    Result result;

    void operator()() {
        switch (state) {
        case START:
            start_fetch([this](Data d) {
                data = d;
                state = FETCHING;
                (*this)();   // re-enter
            });
            break;
        case FETCHING:
            start_process(data, [this](Result r) {
                result = r;
                state = PROCESSING;
                (*this)();
            });
            break;
        case PROCESSING:
            start_save(result, [this]() {
                state = SAVING;
                (*this)();
            });
            break;
        case SAVING:
            notify("done");
            state = DONE;
            break;
        case DONE:
            break;
        }
    }
};
```

This works but is fragile: adding a step means adding an enum value, a callback, and wiring the state transition. The sequential structure is buried inside the switch.

Coroutines solve all three problems at once. They let you write the sequential version — the same code you would write with threads — while executing with the efficiency of the state machine approach. The compiler generates the state machine for you:

```cpp
// Coroutine style: sequential readability, state machine efficiency.
Task fetch_process_save() {
    Data d = co_await async_fetch_data();
    Result r = co_await async_process(d);
    co_await async_save(r);
    notify("done");
}
```

This function reads sequentially, uses no threads for waiting, and the compiler transforms it into a state machine equivalent to the manual version. Each `co_await` becomes a suspension point: the coroutine frame is saved, control returns to the caller, and when the awaited operation completes, the coroutine resumes from the next line.

The cost of this convenience is complexity in the types: the return type (`Task` above), the promise type, and the awaitable types must all cooperate according to the coroutine protocol. Understanding that protocol is essential.

### The Coroutine Frame

When a coroutine is called, the compiler allocates a **coroutine frame** on the heap. This frame stores:

- The **promise object** — a user-defined type that controls the coroutine's behavior (what happens on suspension, what value is returned, how exceptions are handled).
- Copies of the function **parameters** (passed by value; reference parameters are copied as references).
- The **suspended state** of local variables that are live across suspension points. The compiler generates code to save and restore these variables when the coroutine suspends and resumes.
- The **resumption point** — an index into the generated state machine that tells the coroutine where to continue when resumed.

The frame is allocated via `operator new` unless the promise type provides a custom allocation function. This heap allocation is the most commonly cited performance concern with coroutines, but it is not inescapable. The compiler may elide the allocation when the coroutine's lifetime is known to be nested within the caller's scope (a situation called "allocation elision," which most compilers implement for common cases), and the promise type can customize the allocator.

```cpp
// Conceptual structure of a coroutine frame (compiler-generated).
struct CoroutineFrame {
    PromiseType promise;
    Parameters params;       // copies of function parameters
    int resume_point;        // state machine index
    // local variables live across suspension points
};
```

The frame is alive from the moment the coroutine is called until the coroutine reaches a final suspension point (typically after `co_return` or the end of the body). The coroutine handle (`std::coroutine_handle<PromiseType>`) is a non-owning pointer to this frame. Destroying the handle without allowing the coroutine to reach its final suspension leaks the frame; calling `handle.destroy()` destroys the frame and calls the promise's destructor.

### The Promise Type Protocol

Every coroutine return type must define a nested **promise type** (or specialize `std::coroutine_traits` to provide one). The promise type is the control center: it decides what happens when the coroutine starts, suspends, returns a value, throws an exception, and finishes.

The compiler interacts with the promise type through a fixed set of member functions. The following shows the minimal promise type required for a coroutine that returns `void` and does not co_await anything:

```cpp
struct VoidPromise {
    // Called immediately when the coroutine starts.
    std::suspend_never initial_suspend() { return {}; }

    // Called when the coroutine reaches its final suspension point.
    std::suspend_never final_suspend() noexcept { return {}; }

    // Called when co_return is encountered (without a value).
    void return_void() {}

    // Called when an exception escapes the coroutine body.
    void unhandled_exception() { std::terminate(); }
};
```

The return type that uses this promise would look like:

```cpp
struct VoidTask {
    struct promise_type : VoidPromise {
        VoidTask get_return_object() {
            return VoidTask{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
    };

    std::coroutine_handle<promise_type> handle;
};
```

Each member of the promise protocol serves a specific purpose:

| Member | When called | Purpose |
|---|---|---|
| `get_return_object()` | Before the coroutine body starts | Creates the return value that the caller receives. Typically constructs the return object from a `coroutine_handle` pointing to the promise. |
| `initial_suspend()` | After `get_return_object()`, before the body | Returns an awaitable. If it suspends, the coroutine does not execute any body code until the caller resumes it. `suspend_never` means the body starts immediately. |
| `final_suspend()` | After the body completes (return or exception) | Returns an awaitable. This is the last opportunity to observe the coroutine's result before the frame is destroyed. Must return `suspend_always` if the coroutine handle must outlive the coroutine body. `noexcept` is required. |
| `return_void()` or `return_value(T)` | On `co_return;` or `co_return expr;` | Stores the result. Exactly one of these must be defined, not both. |
| `unhandled_exception()` | When an exception escapes the body | Typically stores the exception pointer for later rethrowing. |
| `yield_value(T)` | On `co_yield expr;` | Stores the yielded value and returns an awaitable that controls suspension after the yield. |

The promise type is stored inside the coroutine frame. Its lifetime begins when the coroutine frame is allocated (before the body starts) and ends when the frame is destroyed. It acts as a communication channel between the coroutine body and the external code that holds the coroutine handle.

### The Awaitable Protocol

When a coroutine executes `co_await expr`, the compiler evaluates `expr` to produce an **awaitable** — an object that defines three special functions. These functions control the suspension behavior:

```cpp
// The awaitable protocol (conceptual).
struct MyAwaitable {
    // (1) Should we suspend?
    bool await_ready() const noexcept { return false; }

    // (2) Called if we suspend. Returns void or a coroutine handle.
    //    'handle' is the coroutine_handle of the current coroutine.
    void await_suspend(std::coroutine_handle<> handle) {
        // schedule handle.resume() to be called later
    }

    // (3) Called when the coroutine resumes. The return value
    //    becomes the result of the co_await expression.
    int await_resume() noexcept { return 42; }
};
```

The three functions form a well-defined lifecycle:

1. **`await_ready()`** is called first. If it returns `true`, the awaitable is already complete, and the coroutine does **not** suspend — it proceeds directly to `await_resume()`. This optimization avoids unnecessary suspension overhead when the result is available immediately. For example, a `co_await` on a cached value can return `true` from `await_ready()` and skip the frame save entirely.

2. **`await_suspend()`** is called only if `await_ready()` returned `false`. It receives the current coroutine's handle (typed as `std::coroutine_handle<>` — the type-erased handle). Inside `await_suspend`, you schedule the handle for resumption. Common strategies:
   - Return `void` and store the handle somewhere (e.g., in a callback registry) to resume later.
   - Return `true` to tell the runtime to immediately resume the current coroutine (effectively a no-op suspension).
   - Return `false` to not suspend after all (rare).
   - Return a `coroutine_handle` for a **different** coroutine to transfer control to that coroutine immediately (asymmetric transfer).

3. **`await_resume()`** is called after the coroutine resumes. Its return value becomes the result of the `co_await` expression. If the awaitable completed with an error, `await_resume()` typically rethrows the stored exception.

The standard library provides two trivial awaitables:

- **`std::suspend_always`**: `await_ready()` returns `false`, `await_suspend()` does nothing, `await_resume()` returns `void`. Always suspends.
- **`std::suspend_never`**: `await_ready()` returns `true`. Never suspends.

These are useful in promise member functions like `initial_suspend()` and `final_suspend()`, where you need to control whether suspension happens.

### The Three Keywords

Coroutines use three keywords, each serving a distinct purpose:

**`co_await`** — Suspends the coroutine until the awaited operation completes. This is the general-purpose suspension mechanism:

```cpp
auto result = co_await some_awaitable;
```

The expression `some_awaitable` must satisfy the awaitable protocol. The coroutine suspends (unless `await_ready()` returns true), and control returns to the caller or resumer. When the operation completes, the coroutine resumes and the expression evaluates to `await_resume()`'s return value.

**`co_return`** — Returns a value from the coroutine (or completes it without a value):

```cpp
co_return 42;         // calls promise.return_value(42)
co_return;            // calls promise.return_void()
```

After `co_return`, the coroutine cannot be resumed. The promise's `return_void()` or `return_value()` is called, followed by destruction of local variables and `final_suspend()`.

**`co_yield`** — Produces a value for a generator-style coroutine:

```cpp
co_yield some_value;  // equivalent to co_await promise.yield_value(some_value)
```

The `co_yield` expression is syntactic sugar for calling `promise.yield_value()` and then `co_await`-ing the result. It is used in generator coroutines that produce a sequence of values (covered in the Generator Patterns section).

A function is a coroutine if and only if it contains at least one of these keywords. The compiler detects this at the syntax level before any semantic analysis: the presence of `co_await`, `co_return`, or `co_yield` triggers the coroutine transformation regardless of whether the keyword is actually reachable at runtime.

### The State Machine Mental Model

The compiler's transformation of a coroutine into a state machine is the key to understanding performance and behavior. Consider a simple coroutine:

```cpp
Task example() {
    int x = co_await read_int();
    int y = co_await read_int();
    co_return x + y;
}
```

The compiler generates something equivalent to:

```cpp
// Conceptual transformation (simplified).
struct ExampleFrame : Task::promise_type {
    int resume_point = 0;
    int x, y;

    void resume() {
        switch (resume_point) {
        case 0: {
            auto&& awaitable = read_int();
            if (!awaitable.await_ready()) {
                resume_point = 1;
                awaitable.await_suspend(handle);
                return;  // suspend — control back to caller
            }
            // fall through if ready
        }
        case 1: {
            x = awaitable.await_resume();
            auto&& awaitable2 = read_int();
            if (!awaitable2.await_ready()) {
                resume_point = 2;
                awaitable2.await_suspend(handle);
                return;
            }
        }
        case 2: {
            y = awaitable2.await_resume();
            promise.return_value(x + y);
            // fall through to final_suspend
        }
        }
    }
};
```

Each `co_await` generates a state transition. The `resume_point` index tells the coroutine where to continue when `resume()` is called again. Variables that are live across suspension points (`x`, `y`) are stored in the frame. Variables that are only used between suspension points (like `awaitable`) may be stored on the stack of the `resume()` function — they do not need to persist across suspensions.

This transformation has direct performance implications:

- **Variables that do not cross a suspension point** live on the stack and incur no overhead. The compiler is generally good at detecting which variables are live across suspension points. Only those variables are promoted to the coroutine frame.
- **Each suspension point** adds a branch (the switch/case dispatch) and a store of the resume point. This is typically 2–3 instructions per suspension point.
- **The frame size** depends on how many live-across-suspension variables exist. A coroutine that awaits once with a single `int` live across has a tiny frame. A coroutine that captures large local arrays across suspension points has a larger frame.

The practical takeaway is that a single `co_await` in a hot loop is not expensive — the state machine dispatch is comparable to a virtual function call. The costs that matter are the heap allocation of the frame (which can be elided or customized) and the actual work done in `await_suspend` (which typically involves scheduling the resumption on an executor).

### Returning Values to the Caller

The `get_return_object()` function bridges the coroutine and its caller. It is called before the coroutine body starts, and its return value is what the caller sees when it invokes the coroutine function:

```cpp
Task my_task = example();  // get_return_object() is called here
```

Typically, `get_return_object()` constructs the return type from the promise's `coroutine_handle`. The return type then provides methods to interact with the coroutine — like `resume()`, `destroy()`, or `get()`:

```cpp
struct Task {
    struct promise_type {
        int result_;
        bool done_ = false;

        Task get_return_object() {
            return Task{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }

        std::suspend_never initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_value(int v) { result_ = v; done_ = true; }
        void unhandled_exception() { std::terminate(); }
    };

    std::coroutine_handle<promise_type> handle_;

    int get() const {
        return handle_.promise().result_;
    }

    bool done() const {
        return handle_.done();
    }
};
```

In this example:

- `initial_suspend()` returns `suspend_never`, so the coroutine body starts executing immediately — `example()` begins running before the caller gets control back.
- `final_suspend()` returns `suspend_always`, meaning the coroutine suspends one final time after computing the result. This allows the caller to read the result via `handle_.promise().result_` without the frame being destroyed.
- The caller must eventually call `handle_.destroy()` to free the coroutine frame.

The choice of `initial_suspend()` is significant. **Lazy coroutines** (those that do not start until explicitly resumed) use `initial_suspend()` returning `suspend_always`. **Eager coroutines** (those that start immediately) use `suspend_never`. The trade-off mirrors that of `std::async` with `std::launch::deferred` vs `std::launch::async`: eager coroutines begin work immediately and may produce results faster, but lazy coroutines give the caller control over scheduling and thread affinity.

### Exception Handling

When an exception escapes the coroutine body, the compiler calls `promise.unhandled_exception()`. The typical implementation captures the exception pointer for later propagation:

```cpp
struct TaskPromise {
    std::exception_ptr ex_;

    void unhandled_exception() noexcept {
        ex_ = std::current_exception();
    }

    // In final_suspend, this exception will be rethrown
    // when the caller retrieves the result.
};
```

The coroutine then reaches `final_suspend()`, where it suspends (assuming `suspend_always`). The caller, upon trying to retrieve the result, checks for the stored exception and rethrows it:

```cpp
struct Task {
    // ...
    int get() {
        if (handle_.promise().ex_) {
            std::rethrow_exception(handle_.promise().ex_);
        }
        return handle_.promise().result_;
    }
};
```

If `unhandled_exception()` calls `std::terminate()` instead (or if no exception handling is implemented), the program terminates when an exception escapes the coroutine. This is rarely the right choice for library code but may be acceptable for simple examples.

The exception propagation mechanism means that exceptions work naturally with coroutines: a `co_await` operation that encounters an error can throw, and the exception unwinds through the coroutine frame, triggering `unhandled_exception()` instead of the normal return path. The coroutine type determines whether that exception is stored, suppressed, or transformed.

### Customizing Allocation

By default, the coroutine frame is allocated via `::operator new`. The promise type can customize this in two ways:

**1. Overloading `operator new` in the promise type:**

```cpp
struct TaskPromise {
    // Custom allocator for this coroutine type.
    void* operator new(std::size_t size) {
        return my_pool.allocate(size);
    }

    void operator delete(void* ptr, std::size_t size) {
        my_pool.deallocate(ptr, size);
    }
};
```

The compiler calls `TaskPromise::operator new(size)` to allocate the frame. This allows using a specific memory pool, arena, or stack allocator for coroutines of this type.

**2. Providing `get_return_object_on_allocation_failure()`:**

```cpp
struct TaskPromise {
    static Task get_return_object_on_allocation_failure() {
        throw std::bad_alloc();
        // or: return Task{nullptr}; and check for null handle
    }
};
```

This member is optional. If defined, the compiler uses a `nothrow` allocation attempt and calls this function if allocation fails. This allows the coroutine to handle allocation failure gracefully rather than throwing `std::bad_alloc` from the allocation site.

The allocation customization is one of coroutines' most practical features for real-time or embedded systems, where heap allocation in the hot path is prohibited. A promise type that uses a fixed-size pool or a bump allocator can eliminate the allocation unpredictability.

### The Asymmetric Transfer Optimization

When `await_suspend` returns a `coroutine_handle` for a different coroutine, the runtime performs a **symmetric transfer**: it immediately resumes the returned coroutine without returning to the caller. This is the mechanism behind cooperative multitasking with coroutines:

```cpp
// Inside an awaitable's await_suspend:
std::coroutine_handle<> await_suspend(std::coroutine_handle<> current) {
    // Transfer control to another coroutine instead of returning.
    return next_coroutine_handle;
}
```

This avoids stack growth that would occur if coroutines simply resumed each other through nested `resume()` calls. Instead of:

```
resume(A) -> resumes(B) -> ... depth grows
```

The symmetric transfer does:

```
resume(A) -> (A suspends, returns B's handle) -> resume(B) directly
```

The runtime tail-calls the transfer, keeping the call stack flat. This is essential for coroutine frameworks that chain many operations — without symmetric transfer, deeply nested coroutine calls would overflow the stack.

### Coroutine Handles

`std::coroutine_handle<PromiseType>` is the primary handle type for interacting with coroutines. It is a non-owning, trivially copyable pointer to the coroutine frame (typically just a pointer to the promise object, which lives inside the frame).

Key operations:

```cpp
// Create a handle from a promise reference.
auto handle = std::coroutine_handle<promise_type>::from_promise(promise);

// Resume the coroutine (if suspended).
handle.resume();

// Check if the coroutine is done (at final suspension).
bool done = handle.done();

// Destroy the coroutine frame.
handle.destroy();

// Get a reference to the promise object.
auto& promise = handle.promise();

// Convert to the type-erased handle (no promise type information).
std::coroutine_handle<> erased = handle;
```

The type-erased `std::coroutine_handle<>` is useful for interfaces that do not need to access the promise — for example, a scheduler that only needs to resume coroutines. Most awaitable types store a `std::coroutine_handle<>` to avoid depending on the caller's promise type.

A coroutine handle must be used correctly: calling `resume()` on a completed coroutine is undefined behavior; calling `destroy()` on a coroutine that has not reached final suspension may leak resources held by local variables; and using the handle after the coroutine frame is destroyed is a use-after-free error.

### Lifetime Model and Common Pitfalls

The coroutine lifetime model has several properties that differ from normal functions:

**The coroutine frame outlives the function call.** When you call a coroutine function, it allocates the frame, calls `get_return_object()`, and may execute some or none of the body before returning the return object. The frame persists until the coroutine reaches final suspension or is explicitly destroyed.

**Parameters are copied into the frame.** If a coroutine takes parameters by reference, the reference is copied, not the pointee. If the referenced object is destroyed before the coroutine resumes, the reference dangles:

```cpp
Task bad_coro(const std::vector<int>& data) {
    // 'data' is a reference. The reference is stored in the frame.
    co_await something;  // suspension point
    // If the original vector was destroyed, 'data' dangles here.
    use(data);
}

// Caller:
Task t;
{
    std::vector<int> v = {1, 2, 3};
    t = bad_coro(v);  // reference to v is stored
}  // v is destroyed
t.resume();  // undefined behavior: dangling reference
```

The fix is to take parameters by value (copying them into the frame) or ensure the referenced objects outlive the coroutine.

**Resuming from multiple threads concurrently is a data race.** A coroutine handle is not thread-safe by itself. Calling `handle.resume()` from two threads simultaneously is undefined behavior. The awaitable's `await_suspend` must ensure that the coroutine is only resumed on one thread at a time, typically by scheduling the resumption on a single-threaded executor or using an atomic flag.

**Destroying a suspended coroutine.** Calling `handle.destroy()` on a coroutine that is suspended at a `co_await` is valid — it destroys the frame and all local variables. However, it does not call `await_resume()`, so any side effects that the awaitable expected to happen on resumption are skipped. The awaitable must be designed to handle this case (for example, by unregistering any pending callbacks when the coroutine handle is destroyed).

### When to Use Raw Coroutine Handles vs. Library Types

The C++20 standard provides the coroutine language mechanism but deliberately omits high-level coroutine types from the library. There is no `std::generator`, `std::task`, or `std::async_scope` in C++20 (C++23 adds `std::generator`). This means that for most practical work, you will either:

- Write your own coroutine return types (promise types, awaitables, tasks), which is instructive but time-consuming and error-prone.
- Use a library like cppcoro, folly::coro, or boost::asio that provides production-ready coroutine primitives.

Writing your own promise type from scratch is a rite of passage for understanding coroutines, but for real projects, library types are strongly recommended. The fundamental patterns — generator, task, shared task, awaitable backports — have been refined by the community, and implementing them correctly requires attention to edge cases (destroy during suspension, exception safety, symmetric transfer, executor affinity) that are easy to get wrong.

### Coroutine Fundamentals: Key Takeaways

- A coroutine is any function containing `co_await`, `co_return`, or `co_yield`. The compiler transforms it into a state machine stored in a heap-allocated coroutine frame.
- The **promise type** controls coroutine behavior: what happens on start, suspension, return, and exception. Each coroutine return type defines its own promise type.
- The **awaitable protocol** — `await_ready`, `await_suspend`, `await_resume` — controls suspension for individual `co_await` expressions.
- Variables that are live across suspension points are stored in the frame; other variables remain on the stack. The compiler is good at optimizing this, but large arrays or objects that must persist across suspension increase frame size.
- Frame allocation is customizable via the promise type's `operator new`, enabling pool allocators for real-time use.
- Symmetric transfer (`await_suspend` returning a coroutine handle) enables flat call stacks in cooperative coroutine scheduling.
- Coroutine handles are non-owning pointers. Their validity must be managed manually — the frame is not reference-counted.

The remaining sections of this chapter build on these fundamentals: generators use `co_yield` to produce sequences; awaitable types encapsulate the suspension protocol for specific async operations; and task types compose multiple async operations into a coherent workflow.

---

## Generator Patterns

A generator is a coroutine that produces a sequence of values lazily, one at a time, using `co_yield`. Unlike a function that builds and returns a container (which computes all values eagerly), a generator suspends after each value and resumes only when the next value is requested. This makes generators suitable for infinite sequences, streaming data, and algorithms where computing every element upfront would be wasteful.

The concept is not new — Python generators (`yield`), C# iterators (`yield return`), and JavaScript generators (`function*`) all follow the same pattern. C++20 introduced the language mechanism, and C++23 added `std::generator` to the standard library. Understanding generators requires understanding how `co_yield` interacts with the promise type and how the caller drives the coroutine by resuming it for each value.

### Motivation: Why Generators Exist

Before generators, producing a sequence of values in C++ required one of several approaches, each with limitations:

**Eager containers** compute every element before the caller can use any of them:

```cpp
std::vector<int> fibonacci(int n) {
    std::vector<int> result;
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        result.push_back(a);
        int next = a + b;
        a = b;
        b = next;
    }
    return result;
}

// Caller must wait for all n values to be computed.
for (int x : fibonacci(1000000)) {
    // x is available only after the entire vector is built.
}
```

For large or infinite sequences, eager computation is impossible. Even for finite sequences, eager computation forces the caller to choose between allocating memory for all elements (which may be expensive) or processing elements one at a time from a container (which still requires the container to exist).

**Iterator-based generators** produce values lazily by hand-writing a custom iterator type:

```cpp
class FibonacciIterator {
    int a_ = 0, b_ = 1;
public:
    int operator*() const { return a_; }
    FibonacciIterator& operator++() {
        int next = a_ + b_;
        a_ = b_;
        b_ = next;
        return *this;
    }
    bool operator!=(std::default_sentinel_t) const {
        return true;  // infinite
    }
};
```

This works but requires boilerplate: the iterator class, the sentinel, and the wiring. For each new sequence type, you write a new iterator class. The logic of the sequence is buried inside the iterator's `operator++` and `operator*`, which are separated from each other.

**Callback-based push** has the caller provide a callback that is invoked for each value:

```cpp
template <typename Callback>
void fibonacci(int n, Callback cb) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        cb(a);
        int next = a + b;
        a = b;
        b = next;
    }
}

fibonacci(10, [](int x) { std::cout << x << " "; });
```

The logic of the sequence and the logic of consuming it are cleanly separated. But the pattern inverts control: the producer drives the loop, not the consumer. The consumer cannot easily stop early, skip elements, or compose the sequence with other operations.

**Generators** solve all three problems: the sequence logic is written as a straightforward sequential function (like the eager version), the values are produced lazily one at a time (like the iterator version), and the caller drives consumption (like the callback version, but with control in the caller's hands):

```cpp
// Generator: sequential logic, lazy production, caller-driven consumption.
std::generator<int> fibonacci(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;
        int next = a + b;
        a = b;
        b = next;
    }
}

for (int x : fibonacci(10)) {
    std::cout << x << " ";  // 0 1 1 2 3 5 8 13 21 34
}
```

The function body reads like the eager version, but each `co_yield` suspends execution and returns a value to the caller. The `for` loop drives the coroutine: it resumes `fibonacci` to get each next value, and when the loop body completes, control returns to the coroutine for the next iteration.

### The Generator Promise Type

A generator's promise type must implement `yield_value`, which is called when the coroutine executes `co_yield`. The promise also controls `initial_suspend` and `final_suspend` to match the generator's lazy semantics.

Here is a minimal generator type that works without C++23:

```cpp
template <typename T>
class Generator {
public:
    struct promise_type {
        T current_value_;

        // Lazy: don't start until the caller asks for the first value.
        std::suspend_always initial_suspend() noexcept { return {}; }

        // Keep the frame alive so the caller can observe after completion.
        std::suspend_always final_suspend() noexcept { return {}; }

        // Called on co_yield expr. Stores the value and suspends.
        std::suspend_always yield_value(T value) noexcept {
            current_value_ = std::move(value);
            return {};
        }

        // Generators do not use co_return with a value.
        void return_void() noexcept {}

        void unhandled_exception() noexcept {
            exception_ = std::current_exception();
        }

        Generator get_return_object() {
            return Generator{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }

        std::exception_ptr exception_;
    };

    // Iterator that drives the coroutine.
    class iterator {
        std::coroutine_handle<promise_type> handle_;
    public:
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using iterator_concept = std::input_iterator_tag;

        explicit iterator(std::coroutine_handle<promise_type> h) : handle_(h) {}

        iterator& operator++() {
            handle_.resume();               // resume to produce next value
            if (handle_.done()) {
                // Check for stored exception.
                if (handle_.promise().exception_) {
                    std::rethrow_exception(handle_.promise().exception_);
                }
            }
            return *this;
        }

        const T& operator*() const {
            return handle_.promise().current_value_;
        }

        bool operator==(std::default_sentinel_t) const {
            return handle_.done();
        }
    };

    // begin() resumes the coroutine to produce the first value.
    iterator begin() {
        if (handle_) {
            handle_.resume();
            if (handle_.done() && handle_.promise().exception_) {
                std::rethrow_exception(handle_.promise().exception_);
            }
        }
        return iterator{handle_};
    }

    std::default_sentinel_t end() noexcept { return {}; }

    ~Generator() {
        if (handle_) handle_.destroy();
    }

    Generator(Generator&& other) noexcept : handle_(std::exchange(other.handle_, {})) {}
    Generator& operator=(Generator&& other) noexcept {
        if (this != &other) {
            if (handle_) handle_.destroy();
            handle_ = std::exchange(other.handle_, {});
        }
        return *this;
    }

    Generator(const Generator&) = delete;
    Generator& operator=(const Generator&) = delete;

private:
    explicit Generator(std::coroutine_handle<promise_type> h) : handle_(h) {}
    std::coroutine_handle<promise_type> handle_;
};
```

This implementation illustrates the key design decisions for any generator type:

- **`initial_suspend()` returns `suspend_always`**, so the coroutine does not execute any body code when it is first called. Instead, the first value is produced when `begin()` calls `handle_.resume()`. This is what makes the generator lazy.
- **`final_suspend()` returns `suspend_always`**, so the coroutine frame is not destroyed when the coroutine completes. This allows the caller to check `done()` and retrieve the exception pointer after the sequence ends. The frame is destroyed by the `Generator` destructor.
- **`yield_value()`** stores the value in the promise and returns `suspend_always`, which suspends the coroutine after each yield. The value remains accessible through the promise until the next yield overwrites it.
- **The iterator** calls `handle_.resume()` to advance to the next value. On each `operator++`, the coroutine runs from its suspension point (just after `co_yield`) through the loop body, until it hits the next `co_yield` (or completes). The iterator's `operator*` reads `current_value_` from the promise.
- **`end()` returns `std::default_sentinel`**, and the iterator's `operator==` checks `handle_.done()` — the coroutine is done when it reaches `final_suspend`.

The presence of `co_yield` automatically provides the `yield_value` hook. The compiler transforms `co_yield expr` into `promise.yield_value(expr)` followed by `co_await` on the result. Since `yield_value` returns `suspend_always`, the coroutine always suspends after each yield.

### Using a Generator with Range-Based For

The range-based for loop is the natural way to consume a generator:

```cpp
Generator<int> generate_values() {
    for (int i = 0; i < 5; ++i) {
        co_yield i * i;
    }
}

for (int value : generate_values()) {
    std::cout << value << " ";  // 0 1 4 9 16
}
```

The expansion of the for loop is approximately:

```cpp
auto&& gen = generate_values();
auto it = gen.begin();       // resumes to first yield
auto end = gen.end();
for (; it != end; ++it) {    // ++it resumes to next yield
    int value = *it;
    std::cout << value << " ";
}
```

Each iteration of the loop body corresponds to one `co_yield` execution inside the coroutine. When the loop body finishes, `++it` resumes the coroutine, which runs until the next `co_yield` (or completion). This one-to-one correspondence between loop iterations and yields is the defining characteristic of generators.

### `std::generator` in C++23

C++23 introduces `std::generator<T, Ref = T, Allocator = void>` as a standard library type. It replaces the need to write custom generator types:

```cpp
#include <generator>
#include <ranges>

std::generator<int> fibonacci(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;
        int next = a + b;
        a = b;
        b = next;
    }
}

// Usage with ranges:
auto squares = fibonacci(10)
    | std::views::transform([](int x) { return x * x; })
    | std::views::take(5);

for (int x : squares) {
    std::cout << x << " ";  // 0 1 4 9 25
}
```

`std::generator` satisfies both the `range` concept and the `view` concept, meaning it works with range adaptors. This composability is the key advantage over a hand-written generator: your generator can feed directly into a pipeline of `filter`, `transform`, `take`, and other views, without materializing intermediate sequences.

The template parameters of `std::generator<T, Ref, Allocator>`:

- **`T`** — the value type (what `co_yield` accepts).
- **`Ref`** — the reference type of the iterator's `operator*` (defaults to `T&&`). If `Ref = const T&`, iteration yields `const` references; if `Ref = T`, iteration yields prvalues (copies).
- **`Allocator`** — an allocator type for the coroutine frame, or `void` to use the default allocator.

The reference type parameter is important for performance. If your generator yields large objects by value (e.g., `std::string`), you want `Ref = const std::string&` to avoid a copy on each dereference:

```cpp
std::generator<const std::string&> read_lines(std::istream& input) {
    std::string line;
    while (std::getline(input, line)) {
        co_yield line;  // yields a reference to the local 'line'
    }
}
```

Each `co_yield` does not copy `line` — it yields a reference. The next `co_yield` will overwrite `line` with the next line of input, so the caller must consume or copy the reference before advancing the generator. This is the same aliasing caveat that applies to views of mutable state.

### Stateful Generators: Local Variables Across Yields

A generator can maintain local state across yield points, just like any coroutine. Variables declared in the generator body are stored in the coroutine frame and persist across suspensions:

```cpp
std::generator<int> cumulative_sum(std::generator<int> input) {
    int running = 0;
    for (int value : input) {
        running += value;
        co_yield running;
    }
}

// Usage:
auto input = []() -> std::generator<int> {
    for (int i = 1; i <= 5; ++i) co_yield i;
}();

for (int s : cumulative_sum(input)) {
    std::cout << s << " ";  // 1 3 6 10 15
}
```

The variable `running` is initialized when the coroutine starts (at the first `begin().resume()`) and persists across yields. Each time the coroutine resumes after a `co_yield`, `running` retains its previous value.

This is the generator equivalent of a stateful lambda (Chapter 25), but with a crucial difference: the state is expressed as ordinary local variables in a sequential function, not as captured variables in a closure. The logic is linear — read a value, update state, yield result, repeat — which is often clearer than the equivalent lambda-based accumulator.

The cost of stateful generators is that every local variable live across a `co_yield` point is stored in the coroutine frame. In the `cumulative_sum` example, `running` is live across the `co_yield`, so it resides in the frame. The `value` variable is also live across the yield (it is used in `running += value` after resumption). Frame size grows with the number and size of such variables.

### Generator Adaptors: Filter, Transform, Take

Generators compose. You can write generator functions that consume a source generator and produce a transformed view of it, using the same patterns as range adaptors:

```cpp
template <typename Gen, typename Pred>
std::generator<int> filter(Gen source, Pred pred) {
    for (int value : source) {
        if (pred(value)) {
            co_yield value;
        }
    }
}

template <typename Gen, typename Func>
std::generator<std::invoke_result_t<Func&, int>> transform(Gen source, Func f) {
    for (int value : source) {
        co_yield f(value);
    }
}

template <typename Gen>
std::generator<int> take(Gen source, int n) {
    int count = 0;
    for (int value : source) {
        if (count >= n) break;
        co_yield value;
        ++count;
    }
}
```

These composable generators mirror the behavior of `std::views::filter`, `std::views::transform`, and `std::views::take`, but they execute eagerly within each step: the entire for-range loop inside `filter` runs on each resumption, consuming one or more elements from the source until the predicate matches. The lazy pipeline is preserved across the composition — no intermediate storage is allocated.

The composition is driven by demand: calling `filter(source, pred).begin()` resumes `filter`'s coroutine, which enters the for loop, which resumes `source`'s coroutine to get a value. The resumption chain forms a lazy pull pipeline, exactly like a range adaptor pipeline.

### Recursive Generators

A generator can yield values from another generator using `co_yield` in a loop over the sub-generator. This is the idiomatic way to flatten or walk recursive structures:

```cpp
// Tree traversal as a generator.
struct TreeNode {
    int value;
    TreeNode* left;
    TreeNode* right;
};

std::generator<const int&> inorder_traversal(const TreeNode* root) {
    if (!root) co_return;
    co_yield std::ranges::elements_of(inorder_traversal(root->left));
    co_yield root->value;
    co_yield std::ranges::elements_of(inorder_traversal(root->right));
}
```

`std::ranges::elements_of` (C++23) is an utility that takes a range and yields each of its elements individually. Without it, you would write an explicit loop:

```cpp
for (int v : inorder_traversal(root->left)) {
    co_yield v;
}
```

The recursive approach requires care: each recursive invocation creates a new generator coroutine, which allocates its own coroutine frame. For deep trees (e.g., a degenerate tree of depth 100,000), recursive generators allocate 100,000 coroutine frames on the heap, which may exhaust memory. For balanced trees or shallow structures, the pattern works well.

An alternative for deep structures is an explicit stack (iterative traversal), which uses a single coroutine frame and a manually managed stack:

```cpp
std::generator<const int&> inorder_traversal_iterative(const TreeNode* root) {
    std::stack<const TreeNode*> stack;
    const auto* node = root;
    while (node || !stack.empty()) {
        while (node) {
            stack.push(node);
            node = node->left;
        }
        node = stack.top();
        stack.pop();
        co_yield node->value;
        node = node->right;
    }
}
```

This version uses a single generator with one coroutine frame, regardless of tree depth. The trade-off is that you maintain the stack explicitly, which is more code but avoids the per-recursive-call frame allocation.

### Generators vs. Range Views: When to Use Which

Generators and range views both produce lazy sequences, but they differ in important ways:

| Aspect | Range views (`std::views::filter`, etc.) | Generators |
|---|---|---|
| **Language mechanism** | Library (operator overloading, iterators) | Language (coroutine transformation) |
| **State** | Stateless per view; state in lambda captures | Local variables in coroutine frame |
| **Complex logic** | Difficult — must express as composed primitives | Natural — write sequential code with loops, branches, early returns |
| **Composition** | Pipe syntax (`\|`), fits in range pipelines | Call syntax, or use `elements_of` to nest |
| **Copyability** | Views are cheap to copy (pointer semantics) | Generators are move-only (own the coroutine frame) |
| **Performance** | No heap allocation per view; minimal overhead | Heap allocation per generator (the coroutine frame) |
| **Multi-pass** | Views can be replayed (if underlying range is unchanged) | Generators are single-pass (input range semantics) |
| **Lazy depth** | One level: adaptors wrap a single underlying range | Recursive: generators can call generators |

**Use range views when:**
- The transformation is a simple composition of standard adaptors (filter, transform, take, etc.).
- The sequence can be expressed as a pipeline of element-wise operations.
- You need views that are cheap to copy, store, or pass around.
- The underlying range is already materialized or is itself a view.

**Use generators when:**
- The sequence logic requires complex control flow — nested loops, early returns, conditional yields, error handling within the sequence.
- The sequence involves mutable state that must persist across yields (accumulators, state machines, traversal state).
- You need to produce a lazy sequence from an eager source (e.g., reading lines from a file, walking a directory tree, processing packets from a socket).
- The sequence is naturally expressed as a sequential algorithm (Fibonacci, prime sieve, tree traversal).

The two approaches are complementary, not competing. A common pattern is to write the core sequence logic as a generator (where the control flow is clean and the state is explicit) and then feed the generator into a range pipeline for further transformation:

```cpp
std::generator<int> read_temperatures(std::istream& input) {
    double value;
    while (input >> value) {
        co_yield value;
    }
}

auto hot_days = read_temperatures(sensor_stream)
    | std::views::filter([](int t) { return t > 30; })
    | std::views::take(5);

for (int t : hot_days) {
    activate_cooling(t);
}
```

The generator handles the I/O and parsing (complex sequential logic); the range adaptors handle the filtering and limiting (simple element-wise transformation). Each part does what it does best.

### Generator Performance: The Coroutine Frame Cost

Every generator invocation allocates a coroutine frame on the heap (unless the compiler elides the allocation or the promise type uses a custom allocator). For a generator that yields `n` values, the cost structure is:

- **One allocation**: the coroutine frame, allocated once when the generator function is called.
- **One deallocation**: when the `Generator` object is destroyed (if the coroutine has not already completed).
- **Per-yield cost**: one `handle.resume()` call from the iterator's `operator++`, plus the coroutine's internal dispatch to the resume point.

The per-yield cost is typically 10–30 nanoseconds — comparable to a virtual function call. The dominating cost is the frame allocation, which is on the order of 50–150 nanoseconds depending on the allocator.

For a generator that yields a large number of values (millions), the per-yield cost may matter. In such cases, consider:

- **Batched yields**: instead of yielding one element at a time, fill a small buffer and yield the buffer, then iterate over the buffer on the consumer side.
- **Custom allocator**: use a pool allocator for the coroutine frame to avoid general-purpose heap allocation overhead.
- **Range views instead**: if the generator's logic can be expressed as a simple view adaptor, the view avoids the frame allocation entirely.

For most use cases — generators that yield hundreds or thousands of values, or generators that perform non-trivial work per yield (I/O, computation, parsing) — the coroutine frame cost is negligible compared to the work done.

### Common Generator Pitfalls

**Pitfall 1: Using a generator after it has been moved from.** Generators are move-only. After moving, the source generator's handle is null, and using it is undefined behavior. Always check for null or ensure the generator is in a valid state before iteration.

**Pitfall 2: Multiple concurrent iterations.** A generator is a single-pass input sequence. Iterating it from multiple threads concurrently is a data race — the coroutine frame is not synchronized. Each generator must be consumed on a single thread, or the consumer must use external synchronization.

**Pitfall 3: Yielding references to local variables that are destroyed on advancement.**

```cpp
std::generator<const std::string&> bad_gen() {
    std::string s = "hello";
    co_yield s;  // yields reference to local s
    // On next resumption, s is modified or destroyed.
    s = "world";
    co_yield s;  // previous reference now points to "world"
}

auto gen = bad_gen();
auto it = gen.begin();
const std::string& ref = *it;  // ref points into the coroutine frame
++it;                          // ref now points to "world", not "hello"
```

The reference yielded by the generator aliases the coroutine frame's local storage. Advancing the generator may invalidate previously yielded references. This is the same aliasing issue that affects `std::generator<const T&>` and iterator invalidation in containers. If you need yielded values to outlive the next advancement, yield by value (or copy the reference immediately).

**Pitfall 4: Exceptions in generators.** If a generator's body throws an exception, the coroutine calls `promise.unhandled_exception()`. The exception is stored and rethrown when the caller advances the iterator (`operator++` or `begin()`). This is generally the right behavior — exceptions propagate to the consumer at the point where the next value is requested. But it means that exception handling in generators follows a "lazy propagation" model: the exception is delayed until the consumer interacts with the generator.

```cpp
std::generator<int> faulty() {
    co_yield 1;
    throw std::runtime_error("oops");  // stored, not thrown immediately
    co_yield 2;  // never reached
}

auto gen = faulty();
auto it = gen.begin();  // OK: yields 1
++it;                    // throws std::runtime_error: "oops"
```

The user must be prepared for `operator++` and `begin()` to throw. In range-based for loops, the exception propagates naturally:

```cpp
try {
    for (int x : faulty()) {
        std::cout << x << " ";  // prints 1, then loop exits with exception
    }
} catch (const std::runtime_error& e) {
    std::cout << "caught: " << e.what();
}
```

**Pitfall 5: Forgetting to consume the generator.** A generator that is never iterated leaks the coroutine frame (if the generator destructor does not destroy the handle). The `Generator` class shown earlier handles this in its destructor, but if you use raw `std::coroutine_handle`, forgetting to `destroy()` is a memory leak.

### Generator Patterns: Key Takeaways

- A **generator** is a coroutine that uses `co_yield` to produce a lazy sequence of values. Each `co_yield` suspends the coroutine and returns a value to the caller.
- The generator's promise type requires `yield_value()` (called by `co_yield`), `initial_suspend()` returning `suspend_always` (lazy start), and `final_suspend()` returning `suspend_always` (keep frame alive for result inspection).
- The **iterator** drives the generator: `operator++` calls `handle_.resume()`, `operator*` reads from the promise's stored value.
- C++23 provides `std::generator<T, Ref, Alloc>` as a standard library type that satisfies both `range` and `view` concepts, enabling composition with range adaptors.
- Generators excel at sequences with complex control flow or mutable state across yields. Simple element-wise transformations are better expressed as range views.
- The coroutine frame allocation is the main performance cost; custom allocators can mitigate it for performance-critical generators.
- Reference yields alias the coroutine frame's internal storage and may be invalidated on advancement. Yield by value or copy immediately if values must survive beyond the current iteration.

---

## Awaitable Types

Awaitable types are the bridge between a coroutine and the asynchronous operation it waits on. In the Coroutine Fundamentals section, we covered the awaitable protocol — `await_ready`, `await_suspend`, `await_resume` — at the level of individual suspension mechanics. This section focuses on the practical patterns for designing and implementing awaitable types: how to create awaitables that produce values, handle errors, support cancellation, interact with executors, and compose with other operations.

### Motivation: Beyond `suspend_always` and `suspend_never`

The standard library provides two trivial awaitables — `suspend_always` (suspends unconditionally) and `suspend_never` (never suspends). These are sufficient for promise type internals (`initial_suspend`, `final_suspend`, `yield_value`) but inadequate for real asynchronous work. Real awaitables must:

- **Represent an external event** — a timer expiring, data arriving on a socket, a file read completing.
- **Store and communicate a result** — the bytes read, the success/failure status, the value produced by another coroutine.
- **Handle errors** — propagate exceptions from the async operation to the awaiting coroutine.
- **Support cancellation** — allow the awaiting coroutine to abandon the operation before it completes.
- **Bind to an executor** — ensure the resumption callback runs on the correct thread or strand.

The awaitable protocol is deliberately minimal — three member functions — and the complexity lies in their implementations, not their signatures. Most of the design decisions in an awaitable type boil down to: what does `await_suspend` do with the coroutine handle, and what does `await_resume` return?

### The Awaiter vs. Awaitable Distinction

The `co_await` expression accepts an **awaitable** — any type that either defines the three protocol methods itself or can be converted to an **awaiter** via `operator co_await`. This two-tier system separates the public interface (what you pass to `co_await`) from the suspension machinery (the object that manages the handle and result).

```cpp
// Case 1: The type is its own awaiter.
struct SelfAwaiting {
    bool await_ready() noexcept;
    void await_suspend(std::coroutine_handle<>) noexcept;
    int await_resume() noexcept;
};

// Case 2: The type provides an operator co_await.
struct MyType {
    struct Awaiter {
        bool await_ready() noexcept;
        void await_suspend(std::coroutine_handle<>) noexcept;
        int await_resume() noexcept;
    };
    Awaiter operator co_await() const noexcept;
};

// Case 3: A free operator co_await is defined (C++20).
struct ExternalType { /* ... */ };
auto operator co_await(ExternalType) noexcept {
    // return an awaiter
}
```

The compiler resolves `co_await expr` by checking, in order:

1. Does `expr` have a member `operator co_await()`? If yes, call it to get the awaiter.
2. Is there a free function `operator co_await(decltype(expr))` visible? If yes, call it.
3. Otherwise, is `expr` itself a valid awaiter (has `await_ready`, `await_suspend`, `await_resume`)?

This resolution happens at compile time. The awaiter object is a temporary that lives on the coroutine frame (or the stack, if the awaiter is not needed across a suspension — the compiler can optimize it away in some cases).

The motivation for separating awaitable from awaiter is twofold:

- **The same logical operation can produce different awaiters in different contexts.** A socket read operation might produce one awaiter for reading into a buffer and another for reading into a string. The `operator co_await` layer translates the operation into the appropriate awaiter.
- **The awaiter may need mutable state** (like a flag indicating completion) that the user does not want to expose in the awaitable type itself. The awaitable is the public type; the awaiter is the internal suspension state.

### Designing a Value-Producing Awaitable

A value-producing awaitable needs to communicate a result from the asynchronous operation back to the coroutine. The result is stored in the awaiter and returned from `await_resume`.

Here is a concrete example: an awaitable that reads from a file descriptor asynchronously, using a hypothetical event loop:

```cpp
class AsyncReadOp {
    int fd_;
    char* buffer_;
    size_t size_;
    ssize_t result_ = 0;
    std::exception_ptr error_;
    std::coroutine_handle<> waiter_;

public:
    AsyncReadOp(int fd, char* buffer, size_t size)
        : fd_(fd), buffer_(buffer), size_(size) {}

    // The awaitable protocol.

    bool await_ready() noexcept {
        // Try a non-blocking read first.
        ssize_t n = ::read(fd_, buffer_, size_);
        if (n >= 0) {
            result_ = n;
            return true;  // no suspension needed
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return false;  // would block; need to suspend
        }
        error_ = std::make_exception_ptr(std::system_error(errno, std::generic_category()));
        return true;  // error occurred immediately; no suspension
    }

    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
        // Register with the event loop to call on_read_ready()
        // when fd_ becomes readable.
        event_loop::on_readable(fd_, this);
    }

    ssize_t await_resume() {
        if (error_) std::rethrow_exception(error_);
        return result_;
    }

    // Called by the event loop when the fd is readable.
    void on_read_ready() {
        ssize_t n = ::read(fd_, buffer_, size_);
        if (n >= 0) {
            result_ = n;
        } else {
            error_ = std::make_exception_ptr(
                std::system_error(errno, std::generic_category()));
        }
        // Resume the waiting coroutine.
        if (waiter_) waiter_.resume();
    }
};
```

Key design decisions in this implementation:

- **`await_ready` attempts the operation immediately.** If the non-blocking read succeeds or fails immediately, `await_ready` returns `true` and no suspension occurs. This eliminates the overhead of a coroutine suspension for the common case where data is available. Only when the operation would block (EAGAIN) does the awaitable return `false`, triggering suspension.
- **`await_suspend` registers with the event loop.** It stores the coroutine handle so that `on_read_ready()` can resume the coroutine when the file descriptor becomes readable. The awaiter object itself (`this`) is passed as context so the event loop knows which awaiter to notify.
- **`await_resume` checks for errors and returns the result.** If the read encountered an error (either synchronously in `await_ready` or asynchronously in `on_read_ready`), it rethrows the stored exception.

The awaiter object must remain alive until the operation completes or is cancelled. Since the awaiter is typically a local temporary inside the coroutine frame (created by the `co_await` expression and stored there because its lifetime crosses the suspension point), its lifetime is tied to the coroutine frame — exactly what we need.

### The Awaiter Lifetime Problem

The preceding example has a subtle issue: the awaiter (`AsyncReadOp`) is stored in the coroutine frame as a temporary, but the event loop holds a raw pointer to it (`this`). If the coroutine is destroyed while the event loop still holds that pointer (e.g., the coroutine is cancelled before the fd becomes readable), the event loop will later call `on_read_ready` on a destroyed object.

Three approaches to solve this:

**Approach 1: Unregistration in destructor.** The awaitable unregisters itself from the event loop when destroyed:

```cpp
class AsyncReadOp {
    // ...
    ~AsyncReadOp() {
        if (fd_ >= 0) {
            event_loop::cancel_readable(fd_, this);
        }
    }
};
```

This works but requires the event loop to support cancellation. If the event loop has already dispatched the callback (but it hasn't run yet), the cancellation may race with the callback invocation.

**Approach 2: Shared ownership.** Use `std::shared_ptr` for the awaiter so that both the coroutine frame and the event loop hold a reference:

```cpp
class AsyncReadOp : public std::enable_shared_from_this<AsyncReadOp> {
    // ...
    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
        event_loop::on_readable(fd_, shared_from_this());
    }

    void on_read_ready() {
        // shared_ptr keeps the object alive.
        ssize_t n = ::read(fd_, buffer_, size_);
        if (n >= 0) result_ = n;
        else error_ = std::make_exception_ptr(...);
        if (waiter_) waiter_.resume();
    }
};
```

The event loop holds a `shared_ptr<AsyncReadOp>`, keeping the awaiter alive even if the coroutine frame is destroyed. The coroutine handle stored in `waiter_` is reset when the coroutine is destroyed (though detecting that automatically requires a companion mechanism).

**Approach 3: Intrusive reference counting.** For high-performance systems where `shared_ptr` atomic reference counting is too expensive, embed a reference count directly in the awaiter and have the event loop manipulate it.

In practice, approach 1 (unregistration) is the most common for single-threaded event loops where cancellation can be synchronous. Approach 2 (shared_ptr) is safer for multi-threaded systems where the event loop and coroutine may live on different threads.

### Error Propagation in Awaitables

Errors in awaitables follow one of two patterns: **exception-based** or **error-code-based**.

**Exception-based** awaitables store a `std::exception_ptr` in `await_suspend` and rethrow it in `await_resume`:

```cpp
void await_suspend(std::coroutine_handle<> handle) noexcept {
    try {
        // Start the async operation, which may throw.
        start_operation(handle);
    } catch (...) {
        error_ = std::current_exception();
        // Resume immediately so the coroutine sees the error.
        handle.resume();
    }
}

// In await_resume:
auto await_resume() {
    if (error_) std::rethrow_exception(error_);
    return result_;
}
```

This pattern integrates naturally with C++ exception handling: the coroutine body can use try/catch around `co_await`:

```cpp
try {
    auto result = co_await async_operation();
} catch (const std::system_error& e) {
    // handle the error
}
```

**Error-code-based** awaitables return an error code or a `Result` type from `await_resume`:

```cpp
std::expected<size_t, std::error_code> await_resume() noexcept {
    if (error_) return std::unexpected(error_);
    return result_;
}
```

The coroutine then checks the return value:

```cpp
auto read_result = co_await async_read(fd, buffer, size);
if (!read_result) {
    // handle error_code = read_result.error()
}
```

The choice mirrors the broader error-handling trade-off in C++: exceptions for "can't happen" errors that should propagate up the call stack; error codes for expected failures that the caller must handle. Awaitables can support both by providing two access paths — a throwing `await_resume()` and a non-throwing method that returns an error code.

### Timeouts and Timer Awaitables

A timer awaitable suspends the coroutine until a specified duration has elapsed. This is one of the simplest non-trivial awaitables to implement:

```cpp
class SleepAwaiter {
    std::chrono::steady_clock::time_point deadline_;
    std::coroutine_handle<> waiter_;

public:
    explicit SleepAwaiter(std::chrono::steady_clock::duration dur)
        : deadline_(std::chrono::steady_clock::now() + dur) {}

    bool await_ready() const noexcept {
        return std::chrono::steady_clock::now() >= deadline_;
    }

    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
        event_loop::add_timer(deadline_, this);
    }

    void await_resume() noexcept {}

    // Called by the event loop when the timer expires.
    void on_timer_expired() {
        if (waiter_) waiter_.resume();
    }
};

// The awaitable wrapper:
struct Sleep {
    std::chrono::steady_clock::duration dur;
    SleepAwaiter operator co_await() const noexcept {
        return SleepAwaiter{dur};
    }
};

// Usage:
co_await Sleep{std::chrono::seconds(5)};  // suspend for 5 seconds
```

The timer awaiter follows the same pattern as the I/O awaiter: `await_ready` checks if the time has already passed; `await_suspend` registers with the event loop; a callback (`on_timer_expired`) resumes the coroutine.

A more useful variant supports **timeouts on other operations** — co_await an operation with a maximum wait time:

```cpp
template <typename Awaitable>
class TimeoutAwaiter {
    Awaitable awaitable_;
    std::chrono::steady_clock::duration timeout_;
    std::coroutine_handle<> waiter_;
    bool timed_out_ = false;

public:
    TimeoutAwaiter(Awaitable awaitable, std::chrono::steady_clock::duration timeout)
        : awaitable_(std::move(awaitable)), timeout_(timeout) {}

    bool await_ready() {
        return awaitable_.await_ready();
    }

    void await_suspend(std::coroutine_handle<> handle) {
        waiter_ = handle;
        // Start the original operation.
        awaitable_.await_suspend(handle);
        // Register a timer that will cancel on timeout.
        event_loop::add_timer(
            std::chrono::steady_clock::now() + timeout_,
            [this] { on_timeout(); });
    }

    auto await_resume() {
        if (timed_out_) throw std::system_error(std::make_error_code(std::errc::timed_out));
        return awaitable_.await_resume();
    }

    void on_timeout() {
        timed_out_ = true;
        // Cancel the original operation (if supported).
        // Then resume the coroutine with the timeout error.
        if (waiter_) waiter_.resume();
    }
};
```

The timeout awaiter composes with any other awaitable: it starts the original operation and a timer simultaneously, and whichever completes first triggers the resumption. This pattern — wrapping an awaitable with additional behavior — is the foundation for awaitable composition.

### The `operator co_await` Customization Point

The `operator co_await` is how you make third-party types awaitable or how you provide tailored awaiter behavior for your own types.

**Making a third-party type awaitable:**

```cpp
// Imagine a library provides a Future<T> type.
template <typename T>
class Future {
    // ... library code ...
    bool is_ready() const;
    T get();
    void on_complete(std::function<void()>);
};

// We can make it awaitable without modifying the library:
template <typename T>
struct FutureAwaiter {
    Future<T>& future_;
    std::coroutine_handle<> waiter_;

    bool await_ready() const { return future_.is_ready(); }

    void await_suspend(std::coroutine_handle<> handle) {
        waiter_ = handle;
        future_.on_complete([this] { waiter_.resume(); });
    }

    T await_resume() { return future_.get(); }
};

template <typename T>
FutureAwaiter<T> operator co_await(Future<T>& future) {
    return FutureAwaiter<T>{future};
}
```

Now any `Future<T>` can be used with `co_await`:

```cpp
Future<Data> fetch_data_async();
Data d = co_await fetch_data_async();
```

This is one of the most powerful aspects of the coroutine design: you can retrofit awaitability onto existing asynchronous types without changing them, by defining a free `operator co_await`.

**Providing multiple awaiters for the same type:**

A single type may have different suspension semantics depending on context. For example, a `shared_future<T>` might be awaitable either with `co_await` (resume when ready) or with `co_await` on a specific executor:

```cpp
struct SharedFutureAwaiter {
    std::shared_future<T>& future_;
    std::coroutine_handle<> waiter_;

    bool await_ready() { /* ... */ }
    void await_suspend(std::coroutine_handle<> h) { /* ... */ }
    T await_resume() { return future_.get(); }
};

template <typename T>
SharedFutureAwaiter<T> operator co_await(std::shared_future<T>& fut) {
    return SharedFutureAwaiter<T>{fut};
}

// An alternative awaiter that resumes on a specific executor:
template <typename T>
struct ExecutorFutureAwaiter {
    // ... similar, but schedules resumption via executor
};

struct ExecutorToken { /* ... */ };

// Overload for use with co_await on an executor:
auto co_await(ExecutorToken ex, std::shared_future<T>& fut) {
    return ExecutorFutureAwaiter<T>{ex, fut};
}
```

This kind of overloading requires C++23's `co_await` expressions to support additional arguments (which they do not — `co_await` takes exactly one operand). The idiomatic approach for executor-bound awaiting is to wrap the awaitable in an executor-aware adapter, covered in the next section.

### Executor-Bound Awaitables

When a coroutine resumes after `co_await`, it runs on whatever thread called `handle.resume()`. By default, the entity that completes the asynchronous operation controls which thread resumes the coroutine. For many applications, this is undesirable: the coroutine may need to resume on a specific thread (the main thread, a UI thread, a strand) to avoid data races or meet API requirements.

An **executor-bound awaitable** ensures that the coroutine resumes via a specified executor, even if the underlying operation completes on a different thread:

```cpp
template <typename Executor, typename Awaitable>
class ExecutorBoundAwaiter {
    Executor ex_;
    Awaitable awaitable_;
    std::coroutine_handle<> waiter_;

public:
    ExecutorBoundAwaiter(Executor ex, Awaitable awaitable)
        : ex_(std::move(ex)), awaitable_(std::move(awaitable)) {}

    bool await_ready() { return awaitable_.await_ready(); }

    void await_suspend(std::coroutine_handle<> handle) {
        waiter_ = handle;
        // Wrap the original awaitable's suspend, but intercept
        // the resumption to route through the executor.
        awaitable_.await_suspend(
            std::coroutine_handle<>::from_address(
                // Store executor reference for the callback.
                // In practice, this requires a heap-allocated wrapper.
                nullptr));
    }

    auto await_resume() { return awaitable_.await_resume(); }
};
```

A complete implementation is complex because the resumption callback must capture the executor reference and post the resumption through it. Practical libraries like `boost::asio` and `folly::coro` provide `co_await` on executors directly:

```cpp
// boost::asio style:
co_await boost::asio::post(ex, boost::asio::use_awaitable);

// folly::coro style:
co_await folly::coro::co_reschedule_on_current_executor;
```

The pattern is so common that most coroutine libraries include a `co_await some_executor` that suspends the coroutine and immediately schedules its resumption on that executor — effectively a "switch-to-executor" operation:

```cpp
Task process(boost::asio::io_context& io) {
    // We're on some thread. Switch to io's strand.
    co_await boost::asio::post(io, boost::asio::use_awaitable);
    // Now we're on io's thread. Safe to access io-bound state.
    co_await async_read(socket_, buffer_, boost::asio::use_awaitable);
}
```

The first `co_await` suspends and re-schedules the coroutine on the target executor. This is the idiomatic way to establish thread affinity in coroutine code.

### Cancellation in Awaitables

Cancellation allows an awaiting coroutine to abandon an operation before it completes. The standard approach uses a **cancellation token** — an object shared between the operation initiator and the operation executor that signals whether cancellation has been requested:

```cpp
class CancellationToken {
    std::shared_ptr<std::atomic<bool>> cancelled_;
public:
    CancellationToken() : cancelled_(std::make_shared<std::atomic<bool>>(false)) {}

    void cancel() noexcept { cancelled_->store(true, std::memory_order_relaxed); }
    bool is_cancelled() const noexcept { return cancelled_->load(std::memory_order_relaxed); }

    // Create a child token that shares the same state.
    CancellationToken child() const { return CancellationToken{cancelled_}; }
};

class CancellableAwaiter {
    CancellationToken token_;
    std::coroutine_handle<> waiter_;
    bool cancelled_by_us_ = false;

public:
    explicit CancellableAwaiter(CancellationToken token) : token_(std::move(token)) {}

    bool await_ready() noexcept {
        if (token_.is_cancelled()) {
            cancelled_by_us_ = true;
            return true;  // already cancelled
        }
        return false;
    }

    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
        register_operation(/* ... */);
        // Register a cancellation callback.
        token_.register_callback([this] {
            cancelled_by_us_ = true;
            cancel_operation();
            if (waiter_) waiter_.resume();
        });
    }

    void await_resume() {
        if (cancelled_by_us_) {
            throw std::system_error(std::make_error_code(std::errc::operation_canceled));
        }
        // return the result or rethrow errors
    }
};
```

The cancellation callback is invoked when `token_.cancel()` is called. It cancels the underlying operation and resumes the coroutine, which then sees the cancellation through `await_resume`'s exception path.

Key design decisions for cancellation:

- **Cancellation is cooperative.** The awaiter checks the token in `await_ready` and registers a callback in `await_suspend`. There is no forced termination — the operation must check the cancellation state at safe points.
- **Resumption on cancellation may race with normal completion.** The cancellation callback and the normal completion callback may be invoked concurrently. The awaiter must use atomic flags or a mutex to ensure that `await_resume` is called exactly once.
- **Cancellation should be a choice.** Not every awaitable supports cancellation. The token is passed explicitly, and the awaiter decides how to handle it. An awaitable that does not support cancellation simply ignores the token.

### Awaitable Composition: `when_all` and `when_any`

Awaitable composition allows a coroutine to await multiple operations concurrently. The two fundamental combinators are:

- **`when_all`** — awaits multiple awaitables, resuming when all have completed. Returns a tuple of results.
- **`when_any`** — awaits multiple awaitables, resuming as soon as any one completes. Returns the index of the completed operation and its result.

These combinators are not part of the C++20 standard library but are provided by coroutine libraries (folly::coro, cppcoro, boost::asio). Understanding their implementation reveals how awaitable composition works at the level of coroutine handles.

A simplified `when_all` implementation creates a shared state that counts completions:

```cpp
template <typename... Awaitables>
class WhenAllAwaiter {
    std::tuple<Awaitables...> awaitables_;
    std::coroutine_handle<> waiter_;
    std::atomic<int> remaining_{sizeof...(Awaitables)};
    std::exception_ptr error_;

public:
    explicit WhenAllAwaiter(Awaitables... awaitables)
        : awaitables_(std::move(awaitables)...) {}

    bool await_ready() noexcept { return false; }

    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
        // Start each awaitable concurrently.
        start_all(std::index_sequence_for<Awaitables...>{});
    }

    auto await_resume() {
        if (error_) std::rethrow_exception(error_);
        return std::apply([](auto&... aw) {
            return std::make_tuple(aw.await_resume()...);
        }, awaitables_);
    }

private:
    template <size_t... Is>
    void start_all(std::index_sequence<Is...>) {
        // For each awaitable, spawn a coroutine that awaits it
        // and decrements the counter on completion.
        ((start_one<Is>(std::get<Is>(awaitables_))), ...);
    }

    template <size_t I, typename A>
    void start_one(A& awaitable) {
        if (awaitable.await_ready()) {
            // Complete immediately — capture result.
            on_complete<I>(awaitable);
        } else {
            // For simplicity, this requires each awaitable's
            // await_suspend to be adapted. In production code,
            // each sub-operation is wrapped in a small coroutine
            // that decrements the counter on completion.
            awaitable.await_suspend(/* adapted handle */);
        }
    }

    template <size_t I, typename A>
    void on_complete(A& awaitable) {
        try {
            // Store the result (in practice, store in a tuple)
        } catch (...) {
            if (!error_) error_ = std::current_exception();
        }
        if (--remaining_ == 0 && waiter_) {
            waiter_.resume();
        }
    }
};
```

A production `when_all` is more complex because it must:

- Handle the case where the `when_all` coroutine itself is destroyed before all sub-operations complete (requiring cancellation of incomplete operations).
- Store results in a type-safe tuple.
- Support heterogeneous awaitable types with different result types.
- Propagate the first error (or all errors) without leaking operations.

Despite the implementation complexity, the interface is clean:

```cpp
auto [result1, result2] = co_await when_all(
    async_fetch(url1),
    async_fetch(url2)
);
// Both fetches run concurrently. This line is reached only when both complete.
```

The `when_any` combinator follows the same pattern but uses a completion flag that is set when the first operation completes, at which point it immediately resumes the awaiting coroutine:

```cpp
template <typename T>
struct WhenAnyResult {
    size_t index;
    T value;
};

template <typename... Awaitables>
class WhenAnyAwaiter {
    std::atomic<bool> done_{false};
    std::coroutine_handle<> waiter_;

public:
    // ... await_ready returns false ...

    void await_suspend(std::coroutine_handle<> handle) {
        waiter_ = handle;
        // Start all operations. Each one, on completion,
        // atomically checks done_ and, if it is the first,
        // stores its result and resumes the waiter.
    }

    WhenAnyResult</* common type */> await_resume() {
        // Return the result from the first completed operation.
    }
};
```

`when_any` is useful for race conditions — for example, waiting for either a network response or a timeout:

```cpp
auto result = co_await when_any(
    async_fetch(url),
    Sleep{std::chrono::seconds(5)}
);

if (result.index == 1) {
    // Timeout occurred; handle it.
}
```

### Move-Only Awaitables

An awaitable may hold a move-only resource (like a `std::unique_ptr`) that must be transferred to the coroutine upon resumption. The awaiter must be movable but not copyable, and `await_resume` must return by move:

```cpp
class MoveOnlyAwaiter {
    std::unique_ptr<Resource> resource_;
    std::coroutine_handle<> waiter_;

public:
    MoveOnlyAwaiter(std::unique_ptr<Resource> r) : resource_(std::move(r)) {}

    MoveOnlyAwaiter(const MoveOnlyAwaiter&) = delete;
    MoveOnlyAwaiter& operator=(const MoveOnlyAwaiter&) = delete;
    MoveOnlyAwaiter(MoveOnlyAwaiter&&) = default;
    MoveOnlyAwaiter& operator=(MoveOnlyAwaiter&&) = default;

    bool await_ready() noexcept { return resource_ != nullptr; }

    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
        // Transfer ownership temporarily to the async operation.
        auto* ptr = resource_.release();
        start_operation(ptr, [this] {
            resource_.reset(ptr);
            waiter_.resume();
        });
    }

    std::unique_ptr<Resource> await_resume() {
        return std::move(resource_);
    }
};
```

The awaiter's move constructor is used when the awaitable is passed into the coroutine frame (the awaiter is typically constructed as a temporary and moved into the coroutine frame storage). The move-only semantics ensure that the resource ownership chain is clear: from the caller, into the awaiter, possibly to the async operation temporarily, and back to the coroutine via `await_resume`.

### Thread Safety in Awaitables

Awaitables that interact with multi-threaded event loops must handle several concurrency concerns:

**Resumption races.** The normal completion callback and the cancellation callback may attempt to resume the coroutine concurrently. The solution is an atomic flag that ensures `resume()` is called exactly once:

```cpp
class ThreadSafeAwaiter {
    std::atomic<bool> completed_{false};
    std::coroutine_handle<> waiter_;

public:
    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
    }

    // Called by the event loop on completion (may be on any thread).
    void on_completion() {
        bool expected = false;
        if (completed_.compare_exchange_strong(expected, true)) {
            waiter_.resume();
        }
    }

    // Called by cancellation (may be on a different thread).
    void on_cancel() {
        bool expected = false;
        if (completed_.compare_exchange_strong(expected, true)) {
            waiter_.resume();
        }
    }
};
```

The `compare_exchange_strong` ensures that only one thread can execute `waiter_.resume()`. The losing thread simply returns, knowing that the coroutine has already been (or will be) resumed.

**Executor awareness.** The awaiter should not assume that `resume()` can be called from any thread. If the coroutine must resume on a specific executor, the awaiter should post the resumption rather than calling `waiter_.resume()` directly:

```cpp
void on_completion() {
    bool expected = false;
    if (completed_.compare_exchange_strong(expected, true)) {
        // Resume on the target executor, not this thread.
        executor_.post([handle = waiter_] {
            handle.resume();
        });
    }
}
```

**Awaiter visibility.** If the awaiter is allocated in the coroutine frame (as a temporary across a suspension point), and the event loop accesses it from another thread, the awaiter must be properly synchronized. The `await_suspend` call happens on the coroutine's thread; the event loop's callback may happen on another thread. The awaiter's members must be atomic or protected by a mutex.

### Awaitable Types: Key Takeaways

- An **awaitable** is any type that can be used with `co_await`. It either implements the protocol itself or provides an `operator co_await` that returns an **awaiter** — the object that manages suspension and resumption.
- The `operator co_await` customization point allows retrofitting awaitability onto existing types without modification.
- **Value-producing awaitables** store the result during `await_suspend` and return it from `await_resume`. **Error propagation** can use exceptions (rethrow stored `exception_ptr`) or error codes (return `expected<T, E>`).
- **Awaiter lifetime** must be managed: the event loop may hold a pointer to the awaiter after the coroutine frame is destroyed. Unregistration in the destructor, shared ownership, or intrusive reference counting address this.
- **Timer awaitables** are a simple but powerful pattern: check expiration in `await_ready`, register a timer callback in `await_suspend`, and resume the coroutine when the timer fires.
- **Executor-bound awaitables** ensure the coroutine resumes on a specific thread or strand. This is critical for thread safety in multi-threaded event loops.
- **Cancellation** is cooperative, using a shared cancellation token. The awaiter checks for cancellation in `await_ready` and registers a cancellation callback in `await_suspend`. Resumption races between cancellation and normal completion must be mediated by atomic flags.
- **Awaitable composition** (`when_all`, `when_any`) enables concurrent operations. Implementing these combinators requires managing a shared completion count (for `when_all`) or a first-past-the-post flag (for `when_any`), with careful error propagation.

The next section builds on these patterns to construct **task types** — awaitables that represent the result of an entire coroutine, enabling coroutines to call other coroutines with `co_await` and compose complex async workflows.

---

## Task-based Async Patterns

A **task** is a coroutine return type that represents an asynchronous computation. Unlike a generator (which yields a sequence of values), a task produces a single value (or void) and supports `co_await` so that one coroutine can await the result of another. Tasks are the building blocks of structured asynchronous workflows: a function becomes a coroutine, returns a `Task<T>`, and callers use `co_await task` to obtain the result.

The task pattern is where the promise type protocol and the awaitable protocol meet. The promise type manages the coroutine lifecycle (start, suspend, complete), while the awaitable type lets an external coroutine suspend until the task completes. Together, they enable the key abstraction of structured concurrency: one coroutine launches another, awaits its result, and the calling coroutine's lifetime is naturally nested within the caller's.

### Motivation: The Need for Task Types

Consider a function that needs to perform two sequential async operations:

```cpp
// Without a task type: manual callback wiring.
void process_order(Order order, Callback<Receipt> cb) {
    validate_async(order, [cb = std::move(cb)](ErrorOr<Order> validated) {
        if (!validated) {
            cb(Error(validated.error()));
            return;
        }
        charge_async(validated.value(), [cb = std::move(cb)](ErrorOr<Receipt> receipt) {
            cb(std::move(receipt));
        });
    });
}
```

Each nested callback adds a level of indentation and separates the sequential steps. The code would be much clearer as:

```cpp
// With task types: sequential composition.
Task<Receipt> process_order(Order order) {
    Order validated = co_await validate_async(order);
    Receipt receipt = co_await charge_async(validated);
    co_return receipt;
}
```

The difference is the same as the coroutine-vs-callback motivation from the fundamentals section, but now the awaitables are themselves coroutines — `validate_async` returns a `Task<Order>`, and `charge_async` returns a `Task<Receipt>`. The `co_await` suspends `process_order` until the sub-task completes, then resumes with the result.

For this to work, `Task<T>` must be:

1. A **coroutine return type** — it must have a nested `promise_type` that satisfies the coroutine protocol.
2. An **awaitable type** — you must be able to write `co_await some_task` and get back a `T`.

The first requirement lets you write `Task<T> my_func() { co_return value; }`. The second lets you write `T result = co_await my_func();`. Together, they enable the fundamental composition pattern of async coroutines.

### A Minimal Task Type

Here is a minimal `Task<T>` that satisfies both requirements:

```cpp
template <typename T>
class Task {
public:
    struct promise_type {
        T result_;
        std::exception_ptr exception_;
        std::coroutine_handle<> continuation_;

        Task get_return_object() {
            return Task{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }

        // Lazy by default: don't start until awaited.
        std::suspend_always initial_suspend() noexcept { return {}; }

        // Keep the frame alive after completion.
        std::suspend_always final_suspend() noexcept {
            // If there's a continuation, resume it.
            if (continuation_) {
                continuation_.resume();
            }
            return {};
        }

        void return_value(T value) {
            result_ = std::move(value);
        }

        void unhandled_exception() noexcept {
            exception_ = std::current_exception();
        }
    };

    // Awaitable interface — makes Task<T> awaitable from another coroutine.

    bool await_ready() const noexcept {
        return handle_.done();
    }

    void await_suspend(std::coroutine_handle<> awaiting_handle) noexcept {
        // Store the awaiting coroutine's handle in the promise.
        // When this task completes, final_suspend will resume it.
        handle_.promise().continuation_ = awaiting_handle;
    }

    T await_resume() {
        if (handle_.promise().exception_) {
            std::rethrow_exception(handle_.promise().exception_);
        }
        return std::move(handle_.promise().result_);
    }

    // Lifetime management.

    ~Task() {
        if (handle_) handle_.destroy();
    }

    Task(Task&& other) noexcept : handle_(std::exchange(other.handle_, {})) {}
    Task& operator=(Task&& other) noexcept {
        if (this != &other) {
            if (handle_) handle_.destroy();
            handle_ = std::exchange(other.handle_, {});
        }
        return *this;
    }

    Task(const Task&) = delete;
    Task& operator=(const Task&) = delete;

private:
    explicit Task(std::coroutine_handle<promise_type> h) : handle_(h) {}
    std::coroutine_handle<promise_type> handle_;
};
```

This minimal `Task<T>` demonstrates the core duality:

- As a **coroutine return type**, its promise type defines `initial_suspend` (lazy — `suspend_always`), `final_suspend` (resumes the continuation), `return_value`, `unhandled_exception`, and `get_return_object`.
- As an **awaitable type**, it defines `await_ready` (check if the coroutine is done), `await_suspend` (store the awaiter's handle in the promise's `continuation_` field), and `await_resume` (return the result or rethrow the exception).

The critical wiring is in `final_suspend`: when the task coroutine completes (via `co_return` or an exception), `final_suspend` checks if a continuation was stored (meaning another coroutine is awaiting this task) and resumes it. This is the mechanism that chains coroutines together — when `coroutine A` does `co_await task_of_B`, it stores its handle in B's promise, and when B completes, B's `final_suspend` resumes A.

### Lazy vs. Eager Tasks

The `initial_suspend()` choice determines when the task begins executing:

**Lazy tasks** (`initial_suspend` returns `suspend_always`):

```cpp
Task<int> compute() {
    co_return 42;
}

// The coroutine body has NOT started yet.
Task<int> t = compute();

// Now the body starts.
int result = co_await t;
```

The coroutine body only runs when someone `co_await`s the task (or explicitly calls `handle_.resume()`). This is useful for deferring computation, but it means the first suspension point is immediate — the task is always suspended at creation.

**Eager tasks** (`initial_suspend` returns `suspend_never`):

```cpp
// Modified promise:
std::suspend_never initial_suspend() noexcept { return {}; }

// Usage:
Task<int> compute() {
    co_return 42;
}

// The coroutine body starts running immediately!
Task<int> t = compute();
// t may already be complete by the time we reach this line.

int result = co_await t;  // May not suspend at all (ready).
```

Eager tasks start immediately upon creation and complete in the background. The `co_await` on an eager task may find it already complete (if the work was fast or was running on the current thread) or may suspend until completion.

**The trade-off**:

- **Lazy** gives the caller control over when work starts. This is valuable for work-stealing schedulers and when the task result may not be needed at all. It also avoids the "fire and forget" problem where an eager coroutine starts but is never awaited (its frame leaks).
- **Eager** maximizes parallelism: the task begins work immediately, possibly on another thread, while the caller can do other work before `co_await`. This matches the mental model of `std::async`.

Most production coroutine libraries (folly::coro, cppcoro, boost::asio) default to **lazy** tasks because they compose more predictably: the task's side effects happen in a known order (when awaited, not when created). Eager tasks are available as an explicit opt-in (e.g., `schedule_on(executor, task)`).

### Task with Void Result

A `Task<void>` variant is similar but uses `return_void()` instead of `return_value()`:

```cpp
template <>
class Task<void> {
public:
    struct promise_type {
        std::exception_ptr exception_;
        std::coroutine_handle<> continuation_;

        Task get_return_object() { /* ... */ }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept {
            if (continuation_) continuation_.resume();
            return {};
        }
        void return_void() noexcept {}
        void unhandled_exception() noexcept {
            exception_ = std::current_exception();
        }
    };

    bool await_ready() const noexcept { return handle_.done(); }
    void await_suspend(std::coroutine_handle<> h) noexcept {
        handle_.promise().continuation_ = h;
    }
    void await_resume() {
        if (handle_.promise().exception_) {
            std::rethrow_exception(handle_.promise().exception_);
        }
    }

    // ... destructor, move, etc. ...
};
```

`Task<void>` is used for asynchronous operations that have side effects but no return value — write to a file, send a network message, update a database.

### Exception Propagation Through the Task Chain

When a task coroutine throws an exception, the sequence is:

1. The exception escapes the coroutine body.
2. The compiler calls `promise.unhandled_exception()`, which stores `std::current_exception()`.
3. The coroutine reaches `final_suspend()`, which resumes the continuation (if any).
4. The awaiting coroutine's `await_resume()` checks for the stored exception and rethrows it.
5. The exception propagates in the awaiting coroutine's context — it can be caught with a normal try/catch.

```cpp
Task<int> may_fail(bool fail) {
    if (fail) throw std::runtime_error("oops");
    co_return 42;
}

Task<void> consumer() {
    try {
        int value = co_await may_fail(true);
    } catch (const std::runtime_error& e) {
        // Handle the error from the sub-task.
        std::cout << "Caught: " << e.what() << "\n";
    }
}
```

The exception crosses the coroutine boundary automatically. The awaiting coroutine does not need to know whether the sub-task threw synchronously or asynchronously — the `co_await` expression behaves uniformly.

### Fire-and-Forget Tasks

Sometimes you need to start an async operation and not wait for its result — logging, metrics reporting, cache warming. A **fire-and-forget** task type suppresses the result and does not support awaiting:

```cpp
struct FireForget {
    struct promise_type {
        FireForget get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() noexcept {}
        void unhandled_exception() noexcept {
            // Log the exception, but don't propagate.
            try { throw; }
            catch (const std::exception& e) {
                std::cerr << "FireForget exception: " << e.what() << "\n";
            }
        }
    };
};

// Usage:
FireForget log_async(std::string msg) {
    co_await log_to_file(msg);
    // No one awaits this; exception is logged, not propagated.
}
```

Fire-and-forget coroutines are dangerous because there is no way to know when they complete. The coroutine frame persists until `final_suspend`, and since nothing awaits them, they must ensure they eventually complete. They are best used sparingly, for operations where failure is non-critical and the caller does not need to observe completion.

### Structured Concurrency with Task Scopes

One of the most important concepts in async programming is **structured concurrency**: the principle that the lifetime of a concurrent operation should be nested within the lifetime of its caller. A task scope provides a way to spawn multiple child tasks and ensure they all complete before the scope exits:

```cpp
// Conceptual structured concurrency pattern.
Task<void> process_many(DataStream stream) {
    TaskScope scope;

    // Spawn child tasks within the scope.
    scope.spawn(process_first_half(stream));
    scope.spawn(process_second_half(stream));

    // The scope destructor waits for all children to complete.
    // When this function returns, all children are guaranteed done.
}
```

Without structured concurrency, spawned tasks that outlive their parent lead to dangling references, use-after-free, and unpredictable lifetime errors. The `TaskScope` pattern ensures that:

- All child tasks complete before the parent task completes.
- If a child task throws an exception, it propagates to the scope (and can be rethrown by the parent).
- If the parent task is cancelled, all child tasks are also cancelled.

A minimal `TaskScope` implementation:

```cpp
class TaskScope {
    std::atomic<int> remaining_{0};
    std::coroutine_handle<> waiter_;
    std::exception_ptr error_;

public:
    // Spawn a fire-and-forget child, but track its completion.
    template <typename T>
    void spawn(Task<T> task) {
        remaining_.fetch_add(1, std::memory_order_relaxed);
        // Launch the task. On completion, decrement counter.
        auto child = [this, task = std::move(task)]() -> FireForget {
            try {
                co_await task;
            } catch (...) {
                if (!error_) error_ = std::current_exception();
            }
            if (remaining_.fetch_sub(1, std::memory_order_acq_rel) == 1) {
                // This was the last task; resume the waiter.
                if (waiter_) waiter_.resume();
            }
        };
        child();
    }

    // Awaiter that suspends until all spawned tasks complete.
    bool await_ready() noexcept {
        return remaining_.load(std::memory_order_acquire) == 0;
    }

    void await_suspend(std::coroutine_handle<> handle) noexcept {
        waiter_ = handle;
    }

    void await_resume() {
        if (error_) std::rethrow_exception(error_);
    }
};
```

In usage:

```cpp
Task<void> process_all(std::vector<Job> jobs) {
    TaskScope scope;
    for (auto& job : jobs) {
        scope.spawn(process_one(job));
    }
    // Wait for all children.
    co_await scope;
}
```

Structured concurrency eliminates a class of subtle bugs in async code: leaked tasks, dangling references, and exceptions that disappear into the void.

### Chaining Tasks with Continuations

Beyond `co_await`, tasks can be chained using continuation methods — `.then()`, `.and_then()`, `.map()` — borrowed from the futures and monadic patterns:

```cpp
template <typename T>
class Task {
    // ...

    template <typename F>
    auto then(F&& f) -> Task<decltype(f(std::declval<T>()))> {
        // Return a new task that awaits this one, applies f, and returns.
        return [](Task self, F func) -> Task<decltype(func(std::declval<T>()))> {
            T value = co_await std::move(self);
            co_return func(std::move(value));
        }(std::move(*this), std::forward<F>(f));
    }

    template <typename F>
    auto and_then(F&& f) -> decltype(f(std::declval<T>())) {
        // Like then, but f returns a Task itself.
        return [](Task self, F func) -> decltype(func(std::declval<T>())) {
            T value = co_await std::move(self);
            co_return co_await func(std::move(value));
        }(std::move(*this), std::forward<F>(f));
    }
};
```

These continuation methods enable a style of composition that does not require writing a new coroutine function:

```cpp
// Instead of writing a coroutine:
Task<Result> process(Data d) {
    auto validated = co_await validate(d);
    co_return co_await compute(validated);
}

// Use continuation chaining:
Task<Result> process(Data d) {
    co_return co_await validate(d).and_then(compute);
}
```

The `.and_then(compute)` call produces a `Task<Result>` that, when awaited, runs `validate`, passes its result to `compute`, and returns `compute`'s result. The composition is lazy: neither `validate` nor `compute` starts until the composed task is awaited.

### Cancellation in Task Systems

Cancellation in a task system propagates from parent to child. When a task is cancelled, all tasks it spawned should also be cancelled. The standard approach uses a cancellation token that is implicitly passed through the task chain:

```cpp
struct CancellableTaskPromiseBase {
    std::shared_ptr<CancellationToken> token_;

    // Inherited by all child tasks created within this coroutine.
    std::shared_ptr<CancellationToken> get_cancellation_token() const {
        return token_;
    }
};

template <typename T>
struct CancellableTaskPromise : CancellableTaskPromiseBase {
    // ... standard promise members ...

    CancellableTask<T> get_return_object() {
        return CancellableTask<T>{
            std::coroutine_handle<CancellableTaskPromise>::from_promise(*this),
            token_
        };
    }
};
```

Cancellation is cooperative: each task periodically checks the token and stops its work when cancellation is requested:

```cpp
CancellableTask<void> stream_data(Socket socket) {
    while (!co_await this_coro::cancellation_requested()) {
        auto data = co_await socket.read();
        if (data.empty()) break;
        co_await process(data);
    }
}
```

The cancellation token is shared across the task tree, so cancelling the root task automatically cancels all descendants. This is the async equivalent of stack unwinding — a clean shutdown path for concurrent operations.

### Task as an Executor-Bound Abstraction

In production systems, tasks are typically bound to an executor. An executor-bound task ensures that when it resumes after a suspension point, it resumes on the correct executor:

```cpp
template <typename T>
class ExecutorTask {
    Executor* executor_;
    // ...

    // When this task awaits a sub-task, it posts the resumption
    // back to its own executor.
    void await_suspend(std::coroutine_handle<> handle) noexcept {
        handle_.promise().continuation_ = [this, handle]() mutable {
            executor_->post([handle] { handle.resume(); });
        };
    }
};
```

This ensures that all code in a task runs on the same executor, eliminating thread-safety concerns for data accessed by the task. Libraries like `boost::asio` and `folly::coro` make executor binding transparent:

```cpp
// boost::asio: task inherits the executor from the io_context.
boost::asio::awaitable<void> handle_connection(tcp::socket socket) {
    // This code runs on the io_context's executor.
    std::string data = co_await async_read(socket, buffer, use_awaitable);
    co_await async_write(socket, response, use_awaitable);
}
```

### Async Workflows: Putting It All Together

The following example shows how task types, awaitables, generators, executors, and cancellation combine into a realistic async workflow:

```cpp
// An async HTTP server using coroutines.

using namespace boost::asio;

// Task that reads and parses an HTTP request.
awaitable<http::request> parse_request(tcp::socket& socket) {
    beast::flat_buffer buffer;
    co_await http::async_read(socket, buffer, parser_, use_awaitable);
    co_return parser_.release();
}

// Task that processes the request and produces a response.
awaitable<http::response> handle_get(http::request req, Database& db) {
    auto user = co_await db.fetch_user(req.target());
    auto data = co_await db.fetch_data(user.id);
    http::response resp;
    resp.body() = serialize(data);
    resp.prepare_payload();
    co_return resp;
}

// Task that manages the full connection lifecycle.
awaitable<void> handle_connection(tcp::socket socket) {
    try {
        auto req = co_await parse_request(socket);
        auto resp = co_await handle_get(req, database_);
        co_await http::async_write(socket, resp, use_awaitable);
    } catch (const std::exception& e) {
        // Send error response.
    }
}

// Generator that accepts connections.
std::generator<tcp::socket> accept_loop(tcp::acceptor& acceptor) {
    while (true) {
        co_yield acceptor.accept();
    }
}

// Main coroutine: spawn connection handlers.
awaitable<void> server_main(tcp::acceptor& acceptor) {
    TaskScope scope;
    for (auto socket : accept_loop(acceptor) | std::views::take(100)) {
        scope.spawn(handle_connection(std::move(socket)));
    }
    co_await scope;
}
```

This example demonstrates:

- **Task composition**: `handle_get` awaits `db.fetch_user` and `db.fetch_data`, both async tasks.
- **Generator integration**: `accept_loop` produces a lazy stream of sockets via `co_yield`.
- **Range pipeline**: `std::views::take(100)` limits the number of connections.
- **Structured concurrency**: `TaskScope` ensures all connection handlers complete before the server shuts down.
- **Exception handling**: `handle_connection` catches errors from the sub-tasks and sends an error response.
- **Executor binding**: all coroutines run on the io_context's executor, so no locks are needed for socket access.

### Task Lifetime: The Invariant to Protect

The most important invariant across all task types is the relationship between the coroutine frame and the task object:

- The **task object** (`Task<T>`) is a move-only handle to the coroutine frame. The task destructor destroys the frame if the coroutine has not already completed.
- The **coroutine frame** is alive from creation (when the coroutine function is called) until either the coroutine reaches final suspension (after `co_return` or unhandled exception) or the task handle is destroyed.
- **If the task is destroyed before completion**, the coroutine frame is destroyed, and any pending async operations holding a pointer to the frame (via the awaitable's user data) will access destroyed memory. This is a use-after-free bug.

The solution is to ensure that tasks are always awaited (their lifetime is managed by the consumer) or that the executor they run on holds a reference to keep them alive. This is why structured concurrency (TaskScope) and eager task types often use shared ownership internally.

### Task-based Async Patterns: Key Takeaways

- A **task** is a coroutine return type that is itself awaitable. It lets one coroutine call another with `co_await`, forming a composable async workflow.
- The critical wiring is in `final_suspend`, which resumes the awaiting coroutine (if any) when the task completes.
- **Lazy tasks** start only when awaited; **eager tasks** start immediately. Lazy tasks compose more predictably and are the default in most coroutine libraries.
- **Exception propagation** is automatic: the task stores the exception in `unhandled_exception()` and rethrows it in the awaiting coroutine's context via `await_resume()`.
- **Structured concurrency** (TaskScope) ensures that child tasks complete before the parent, eliminating lifetime bugs and providing deterministic cleanup.
- **Cancellation** propagates through cancellation tokens shared across the task tree. Cancellation is cooperative — tasks check the token and stop at safe points.
- **Executor-bound tasks** ensure all code in a task runs on the same executor, simplifying thread-safety reasoning.
- **Fire-and-forget** tasks suppress results and exceptions. They should be used sparingly, only for operations where failure is non-critical.

---

## Summary

C++20 coroutines provide a language-level mechanism for writing resumable functions. The coroutine frame, promise type protocol, and awaitable protocol form the foundation upon which higher-level patterns like generators, awaitable types, and task systems are built.

**Coroutine fundamentals** — A coroutine is any function containing `co_await`, `co_return`, or `co_yield`. The compiler transforms it into a state machine stored in a heap-allocated coroutine frame. The promise type controls lifecycle (start, suspension, return, exception). The awaitable protocol (`await_ready`, `await_suspend`, `await_resume`) controls per-suspension behavior.

**Generator patterns** — Generators use `co_yield` to produce lazy sequences. They combine the readability of sequential code with the efficiency of demand-driven iteration. C++23's `std::generator` integrates with range adaptors, allowing generators to serve as sources in range pipelines. Generators are the right tool when sequence logic involves complex control flow or mutable state; simple transformations remain better suited to views.

**Awaitable types** — Awaitables bridge coroutines to external asynchronous operations. The `operator co_await` customization point enables retrofitting awaitability onto existing types. Practical awaitables must handle result storage, error propagation, lifetime management (unregistration or shared ownership), executor binding for thread affinity, cooperative cancellation, and composition via combinators like `when_all` and `when_any`. The awaitable's design determines the correctness, performance, and safety of the entire coroutine-based async system.

**Task-based async patterns** — Tasks are coroutine return types that are themselves awaitable, enabling coroutines to call other coroutines with `co_await`. The `final_suspend` continuation mechanism chains coroutines together: when a task completes, it resumes the awaiting coroutine. Lazy vs. eager startup, exception propagation, structured concurrency (TaskScope), cancellation token propagation, and executor binding form the backbone of production coroutine systems. Together with generators and awaitables, tasks enable writing complex asynchronous workflows that are as readable as synchronous code while matching the performance of hand-crafted state machines.

---

## Exercises

1. **Write a generator.** Implement a `std::generator<int>` that yields the Collatz sequence starting from a given integer: if n is even, n/2; if odd, 3n+1; stop when n reaches 1.

2. **Write a generator adaptor.** Write a generic `take_last(Gen source, int n)` that yields only the last `n` elements of a generator. (Hint: you will need a buffer of size `n` that is updated as the source is consumed.)

3. **Recursive generator.** Write a generator that performs a depth-first traversal of a filesystem directory tree, yielding file paths. Compare the recursive approach (one generator per directory) with an iterative approach using an explicit stack. Measure the coroutine frame allocation count for a deep directory tree.

4. **Generator composition.** Write a generator `zip(Gen a, Gen b)` that yields pairs of values from two input generators, stopping when either generator is exhausted. Then feed the result into a range pipeline that filters pairs where the first element is even.

5. **Custom allocator for generators.** Modify the `Generator` type shown in the chapter to accept an allocator template parameter. Use `std::pmr::monotonic_buffer_resource` with a stack buffer to eliminate heap allocation for small generator frames. Measure the performance difference for a generator that yields 1 million integers.

6. **Generator vs. views comparison.** Implement the same problem — take the first 20 odd Fibonacci numbers — twice: once using a generator and once using `std::views::filter` on `std::views::iota` with a Fibonacci lambda. Compare code readability, performance, and memory allocation.

7. **Implement an awaitable for `std::future`.** Write an `operator co_await` for `std::future<T>` that polls `is_ready()` in a spin loop (or uses a callback-based approach). Test it by awaiting a `std::future` from within a coroutine.

8. **Timer-based cancellation.** Implement an awaitable `with_timeout(awaitable, duration)` that wraps any awaitable with a timeout. If the timeout expires before the awaitable completes, cancel the awaitable and resume with an error.

9. **Thread-safe completion flag.** Write an awaiter that can be completed from any thread. Use `std::atomic<bool>` to ensure that the coroutine handle's `resume()` is called exactly once, even if completion, cancellation, and timeout callbacks race.

10. **Simple `when_all`.** Implement a `when_all` combinator for two awaitables of the same type. The awaiter should start both operations, count completions, and resume the awaiting coroutine only after both have finished. Collect both results into a `std::pair`.

11. **Lazy vs. eager benchmark.** Implement two versions of a `Task<int>` — one with `initial_suspend` returning `suspend_always` (lazy) and one returning `suspend_never` (eager). Measure the wall-clock time for a chain of 1,000 tasks where each task awaits the previous one. What do you observe about overhead and progression?

12. **Implement a TaskScope.** Write a minimal `TaskScope` class that supports `spawn(Task<T>)` and `co_await scope`. Ensure that exceptions from child tasks are collected and rethrown by the scope. Test it by spawning tasks that may throw.

13. **Cancellation token propagation.** Modify the `Task<T>` implementation to accept an optional `CancellationToken` parameter. Ensure that when a task is cancelled, all tasks it spawned via `co_await` are also cancelled. Verify the cancellation propagates through a chain of three nested tasks.

14. **Async workflow.** Build a small async HTTP client using task types: write a `Task<std::string> fetch_url(std::string url)` that resolves DNS (simulated async), connects a socket, sends an HTTP request, and reads the response. Compose three concurrent fetches using `when_all` and a timeout using `with_timeout`.

15. **Executor-bound task.** Create an `ExecutorTask<T>` that stores an executor reference and ensures resumption happens on that executor. Write a test that spawns tasks on a thread pool and verifies that all resumptions happen on the correct thread (using `std::this_thread::get_id()` for verification).
