# Chapter 18: Error Handling Idioms

Error handling in C++ is a design decision with deep implications for correctness, performance, and code clarity. The language gives you multiple mechanisms—exceptions, error codes, `std::optional`, `std::expected`—and each comes with its own set of trade-offs. The idioms in this chapter give you a structured way to think about and implement error handling that integrates naturally with the rest of your C++ code. Rather than treating errors as an afterthought, the patterns here make failure modes explicit, composable, and maintainable.

The chapter begins with the framework that underpins all idiomatic C++ error handling: exception safety guarantees. By understanding these guarantees—what they mean, how they compose, and how to achieve them—you gain a vocabulary for reasoning about correctness that applies regardless of the specific error-handling mechanism you choose. From there, we explore how RAII naturally provides exception safety, compare error codes with exceptions to help you choose the right tool, and finally examine `std::expected` and `Result` types that bring functional error handling into modern C++.

## Exception Safety Guarantees

Exception safety guarantees are a contract between a function and its callers. When a function advertises a certain guarantee, it is promising what the program state will be if the function is interrupted by an exception. Without this contract, every call site would need to assume the worst: that any thrown exception could leave objects in an arbitrary, unusable state. With documented guarantees, callers can reason about recovery and write correct exception-handling code.

C++ recognizes four levels of exception safety, originally formalized by Abrahams (2001). From strongest to weakest, they are: no-throw, strong, basic, and none. Understanding and documenting these levels is itself an idiom—it gives you and your team a shared language for talking about correctness under failure.

### No-Throw Guarantee

The no-throw guarantee means the operation will never throw an exception. This is the strongest guarantee and the only one that is verifiable at compile time through the `noexcept` specifier. Destructors should always provide this guarantee, and move operations should generally provide it when possible.

```cpp
class Buffer {
public:
    ~Buffer() noexcept {
        delete[] data_;
    }

    void swap(Buffer& other) noexcept {
        std::swap(data_, other.data_);
        std::swap(size_, other.size_);
    }

    int value_at(size_t index) const noexcept {
        // If index is out of bounds, we still don't throw.
        // This may not be the right choice for all APIs.
        return (index < size_) ? data_[index] : -1;
    }

private:
    int* data_ = nullptr;
    size_t size_ = 0;
};
```

The `noexcept` specifier serves both as documentation and as an optimization hint—the compiler can generate more efficient code when it knows no exception handling is needed. Destructors are `noexcept` by default, which is why throwing destructors are so dangerous: if a destructor throws during stack unwinding (when another exception is active), `std::terminate` is called immediately.

The guarantee is strongest when you actually enforce it. Functions declared `noexcept` that nevertheless throw will call `std::terminate`, so `noexcept` should only be applied to functions you are confident will never throw. Operations that involve user-defined callbacks, custom allocators, or complex logic are rarely candidates for this guarantee.

### Strong Guarantee

The strong guarantee, also called the transactional or commit-or-rollback guarantee, promises that if an exception is thrown, the program state is exactly as it was before the operation began. The operation either succeeds completely or has no observable effect. This is the safety level that STL containers provide for most mutating operations, and it is the level most library code should aim for.

```cpp
class DocumentStore {
public:
    // Strong guarantee: if append throws, the store is unchanged.
    void append(const Document& doc) {
        // Work on a copy first.
        auto temp = data_;
        temp.push_back(doc);
        // Only commit once all dangerous work is done.
        data_ = std::move(temp);
    }

private:
    std::vector<Document> data_;
};
```

The key technique for achieving the strong guarantee is the "copy-and-swap" idiom: perform all operations on a copy of the state, then commit with a single `noexcept` swap. If any intermediate step throws, the original state is untouched. This pattern extends beyond containers to any object with a `noexcept` swap operation.

```cpp
class ImageProcessor {
public:
    void apply_filter(const Filter& f) {
        auto result = std::make_unique<Image>(*image_);  // Copy
        result->apply(f);                                 // May throw
        image_.swap(result);                              // noexcept commit
    }

private:
    std::unique_ptr<Image> image_;
};
```

The strong guarantee does not come for free. Copying before modification introduces overhead, especially for large objects. For operations that are rarely expected to fail, the basic guarantee may be a better fit. The choice between strong and basic is a trade-off between safety and performance that should be made per-operation, documented, and justified.

The strong guarantee also interacts with side effects. Consider a function that sends a network message and updates local state. Even if local state is protected by copy-and-swap, the network message has already been sent. True transactional semantics require all observable effects to be revertible, which is often impractical. In such cases, the strong guarantee applies only to internal state, and external side effects must be managed separately.

### Basic Guarantee

The basic guarantee promises that if an exception is thrown, no resources are leaked and all objects remain in a valid (though potentially indeterminate) state. Invariants are preserved, but the specific values may differ from what they were before the operation. This is the minimum acceptable level of exception safety for most production code.

```cpp
class ShoppingCart {
public:
    void add_item(Item item) {
        try {
            total_ += item.price();
            items_.push_back(std::move(item));
        } catch (...) {
            // We must restore invariants.
            // But we don't know what exactly failed, so we
            // cannot easily undo total_ adjustment.
            // Better design: update after push_back.
            throw;
        }
    }

private:
    double total_ = 0.0;
    std::vector<Item> items_;
};
```

    void add_item(Item item) {
        // Capture the price before moving the item
        double price = item.price();
        items_.push_back(std::move(item));
        total_ += price;
    }

The basic guarantee requires careful thought about operation ordering and side effects. Each mutating operation must either succeed fully or leave every object in a consistent state—even if that state is not the one originally intended. In practice, this means:

- Perform non-throwing operations before throwing ones whenever possible.
- Keep invariants simple so that restoration is straightforward.
- Use RAII wrappers to automate cleanup so that resource leaks cannot happen regardless of where exceptions strike.
- Document exactly what state objects may be in after an exception, so callers can make informed decisions.

### No Guarantee

The no-guarantee level means exactly what it sounds like: if an exception is thrown, the program state may be corrupted in arbitrary ways. Resources may leak, invariants may be violated, and objects may be in irrecoverable states. Very few operations in well-written C++ code should be at this level. Destructors that throw, move constructors that fail without proper cleanup, and functions that terminate the program are examples of constructs that effectively provide no guarantee.

The no-guarantee level is sometimes explicitly chosen for performance-critical paths where exception safety would introduce unacceptable overhead. This is a valid choice, but it must be documented and carefully isolated. A function at this level should be called only from contexts where the caller accepts the risk—typically because the caller itself provides no guarantee in that code path, or because it can tolerate full program termination.

```cpp
// WARNING: This function provides no exception safety guarantee.
// Only call from contexts where leaks are acceptable (e.g., process shutdown).
void unsafe_append(Container& c, int value) {
    c.raw_append(value);  // May leak memory if reallocation fails
}
```

