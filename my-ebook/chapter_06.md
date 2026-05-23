# Chapter 6: Smart Pointers and Ownership

Smart pointers are the cornerstone of modern C++ resource management. They automate memory management through RAII, ensuring resources are released at the right time regardless of how control flows through your code. This chapter explores idioms for using smart pointers effectively, covering exclusive ownership with `unique_ptr`, shared ownership with `shared_ptr` and `weak_ptr`, custom lifecycle management with deleters, integration with class design, and interoperability with legacy C-style APIs.

Understanding smart pointers is essential because they fundamentally change how you think about resource ownership. Instead of manually managing memory and hoping you release it correctly (which is error-prone), you express ownership semantics in type information, and the type system ensures correct behavior. This makes code safer, clearer, and easier to reason about.

## unique_ptr Patterns

`std::unique_ptr` represents exclusive ownership—one and only one owner is responsible for deleting the object. It's lightweight (typically a single pointer), zero-overhead compared to raw pointers, and the default choice for single-owner scenarios. Understanding its patterns helps you use it effectively across different contexts.

The fundamental pattern is simply replacing raw pointers where you own the pointed-to object:

```cpp
// Before: manual memory management
class Widget {
public:
    Widget() { data_ = new int[100]; }
    ~Widget() { delete[] data_; }
    
private:
    int* data_;
};

// After: unique_ptr handles lifetime
class Widget {
public:
    Widget() : data_(std::make_unique<int[]>(100)) {}
    
private:
    std::unique_ptr<int[]> data_;
};
```

This simple change ensures `data_` is deleted automatically, even if exceptions occur between construction and destruction, or if multiple early returns exist.

`unique_ptr` works with arrays too:

```cpp
std::unique_ptr<double[]> coefficients = std::make_unique<double[]>(256);
// Automatically deletes the array when going out of scope
```

For polymorphism, use `unique_ptr<Base>` pointing to derived objects:

```cpp
std::unique_ptr<Shape> createCircle(double radius) {
    return std::make_unique<Circle>(radius);
}

void drawShape(std::unique_ptr<Shape> shape) {
    shape->draw();
    // shape is destroyed here
}

// Usage:
auto circle = createCircle(5.0);
drawShape(std::move(circle));  // Transfer ownership
```

Moving the `unique_ptr` transfers ownership—the source becomes empty and the destination owns the object. This is the primary way to pass ownership across function boundaries. The caller gives up ownership, and the receiver takes it.

A common pattern is factory functions that return `unique_ptr`:

```cpp
class DocumentParser {
public:
    static std::unique_ptr<DocumentParser> createXMLParser();
    static std::unique_ptr<DocumentParser> createJSONParser();
    static std::unique_ptr<DocumentParser> createBinaryParser();
    
    virtual ~DocumentParser() = default;
    virtual std::unique_ptr<Document> parse(std::istream& input) = 0;
};
```

This pattern ensures the caller receives exclusive ownership of the parser, and when they're done, the parser is automatically destroyed.

When storing `unique_ptr` in containers, prefer `std::vector<std::unique_ptr<T>>` rather than `std::unique_ptr<T[]>`:

```cpp
class Component {
public:
    virtual ~Component() = default;
    virtual void update() = 0;
};

class Entity {
public:
    void addComponent(std::unique_ptr<Component> comp) {
        components_.push_back(std::move(comp));
    }
    
    void updateAll() {
        for (auto& comp : components_) {
            comp->update();
        }
    }
    
private:
    std::vector<std::unique_ptr<Component>> components_;
};
```

This gives you polymorphic containers that own their elements, with each element's lifetime managed individually. Removing an element from the vector automatically destroys that component.

`unique_ptr` also enables the pImpl pattern efficiently:

```cpp
class TextEditor {
public:
    TextEditor();
    ~TextEditor();
    
    void setText(const std::string& text);
    std::string text() const;
    
    // Move-only
    TextEditor(const TextEditor&) = delete;
    TextEditor& operator=(const TextEditor&) = delete;
    TextEditor(TextEditor&&);
    TextEditor& operator=(TextEditor&&);
    
private:
    struct Impl;
    std::unique_ptr<Impl> pImpl_;
};
```

