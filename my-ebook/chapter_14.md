# Chapter 14: Concurrent Data Structures

## Thread-safe queues

Thread-safe queues are fundamental building blocks for concurrent programming, enabling safe communication between threads without data races. Unlike regular queues that require external synchronization, thread-safe queues encapsulate their own synchronization mechanisms, providing a clean interface for producer-consumer patterns.

The core challenge in designing thread-safe queues lies in balancing three often-conflicting requirements: correctness under concurrent access, performance under contention, and usability in generic contexts. A poorly designed queue can become a bottleneck in concurrent applications, while an overly conservative design might sacrifice performance unnecessarily.

Most thread-safe queue implementations use a combination of mutexes and condition variables to coordinate access. The mutex protects the internal state (typically a linked list or circular buffer), while condition variables allow threads to wait efficiently for specific conditions—such as "queue not empty" for consumers or "queue not full" for bounded queues.

Consider the mental model of a thread-safe queue as a synchronized handoff point: producers deposit items and consumers retrieve them, with the queue handling all the complexity of ensuring that no two threads corrupt the internal state simultaneously. This abstraction allows application code to focus on the logic of what data to produce and consume, rather than the mechanics of thread coordination.

Bounded versus unbounded queues represent a key design decision. Unbounded queues can grow indefinitely, which simplifies the full condition check but risks unbounded memory consumption if producers outpace consumers. Bounded queues require blocking when full (for producers) or empty (for consumers), providing natural backpressure but potentially leading to deadlock if not used carefully.

Performance characteristics vary significantly based on the underlying implementation. Lock-based queues typically show good performance under low to moderate contention but can suffer from convoy effects under high contention. Lock-free queues, while more complex to implement correctly, can offer better scalability by eliminating the convoy problem, though they often come with higher constant factors and more complex memory reclamation challenges.

Common patterns built on thread-safe queues include thread pools (where work items are queued for available workers), event loops (where asynchronous callbacks are queued for processing), and pipeline architectures (where each stage processes items from an input queue and places results in an output queue).

## Double-checked locking

Double-checked locking is an optimization pattern used to reduce the overhead of acquiring a lock by first testing the locking criterion without acquiring the lock. Only if the test indicates that locking is required does the actual lock acquisition proceed. This pattern is particularly useful in lazy initialization scenarios where initialization should happen only once, but subsequent accesses should be as fast as possible.

The classic problem double-checked locking aims to solve is the initialization of a singleton or other shared resource that is expensive to create but needed infrequently. A naive approach would use a mutex every time the resource is accessed, causing unnecessary overhead after initialization. Double-checked locking attempts to avoid this overhead by checking the initialization status twice: once without locking, and if that check suggests initialization is needed, then with locking to ensure thread safety.

However, double-checked locking is notoriously difficult to implement correctly in C++ due to the complexities of memory ordering and compiler optimizations. Without proper memory barriers, several issues can arise:

1. **Compiler reordering**: The compiler might reorder instructions such that the pointer to the resource becomes visible before the resource is fully constructed
2. **CPU reordering**: Even if the compiler doesn't reorder, the CPU might execute memory operations out of order for performance
3. **Cache coherence issues**: In multi-core systems, changes made by one thread might not be immediately visible to others

The key to making double-checked locking work correctly in C++ is using `std::atomic` with appropriate memory ordering specifications. The pattern typically involves:

1. An atomic pointer or flag to track initialization status
2. Memory acquire/release semantics to ensure proper visibility
3. A mutex to protect the actual initialization when needed

Consider this corrected implementation:

```cpp
class Singleton {
public:
    static Singleton& instance() {
        Singleton* tmp = instance_ptr.load(std::memory_order_acquire);
        if (tmp == nullptr) {
            std::lock_guard<std::mutex> lock(mutex_);
            tmp = instance_ptr.load(std::memory_order_relaxed);
            if (tmp == nullptr) {
                tmp = new Singleton();
                instance_ptr.store(tmp, std::memory_order_release);
            }
        }
        return *tmp;
    }

private:
    Singleton() = default;
    ~Singleton() = default;
    Singleton(const Singleton&) = delete;
    Singleton& operator=(const Singleton&) = delete;

    static std::atomic<Singleton*> instance_ptr;
    static std::mutex mutex_;
};
```

The double-checked locking pattern has evolved with C++ standards. In C++11 and later, the language provides stronger guarantees about atomic operations and memory ordering, making the pattern safer to implement. However, even with these improvements, developers must still understand the underlying memory model to use it correctly.

Alternatives to double-checked locking often provide safer and simpler solutions:

1. **Meyers' Singleton**: Using a local static variable (guaranteed thread-safe initialization in C++11+)
2. **std::call_once**: Specifically designed for one-time initialization
3. **Eager initialization**: Creating the resource at program startup when performance isn't critical

Despite its complexity, understanding double-checked locking is valuable because it teaches important concepts about concurrent programming:

- The importance of memory ordering in multi-threaded environments
- How compiler and CPU optimizations can affect correctness
- The distinction between atomic operations and synchronization primitives
- Why seemingly obvious optimizations can be dangerously misleading

In practice, double-checked locking should be reserved for performance-critical paths where profiling has shown that the overhead of simpler synchronization mechanisms is unacceptable. For most applications, the alternatives mentioned above provide better safety with comparable performance.

## Actor model implementation

The Actor model is a conceptual framework for concurrent computation that treats "actors" as the fundamental units of computation. In this model, actors communicate exclusively through asynchronous message passing, eliminating the need for explicit locking mechanisms and reducing the risk of common concurrency issues like deadlocks and race conditions.

At its core, the Actor model is based on three principles:

1. **Encapsulation**: Each actor encapsulates its own state and behavior
2. **Isolation**: Actors do not share state; they communicate only through messages
3. **Message-driven computation**: Actors react to incoming messages by updating their state, sending messages to other actors, or creating new actors

This model naturally fits concurrent and distributed systems because it avoids the complexities of shared-memory synchronization. Since actors don't share memory, there's no need for locks, semaphores, or other synchronization primitives when accessing actor state. Instead, all coordination happens through the message passing mechanism.

In C++, implementing the Actor model requires careful consideration of several key components:

- **Message passing mechanism**: How actors send and receive messages
- **Actor lifecycle management**: How actors are created, started, and terminated
- **Mailbox implementation**: How messages are queued for each actor
- **Scheduler/dispatcher**: How actors are assigned to threads for execution
- **Location transparency**: Whether the system supports distributed actors

A typical actor implementation in C++ involves:

1. An actor base class that defines the interface for receiving and processing messages
2. A message queue (mailbox) for each actor to store incoming messages
3. A scheduler that assigns actors to threads when they have messages to process
4. Concrete actor classes that inherit from the base and implement specific behavior

Consider a simplified actor framework:

```cpp
// Message base class
class Message {
public:
    virtual ~Message() = default;
};

// Actor base class
class Actor {
public:
    virtual ~Actor() {
        stop();
    }

    // Send a message to this actor (thread-safe)
    void send(std::unique_ptr<Message> msg) {

    // Send a message to this actor (thread-safe)
    void send(std::unique_ptr<Message> msg) {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        message_queue_.push(std::move(msg));
        condition_.notify_one();
    }

    // Start the actor's message processing loop
    void start() {
        bool expected = false;
        if (!running_.compare_exchange_strong(expected, true)) return;
        processing_thread_ = std::thread(&Actor::processMessages, this);
    }

    // Stop the actor
    void stop() {
        {
            std::lock_guard<std::mutex> lock(queue_mutex_);
            running_ = false;
        }
        condition_.notify_all();
        if (processing_thread_.joinable()) {
            processing_thread_.join();
        }
    }

protected:
    // Pure virtual function to process a message
    virtual void onReceive(std::unique_ptr<Message> msg) = 0;

private:
    void processMessages() {
        while (true) {
            std::unique_ptr<Message> msg;
            {
                std::unique_lock<std::mutex> lock(queue_mutex_);
                condition_.wait(lock, [this] { return !message_queue_.empty() || !running_; });
                if (message_queue_.empty() && !running_) break;
                if (!message_queue_.empty()) {
                    msg = std::move(message_queue_.front());
                    message_queue_.pop();
                }
            }
            if (msg) {
                onReceive(std::move(msg));
            }
        }
    }

    std::queue<std::unique_ptr<Message>> message_queue_;
    std::mutex queue_mutex_;
    std::condition_variable condition_;
    std::thread processing_thread_;
    std::atomic<bool> running_{false};
};
```

This basic implementation shows the core concepts:

- Actors encapsulate their state (the message queue and processing thread)
- Communication happens exclusively through message passing (the send method)
- Each actor processes messages sequentially in its own thread
- The onReceive method must be implemented by concrete actors to define their behavior

However, production-ready actor frameworks need additional features:

- **Message routing**: Ability to send messages to specific actors by address/reference
- **Supervision hierarchies**: Mechanisms for handling actor failures
- **Routing logic**: More sophisticated mailbox implementations (priority queues, etc.)
- **Scheduler integration**: Better thread utilization through work-stealing or thread pools
- **Dead letter handling**: What happens when messages can't be delivered
- **Monitoring and observability**: Tracking actor lifecycle and message counts