Functions at this level should be rare, clearly named (consider prefixing with `unsafe_`), and kept short so the scope of potential corruption is limited.

### Composing Guarantees

Exception safety guarantees compose in specific ways. If you call a function that provides the strong guarantee, and your own function throws after that call, you must consider whether the strong guarantee of the callee is sufficient for your own guarantee. If you are providing the strong guarantee, you must be able to revert or compensate for every callee's effects.

```cpp
class SecureTransaction {
public:
    // Strong guarantee overall
    void transfer(Account& from, Account& to, double amount) {
        auto from_copy = from;
        auto to_copy = to;

        from_copy.withdraw(amount);       // Must provide strong guarantee
        to_copy.deposit(amount);          // Must provide strong guarantee

        // Commit point
        from.swap(from_copy);
        to.swap(to_copy);
    }
};
```

When composing operations, the overall guarantee is typically the weakest guarantee of any operation in the sequence, unless you add compensating logic. A function that calls a basic-guarantee operation cannot provide the strong guarantee without additional work.

### Documenting Guarantees

In the standard library, exception safety guarantees are part of the specification. `std::vector::push_back` provides the strong guarantee unless the element type's copy constructor throws, in which case the guarantee degrades to basic. For your own code, documenting guarantees is equally important. A function's exception safety level is part of its interface contract—as important as its parameter types and return value.

The simplest documentation convention is to state the guarantee in the function's comment or specification:

```cpp
/// Appends a document to the store.
/// @exception std::bad_alloc if memory is exhausted.
/// @guarantee strong - on failure, the store is unchanged.
void append(const Document& doc);
```

More formally, some projects use a system of annotations (`THROWS`, `NOEXCEPT`, `STRONG_GUARANTEE`) in comments or custom attributes. The specific mechanism matters less than the habit of thinking about and documenting guarantees as part of interface design.

### Trade-offs and Guidance

The strongest guarantee is not always the right choice. No-throw guarantees restrict what a function can do—memory allocation itself can throw, so any function that allocates cannot strictly be `noexcept`. Strong guarantees may force expensive copies that slow down common-case performance. Basic guarantees strike a balance but leave callers with less certainty about post-conditions.

A pragmatic approach is:

- Destructors, swap, and move operations should aim for **no-throw**.
- Mutating operations that allocate or perform complex logic should aim for **strong**, using copy-and-swap where practical.
- Performance-critical code that cannot afford copies may use **basic** or **no-guarantee**, but this should be explicitly documented and contained.
- No code should knowingly provide **no guarantee** unless the alternative is unacceptable overhead and the scope of risk is well understood.

The real value of the exception safety guarantee framework is not in the guarantees themselves but in the discipline they enforce. Thinking about guarantees forces you to understand exactly what your code does during failure, which inevitably leads to better, more resilient design. Once this mental model becomes habit, you will find yourself naturally writing code that is exception-safe even without consciously aiming for a specific guarantee level.

## RAII for Exception Safety

Resource Acquisition Is Initialization (RAII) is arguably the single most important C++ idiom for exception safety. It ties resource lifetimes to object lifetimes: resources are acquired during construction and released during destruction. Because destructors run during stack unwinding—the process by which C++ unwinds the call stack when an exception propagates—any resource managed by an RAII object is automatically released when an exception exits the object's scope. This automatic cleanup is the foundation upon which all exception-safe C++ code is built.

Without RAII, exception-safe code degenerates into a maze of `try`/`catch` blocks, manual cleanup, and fragile state management. With RAII, the compiler handles cleanup automatically, eliminating entire classes of resource leaks and state corruption bugs.

### The Problem RAII Solves

Consider what happens when raw resource management meets exceptions:

```cpp
void process_data_bad() {
    int* buffer = new int[1024];
    FILE* file = fopen("data.bin", "rb");
    if (!file) {
        delete[] buffer;           // Manual cleanup 1
        return;
    }

    if (fread(buffer, sizeof(int), 1024, file) != 1024) {
        fclose(file);              // Manual cleanup 2
        delete[] buffer;           // Manual cleanup 3
        return;
    }

    // Processing logic that might throw...
    transform(buffer, 1024);       // If this throws: buffer AND file leak!

    fclose(file);
    delete[] buffer;
}
```

If `transform` throws, neither `file` nor `buffer` is released. The function leaks two resources. Even if `transform` does not throw, every early return path must remember to release both resources, and any future maintainer adding a new code path must do the same. This is fragile, verbose, and error-prone.

### RAII Wrappers for Resources

The RAII solution wraps each resource in an object whose destructor releases it:

```cpp
void process_data_good() {
    std::vector<int> buffer(1024);       // RAII: memory released automatically
    std::unique_ptr<FILE, decltype(&fclose)> file(
        fopen("data.bin", "rb"), fclose); // RAII: file closed automatically

    if (!file) return;                   // buffer cleaned up automatically

    if (fread(buffer.data(), sizeof(int), 1024, file.get()) != 1024)
        return;                          // Both resources cleaned up

    transform(buffer.data(), 1024);      // If throws: both resources cleaned up
}
```

Every resource is now managed by an object whose destructor handles cleanup. The `std::vector` destructor frees the memory. The `unique_ptr` with a custom deleter closes the file. No explicit cleanup is needed on any code path, and the cleanup happens correctly even when exceptions unwind the stack.

This pattern extends to any resource that must be acquired and released: mutexes (`std::lock_guard`), sockets, database connections, GPU command buffers, temporary files, and custom allocations. The principle is always the same: wrap the resource in a class that acquires it in the constructor and releases it in the destructor.

### RAII Provides the Basic Guarantee

RAII alone gives you the basic exception safety guarantee automatically. No matter where an exception is thrown, every fully-constructed RAII object will have its destructor invoked during stack unwinding. This means resources do not leak. The object's invariants may not hold (the object may be in a partially modified state), but the system as a whole will not lose track of any resource.

```cpp
class ScopedFile {
public:
    ScopedFile(const char* filename, const char* mode)
        : file_(fopen(filename, mode)) {
        if (!file_) {
            throw std::runtime_error("Failed to open file");
        }
    }

    ~ScopedFile() noexcept {
        if (file_) fclose(file_);
    }

    // Non-copyable (we own the file handle)
    ScopedFile(const ScopedFile&) = delete;
    ScopedFile& operator=(const ScopedFile&) = delete;

    // Movable (transfer ownership)
    ScopedFile(ScopedFile&& other) noexcept
        : file_(std::exchange(other.file_, nullptr)) {}

    ScopedFile& operator=(ScopedFile&& other) noexcept {
        if (this != &other) {
            if (file_) fclose(file_);
            file_ = std::exchange(other.file_, nullptr);
        }
        return *this;
    }

    void write(const char* data, size_t size) {
        if (fwrite(data, 1, size, file_) != size) {
            throw std::runtime_error("Write failed");
        }
    }

private:
    FILE* file_;
};
```