The `unique_ptr` stores the implementation struct, and changing the implementation doesn't require recompiling code that uses `TextEditor`.

One important pattern is converting existing raw pointers to `unique_ptr`:

```cpp
void legacyFunction(Widget* w);  // C API

// Wrap existing pointer
std::unique_ptr<Widget> owned(legacyCreateWidget());
// Or when taking ownership from external source:
Widget* raw = getWidgetFromLegacy();
std::unique_ptr<Widget> owned(raw);
```

However, be careful about double-deletion if the raw pointer is already managed elsewhere. Only wrap pointers you're truly transferring ownership of.

## shared_ptr and weak_ptr Cycles

`std::shared_ptr` implements shared ownership through reference counting. The object is deleted when the last `shared_ptr` owning it is destroyed or reset. This enables scenarios where multiple parts of code need to share an object and none has exclusive ownership.

The basic pattern is straightforward:

```cpp
std::shared_ptr<Resource> createShared() {
    return std::make_shared<Resource>();
}

void process(std::shared_ptr<Resource> res) {
    // res shares ownership
}

auto resource = createShared();
process(resource);  // Reference count: 2
// Reference count: 1 when process returns
// Reference count: 0 when resource goes out of scope, object deleted
```

Copying a `shared_ptr` increments the reference count. Moving doesn't. This makes passing by value (for functions that need ownership) and by `const&` (for functions that just observe) both correct, with different semantics.

The subtle issue with `shared_ptr` is cycles. If objects reference each other through `shared_ptr`, they may never be destroyed because reference counts never reach zero:

```cpp
class Node {
public:
    void setParent(std::shared_ptr<Node> p) { parent_ = p; }
    void addChild(std::shared_ptr<Node> c) { 
        children_.push_back(c); 
    }
    
private:
    std::shared_ptr<Node> parent_;
    std::vector<std::shared_ptr<Node>> children_;
};

auto a = std::make_shared<Node>();
auto b = std::make_shared<Node>();

a->setParent(b);
b->addChild(a);

// Reference counts: a=2 (one for 'a', one in b's children)
//                    b=2 (one for 'b', one in a's parent)
// Neither reaches 0, both leak!
```

The solution is `std::weak_ptr`, which breaks the cycle by providing non-owning references:

```cpp
class Node {
public:
    void setParent(std::weak_ptr<Node> p) { parent_ = p; }
    void addChild(std::shared_ptr<Node> c) { 
        children_.push_back(c); 
    }
    
    void traverseUp() {
        if (auto p = parent_.lock()) {  // Convert to shared_ptr if alive
            // Use parent
        }
    }
    
private:
    std::weak_ptr<Node> parent_;  // Non-owning reference
    std::vector<std::shared_ptr<Node>> children_;
};
```

Now the child doesn't own its parent—it's just observing it. The parent owns its children, so when the parent is destroyed, children are destroyed, breaking the cycle.

`weak_ptr` provides three ways to access the owned object:

```cpp
std::weak_ptr<T> wp;

// Check if the object still exists
if (wp.expired()) { /* object is gone */ }

// Get a shared_ptr to use the object
if (auto sp = wp.lock()) {
    sp->doSomething();  // Safe to use
}

// Get shared_ptr directly (throws if expired)
auto sp = wp.lock();  // May throw std::bad_weak_ptr
// Or:
auto sp2 = wp.shared_from_this();
```

The `lock()` method is the most common pattern—it returns an empty `shared_ptr` if the object has been destroyed, otherwise returns a valid `shared_ptr`.

A common pattern is caching with `weak_ptr` to avoid redundant allocations while allowing cleanup:

```cpp
class Cache {
public:
    std::shared_ptr<Data> get(const std::string& key) {
        auto it = cache_.find(key);
        if (it != cache_.end()) {
            if (auto entry = it->second.lock()) {
                return entry;  // Return cached entry
            }
        }
        
        // Create new entry
        auto entry = std::make_shared<Data>(loadData(key));
        cache_[key] = entry;
        return entry;
    }
    
private:
    std::unordered_map<std::string, std::weak_ptr<Data>> cache_;
    
    Data loadData(const std::string& key);
};
```

