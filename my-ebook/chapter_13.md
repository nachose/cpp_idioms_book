# Chapter 13: Thread-Safe Interfaces

Modern C++ applications frequently involve concurrent execution. Multiple threads may access shared data simultaneously, and without proper synchronization, this leads to data races, corruption, and undefined behavior. Thread-safe interfaces provide the abstraction boundary between concurrent code and the data it accesses, ensuring that correct usage is natural and incorrect usage is difficult or impossible.

This chapter explores the design principles and implementation patterns for creating thread-safe interfaces in C++. We move beyond simple mutexes to examine how to structure classes so that they remain correct under concurrent access while maintaining reasonable performance. The goal is interfaces that guide developers toward correct usage without imposing unnecessary overhead.

---

## Thread-Agnostic Design

The most fundamental principle in concurrent design is to minimize shared mutable state. Thread-agnostic design doesn't mean ignoring concurrency—it means designing interfaces that remain correct regardless of which thread calls them, reducing the cognitive burden on developers.

### Why Thread-Agnostic Design Matters

When a class assumes a particular threading model, it becomes fragile. Code that works correctly in single-threaded tests may fail mysteriously in production when multiple threads access the class. Thread-agnostic design shifts the burden of reasoning about concurrency from the class user to the class implementer, where it can be handled consistently.

Consider a simple counter class:

```cpp
class Counter {
    int value = 0;
public:
    void increment() { ++value; }
    int get() const { return value; }
};
```

This class has a data race—incrementing and reading can happen concurrently on different threads, leading to undefined behavior. Fixing this requires either internal synchronization or thread-agnostic design that makes concurrent access safe by default.

A thread-agnostic approach would involve making the counter safe for concurrent use without requiring callers to manage locks:

```cpp
class ThreadSafeCounter {
    mutable std::mutex mutex_;
    int value = 0;
public:
    void increment() {
        std::lock_guard<std::mutex> lock(mutex_);
        ++value;
    }

    int get() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return value;
    }
};
```

Now callers can use the counter safely from any thread without knowing about the mutex. The interface is thread-agnostic—callers don't need to reason about threading at all.

### Designing for Immutability

The simplest way to achieve thread-agnostic design is to minimize mutable state. Immutable data structures can be safely shared between threads without synchronization because no thread can modify the data.

In C++, you can enforce immutability by providing only const member functions and avoiding mutable members. Once constructed, an immutable object never changes state. This model eliminates entire categories of concurrency bugs.

```cpp
class ImmutableUserProfile {
    const std::string name_;
    const std::string email_;
    const std::vector<std::string> roles_;
public:
    ImmutableUserProfile(std::string name, std::string email,
                        std::vector<std::string> roles)
        : name_(std::move(name))
        , email_(std::move(email))
        , roles_(std::move(roles)) {}

    // All const - no modifications possible
    const std::string& name() const { return name_; }
    const std::string& email() const { return email_; }
    const std::vector<std::string>& roles() const { return roles_; }

    // Instead of modification, return new instances
    ImmutableUserProfile with_email(std::string new_email) const {
        return ImmutableUserProfile(name_, std::move(new_email), roles_);
    }
};
```

When you need to change a user's email, you create a new profile rather than modifying the existing one. This approach may seem inefficient due to copying, but it often leads to simpler reasoning about code and enables optimization through structural sharing.

### Value Types and Thread Safety

C++ classes that follow value semantics—copying and assigning like integers—can often achieve thread safety more easily than reference semantics classes. When you pass a value type to another thread, you pass a complete copy, eliminating the possibility of data races on the shared state.

The standard library containers and strings are value types, but they contain internal pointers to heap-allocated data. Copying them copies the pointers, not the pointed-to data, which doesn't automatically make them thread-safe for concurrent modification.

For thread-safe value passing, consider representing your data as a simple aggregate of built-in types or as an immutable structure. When you must share complex data between threads, either protect it with synchronization or use concurrent data structures.