The `ScopedFile` class above demonstrates the full RAII pattern. The constructor acquires the resource and throws if acquisition fails. The destructor releases it unconditionally. Move operations transfer ownership without duplication. If `write` throws, the `ScopedFile` destructor still runs and closes the file. The basic guarantee is satisfied: no resource leaks, and the file handle is properly closed.

### RAII and the Strong Guarantee

RAII is also a building block for the strong guarantee. The copy-and-swap idiom from the previous section relies on RAII wrappers to manage temporary state. When you create an RAII-managed copy of an object's internal state, that copy becomes self-cleaning—if any subsequent operation throws, the temporary RAII object's destructor releases any resources it held, and the original object's state is untouched because only the swap (which is `noexcept`) touched it.

```cpp
class WidgetManager {
public:
    void add_widget(Widget w) {
        // RAII temporary: if push_back throws, temp is destroyed,
        // but this->widgets_ is unchanged.
        auto temp = widgets_;
        temp.push_back(std::move(w));
        widgets_.swap(temp);
    }

private:
    std::vector<Widget> widgets_;
};
```

Here `temp` is an RAII object—its destructor releases the memory allocated for its vector elements. If any operation throws, `temp` self-destructs without affecting `widgets_`. If everything succeeds, the swap commits the change and `temp`'s destructor releases the *old* state.

### The Scope Guard Pattern

Sometimes you need to perform an action at scope exit that does not fit neatly into a resource wrapper. The scope guard idiom generalizes RAII to any cleanup action, using a lightweight RAII wrapper with a callable:

```cpp
template <typename F>
class ScopeGuard {
public:
    ScopeGuard(F&& f) : func_(std::forward<F>(f)), active_(true) {}
    ~ScopeGuard() noexcept {
        if (active_) func_();
    }
    void dismiss() { active_ = false; }

    ScopeGuard(const ScopeGuard&) = delete;
    ScopeGuard& operator=(const ScopeGuard&) = delete;

private:
    F func_;
    bool active_;
};

void process_with_cleanup() {
    acquire_resource();
    ScopeGuard cleanup([&] { release_resource(); });

    dangerous_operation();    // If throws, cleanup runs
    another_dangerous_op();   // If throws, cleanup runs

    cleanup.dismiss();        // Everything succeeded; suppress cleanup
}
```

The C++ standard library provides `std::unique_ptr` with a custom deleter as a general-purpose scope guard for pointer-like resources. For non-pointer resources, the `ScopeGuard` pattern (or its superior implementation from existing libraries like `gsl::finally` or `folly::ScopeGuard`) gives you arbitrary cleanup that fires automatically on any exit path.

### Transactional RAII: Commit or Rollback

A powerful extension of the scope guard pattern is the transactional RAII wrapper, which applies an action on success and a different action on failure:

```cpp
class Transaction {
public:
    Transaction(Database& db) : db_(db) {
        db_.begin_transaction();
    }

    ~Transaction() noexcept {
        if (std::uncaught_exceptions() > 0) {
            db_.rollback();      // Exception in flight: rollback
        } else {
            if (!committed_) {
                db_.commit();    // Normal exit: commit
            }
        }
    }

    void commit() noexcept {
        committed_ = true;
    }

    Transaction(const Transaction&) = delete;
    Transaction& operator=(const Transaction&) = delete;

private:
    Database& db_;
    bool committed_ = false;
};

void transfer_money(Database& db, int from, int to, double amount) {
    Transaction tx(db);
    db.debit(from, amount);
    db.credit(to, amount);
    // If either operation throws: rollback is automatic
    // If both succeed:
    tx.commit();  // Suppress automatic rollback; function exit commits
}
```

The `Transaction` class detects whether an exception is in flight by checking `std::uncaught_exceptions()` in its destructor. If an exception is active, it rolls back; otherwise, it commits—unless `commit()` was explicitly called to indicate success. This pattern makes transactional semantics composable and exception-safe without requiring explicit `try`/`catch` at every call site.

Note that `std::uncaught_exceptions()` (the count-based version from C++17) is correct here, while the older `std::uncaught_exception()` (the boolean version from C++98) is not. The count-based version correctly handles nested destructor calls during stack unwinding.

### RAII Without Exceptions

Some codebases disable exceptions entirely (via `-fno-exceptions` or equivalent). In such environments, RAII is still valuable for deterministic resource management, but its role in error handling changes. Without exceptions, errors are typically propagated through return values or error codes, and RAII handles the resource cleanup between error checks:

```cpp
class RaiiBuffer {
public:
    RaiiBuffer(size_t size) : data_(new int[size]), size_(size) {}
    ~RaiiBuffer() noexcept { delete[] data_; }

    int* get() { return data_; }
    size_t size() const { return size_; }

    // Move-only
    RaiiBuffer(RaiiBuffer&&) noexcept = default;
    RaiiBuffer& operator=(RaiiBuffer&&) noexcept = default;

private:
    int* data_;
    size_t size_;
};

ErrorCode process_noexcept(const char* filename) {
    RaiiBuffer buffer(1024);
    if (!buffer.get()) return ErrorCode::OutOfMemory;

    RaiiFile file(filename, "rb");
    if (!file.is_open()) return ErrorCode::FileNotFound;

    ErrorCode ec = file.read(buffer.get(), buffer.size());
    if (ec != ErrorCode::Success) return ec;

    return process(buffer.get(), buffer.size());
}
```

Even without exceptions, RAII eliminates manual cleanup and ensures that every code path—including early returns—releases resources correctly. The pattern remains the same: acquire in constructor, release in destructor, move to transfer ownership.

### Limits of RAII for Exception Safety

RAII is not a complete solution for exception safety. It handles resource cleanup automatically, but it does not handle the problem of partially-modified state. Consider:

```cpp
class BankAccount {
public:
    void deposit(double amount) {
        balance_ += amount;       // Modified
        log_.add_entry(amount);   // May throw — balance_ now inconsistent!
    }

private:
    double balance_ = 0.0;
    TransactionLog log_;
};
```

RAII ensures that if `log_.add_entry()` throws, no resources leak. But `balance_` has already been updated, leaving the object in a state where its invariants are violated. RAII does not automatically undo this mutation. Handling partial state changes requires the copy-and-swap idiom (for the strong guarantee) or careful operation ordering (for the basic guarantee).

RAII also does not handle errors that are not exceptions. A function that returns an error code must still check every error return manually. RAII handles cleanup but not error propagation.

### Guidance