When cached `Data` objects are no longer used elsewhere, they're automatically removed from the cache as `weak_ptr`s expire.

The performance characteristics of `shared_ptr` are important to understand. Each `shared_ptr` is typically two pointers (control block plus data pointer), and the control block stores the reference count. Incrementing and decrementing the count requires atomic operations, which have overhead. Creating `shared_ptr` from `make_shared` is more efficient than creating separately because it allocates the object and control block together.

Avoid `shared_ptr` when exclusive ownership suffices. If you can express ownership with `unique_ptr`, do so—it's more efficient and clearer about ownership semantics.

## Custom Deleters and Aliasing Constructors

By default, `unique_ptr` calls `delete` and `shared_ptr` calls `delete` when the reference count reaches zero. But this isn't always correct—sometimes you need custom cleanup logic. Smart pointers support custom deleters that are part of the type, enabling correct resource management for non-memory resources or complex memory scenarios.

Custom deleters work by providing a callable that takes the pointer and performs appropriate cleanup:

```cpp
// Custom deleter for a FILE
struct FileDeleter {
    void operator()(FILE* f) const {
        if (f) fclose(f);
    }
};

using FilePtr = std::unique_ptr<FILE, FileDeleter>;

FilePtr openFile(const char* path, const char* mode) {
    FILE* f = fopen(path, mode);
    if (!f) throw std::runtime_error("Cannot open file");
    return FilePtr(f);  // Uses custom deleter automatically
}

// Usage:
auto file = openFile("data.txt", "r");
// Automatically calls fclose when file goes out of scope
```

The type of the smart pointer includes the deleter: `std::unique_ptr<FILE, FileDeleter>`. This means the deleter is stored in the smart pointer (adding to its size unless empty), and the correct deleter is always used—no chance of mismatching delete and allocation.

Custom deleters work identically for `shared_ptr`:

```cpp
using SharedFile = std::shared_ptr<FILE>;

SharedFile openFile(const char* path, const char* mode) {
    FILE* f = fopen(path, mode);
    if (!f) throw std::runtime_error("Cannot open file");
    
    return SharedFile(f, FileDeleter());  // Pass deleter to constructor
}
```

The key insight is that the deleter is part of the type, ensuring it's always used correctly. You can't accidentally use the wrong deleter because the type system prevents it.

A common use case is managing C-style handles that aren't pointers:

```cpp
struct HandleDeleter {
    void operator()(void* handle) const {
        closeHandle(handle);  // Your API's close function
    }
};

using Handle = std::unique_ptr<void, HandleDeleter>;

Handle openDevice(const char* name) {
    void* h = open(name, O_RDONLY);
    if (h == INVALID_HANDLE) {
        throw std::runtime_error("Cannot open device");
    }
    return Handle(h);
}
```

This wraps any resource with appropriate cleanup, not just memory.

For memory specifically, you might want non-default deallocation:

```cpp
// Custom allocator with custom deallocation
void* allocateAligned(size_t size, size_t alignment);
void deallocateAligned(void* ptr);

struct AlignedDeleter {
    void operator()(void* ptr) const {
        deallocateAligned(ptr);
    }
};

template<typename T>
using AlignedUnique = std::unique_ptr<T[], AlignedDeleter>;

AlignedUnique<double> createAlignedArray(size_t size) {
    void* p = allocateAligned(size * sizeof(double), 64);
    return AlignedUnique<double>(static_cast<double*>(p));
}
```

The aliasing constructor is a specific feature of `shared_ptr` that lets a `shared_ptr` point to a subobject or unrelated memory while sharing ownership of the main object:

```cpp
struct Buffer {
    char data[1024];
    int size;
};

std::shared_ptr<Buffer> buffer = std::make_shared<Buffer>();

// Aliasing: share ownership of 'buffer' but point to 'buffer->data'
std::shared_ptr<char> charData(buffer.get(), buffer->data);

// Now:
// - charData uses buffer's reference count
// - charData points to data within buffer
// - When buffer's ref count reaches 0, the Buffer is deleted
//   (including data), even though charData points there
```