```cpp
// Simple value type - inherently thread-safe to copy
struct Point {
    double x, y;
};

// More complex, but still value-like
struct Transformation {
    double scale = 1.0;
    double rotation = 0.0;
    double translate_x = 0.0;
    double translate_y = 0.0;
};
```

### Thread-Agnostic Member Functions

When you must have mutable state, design member functions to be thread-agnostic individually. Each function should work correctly when called from any thread, with no special ordering requirements between calls.

A thread-agnostic member function holds these properties: it doesn't assume anything about the calling thread, it doesn't modify state accessible from other threads, and multiple concurrent calls produce correct results.

```cpp
class Circle {
    mutable std::mutex mutex_;
    Point center_;
    double radius_;
public:
    // Thread-agnostic: can be called from any thread
    double area() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return 3.14159 * radius_ * radius_;
    }

    bool contains(Point p) const {
        std::lock_guard<std::mutex> lock(mutex_);
        double dx = p.x - center_.x;
        double dy = p.y - center_.y;
        return (dx * dx + dy * dy) <= (radius_ * radius_);
    }
};
```

Note that both functions lock the mutex. Even read-only operations must lock because the underlying representation might change between reading individual members. A reader that sees an updated radius but an old center would compute incorrect results.

### Trade-offs and Considerations

Thread-agnostic design has costs. Internal synchronization adds overhead, especially for fine-grained operations. It can limit parallelism if too much state is protected by a single mutex. And it can't solve all concurrency problems—some algorithms require coordination that can't be encapsulated in a single object.

The appropriate level of thread-agnosticism depends on your use case. For library code used by many callers, thread-agnosticism provides a safer default. For performance-critical internal components, you might choose to expose synchronization primitives and trust callers to coordinate correctly.

---

## Lock Granularity and Lock-Free Idioms

Once you've decided to use synchronization, the next question is how much data to protect with each lock. Lock granularity—the amount of data protected by a single lock—affects both correctness and performance. Too coarse, and you limit parallelism. Too fine, and you increase overhead and complexity.

Lock-free programming goes further, eliminating locks entirely through atomic operations. This approach can improve performance and scalability, but requires more careful reasoning about correct behavior.

### Coarse-Grained Locking

The simplest approach protects an entire object with a single mutex. This coarse granularity is easy to implement and reason about, but can become a bottleneck in highly concurrent code.

```cpp
class BankAccount {
    mutable std::mutex mutex_;
    double balance_;
public:
    void deposit(double amount) {
        std::lock_guard<std::mutex> lock(mutex_);
        balance_ += amount;
    }

    bool withdraw(double amount) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (balance_ >= amount) {
            balance_ -= amount;
            return true;
        }
        return false;
    }

    double get_balance() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return balance_;
    }
};
```

This implementation is correct—concurrent calls from multiple threads won't corrupt the balance. However, only one operation can proceed at a time, even for unrelated accounts. In a banking system with millions of accounts, this could severely limit throughput.

### Fine-Grained Locking

Fine-grained locking protects different parts of an object with separate mutexes, allowing concurrent access to different parts simultaneously.

```cpp
class UserProfile {
    mutable std::mutex name_mutex_;
    mutable std::mutex data_mutex_;
    std::string name_;
    std::unordered_map<std::string, std::string> data_;

public:
    void set_name(const std::string& name) {
        std::lock_guard<std::mutex> lock(name_mutex_);
        name_ = name;
    }

    std::string get_name() const {
        std::lock_guard<std::mutex> lock(name_mutex_);
        return name_;
    }

    void set_data(const std::string& key, const std::string& value) {
        std::lock_guard<std::mutex> lock(data_mutex_);
        data_[key] = value;
    }

    std::optional<std::string> get_data(const std::string& key) const {
        std::lock_guard<std::mutex> lock(data_mutex_);
        auto it = data_.find(key);
        if (it != data_.end()) {
            return it->second;
        }
        return std::nullopt;
    }
};
```

Now name operations and data operations can proceed concurrently. However, this introduces complexity—you must ensure that operations requiring multiple parts of the state acquire the correct locks in a consistent order to avoid deadlock.

### Lock Ordering to Prevent Deadlock