RAII should be your default strategy for any resource that must be cleaned up:

- Wrap every resource in an RAII class. `std::unique_ptr` for heap-allocated objects. `std::vector` for dynamic arrays. `std::lock_guard` for mutexes. `std::fstream` for files. Custom RAII wrappers for domain-specific resources.
- Make destructors `noexcept`. A throwing destructor breaks RAII completely—it can cause `std::terminate` during stack unwinding and prevents cleanup of other resources.
- Use move semantics to transfer ownership of RAII resources. Non-copyable, move-only types express exclusive ownership and prevent accidental duplication.
- For one-off cleanup actions, use scope guards (`gsl::finally` or equivalent) rather than writing a full wrapper class.
- Use the Transaction/ScopeGuard pattern with `std::uncaught_exceptions()` for commit-or-rollback semantics.

RAII is not just about exception safety. It is a general-purpose tool for managing any resource whose lifetime must be tied to a scope. The exception safety it provides is a happy consequence of the core design: cleanup is automatic, deterministic, and happens exactly once, on every exit path, whether normal or exceptional. This property is why RAII is considered the foundation of idiomatic C++ resource management.

## Error Code vs Exception Patterns

Exceptions and error codes are the two dominant error-handling mechanisms in C++, and the choice between them is one of the most persistent debates in the C++ community. Each has strengths and weaknesses that make it suitable for different contexts, and idiomatic C++ code often uses both in different layers of the same application. Understanding the trade-offs allows you to choose the right tool for each situation rather than following a single dogma.

### How Exceptions Work

Exceptions transfer control flow from the point where an error is detected to the nearest matching `catch` handler, unwinding the stack in between. During unwinding, all fully-constructed RAII objects in the skipped scopes have their destructors invoked, ensuring automatic cleanup.

```cpp
int read_config(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open config: " + path);
    }

    int value;
    if (!(file >> value)) {
        throw std::runtime_error("Invalid config format");
    }

    return value;
}

void initialize() {
    try {
        int timeout = read_config("app.conf");
        set_timeout(timeout);
    } catch (const std::runtime_error& e) {
        // Handle configuration errors uniformly
        log_error(e.what());
        use_defaults();
    }
}
```

The key properties of exceptions are: they cannot be ignored (if you do not catch an exception, it propagates until it terminates the program), they separate error handling from normal control flow (reducing clutter at call sites), and they carry arbitrary information about the error. The cost is runtime overhead: exceptions add to binary size, can slow down the happy path (even when no exception is thrown, the compiler must generate unwind tables), and make control flow non-local and harder to reason about.

### How Error Codes Work

Error codes represent errors as return values. The caller must explicitly check whether a function succeeded before using its result. Error codes are a value type—they carry no additional context beyond the numeric code unless paired with a separate lookup mechanism.

```cpp
enum class ErrorCode {
    Success = 0,
    FileNotFound,
    InvalidFormat,
    PermissionDenied
};

ErrorCode read_config(const std::string& path, int& out_value) {
    std::ifstream file(path);
    if (!file.is_open()) {
        return ErrorCode::FileNotFound;
    }

    int value;
    if (!(file >> value)) {
        return ErrorCode::InvalidFormat;
    }

    out_value = value;
    return ErrorCode::Success;
}

void initialize() {
    int timeout = 0;
    ErrorCode ec = read_config("app.conf", timeout);
    if (ec == ErrorCode::Success) {
        set_timeout(timeout);
    } else {
        log_error(error_message(ec));
        use_defaults();
    }
}
```

The key properties of error codes are: they are visible in the function signature (unlike exceptions, which are not part of the type system), they have minimal runtime overhead (no unwind tables, no RTTI), and they make every failure path explicit at the call site. The cost is verbosity: every call site must check the return value, and unhandled errors are silently ignored unless you use additional attributes like `[[nodiscard]]`.

### Comparison Matrix

| Aspect | Exceptions | Error Codes |
|---|---|---|
| **Visibility in signature** | Not declared (apart from noexcept) | Explicit in return type |
| **Ignorability** | Cannot be ignored (propagates upward) | Can be silently ignored (unless [[nodiscard]]) |
| **Happy-path performance** | Small overhead (unwind tables) | Minimal (return value check) |
| **Error-path performance** | Slow (stack unwinding, RTTI) | Fast (branch + return) |
| **Information carried** | Arbitrary (what(), nested exceptions) | Single integer/enum |
| **Binary size impact** | Significant (unwind tables, catch blocks) | Negligible |
| **Local vs non-local** | Non-local (jumps to handler) | Local (returned to caller) |
| **RAII interaction** | Natural (destructors run during unwinding) | Manual (branches between cleanup) |
| **Overload/operator compatibility** | Works everywhere | Requires output parameters or wrapper types |

### When to Use Exceptions

Exceptions excel in situations where errors are rare relative to successes, where errors would otherwise need to propagate through many layers of the call stack, and where the error handling logic is far removed from the error detection point.

```cpp
class Parser {
public:
    Document parse(const std::string& input) {
        TokenStream tokens = lex(input);     // May throw
        ASTNode ast = build_ast(tokens);     // May throw
        return optimize(ast);                // May throw
    }
};

// Usage: users only care about success or failure, not intermediate steps.
void load_document(const std::string& path) {
    try {
        Parser parser;
        Document doc = parser.parse(read_file(path));
        render(doc);
    } catch (const ParseError& e) {
        show_error("Failed to parse: " + std::string(e.what()));
    } catch (const std::runtime_error& e) {
        show_error("Unexpected error: " + std::string(e.what()));
    }
}
```

Good candidates for exceptions include:

- **Constructor failures**. Constructors have no return value, so the only way to signal failure is an exception (or a post-construction validity check, which is an anti-pattern).
- **Operator overloads**. Operators cannot return error codes without changing their semantics. `operator+` cannot return both a sum and an error.
- **Deep call stacks**. When an error must propagate through 10 or 20 layers of function calls, threading error codes through every intermediate function creates enormous boilerplate and obscures the normal flow.
- **Failures that should terminate the operation**. When a single problem invalidates an entire sequence of operations, exceptions let you abort at any depth without checking at every step.
- **Framework and library code**. When the caller's error-handling strategy is unknown, exceptions are the most flexible mechanism because the caller decides where to catch them.

### When to Use Error Codes

Error codes excel in situations where errors are frequent or expected, where performance is critical, where binary size matters, and where the caller needs to handle every error immediately.