This is useful when you want to pass a pointer to a subobject while maintaining shared ownership of the containing object:

```cpp
class Packet {
public:
    std::shared_ptr<const char> header() const {
        return { shared_from_this(), data_.data() };
    }
    
    std::shared_ptr<const char> payload() const {
        return { shared_from_this(), data_.data() + HEADER_SIZE };
    }
    
private:
    std::array<char, 1024> data_;
};
```

The aliasing constructor is: `shared_ptr(shared_ptr<Y> const& r, T* p)` where `Y` is convertible to `T`. The resulting `shared_ptr` shares ownership with `r` but points to `p`.

Custom deleters and aliasing constructors combine in advanced scenarios like intrusive reference counting or managing resources within larger structures:

```cpp
class ResourcePool {
public:
    struct Header {
        std::atomic<int> refcount;
        // ... other metadata
    };
    
    std::shared_ptr<void> allocate(size_t size) {
        size_t total = sizeof(Header) + size;
        void* memory = ::operator new(total);
        
        auto* header = new (memory) Header{1};
        void* data = static_cast<char*>(memory) + sizeof(Header);
        
        // Custom deleter that decrements refcount instead of delete
        auto deleter = [](void* p) {
            auto* h = static_cast<Header*>(p) - 1;
            if (h->refcount.fetch_sub(1) == 1) {
                h->~Header();
                ::operator delete(h);
            }
        };
        
        return { data, deleter };
    }
};
```

## Smart Pointers as Class Members

Using smart pointers as class members affects class design, particularly regarding special member functions and ownership semantics. The choice between `unique_ptr`, `shared_ptr`, and raw pointers (for non-owning observation) significantly impacts class behavior.

The simplest case is `unique_ptr` member with default behavior:

```cpp
class Widget {
public:
    Widget() = default;
    
    // Compiler-generated: move constructor/assignment, deleted copy
    // This is usually what you want for exclusive ownership
    
private:
    std::unique_ptr<Impl> impl_;
};
```

The compiler generates move operations that transfer ownership of the `unique_ptr`. Copy is deleted because having two copies of exclusive ownership doesn't make sense.

When you need copyability with exclusive ownership, you have options:

```cpp
class CopyableWidget {
public:
    CopyableWidget() : impl_(std::make_unique<Impl>()) {}
    
    // Deep copy: create a new unique_ptr with a copy of the impl
    CopyableWidget(const CopyableWidget& other) 
        : impl_(std::make_unique<Impl>(*other.impl_)) {}
    
    CopyableWidget& operator=(const CopyableWidget& other) {
        if (this != &other) {
            impl_ = std::make_unique<Impl>(*other.impl_);
        }
        return *this;
    }
    
    // Move is still supported
    CopyableWidget(CopyableWidget&&) = default;
    CopyableWidget& operator=(CopyableWidget&&) = default;
    
private:
    std::unique_ptr<Impl> impl_;
};
```

This pattern implements deep copy for exclusive-ownership members—each copy of the object gets its own copy of the implementation.

For shared ownership, use `shared_ptr` members:

```cpp
class SharedWidget {
public:
    void setSubComponent(std::shared_ptr<SubComponent> c) {
        subComponent_ = c;
    }
    
    std::shared_ptr<SubComponent> getComponent() const {
        return subComponent_;
    }
    
private:
    std::shared_ptr<SubComponent> subComponent_;
};
```

Now `SharedWidget` can share its component with other objects. Copying `SharedWidget` increases the reference count. Moving transfers the `shared_ptr`.

A common pattern is a class that can either own a component or reference an external one:

```cpp
class Renderer {
public:
    // Take ownership
    void setOwnedBuffer(std::unique_ptr<Buffer> buffer) {
        buffer_ = std::move(buffer);
        external_ = nullptr;
    }
    
    // Use external reference (non-owning)
    void setExternalBuffer(Buffer* buffer) {
        external_ = buffer;
        buffer_ = nullptr;
    }
    
    Buffer* getBuffer() {
        if (buffer_) return buffer_.get();
        return external_;
    }
    
private:
    std::unique_ptr<Buffer> buffer_;  // Owned
    Buffer* external_ = nullptr;       // Non-owning reference
};
```