Popular C++ actor frameworks like CAF (C++ Actor Framework) or SObjectizer provide these advanced features while maintaining the core Actor model principles.

Benefits of the Actor model include:

- **Elimination of common concurrency bugs**: No shared state means no data races
- **Natural fit for distributed systems**: Message passing works well across network boundaries
- **Scalability**: Easy to add more actors to handle increased load
- **Fault tolerance**: Supervision hierarchies can isolate failures
- **Location transparency**: Actors can be moved between processes or machines without changing code

Challenges and considerations:

- **Performance overhead**: Message passing involves memory allocation and copying
- **Learning curve**: Developers must shift from shared-state to message-passing thinking
- **Debugging complexity**: Asynchronous message flows can be harder to trace
- **Message ordering guarantees**: Ensuring causal relationships between messages
- **Deadlock possibilities**: Circular waiting patterns can still occur with message dependencies

The Actor model shines in applications like:

- **Concurrent servers**: Handling multiple client connections
- **Game development**: Managing game entities and systems
- **Financial systems**: Processing market data feeds
- **IoT applications**: Managing device communications
- **Workflow systems**: Coordinating multi-step processes

When compared to other concurrency approaches:

- **vs. Thread pools with shared queues**: Actors provide better encapsulation and reduce contention
- **vs. Lock-based data structures**: Actors eliminate lock contention entirely
- **vs. Futures/promises**: Actors are better suited for long-lived, stateful computations
- **vs. Reactive streams**: Actors offer more explicit control over state and behavior

Understanding the Actor model provides valuable insights into designing concurrent systems that are easier to reason about, maintain, and scale, particularly when distribution or fault tolerance is important.

## Futures and promises patterns

Futures and promises are abstractions for managing asynchronous results, decoupling the initiation of an operation from its eventual outcome. A promise acts as the producer end of a channel: it holds a value (or an exception) that does not yet exist. A future acts as the consumer end: it provides a mechanism to retrieve that value once it becomes available.

The mental model is that of a single-producer, single-consumer rendezvous point. The producer writes a result into the promise, and the consumer reads it from the future. The thread that fulfills the promise and the thread that waits on the future may be different, or they may even be the same thread if the value is already available at the time of retrieval. The channel has three states: empty (no result yet), ready (a value is stored), and broken (an exception was stored).

Consider the simplest case of a standalone promise-future pair:

```cpp
std::promise<int> promise;
std::future<int> future = promise.get_future();

std::thread producer([p = std::move(promise)]() mutable {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    p.set_value(42);
});

int result = future.get();
producer.join();
```

The call to `future.get()` blocks until the producer calls `set_value`. This pattern replaces the awkwardness of manually managing a mutex, condition variable, and shared state. The promise-future pair encapsulates all of that synchronization internally.

The most important design consideration is that a promise can be moved but not copied. This expresses the ownership transfer model: only one producer may fulfill the promise. Similarly, a future is move-only, though a `std::shared_future` can be cloned for multiple consumers.

### Fulfillment strategies

There are three ways to fulfill a promise: with a value, with an exception, or by breaking it explicitly.

```cpp
promise.set_value(42);                              // normal completion
promise.set_exception(std::make_exception_ptr(...)); // error completion
promise.set_exception(std::current_exception());          // re-throw caught exception
```

Setting a value on an already-fulfilled promise throws `std::future_error`. This is by design: a promise represents an exclusive contract, and fulfilling it twice would violate the expectations of the holder of the future.

### Using futures in practice

The simplest use of a future is the blocking `get()` call, which returns the value and invalidates the future. For non-blocking checks, `wait_for` and `wait_until` accept a timeout and return a `future_status`:

```cpp
if (future.wait_for(std::chrono::milliseconds(10)) == std::future_status::ready) {
    auto value = future.get();
}
```

The `future_status` enum has three values: `ready` (the promise was fulfilled), `timeout` (the timeout elapsed with no result), and `deferred` (the task is lazy-evaluated and will only run when `get` or `wait` is called). The deferred case arises when using `std::async` with the `std::launch::deferred` policy.

### std::async for fire-and-forget parallelism

Rather than managing promise-future pairs manually, `std::async` creates them implicitly. Given a callable, `std::async` returns a future that will be fulfilled when the callable completes:

```cpp
auto future = std::async(std::launch::async, [] {
    return computeExpensiveResult();
});
// do other work...
auto result = future.get();
```