When you need to hold multiple locks simultaneously, consistent lock ordering prevents deadlock. Define a global ordering for all locks, and always acquire them in that order.

```cpp
class MultiLockExample {
    mutable std::mutex mutex_a_;
    mutable std::mutex mutex_b_;
    int data_a_ = 0;
    int data_b_ = 0;

public:
    // Always acquire a before b
    void update_both(int a, int b) {
        // Use std::scoped_lock to acquire both without deadlock
        std::scoped_lock lock(mutex_a_, mutex_b_);
        data_a_ = a;
        data_b_ = b;
    }
};
```

The `std::lock` function acquires multiple locks in a deadlock-free way by implementing a deadlock-avoidance algorithm. After acquiring, the lock guards adopt the lock state using `std::adopt_lock`.

### Lock-Free Concepts

Lock-free programming uses atomic operations instead of locks. This can improve performance and avoids deadlock, but requires careful algorithm design.

A lock-free algorithm guarantees that at least one thread can make progress even if other threads are blocked. Compare-and-swap (CAS) is the fundamental operation:

```cpp
template<typename T>
class LockFreeStack {
    struct Node {
        T data;
        Node* next;
    };
    std::atomic<Node*> head_;

public:
    void push(T value) {
        Node* new_node = new Node{value, nullptr};
        new_node->next = head_.load();
        // CAS loop: try to set head, retry if another thread modified it
        while (!head_.compare_exchange_weak(
            new_node->next,
            new_node,
            std::memory_order_release,
            std::memory_order_relaxed)) {
            // new_node->next updated by compare_exchange_weak
            // retry with updated pointer
        }
    }

    std::optional<T> pop() {
        Node* old_head = head_.load(std::memory_order_acquire);
        while (old_head != nullptr) {
    std::optional<T> pop() {
        std::shared_ptr<Node> old_head = head_.load(std::memory_order_acquire);
        while (old_head && !head_.compare_exchange_weak(
            old_head, old_head->next,
            std::memory_order_release, 
            std::memory_order_acquire)) {
            // old_head is updated by compare_exchange_weak on failure
        }
        return old_head ? std::make_optional(old_head->data) : std::nullopt;
    }
            if (head_.compare_exchange_weak(
                    old_head, next,
                    std::memory_order_release,
                    std::memory_order_acquire)) {
                T value = std::move(old_head->data);
                delete old_head;
                return value;
            }
            // old_head updated by CAS, retry
        }
        return std::nullopt;
    }
};
```

This implementation uses a compare-and-exchange loop to atomically replace the head pointer. If another thread modified the head between reading and updating, the CAS fails, and the loop retries with the new value.

### Lock-Free Considerations

Lock-free algorithms are more complex to implement correctly than lock-based ones. You must consider memory ordering—using the correct memory order for each operation. You must handle the ABA problem—where a value changes and changes back between checks. And you must verify progress guarantees.

In practice, prefer existing concurrent containers from the standard library or well-tested libraries. Implementing your own lock-free structures is appropriate only when you have specific performance requirements that existing solutions don't meet.

---

## Thread-Local Storage Patterns

Thread-local storage (TLS) provides each thread with its own independent copy of a variable. Unlike shared variables, thread-local variables don't require synchronization—each thread operates on its own copy, eliminating data races on that variable.

### Understanding Thread-Local Storage

In C++, the `thread_local` keyword declares a variable with thread storage duration. Each thread gets its own instance of the variable, initialized when the thread starts, and destroyed when the thread exits.

```cpp
thread_local int current_request_id = 0;
thread_local std::string thread_name;

void handle_request(int id) {
    current_request_id = id;
    // Process request - other threads have their own current_request_id
}

void log(const std::string& message) {
    std::cout << "[" << thread_name << "] " << message << "\n";
}
```

The `current_request_id` variable changes independently in each thread. One thread can set its ID to 5 while another thread sets its ID to 10, and neither affects the other.

### Common Use Cases