The non-owning raw pointer is appropriate here because this class doesn't manage the buffer's lifetime when using external references.

For observing objects that may or may not exist, `weak_ptr` is appropriate:

```cpp
class Subscriber {
public:
    void subscribe(std::weak_ptr<Publisher> pub) {
        publisher_ = pub;
    }
    
    void notify() {
        if (auto p = publisher_.lock()) {
            p->publish(message_);
        }
    }
    
private:
    std::weak_ptr<Publisher> publisher_;
    std::string message_;
};
```

The `weak_ptr` allows observing the publisher without preventing its destruction. If the publisher is destroyed, `lock()` returns empty.

When a class needs to create objects that callers will own, return `unique_ptr` from factory methods:

```cpp
class Factory {
public:
    std::unique_ptr<Product> createProduct(ProductType type) {
        switch (type) {
            case TypeA: return std::make_unique<ProductA>();
            case TypeB: return std::make_unique<ProductB>();
        }
        return nullptr;
    }
};
```

Callers receive ownership and manage the product's lifetime.

When a class needs to expose objects it shares ownership of, return `shared_ptr`:

```cpp
class Document {
public:
    std::shared_ptr<Section> addSection(std::string name) {
        auto section = std::make_shared<Section>(std::move(name));
        sections_.push_back(section);
        return section;  // Caller shares ownership
    }
    
    std::shared_ptr<const Section> getSection(size_t i) const {
        return sections_[i];
    }
    
private:
    std::vector<std::shared_ptr<Section>> sections_;
};
```

The document and callers both own the sections—the reference count ensures sections live as long as anyone needs them.

## Interfacing with Legacy Code

Most C++ code interacts with legacy C APIs, older libraries, or code that predates smart pointers. Bridging between smart pointers and these systems requires careful attention to ownership semantics. The key is clearly defining who owns what and ensuring smart pointers are used appropriately.

The simplest case is wrapping C APIs that return owned pointers:

```cpp
// C API
extern "C" {
    Widget* createWidget(const char* config);
    void destroyWidget(Widget*);
}

// C++ wrapper with unique_ptr
struct WidgetDeleter {
    void operator()(Widget* w) const {
        destroyWidget(w);
    }
};

using ManagedWidget = std::unique_ptr<Widget, WidgetDeleter>;

ManagedWidget createWidget(const char* config) {
    Widget* w = createWidget(config);
    if (!w) throw std::runtime_error("Failed to create widget");
    return ManagedWidget(w);  // Takes ownership
}
```

The custom deleter ensures the correct C function is called for cleanup.

When calling functions that take raw pointers, you can pass the raw pointer from a smart pointer, but be careful about lifetime:

```cpp
void processWidget(Widget* w);

void example() {
    ManagedWidget w = createWidget("config");
    processWidget(w.get());  // Pass raw pointer - doesn't transfer ownership
    
    // w still owns the widget, will destroy it when going out of scope
}
```

This is safe because `processWidget` doesn't store the pointer—if it did, you'd need a different approach.

For callbacks that need to keep the object alive, pass a `shared_ptr`:

```cpp
void registerCallback(Widget* w, void (*callback)(void*), void* data);

void example() {
    auto w = std::make_shared<Widget>();
    registerCallback(w.get(), 
        [](void* data) { 
            // How to keep w alive? 
        }, 
        nullptr);
    
    // If w goes out of scope, the callback has invalid pointer
}
```

The solution requires more careful design—often passing `shared_ptr` itself through the callback data:

```cpp
void callbackThunk(void* data) {
    auto* wrapper = static_cast<std::shared_ptr<Widget>*>(data);
    wrapper->get()->process();
}

void example() {
    auto w = std::make_shared<Widget>();
    auto* data = new std::shared_ptr<Widget>(w);  // Keep alive
    
    registerCallback(w.get(), callbackThunk, data);
    
    // Need mechanism to delete 'data' when w is no longer needed
    // Or use weak_ptr in callback and check before use
}
```