The launch policy controls execution timing. With `std::launch::async`, the function runs immediately on a separate thread. With `std::launch::deferred`, the function runs lazily when `get` is called. The default `std::launch::async | std::launch::deferred` leaves the choice to the implementation, which introduces subtle behavior differences: a deferred future never throws an exception at construction time, only at `get` time.

The lifetime of a `std::future` matters. When the last future referencing a shared state is destroyed, the shared state is released. If the associated task has not yet completed, the implementation may block until it does. This means that destructors of futures returned by `std::async` can be blocking, which is a frequent source of surprise.

### packaged_task as a bridge

`std::packaged_task` wraps a callable object and exposes a future that will be fulfilled when the callable returns. This decouples the execution of the task from both the creation of the promise and the act of launching a thread:

```cpp
std::packaged_task<int(int)> task([](int n) {
    return fibonacci(n);
});
auto future = task.get_future();

std::thread t(std::move(task), 30);
// ... other work ...
auto result = future.get();
t.join();
```

The key insight is that `packaged_task` is a callable itself: it can be passed to a thread pool, a scheduler, or any execution context. The consumer of the result does not need to know how or when the task runs.

### Exception propagation

Promises propagate exceptions transparently. If a callable wrapped in `std::async` or `packaged_task` throws, the exception is stored in the shared state and rethrown when `future.get()` is called:

```cpp
auto future = std::async([] {
    throw std::runtime_error("task failed");
});

try {
    future.get();
} catch (const std::runtime_error& e) {
    // handles the exception
}
```

This gives futures and promises a consistent error handling model: the caller uses the same mechanism (catch) for both synchronous and asynchronous errors. The alternative of returning error codes would require the caller to check explicitly, which is error-prone.

### shared_future for multiple consumers

A `std::future` is move-only and `get()` transfers the value out. To broadcast a result to multiple consumers, `std::shared_future` supports copy construction and allows multiple calls to `get()`:

```cpp
std::shared_future<int> shared = std::async(std::launch::async, heavyComputation).share();

std::thread consumer1([shared] { auto val = shared.get(); });
std::thread consumer2([shared] { auto val = shared.get(); });
```

Internally, `shared_future` reference-counts the shared state. The state is destroyed only when all shared_future instances and the associated promise have been destroyed. This is analogous to `shared_ptr` in ownership terms.

### Future continuations (C++20 and beyond)

While C++20 did not standardize `.then()` continuations, the C++23 standard introduces the Sender/Receiver model (P2300) as a powerful, unified framework for asynchronous composition. This model generalizes the concept of futures by decoupling the creation of work (senders) from its execution (receivers).

````cpp
// Conceptual example of the Sender/Receiver model (P2300)
auto sender = async_operation() | then([](auto val) {
    return process(val);
});
std::this_thread::sync_wait(std::move(sender));

```cpp
future.then([](auto f) {
    auto val = f.get();
    return process(val);
});
````

While standard C++ continues to evolve in this direction, the basic promise-future model remains the foundation. For production code that requires complex asynchronous pipelines, libraries like Folly Futures, HPX, or Boost.Asio provide richer continuation and composition support.

### Trade-offs and considerations

Futures and promises solve an important coordination problem, but they are not always the right tool:

- **Blocking is wasteful**: Calling `future.get()` blocks the calling thread. In high-concurrency systems, blocking a thread prevents it from doing other useful work. Callbacks, continuations, or coroutines may be better suited.

- **One-shot only**: A promise can be fulfilled exactly once, and a future consumes the result exactly once (or multiple times with shared_future). There is no built-in retry or streaming. For repeated events, use queues or channels.

- **Memory overhead**: Each promise-future pair allocates a shared state on the heap. Creating thousands of short-lived promises can pressure the allocator.

- **No cancellation**: Standard C++ futures do not support cancellation. Once a task is launched via `std::async`, it must run to completion (or until the thread terminates). Libraries like `std::stop_token` (C++20) provide a cancellation mechanism, but it requires explicit cooperation from the task.

- **Exception safety**: If the thread that owns the promise terminates without fulfilling it, the shared state is broken, and `future.get()` will throw `std::future_error` with `broken_promise`. RAI wrappers can ensure promises are always fulfilled.

Despite these limitations, futures and promises are the right choice when a computation produces exactly one result asynchronously and the consumer can afford to wait synchronously (or can poll with timeouts). They form the backbone of many task-based concurrency systems and are well worth understanding deeply, both because of their wide applicability and because their design reveals fundamental concepts in synchronization and ownership that recur throughout concurrent programming.