Thread-local storage is useful in several scenarios: maintaining per-thread state that would otherwise require passing state through many function calls, caching thread-specific data to avoid contention, and storing random number generator state for multi-threaded programs.

The most common use is maintaining context that doesn't need to be shared:

```cpp
class RequestContext {
    thread_local static RequestContext* current_;
    std::string request_id_;
    std::unordered_map<std::string, std::string> headers_;
public:
    static RequestContext* current() { return current_; }
    static void set_current(RequestContext* ctx) { current_ = ctx; }

    const std::string& request_id() const { return request_id_; }
    // ...
};

void process_request(RequestContext& ctx) {
    RequestContext::set_current(&ctx);
    // Now any function in the call stack can access the context
    handle_header();
    handle_body();
    RequestContext::set_current(nullptr);
}
```

This pattern eliminates the need to pass the request context through every function call. Any function can access the current request's context through the thread-local pointer.

### Performance Considerations

Thread-local storage has performance characteristics worth understanding. Access to thread-local variables is typically as fast as regular global variables—often a single load from a thread-specific base pointer. However, the first access on each thread may involve initialization overhead.

Memory usage scales with the number of threads. If you have 100 threads and each thread-local variable is 1KB, you use 100KB of thread-local storage. This can become significant with many threads.

Some systems limit the total amount of thread-local storage, and creating too many thread-local variables can fail at runtime. Use thread-local judiciously, and consider whether per-thread caching is truly necessary.

### Thread-Local with Static Storage Duration

Variables with static storage duration can also be thread-local. This includes global variables, static class members, and local static variables.

```cpp
class Logger {
    static thread_local std::ostringstream buffer_;
public:
    static void log(const std::string& message) {
        buffer_ << message << "\n";
    }

    static void flush() {
        // Each thread has its own buffer
        std::cout << buffer_.str();
        buffer_.str("");
    }
};
```

The buffer exists separately for each thread. When thread A logs a message, it goes into thread A's buffer. When thread B logs, it goes into thread B's buffer. This avoids contention on logging output without requiring explicit synchronization.

### Trade-offs

Thread-local storage simplifies some concurrency problems but creates others. Thread-local variables are implicitly shared between any code running in the same thread, which can lead to subtle bugs when code that runs in multiple contexts—perhaps a function used both in a worker thread and the main thread—depends on thread-local state.

Additionally, thread-local variables can leak across unrelated operations if not cleared properly. The request context example shows the pattern: set the context at the start of a request and clear it at the end.

---

## Reader-Writer Lock Patterns

Many data structures are read frequently but modified infrequently. A standard mutex treats all operations equally—while one thread holds the lock, no other thread can proceed, even for read-only access. Reader-writer locks allow multiple concurrent readers while ensuring exclusive access for writers.

### The Problem with Simple Mutexes

Consider a configuration object that's read frequently but only changed occasionally:

```cpp
class Configuration {
    mutable std::mutex mutex_;
    std::unordered_map<std::string, std::string> values_;
public:
    std::optional<std::string> get(const std::string& key) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = values_.find(key);
        return it != values_.end() ? std::make_optional(it->second) : std::nullopt;
    }

    void set(const std::string& key, std::string value) {
        std::lock_guard<std::mutex> lock(mutex_);
        values_[key] = std::move(value);
    }
};
```

With many concurrent readers, this implementation serializes all access. Even though reads don't modify state and could proceed concurrently, they all wait for each other. A reader-writer lock allows multiple readers to hold the lock simultaneously.

### Reader-Writer Lock in C++

C++17 introduced `std::shared_mutex` (and `std::shared_timed_mutex`) which implements this pattern. Multiple readers can acquire the lock in shared mode, while writers get exclusive access.