```cpp
enum class ReadResult {
    Success,
    Timeout,
    ChecksumError,
    DeviceDisconnected
};

ReadResult read_sensor(int16_t& out_value) {
    if (!device_ready()) return ReadResult::DeviceDisconnected;
    if (!wait_for_data(timeout_ms)) return ReadResult::Timeout;

    uint16_t raw = read_register();
    if (!verify_checksum(raw)) return ReadResult::ChecksumError;

    out_value = static_cast<int16_t>(raw & 0xFFF);
    return ReadResult::Success;
}

void poll_sensors() {
    int16_t temperature;
    ReadResult r = read_sensor(temperature);

    switch (r) {
    case ReadResult::Success:
        update_display(temperature);
        break;
    case ReadResult::Timeout:
        // Expected in normal operation; just retry
        break;
    case ReadResult::ChecksumError:
        log_warning("Bad sensor reading");
        break;
    case ReadResult::DeviceDisconnected:
        enter_safe_mode();
        break;
    }
}
```

Good candidates for error codes include:

- **Hot paths and tight loops**. When a function is called millions of times per second, the overhead of exception handling infrastructure (even on the happy path) may be unacceptable.
- **Expected or frequent failures**. Network timeouts, file-not-found conditions, and validation errors happen regularly. Treating them as exceptions conflates "exceptional" with "unexpected."
- **Embedded and constrained environments**. Exception support increases binary size significantly. Many embedded projects disable exceptions entirely.
- **System-level code**. Operating system APIs, driver code, and real-time systems typically use error codes because they need deterministic, bounded execution time.
- **Cross-language boundaries**. C++ exceptions cannot propagate through C frames. Libraries with C interfaces must convert exceptions to error codes at the boundary.

### Hybrid Approaches

Most real-world C++ codebases use both mechanisms, choosing the right tool for each layer:

```cpp
// Low-level I/O: error codes for expected failures
ErrorCode read_sector(int sector_number, std::span<uint8_t> buffer);

// Mid-level logic: still error codes, but enriched
class StorageError {
public:
    ErrorCode code;
    int sector;
    std::string details;
};

StorageErrorOr<std::vector<uint8_t>> read_file_sectors(
    const std::string& path, int start, int count);

// High-level API: exceptions for unexpected failures
class FileSystem {
public:
    std::vector<uint8_t> read_file(const std::string& path) {
        auto result = read_file_sectors(path, 0, 100);
        if (!result) {
            throw FileSystemError(result.error());
        }
        return std::move(result.value());
    }
};
```

This layered approach follows a common pattern: low-level code uses error codes for performance and explicitness; middleware enriches errors with context; high-level code converts errors to exceptions for convenience. Each layer is free to choose the mechanism that best fits its constraints, and the conversion between mechanisms is explicit and controlled.

Another hybrid pattern uses exceptions only for truly exceptional conditions while using error codes for routine validation:

```cpp
class UserInput {
public:
    static Expected<int> parse_age(const std::string& input) {
        // Validation: this is an expected, routine failure
        if (input.empty()) {
            return make_error(ErrorCode::EmptyInput);
        }

        char* end = nullptr;
        long value = std::strtol(input.c_str(), &end, 10);

        if (*end != '\0' || value < 0 || value > 150) {
            return make_error(ErrorCode::InvalidInput);
        }

        return static_cast<int>(value);
    }
};

void process_registration(const std::string& age_input) {
    auto age = UserInput::parse_age(age_input);
    if (!age) {
        // Handle immediately — no need for exception.
        show_error(get_message(age.error()));
        return;
    }

    // But deeper system failures are still exceptions.
    Database::get_instance().store_user_age(*age); // May throw if DB is down
}
```

The key insight is that the choice depends on the *nature of the failure*: expected failures (bad input, missing files, timeouts) that callers should handle immediately are better served by error codes; unexpected failures (out of memory, disk corruption, network partition) that callers often cannot handle locally are better served by exceptions.

### The [[nodiscard]] Discipline

Error codes are only useful if callers actually check them. The `[[nodiscard]]` attribute (C++17) makes the compiler warn (or error) when a return value is discarded, turning unchecked errors into compile-time failures:

```cpp
class [[nodiscard]] ErrorCode {
    // ...
};

[[nodiscard]] ErrorCode critical_operation();

void caller() {
    critical_operation();  // Compiler warning: nodiscard
}
```

This is an essential tool for making error codes safe. Without it, the most common error-code bug is forgetting to check the return value, which silently ignores the failure and continues with stale or uninitialized data.

### Error Handling in the Middle

Some domains require fine-grained control that neither pure exceptions nor pure error codes handle well. The `std::error_code` and `std::error_condition` system from `<system_error>` provides a third path: a lightweight, extensible error representation that can be used either as a return value or wrapped in a `std::system_error` exception.

```cpp
enum class NetworkErrc {
    Timeout = 1,
    ConnectionReset,
    DnsFailure
};

class NetworkErrorCategory : public std::error_category {
public:
    const char* name() const noexcept override {
        return "network";
    }

    std::string message(int ev) const override {
        switch (static_cast<NetworkErrc>(ev)) {
        case NetworkErrc::Timeout: return "connection timed out";
        case NetworkErrc::ConnectionReset: return "connection reset by peer";
        case NetworkErrc::DnsFailure: return "DNS resolution failed";
        default: return "unknown network error";
        }
    }
};

const std::error_category& network_category() {
    static NetworkErrorCategory category;
    return category;
}

std::error_code make_error_code(NetworkErrc e) {
    return {static_cast<int>(e), network_category()};
}

// Now NetworkErrc integrates with the standard error code framework.
// It can be returned, compared, or turned into an exception:
//
//   if (ec == NetworkErrc::Timeout) { ... }
//   throw std::system_error(ec);
```

This system is used by the standard library (for example, `std::filesystem` errors) and is extensible for your own error domains. It provides the efficiency of error codes with the richness of a category-and-message system, and it bridges to exception handling through `std::system_error`.

### Performance Measurement

The performance difference between exceptions and error codes depends heavily on the compiler, optimization level, and the frequency of errors. On modern compilers with optimizations enabled, the happy-path cost of exceptions is roughly 5-20% overhead in code size and a small runtime cost from the presence of unwind tables. The error-path cost of exceptions is orders of magnitude higher than error codes (stack unwinding is expensive), but if errors are rare, this cost is amortized.

Error codes have near-zero overhead on both paths: a branch and a register move. However, the cumulative cost of checking error codes at every call site in a deep call chain can add up, especially when errors are rare and the checks are always predicting success.

A pragmatic approach is to profile before deciding. In most application code, the performance difference is negligible and clarity matters more. In hot loops, embedded systems, or library code with strict latency requirements, error codes (or the `std::expected` pattern from the next section) are usually the right choice.

### Guidance

