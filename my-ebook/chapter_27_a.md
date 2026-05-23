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
        std::suspend_never final_suspend() noexcept { return {}; }
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