```cpp
class Configuration {
    mutable std::shared_mutex mutex_;
    std::unordered_map<std::string, std::string> values_;
public:
    std::optional<std::string> get(const std::string& key) const {
        // Shared lock for reading - multiple threads can read simultaneously
        std::shared_lock<std::shared_mutex> lock(mutex_);
        auto it = values_.find(key);
        return it != values_.end() ? std::make_optional(it->second) : std::nullopt;
    }

    void set(const std::string& key, std::string value) {
        // Exclusive lock for writing
        std::unique_lock<std::shared_mutex> lock(mutex_);
        values_[key] = std::move(value);
    }

    // For more complex read-modify-write operations
    bool update_if_exists(const std::string& key, std::function<void(std::string&)> updater) {
        std::unique_lock<std::shared_mutex> lock(mutex_);
        auto it = values_.find(key);
        if (it == values_.end()) {
            return false;
        }
        updater(it->second);
        return true;
    }
};
```

The `std::shared_lock` allows multiple concurrent readers. When `get()` is called by multiple threads simultaneously, they all proceed. When `set()` is called, it acquires an exclusive lock, blocking all readers and other writers until it completes.

### Writer Priority vs Reader Priority

Reader-writer locks can favor readers or writers. Under reader preference, waiting readers may starve writers if new readers continuously arrive. Under writer preference, waiting writers block new readers to ensure eventual progress for write operations.

The standard library doesn't specify priority behavior, which is implementation-defined. If writer starvation is a concern in your application, consider using a writer-preferring lock implementation or adding explicit yield points for readers.

### Read-Copy-Update (RCU) Pattern

For scenarios with very high read frequency and infrequent updates, consider the Read-Copy-Update pattern. Rather than locking during reads, RCU allows readers to proceed without any synchronization, while updates create new versions of the data.

```cpp
template<typename T>
class RCUObject {
    std::atomic<T*> ptr_;
public:
    explicit RCUObject(T* initial) : ptr_(initial) {}

    T* read() const {
        return ptr_.load(std::memory_order_acquire);
    }

    void write(T* new_value) {
        T* old = ptr_.load(std::memory_order_relaxed);
        ptr_.store(new_value, std::memory_order_release);
        // Wait for all existing readers to complete
        // In practice, use synchronization primitives or platforms-specific APIs
        synchronize();
        delete old;
    }
};
```

The actual RCU implementation is more complex and typically uses platform-specific primitives. Linux provides `synchronize_rcu()`; other systems have different mechanisms. The pattern is particularly effective for read-heavy data structures like routing tables or configuration caches.

### Trade-offs and Considerations

Reader-writer locks have overhead that simple mutexes don't. The lock implementation is more complex, and each lock/unlock operation may be slower. For data structures with very high read frequency and very infrequent writes, the concurrency benefit outweighs the overhead. For write-heavy workloads, the extra complexity provides no benefit.

Consider whether you need the complexity at all. If your reads are fast and contention is low, a simple mutex may perform adequately with less code. Only add reader-writer locks when profiling shows that serialization of reads is a bottleneck.

---

## Summary

Creating thread-safe interfaces requires balancing correctness, performance, and complexity. The patterns in this chapter address different aspects of this challenge.

Thread-agnostic design minimizes the concurrency burden on callers by making classes safe for concurrent use. Immutability provides the strongest guarantees, while value semantics simplify reasoning about thread safety.

Lock granularity affects both correctness and performance. Coarse-grained locking is simpler but can limit parallelism. Fine-grained locking allows more concurrency but requires careful attention to lock ordering to avoid deadlock. Lock-free programming eliminates locks but requires more complex algorithms.

Thread-local storage provides independent state for each thread, useful for maintaining context without explicit parameter passing. Use it judiciously, as thread-local variables become implicit shared state within each thread.

Reader-writer locks allow concurrent reads while ensuring exclusive writes, ideal for read-heavy data structures. Consider whether the additional complexity is warranted by your access patterns.

### Exercises

1. Design a thread-safe wrapper around `std::vector<int>` that supports concurrent reads and occasional writes. What locking strategy would you use, and why?

2. Implement a thread-local singleton that tracks the current request in a web server. How would you ensure the context is properly cleared when a request completes?

3. Create a reader-writer lock implementation and benchmark it against a simple mutex for various read/write ratios. When does the reader-writer lock provide measurable benefit?

4. Implement a lock-free stack using atomic operations. Add memory ordering annotations and explain why each annotation is correct.