- **Do not default to one mechanism exclusively**. Use each where it fits.
- **Use exceptions for constructor failures, operator overloads, and deep error propagation** where the caller cannot reasonably handle the error at the point of call.
- **Use error codes for hot paths, frequent failures, embedded targets, and C interfaces**.
- **Use `[[nodiscard]]` on all error-code return types** to prevent silent ignoring.
- **Layer the mechanisms**: low-level code with error codes, high-level code with exceptions, with explicit conversion at the boundary.
- **Document the error contract**. Whether you throw or return an error, callers need to know what errors to expect and how to handle them.
- **Prefer `std::error_code` over raw enums** when you need a rich, extensible error reporting system that can bridge between code and exceptions.

The choice between error codes and exceptions is ultimately a design decision about failure semantics. Error codes say "failure is part of the normal flow; handle it here." Exceptions say "failure is exceptional; delegate it upward." The most robust codebases recognize both as valid tools and deploy each where it communicates the right intent.

## Expected/Result Types

The `std::expected<T, E>` type, standardized in C++23, represents a value that either contains a valid result of type `T` or an error of type `E`. It is a tagged union—a sum type—that makes errors a first-class part of the return type without the runtime overhead of exceptions or the verbosity of output-parameter error codes. The Result type pattern has existed in the functional programming world for decades (Haskell's `Either`, Rust's `Result`) and has been available in C++ through libraries like `tl::expected` and `Boost.Outcome` long before standardization. Its adoption in the standard library reflects a broader shift toward explicit, composable error handling that bridges the gap between error codes and exceptions.

### Basic Usage

At its core, `std::expected<T, E>` is a value that is either a `T` or an `E`. You test it, inspect it, and extract the value or handle the error:

```cpp
#include <expected>
#include <string>
#include <fstream>

enum class ParseError {
    FileNotFound,
    InvalidFormat,
    OutOfMemory
};

std::expected<int, ParseError> read_timeout(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        return std::unexpected(ParseError::FileNotFound);
    }

    int value;
    if (!(file >> value) || value < 0) {
        return std::unexpected(ParseError::InvalidFormat);
    }

    return value;  // Implicitly converts to expected containing the value
}

void configure() {
    auto result = read_timeout("app.conf");

    if (result) {
        set_timeout(*result);  // Access the value
    } else {
        switch (result.error()) {
        case ParseError::FileNotFound:
            log_warning("Config not found, using defaults");
            set_timeout(30);
            break;
        case ParseError::InvalidFormat:
            log_error("Bad config format");
            set_timeout(30);
            break;
        case ParseError::OutOfMemory:
            // Cannot recover — propagate or terminate
            throw std::bad_alloc();
        }
    }
}
```

The `std::unexpected` factory function creates the error representation. Returning a value directly (without `unexpected`) creates the success representation. The interface is intuitive: `operator bool()` or `has_value()` checks for success, `operator*` and `operator->` access the value, and `error()` retrieves the error. Calling `value()` instead of `operator*` throws `std::bad_expected_access<E>` if the expected holds an error, providing a bridge to exception-based code.

### Monadic Operations

The power of `std::expected` goes beyond simple check-and-extract. It supports monadic operations that let you chain computations without explicitly checking for errors at every step. This is where the pattern truly shines compared to raw error codes.

```cpp
using ConfigResult = std::expected<Config, ConfigError>;

ConfigResult load_config(const std::string& path);
ConfigResult validate_config(Config cfg);
ConfigResult apply_defaults(Config cfg);

// Chaining without intermediate checks:
ConfigResult final = load_config("app.conf")
    .and_then(validate_config)
    .and_then(apply_defaults);

// Pattern matching with error transformation:
final
    .and_then(save_config)
    .or_else([](ConfigError e) -> ConfigResult {
        log_error("Config pipeline failed: " + to_string(e));
        return Config{default_values};
    });
```

The key operations are:

- **`and_then`** — If the expected holds a value, apply a function that returns a new expected (possibly of a different type). If it holds an error, propagate the error unchanged. This is the monadic bind operation and is the primary tool for sequential composition.
- **`transform`** — If the expected holds a value, apply a function that returns a plain value (not an expected), wrapping the result in expected. Used for simple value transformations that cannot fail.
- **`or_else`** — If the expected holds an error, invoke a callable to handle or transform it. Used for error recovery or logging.
- **`transform_error`** — Transform the error type while preserving the error state.

These operations make `std::expected` a fully monadic type, enabling composable error-aware pipelines that resemble Rust's `Result` or Haskell's `Either`.

### A Practical Example: Parsing Pipeline

Consider a configuration parser that must validate, transform, and merge settings from multiple sources. With exceptions, the code is clean but the failure paths are invisible in the type signatures. With error codes, every intermediate result must be checked manually. With `expected`, the pipeline is explicit, composable, and self-documenting:

```cpp
struct RawConfig {
    std::string content;
    std::string source_name;
};

struct ValidatedConfig {
    int timeout;
    std::string host;
    int port;
};

enum class ConfigError {
    ReadFailed,
    SyntaxError,
    ValidationError,
    MergeConflict
};

// Each stage returns expected, making failure explicit in the type.

std::expected<RawConfig, ConfigError> read_config_file(
    const std::string& path) {
    std::ifstream file(path);
    if (!file) {
        return std::unexpected(ConfigError::ReadFailed);
    }
    return RawConfig{
        std::string(std::istreambuf_iterator<char>(file),
                    std::istreambuf_iterator<char>()),
        path
    };
}

std::expected<ValidatedConfig, ConfigError> parse_and_validate(
    RawConfig raw) {
    // Parsing logic that may fail...
    if (raw.content.empty()) {
        return std::unexpected(ConfigError::SyntaxError);
    }
    return ValidatedConfig{30, "localhost", 8080};
}

std::expected<ValidatedConfig, ConfigError> merge_configs(
    ValidatedConfig base, ValidatedConfig override) {
    if (base.port == override.port) {
        return std::unexpected(ConfigError::MergeConflict);
    }
    return override;  // Override takes precedence
}

// The pipeline is explicit and composable:

ConfigResult load_and_merge(const std::string& base_path,
                             const std::string& override_path) {
    return read_config_file(base_path)
        .and_then(parse_and_validate)
        .and_then([&](ValidatedConfig base) {
            return read_config_file(override_path)
                .and_then(parse_and_validate)
                .and_then([&](ValidatedConfig over) {
                    return merge_configs(base, over);
                });
        });
}
```

Each function expresses its failure mode in its return type. The pipeline composes these stages without manual error propagation. If any stage fails, the remaining stages are skipped and the error propagates to the caller, who can inspect exactly which error occurred and at which stage.

### Comparison with Other Mechanisms