A simpler pattern is weak_ptr-based callbacks:

```cpp
class CallbackRegistry {
public:
    using Callback = std::function<void(Widget&)>;
    
    void registerCallback(std::weak_ptr<Widget> w, Callback cb) {
        callbacks_.push_back({std::move(w), std::move(cb)});
    }
    
    void invokeAll(Widget& w) {
        for (auto& [weak, cb] : callbacks_) {
            if (auto locked = weak.lock()) {
                cb(*locked);
            }
        }
    }
    
private:
    std::vector<std::pair<std::weak_ptr<Widget>, Callback>> callbacks_;
};
```

When interfacing with C libraries that provide arrays, use `unique_ptr` with custom deleters:

```cpp
extern "C" {
    char* allocateString(const char* input);
    void freeString(char*);
}

struct CStringDeleter {
    void operator()(char* s) const { freeString(s); }
};

using CString = std::unique_ptr<char[], CStringDeleter>;

CString createString(const char* input) {
    char* s = allocateString(input);
    return CString(s);
}
```

For const C arrays that shouldn't be deleted, use a no-op deleter:

```cpp
// C function that returns a pointer to constant internal data
extern "C" const char* getBuiltinMessage(int id);

const char* getMessage(int id) {
    return getBuiltinMessage(id);  // Don't delete this!
}

struct NoDelete {
    void operator()(const char*) const {}  // Do nothing
};

std::shared_ptr<const char> getSharedMessage(int id) {
    return { getBuiltinMessage(id), NoDelete{} };
}
```

A common scenario is adapting existing code that uses raw pointers:

```cpp
class LegacyWidget {
public:
    void setOwner(Widget* w) { owner_ = w; }  // Non-owning
    Widget* getOwner() const { return owner_; }
    
private:
    Widget* owner_ = nullptr;  // Raw for non-owning relationship
};
```

This is appropriate for non-owning relationships where the pointer's lifetime is managed elsewhere.

The key principles for legacy interface bridging are: clearly define ownership (who deletes), use custom deleters for non-delete cleanup, prefer `unique_ptr` for exclusive ownership from C APIs, use `shared_ptr` when sharing ownership, and use raw pointers for non-owning observation.

## Summary

This chapter explored five idioms for smart pointer usage in modern C++. `unique_ptr` patterns cover the fundamental exclusive ownership case—simple ownership transfer, factory functions, polymorphic objects, and container storage. `shared_ptr` and `weak_ptr` patterns address shared ownership, with emphasis on avoiding reference counting cycles through `weak_ptr` for non-owning back-references. Custom deleters and aliasing constructors extend smart pointers beyond simple memory management, supporting files, handles, and subobject references. Smart pointers as class members affect copy/move semantics and ownership design decisions. Legacy code interfacing shows how to bridge between C APIs and modern smart pointer ownership.

Smart pointers fundamentally change resource management from manual to type-based. By expressing ownership in types, you let the compiler enforce correct behavior. The key is choosing the right smart pointer for the ownership model: `unique_ptr` for exclusive ownership, `shared_ptr` for shared ownership, and `weak_ptr` for non-owning references to shared objects.

### Exercises

1. **Ownership Analysis**: Take a codebase you know and identify every raw pointer. Classify each as owning or non-owning, and convert owning pointers to appropriate smart pointers. What challenges did you encounter?

2. **Cycle Breaking**: Design a scene graph (parent-child relationships) that naturally creates cycles and show how `weak_ptr` breaks them. Implement both parent and child with proper traversal methods.

3. **Custom Deleter Design**: Create a wrapper for a graphics API (like OpenGL or DirectX) where resources must be released in a specific way. Show how custom deleters ensure correct cleanup.

4. **Class Design**: Design a class that holds both owned and non-owned references to other objects. Implement copy and move constructors appropriately, explaining your ownership design decisions.

5. **Legacy Bridge**: Write a C++ wrapper around a C library that manages database connections. Ensure the wrapper is exception-safe and demonstrates proper deleter usage.