| Aspect | Exceptions | Error Codes | std::expected |
|---|---|---|---|
| **Signature visibility** | Invisible | Explicit (enum return) | Explicit (return type) |
| **Happy-path overhead** | Small (unwind tables) | Minimal | Minimal (union + bool) |
| **Error-path overhead** | High (unwinding) | Low (branch) | Low (branch) |
| **Ignorability** | Cannot ignore | Can ignore (without [[nodiscard]]) | [[nodiscard]] by convention |
| **Error context** | Arbitrary (what(), nested) | Single enum value | Arbitrary error type E |
| **Composability** | Try/catch nesting | Manual if/else chaining | Monadic (and_then, transform) |
| **Binary size** | Significant | Negligible | Small |
| **Interop with C** | Impossible (needs catch boundary) | Natural | Natural (error code as E) |
| **Standardization** | C++98 | Always | C++23 (previously tl::expected) |

`std::expected` occupies a sweet spot: it has the explicitness and performance profile of error codes, but with the composability and error-context richness that approaches exceptions. It is not a replacement for either—it is a third tool that fits situations where neither exceptions nor raw error codes are ideal.

### Building Custom Result Types

Before C++23, or when you need more control than `std::expected` provides, you can build your own Result type. This is a valuable exercise in understanding the pattern and is still common in C++17 codebases:

```cpp
template <typename T, typename E>
class Result {
public:
    // Construct a success value
    static Result success(T value) {
        return Result(std::move(value));
    }

    // Construct an error value
    static Result error(E err) {
        return Result(std::move(err));
    }

    // Check state
    explicit operator bool() const { return has_value_; }
    bool has_value() const { return has_value_; }

    // Access value (undefined behavior if no value)
    T& value() {
        if (!has_value_) throw ResultError("accessing error as value");
        return storage_.value;
    }

    const T& value() const {
        if (!has_value_) throw ResultError("accessing error as value");
        return storage_.value;
    }

    // Access error (undefined behavior if has value)
    E& error() {
        if (has_value_) throw ResultError("accessing value as error");
        return storage_.error;
    }

    const E& error() const {
        if (has_value_) throw ResultError("accessing value as error");
        return storage_.error;
    }

    // Monadic: and_then
    template <typename F>
    auto and_then(F&& f) -> decltype(f(std::declval<T&>())) {
        if (has_value_) {
            return std::forward<F>(f)(storage_.value);
        }
        return decltype(f(std::declval<T&>()))::error(storage_.error);
    }

    // Monadic: transform
    template <typename F>
    auto transform(F&& f) -> Result<decltype(f(std::declval<T&>())), E> {
        if (has_value_) {
            return Result<decltype(f(std::declval<T&>())), E>::success(
                std::forward<F>(f)(storage_.value));
        }
        return Result<decltype(f(std::declval<T&>())), E>::error(storage_.error);
    }

    // Monadic: or_else
    template <typename F>
    Result or_else(F&& f) {
        if (!has_value_) {
            return std::forward<F>(f)(storage_.error);
        }
        return *this;
    }

private:
    union Storage {
        T value;
        E error;
        Storage() {}
        ~Storage() {}
    };

    Result(T val) : has_value_(true) {
        std::construct_at(&storage_.value, std::move(val));
    }

    Result(E err) : has_value_(false) {
        std::construct_at(&storage_.error, std::move(err));
    }

    ~Result() {
        if (has_value_) {
            storage_.value.~T();
        } else {
            storage_.error.~E();
        }
    }

    Storage storage_;
    bool has_value_;
};
```

This implementation demonstrates the core mechanics: a tagged union, explicit construction through named static methods (to avoid ambiguity between `T` and `E` when both are the same type), and the three key monadic operations. A production implementation would add move semantics, copy semantics when the types allow it, `value_or()`, `emplace()`, and proper `noexcept` annotations—all of which `std::expected` provides out of the box.

### The Outcome Pattern (Boost.Outcome)

Boost.Outcome provides an alternative to `std::expected` that adds a third state for "cancelled" or "unknown" outcomes, and integrates with the `std::error_code` / `std::error_category` system. It is useful when you need to distinguish between failure outcomes that are error-code-representable and those that carry additional context:

```cpp
#include <boost/outcome.hpp>
namespace outcome = BOOST_OUTCOME_V2_NAMESPACE;

outcome::result<int> read_value(const std::string& key) {
    // Can return:
    //   - A success value (int)
    //   - A std::error_code for system-level errors
    //   - A boost::system::error_code for Boost-specific errors
    if (!config_contains(key)) {
        return outcome::failure(
            std::make_error_code(std::errc::invalid_argument));
    }
    return config_get(key);
}
```

Boost.Outcome's `result<T, E>` is similar to `std::expected<T, E>` but predates standardization. Its `outcome<T, EC, EP>` variant adds a third type for "payload" error information, enabling patterns where you have both a portable error code and domain-specific error data.

### Error Type Design

Choosing the error type `E` for your expected is as important as choosing the value type `T`. The error type must communicate enough information for callers to make decisions without being so heavyweight that it discourages error handling.

Common choices for `E`, from simplest to richest:

- **`std::error_code`** — Portable, lightweight, extensible through custom error categories. Preferred for library interfaces that may cross module or ABI boundaries.
- **An enum** — Simple and efficient, but carries no context beyond the code. Good for hot paths and embedded code.
- **A variant of enums with payload** — Use `std::variant<Errc, std::pair<Errc, std::string>>` when some errors need extra context and others do not.
- **A dedicated error struct** — Full control over what information each error carries. Best when different errors carry different data (file path, line number, system errno, etc.).
- **`std::exception_ptr`** — Store a caught exception as the error type. This bridges exception-based and expected-based code, though it incurs the overhead of allocating the exception object.

```cpp
// Lightweight: enum
std::expected<size_t, FileErrc> file_size(const std::string& path);

// Medium: error code with category
std::expected<size_t, std::error_code> file_size(const std::string& path);

// Rich: struct with context
struct FileError {
    std::string path;
    std::error_code ec;
    int line;
};

std::expected<size_t, FileError> file_size(const std::string& path);
```

The rule of thumb is: use the simplest error type that gives callers enough information to make a decision. An enum suffices when the caller only needs to know which of a few known errors occurred. A struct is appropriate when recovery requires context like the file path or the exact byte offset. `std::error_code` balances portability with expressiveness and is the best default for library interfaces.

### Integrating Expected with Existing Code

`std::expected` does not have to be an all-or-nothing choice. It can coexist with both exceptions and error codes, serving as a bridge between them:

```cpp
// Wrap an exception-throwing function into expected
std::expected<Document, ParseError> try_parse(const std::string& input) {
    try {
        return parse_document(input);  // May throw
    } catch (const ParseError& e) {
        return std::unexpected(e);
    } catch (const std::bad_alloc&) {
        return std::unexpected(ParseError::OutOfMemory);
    }
}

// Convert expected to an exception at a boundary
Document parse_or_throw(const std::string& input) {
    auto result = try_parse(input);
    if (!result) {
        throw std::runtime_error("Parse failed: " + to_string(result.error()));
    }
    return std::move(*result);
}

// Or handle the expected directly in hot paths
void process_config() {
    auto doc = try_parse(read_file("config.xml"));
    if (!doc) {
        log_error("Config error: " + to_string(doc.error()));
        return;
    }
    apply_config(*doc);
}
```

This layering is the same principle from the previous section—low-level or performance-critical code uses expected for explicit error handling, while high-level convenience wrappers convert expected failures to exceptions for callers who prefer that style.

### When to Use Expected

`std::expected` is ideal when:

- **Errors are expected but need context**. A file not found is an expected outcome, but the caller may want to know the exact path that failed. An error code alone cannot carry this; an exception has overhead; an expected with a struct or `std::error_code` carries exactly what is needed with minimal cost.
- **The caller must handle the error**. Unlike exceptions, which can propagate unnoticed until they crash the program, expected values must be explicitly examined. This makes them a good fit for API boundaries where errors should not be silently ignored.
- **You need composable error pipelines**. The monadic operations (`and_then`, `transform`, `or_else`) make it natural to chain fallible operations without the nested `if`/`switch` that error codes require.
- **Performance matters**. Expected has near-zero overhead on the happy path and minimal overhead on the error path, making it suitable for hot code where exceptions would be too expensive.
- **You want a single mechanism across language boundaries**. Expected works naturally with C interfaces and FFI: the error type can be an `int` or `std::error_code` that C code understands.

### When Not to Use Expected

Expected is not always the right choice:

- **Deep propagation**. If an error must pass through 20 stack frames before it is handled, threading an expected through every intermediate function pollutes every signature with error-handling machinery. Exceptions handle this case more cleanly.
- **Constructors and operators**. Neither constructors nor operators can return an expected (constructors have no return type; operators have fixed signatures). If construction can fail, you must either throw or use a post-construction validity check.
- **Truly exceptional conditions**. If an error indicates a programming bug (assertion failure, invalid invariant) or an environmental catastrophe (out of memory, stack overflow), exceptions or termination are more appropriate than propagating an expected through the system.
- **Legacy codebases without expected support**. Before C++23, you need a library implementation. Adding a new dependency or writing your own may not be justified for small projects.

### Guidance

- **Use `std::expected` as the default return type for any function that can fail with a recoverable error.** It is explicit, efficient, and composable.
- **Choose the error type carefully.** Prefer `std::error_code` for portable library code, an enum for simple cases, and a struct when you need per-error context.
- **Use monadic operations (`and_then`, `transform`, `or_else`) to compose fallible operations.** They eliminate the boilerplate of manual error checking without hiding the fact that errors can occur.
- **Bridge to exceptions at API boundaries** when callers prefer exception handling, or when the error must propagate across many layers.
- **Do not use `std::expected` for programming errors** (assertions, precondition violations). Use `assert`, `std::terminate`, or exceptions for bugs, not expected.
- **Mark expected-returning functions with `[[nodiscard]]`** to prevent callers from silently discarding errors.

`std::expected` completes a spectrum of error-handling tools in C++. Exceptions handle the unexpected, error codes handle the frequent and simple, and expected handles everything in between—with composability, efficiency, and explicitness that neither of the other mechanisms fully provides. It is the natural evolution of the error-handling story in C++, and its addition to the standard library is one of the most important improvements for writing correct, maintainable C++ code.

## Summary

This chapter explored four complementary approaches to error handling in C++, each occupying a different point in the design space between explicitness, performance, and convenience.

Exception safety guarantees provide the vocabulary and framework for reasoning about correctness under failure. The four levels—nothrow, strong, basic, and none—give you a way to document and compose the behavior of operations when exceptions strike. Thinking in terms of guarantees forces you to understand exactly what your code does during failure, which leads to more resilient design regardless of which error-handling mechanism you choose.

RAII is the foundation that makes exception safety practical. By tying resource lifetimes to object lifetimes, RAII ensures that cleanup happens automatically on every exit path, including during stack unwinding. The scope guard and transactional RAII patterns extend this principle to arbitrary cleanup actions and commit-or-rollback semantics.

The choice between error codes and exceptions is a design decision about failure semantics. Error codes make failure part of the normal flow, requiring explicit handling at every call site. Exceptions treat failure as exceptional, delegating handling to distant callers. Each has strengths and weaknesses, and the most robust codebases use both, layering them appropriately and converting between mechanisms at module boundaries.

`std::expected` bridges the gap between error codes and exceptions, combining the explicitness and performance of error codes with the composability and error-context richness of exceptions. Its monadic operations enable clean, composable error pipelines that are explicit about failure without being verbose. It is the natural evolution of the error-handling idiom in C++, providing a third tool that fits situations where neither exceptions nor raw error codes are ideal.

The common thread across all four sections is that deliberate error handling—documented guarantees, RAII-based cleanup, conscious mechanism choice, and explicit error types—produces code that is more correct, more maintainable, and more resilient than code that treats errors as an afterthought. In C++, error handling is not a separate concern bolted on after the fact; it is woven into the design of every function, every class, and every interface from the beginning.

### Exercises

1. **Exception Safety Audit**: Take a class you have written that manages a resource (file handle, network connection, buffer). Document its exception safety guarantees for each public member function. Identify any places where the guarantee is weaker than you intended and refactor to strengthen it.

2. **RAII Wrapper**: Write a RAII wrapper for a POSIX file descriptor (`int`) that: acquires the fd in the constructor, closes it in the destructor, supports move semantics but not copy, and throws on construction failure. Then use it in a function that reads from the fd, transforms the data, and writes to another fd—all while ensuring no leaks if any step fails.

3. **Error Strategy Comparison**: Implement the same function three ways: once with exceptions, once with error codes, and once with `std::expected`. The function should parse a string of comma-separated integers, returning a `std::vector<int>`. Compare the three implementations on: (a) code clarity, (b) what the function signature communicates, (c) how hard it is for the caller to handle a specific error (e.g., malformed input at position 42), and (d) how hard it is to wrap the function in a retry loop.

4. **Expected Pipeline**: Build a pipeline of three or more operations using `std::expected` and its monadic operations. The pipeline should: (1) read a JSON file, (2) parse it into a struct, (3) validate the fields, and (4) write the validated config to a registry. Use `and_then` for fallible steps and `transform` for infallible transformations. Handle errors with `or_else` at the end of the pipeline.

5. **Hybrid Error Handling**: Design a small library that uses error codes internally (for performance) but exposes a public API that converts those error codes to `std::expected` (for ergonomics). Demonstrate how the conversion happens and discuss the trade-offs: what does the library gain from internal error codes? What do its users gain from the expected-based API?
