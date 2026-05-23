# Chapter 23: Structural Patterns

Structural patterns are about assembling objects and classes into larger structures while keeping those structures flexible and efficient. Where creational patterns abstract the instantiation process, structural patterns abstract the composition itself—they answer the question "how do I arrange my objects so that the system is greater than the sum of its parts?"

The four patterns in this chapter—Adapter, Facade, Flyweight, and Decorator—each solve a distinct composition problem. The Adapter reconciles incompatible interfaces. The Facade simplifies access to a complex subsystem. The Flyweight shares state to conserve memory across many fine-grained objects. The Decorator attaches additional responsibilities to an object without subclassing.

What ties them together is a shared insight about indirection: by inserting a layer of abstraction between a client and its dependencies, you gain the freedom to change how those dependencies are structured, accessed, or shared without perturbing the client. In C++, the choice between compile-time and runtime indirection is often as important as the pattern itself.

## Adapter and Wrapper Idioms

The Adapter pattern converts the interface of a class into another interface that a client expects. It is the software equivalent of a travel power adapter — you have a device with a European plug (your existing class) and a US wall socket (your target interface). The adapter sits in between, making the electrical and physical translation invisible to both sides.

The motivation arises whenever you need to integrate a component whose interface does not match the interface your code already depends on. This happens constantly in practice: you switch logging libraries but your code calls `log_info()`, while the new library uses `write_message()`. You adopt a third-party geometry library, but its `Vector3D` class does not support the operators your template code expects. You inherit a codebase that uses a legacy `FILE*`-based API, but your new modules consume `std::string_view` through a `Stream` abstract class.

In every case, you have two choices: modify the existing class to match the expected interface (often impossible — it is in a third-party library or used by other code), or write an adapter that translates between them. The adapter is the less invasive option.

### Class Adapter (Inheritance-Based)

A class adapter uses multiple inheritance to adapt one interface to another. The adapter inherits the interface the client expects *and* the implementation being adapted, then overrides the interface methods to delegate to the implementation.

```cpp
// The interface our code expects.
class Logger {
public:
    virtual ~Logger() = default;
    virtual void log_info(const std::string& msg) = 0;
    virtual void log_error(const std::string& msg) = 0;
};

// A third-party logging library with a different interface.
class ThirdPartyLogger {
public:
    void write_message(int level, const char* text) {
        // level 1 = info, level 2 = error
    }
};

// Class adapter: inherits both the target interface and the adaptee.
class LoggerAdapter : public Logger, private ThirdPartyLogger {
public:
    void log_info(const std::string& msg) override {
        write_message(1, msg.c_str());
    }
    void log_error(const std::string& msg) override {
        write_message(2, msg.c_str());
    }
};
```

The adapter inherits the adaptee privately — the adapter's clients should not know that a `ThirdPartyLogger` exists behind the scenes. The `log_info` and `log_error` functions are thin wrappers that translate the interface call to the adaptee's equivalent.

The class adapter has the advantage that it can override adaptee behavior if needed (since it inherits from the adaptee), and it does not require a separate adaptee object — the adaptee's state lives in the adapter itself. Its drawback is that it commits to a specific adaptee class at compile time — you cannot adapt a family of related classes without writing separate adapters for each.

### Object Adapter (Composition-Based)

The object adapter uses composition instead of inheritance: the adapter holds a pointer or reference to an instance of the adaptee and delegates to it.

```cpp
class LoggerAdapter : public Logger {
public:
    explicit LoggerAdapter(ThirdPartyLogger& logger)
        : logger_(&logger) {}

    void log_info(const std::string& msg) override {
        logger_->write_message(1, msg.c_str());
    }
    void log_error(const std::string& msg) override {
        logger_->write_message(2, msg.c_str());
    }

private:
    ThirdPartyLogger* logger_;  // Adapted object
};
```

The adapter now works with *any* instance of `ThirdPartyLogger` — or a subclass of it — because the adaptee is passed in at runtime. This is more flexible than the class adapter when the adaptee configuration varies (different log files, different backends) or when the adaptee is an interface with multiple implementations.

The trade-off is that the adapter now manages an indirection through a pointer, which may affect inlining and optimization. In practice, the virtual dispatch on `log_info` already prevents inlining, so the extra pointer indirection rarely matters. The composition-based adapter is the default choice in modern C++; reach for the class adapter only when you need to override adaptee behavior or when the adaptee is itself a template parameter whose concrete type is resolved at compile time.

### Template Adapter (Compile-Time)

When the adaptation cost must be zero at runtime and the adaptee type is known at compile time, a template adapter avoids virtual dispatch entirely:

```cpp
template <typename Adaptee>
class LoggerAdapter : public Logger {
public:
    explicit LoggerAdapter(Adaptee& logger)
        : logger_(&logger) {}

    void log_info(const std::string& msg) override {
        logger_->write_message(1, msg.c_str());
    }
    void log_error(const std::string& msg) override {
        logger_->write_message(2, msg.c_str());
    }

private:
    Adaptee* logger_;
};
```

The template parameter `Adaptee` can be any class that provides `write_message(int, const char*)`. The adapter itself still uses virtual dispatch through the `Logger` interface (so clients can use it polymorphically), but the delegation to the adaptee is statically resolved and fully inlinable.

Going further, if the client code itself is templated on the logger type, you can eliminate virtual dispatch entirely:

```cpp
template <typename LoggerImpl>
class Client {
    LoggerImpl& logger_;
public:
    explicit Client(LoggerImpl& log) : logger_(log) {}
    void do_work() {
        logger_.log_info("Working...");
    }
};
```

This is policy-based design applied to adaptation. The client does not care whether `LoggerImpl` is the original `ThirdPartyLogger` or a wrapper — the interface is duck-typed at compile time. The cost is that `Client` is now a template, which must be defined in a header and may increase compilation time.

### Wrapper Idioms Beyond Adapter

The Adapter pattern is one specific kind of wrapper. In C++ practice, "wrapper" is a broader category that includes several related idioms with different intents:

**Type-safe wrappers** prevent mixing up semantically distinct values that share the same underlying type. A common C++ idiom wraps a primitive type in a lightweight struct:

```cpp
struct UserId { int value; };
struct OrderId { int value; };

void process_order(UserId user, OrderId order);
// process_order(OrderId{42}, UserId{7});  // Compile error: wrong order
```

The wrapper struct adds zero overhead (the struct is the same size as its single `int` member) but prevents the accidental swapping of arguments that would occur with bare `int` parameters. The trade-off is verbosity — every value must be explicitly wrapped and unwrapped.

**Ownership wrappers** manage resource lifetime through RAII. Every smart pointer is a wrapper: it holds a raw pointer but exposes a pointer-like interface while managing destruction. The wrapper pattern here is so fundamental that C++ programmers rarely think of it as "adapter," but that is exactly what it is — `std::unique_ptr` wraps a raw pointer and a deleter into a type that behaves like a pointer with automatic lifetime.

**Protocol wrappers** adapt an object's external protocol (the sequence of calls and preconditions) without changing its interface. Consider a connection object that requires explicit `connect()` before use and `disconnect()` after. A wrapper can make these calls automatic:

```cpp
class AutoConnect {
    Connection conn_;
    bool connected_ = false;
public:
    AutoConnect() = default;
    ~AutoConnect() {
        if (connected_) { conn_.disconnect(); }
    }
    // Prevent accidental double-disconnection via copying
    AutoConnect(const AutoConnect&) = delete;
    AutoConnect& operator=(const AutoConnect&) = delete;
    
    AutoConnect(AutoConnect&& other) noexcept 
        : conn_(std::move(other.conn_)), connected_(std::exchange(other.connected_, false)) {}
    
    AutoConnect& operator=(AutoConnect&& other) noexcept {
        if (this != &other) {
            if (connected_) conn_.disconnect();
            conn_ = std::move(other.conn_);
            connected_ = std::exchange(other.connected_, false);
        }
        return *this;
    }

    void send(const Message& msg) {
        if (!connected_) { conn_.connect(); connected_ = true; }
        conn_.send(msg);
    }
};
```

The wrapper does not change the `send` signature — it changes the precondition. This is a structural change without an interface change, and it is one of the most powerful uses of wrapping in C++.

### Trade-offs

Adapters and wrappers always introduce a layer of indirection. The question is what you gain in exchange:

- **Decoupling.** The client depends on an interface, not an implementation. You can swap implementations without changing client code.
- **Reusability.** Existing classes can be plugged into new contexts without modification.
- **Testability.** An adapter can be replaced with a mock in tests, isolating the unit under test.

The costs are:
- **Code volume.** Every adaptation requires its own forwarding code. Template adapters reduce the per-adaptee boilerplate but increase compilation time.
- **Abstraction leakage.** If the adapter cannot fully hide the adaptee's semantics — for example, if the adaptee throws exceptions with different meaning — callers may need to understand both interfaces.
- **Performance.** Runtime adapters add a virtual call and possibly a pointer indirection. For most code this is noise; for inner-loop code it may matter.

The guideline: adapt when modification is impossible or unwise. Do not adapt when you can refactor the client and the adaptee to share a common interface — that is the simpler and more maintainable solution.

### Exercises

1. Given a `LegacyRectangle` with `int getX(), int getY(), int getW(), int getH()` and a target interface `Shape` with `int left(), int top(), int width(), int height()`, implement both a class adapter and an object adapter. What changes if `LegacyRectangle` uses unsigned coordinates?

2. Write a template adapter that wraps any class providing `void send(const char*, size_t)` into an interface with `void write(std::span<const char>)`. The adapter should be zero-overhead when the adaptee's `send` is inlinable.

3. A type-safe wrapper `struct Meters { double v; }` and `struct Feet { double v; }` can prevent unit confusion. Implement conversion operators that make `Meters` implicitly convertible to `Feet` (and vice versa) and discuss whether implicit conversion in a type-safe wrapper violates the principle of least surprise.

## Facade Patterns for Libraries

A facade provides a unified, simplified interface to a larger body of code — typically a subsystem consisting of many classes with complex interdependencies. The pattern does not add new functionality; it reduces the surface area that a client needs to understand.

The motivation is straightforward. A video encoding library might expose classes for containers (`MkvContainer`, `Mp4Container`), codecs (`H264Codec`, `AacCodec`), multiplexers, demultiplexers, audio resamplers, subtitle renderers, and parameter profiles. Using the library correctly requires understanding the relationships among these classes: which codecs pair with which containers, what initialization order is required, how to handle resource cleanup on failure. A facade wraps this complexity behind a single function call — `encode(input, output, settings)` — and manages the subsystem interactions internally.

```cpp
// Facade for a video encoding subsystem.
class VideoEncoder {
public:
    void encode(const std::filesystem::path& input,
                const std::filesystem::path& output,
                const EncodeSettings& settings) {
        auto source = Demuxer::open(input);
        if (!source) return; // Handle error

        auto stream = source->best_video_stream();
        if (!stream) return;

        auto decoder = CodecFactory::create(stream->codec_id());
        if (!decoder) return;
        decoder->open(stream);

        auto encoder = CodecFactory::create(settings.codec);
        encoder->configure(settings.bitrate, settings.fps);
        auto muxer = Muxer::create(output, encoder->format());

        Packet pkt;
        Frame frame;
        while (decoder->read(pkt)) {
            decoder->decode(pkt, frame);
            encoder->encode(frame);
            muxer->write(encoder->packet());
        }
        muxer->finalize();
    }
};
```

The client of `VideoEncoder::encode` never touches a `Demuxer`, `CodecFactory`, `Packet`, `Frame`, or `Muxer`. The facade encapsulates the entire encoding pipeline: the correct sequence of operations, the error handling at each stage, and the resource cleanup.

### What a Facade Is Not

A facade is often confused with two related patterns. The distinction matters for design:

**A facade is not a mediator.** The Mediator pattern coordinates interactions among a set of objects — it provides a hub through which communication flows. A facade does not coordinate interactions; it provides a single entry point to a subsystem and delegates calls to the appropriate subsystem objects in the correct order. The facade's objects typically do not talk through the facade; they talk to each other as before, and the facade orchestrates them.

**A facade is not a wrapper.** A wrapper (or adapter) transforms one interface into another. A facade transforms *many* interfaces into *one* — it is a megaphone that says "you only need to know one function, trust me, I will handle the rest." The wrapper says "I speak your language even though the thing behind me speaks a different one."

### Subsystem Encapsulation with RAII

In C++, a well-designed facade handles resource management internally using RAII, so the client does not need to track subsystem state. The `VideoEncoder::encode` function above creates local objects (decoder, encoder, muxer), and their destructors clean up automatically — even if an exception is thrown mid-pipeline.

When the facade itself holds state — for example, when you want to reuse an encoding session across multiple operations — the facade class should own the subsystem objects and manage their lifetimes through RAII members:

```cpp
class VideoEncoderSession {
public:
    VideoEncoderSession(const std::filesystem::path& input,
                        const EncodeSettings& settings)
        : source_(Demuxer::open(input))
    {
        auto stream = source_->best_video_stream();
        decoder_ = CodecFactory::create(stream->codec_id());
        decoder_->open(stream);

        encoder_ = CodecFactory::create(settings.codec);
        encoder_->configure(settings.bitrate, settings.fps);
        muxer_ = Muxer::create(settings.output, encoder_->format());
    }

    void encode_next_frame() {
        Packet pkt;
        Frame frame;
        if (decoder_->read(pkt)) {
            decoder_->decode(pkt, frame);
            encoder_->encode(frame);
            muxer_->write(encoder_->packet());
        }
    }

    void finalize() { muxer_->finalize(); }

private:
    std::unique_ptr<Demuxer>  source_;
    std::unique_ptr<Decoder>  decoder_;
    std::unique_ptr<Encoder>  encoder_;
    std::unique_ptr<Muxer>    muxer_;
};
```

The constructor is the initialization sequence for the subsystem. If any step fails — say `CodecFactory::create` returns `nullptr` — the partially constructed session is destructed, and the destructors of members already initialized run automatically. The client sees a single object with simple methods.

### Compile-Time Facade with Templates

When the subsystem is a collection of types known at compile time, a template facade can generate the simplified interface automatically. Consider a configuration system with multiple backends (environment variables, JSON files, command-line arguments):

```cpp
// Backends
struct EnvConfig { std::string get(const std::string& key); };
struct JsonConfig { std::string get(const std::string& key); };
struct CmdLineConfig { std::string get(const std::string& key); };

// Compile-time facade — tries each backend in order.
template <typename... Backends>
class ConfigFacade {
    std::tuple<Backends...> backends_;
public:
    ConfigFacade(Backends... bs) : backends_(std::move(bs)...) {}

    std::string get(const std::string& key) const {
        return get_impl(key, std::index_sequence_for<Backends...>{});
    }

private:
    template <size_t... Is>
    std::string get_impl(const std::string& key,
                         std::index_sequence<Is...>) const {
        std::string result;
        // Try each backend; return first found.
        ((result = std::get<Is>(backends_).get(key),
          !result.empty()) || ...);
        return result;
    }
};

// Usage — facade unifies three backends into one interface.
auto config = ConfigFacade{
    EnvConfig{},
    JsonConfig{"config.json"},
    CmdLineConfig{argc, argv}
};
auto timeout = config.get("timeout");
```

The fold expression `( ... || ... )` short-circuits on the first backend that returns a non-empty result. The client sees a single `get()` call; the order-of-precedence logic is hidden inside the facade.

Compile-time facades are zero-overhead — the template is fully resolved at compile time, and the fold expression inlines to a simple chain of conditionals. The trade-off is that the set of backends is fixed at compile time, and any error messages from template instantiation are opaque to the user of the facade.

### Module Facade (C++20)

C++20 modules provide a new way to implement facades at the source level. A module can export only a few names while keeping the subsystem's internal classes and functions private:

```cpp
// video_encoder.cppm (C++20 module)
export module video_encoder;

export class VideoEncoder {
public:
    void encode(std::filesystem::path input,
                std::filesystem::path output,
                EncodeSettings settings);
};

// Demuxer, CodecFactory, Muxer, etc. are NOT exported.
// They are reachable only inside the module.
class Demuxer { /* ... */ };
```

The module serves as a source-level facade: the compiler enforces that clients cannot depend on the internal classes. This is stronger than a namespace-based facade (where internal classes remain visible, just discouraged) and avoids the preprocessor-based trick of hiding headers inside a detail directory.

The module facade does not change the runtime structure — it still uses the same object composition as a traditional facade — but it enforces the separation at compile time, preventing clients from forming accidental dependencies on the subsystem's internals.

### When to Facade

Build a facade when:
- The subsystem's learning curve is a barrier to adoption. A facade provides a "quick start" API that covers 80% of use cases.
- The subsystem's internal dependencies make it fragile. A facade captures the correct usage pattern in one place, so clients do not need to replicate the delicate initialization sequence.
- You control the subsystem and want to reserve the right to refactor it without breaking clients. The facade is the public API; everything behind it is implementation detail.
- The subsystem has multiple alternate configurations. A facade with parameters is simpler than exposing the configuration objects directly.

Do not build a facade when:
- The subsystem is already simple. Adding a facade is extra code with no benefit.
- Clients need direct access to subsystem internals for advanced use cases. A facade that hides everything frustrates power users. Consider providing both a high-level facade and a lower-level API.
- The facade would duplicate the interface of a single class. If the subsystem *is* one class, the facade is just another name for the same thing.

### Exercises

1. Design a facade for a database library that exposes classes `Connection`, `Statement`, `ResultSet`, `Transaction`, and `ConnectionPool`. The facade should provide a single function `query(connection_info, sql)` that returns a vector of rows and handles connection pooling internally. Show both the facade interface and how it uses the subsystem classes.

2. Compare a facade implemented with virtual functions (runtime polymorphism) against a template facade using fold expressions. Write both versions for a logging subsystem that routes messages to a file, the console, and a remote server. Discuss the trade-offs for a case where the set of backends is known at compile time vs. configurable at runtime.

3. Identify a subsystem in a codebase you know that would benefit from a facade. Write the facade interface without implementing it. What patterns in the subsystem does the facade hide? What is the risk that a client will need to bypass the facade?

## Flyweight for Memory Optimization

The Flyweight pattern shares data across many fine-grained objects to reduce memory usage. It is relevant when you have a large number of similar objects and the memory cost of storing all of their state individually is prohibitive.

The core insight is that object state can be split into two categories: *intrinsic* state that is shared across many objects and never changes, and *extrinsic* state that is context-dependent and must be supplied by the client. A flyweight stores only intrinsic state; the client supplies extrinsic state when it invokes operations on the flyweight.

A classic example is a text renderer. In a document with thousands of character glyphs, storing position, font, size, color, and glyph outline for every character is wasteful. The intrinsic state — the glyph outline, metrics, and rendering data — is shared among all instances of the same character in the same font. The extrinsic state — the position on the page — is context-dependent and is computed on the fly during rendering.

```cpp
// Intrinsic state: shared across all instances of the same character.
class Glyph {
public:
    Glyph(std::string_view face, int size, char32_t codepoint,
          const std::vector<uint8_t>& bitmap)
        : face_(face), size_(size), codepoint_(codepoint),
          bitmap_(bitmap) {}

    void render(int x, int y, Canvas& canvas) const {
        canvas.blit(bitmap_, x, y);
    }

private:
    std::string face_;
    int size_;
    char32_t codepoint_;
    std::vector<uint8_t> bitmap_;  // Large — the rendered glyph
};

// Flyweight factory — ensures shared Glyph instances.
class GlyphFactory {
public:
    const Glyph& get_glyph(std::string_view face, int size,
                           char32_t codepoint) {
        auto key = std::tuple(face, size, codepoint);
        auto it = glyphs_.find(key);
        if (it == glyphs_.end()) {
            auto bitmap = render_glyph(face, size, codepoint);
            it = glyphs_.emplace(key,
                Glyph(face, size, codepoint, bitmap)).first;
        }
        return it->second;
    }

private:
    std::map<std::tuple<std::string, int, char32_t>, Glyph, std::less<>> glyphs_;
};
```

The `Glyph` objects are shared. A page with 5000 'e' characters in 12pt Times New Roman uses only one `Glyph` instance for all of them. The extrinsic state — the position of each character on the page — is not stored in the `Glyph` at all. The renderer either stores it separately (e.g., in a `std::vector<Position>`) or computes it on the fly from the document's layout.

```cpp
// The document does not own Glyph objects — it references them.
class Character {
public:
    const Glyph* glyph;
    int x, y;  // Extrinsic state
};

class Document {
    std::vector<Character> characters_;
    GlyphFactory glyphs_;
public:
    void render(Canvas& canvas) const {
        for (auto& ch : characters_) {
            ch.glyph->render(ch.x, ch.y, canvas);
        }
    }
};
```

### Flyweight vs. Immutable Sharing

C++ programmers sometimes conflate the Flyweight pattern with simply sharing immutable objects. The two concepts are related but distinct. Immutable sharing — like `std::string` with copy-on-write or interning — is an implementation detail that can be transparent to the user. The Flyweight pattern is an *explicit* split between intrinsic and extrinsic state that affects the design of the objects themselves.

In the text renderer, the `Glyph` does not just happen to be shared — it is *designed* to be shared. The factory is a deliberate API, and the client is aware that extrinsic state (the position) must be managed separately. The design decision to separate intrinsic and extrinsic state is the pattern, not the sharing mechanism itself.

### Flyweight with String Interning

A concrete example that many C++ programmers encounter is string interning. In applications that process large amounts of repetitive textual data (XML parsing, log analysis, RDF stores), storing every string value separately wastes memory. A string interning pool deduplicates identical strings:

```cpp
class StringPool {
public:
    std::string_view intern(std::string_view str) {
        auto [it, inserted] = pool_.emplace(str);
        return *it;
    }

private:
    std::unordered_set<std::string> pool_;
};
```

Every call to `intern` with the same string returns a `string_view` pointing to the same storage. The memory savings come from the fact that the pool stores each unique string once. The cost is the hash lookup on every intern operation and the fact that interned strings are never deallocated (unless the pool is destroyed).

This is a pure intrinsic-state flyweight: the entire string value is shared. There is no extrinsic state because the string's value is used directly. A richer variant might separate the string value (intrinsic) from its metadata like encoding or language tag (extrinsic).

### Intrusive Flyweight with `shared_ptr`

When the flyweight objects have lifetimes that extend beyond a single pool and may be shared across multiple containers, `std::shared_ptr` gives automatic reference counting and lifetime management:

```cpp
class Texture {
    std::vector<uint8_t> pixels_;
    int width_, height_;
public:
    Texture(int w, int h, std::span<const uint8_t> data);
    void bind() const;
};

class TextureCache {
public:
    std::shared_ptr<const Texture> load(const std::string& path) {
        std::lock_guard lock(mutex_);
        auto it = cache_.find(path);
        if (it != cache_.end()) {
            return it->second;  // Return existing flyweight.
        }
        auto tex = std::make_shared<Texture>(
            load_texture_from_disk(path));
        cache_.emplace(path, tex);
        return tex;
    }

private:
    std::mutex mutex_;
    std::unordered_map<std::string,
        std::shared_ptr<const Texture>> cache_;
};
```

The `shared_ptr` ensures that the texture stays alive as long as any object references it. When the last reference drops, the texture is automatically deallocated. The cache itself holds a reference for each entry, so textures persist as long as they are in the cache. The const-qualified `shared_ptr<const Texture>` ensures that flyweight objects are immutable — a crucial invariant for safe sharing.

The trade-off is the atomic reference counting overhead on every copy of the `shared_ptr`. In performance-critical paths, consider `std::shared_ptr` with `std::memory_order_relaxed` where safe, or use a non-owning observer pattern (like a raw pointer or index) with explicit lifetime management.

### Extrinsic State Strategies

The flyweight pattern shifts work from memory (storing state in objects) to computation (looking up state or passing it at call time). The extrinsic state must be supplied by the client, and how you supply it is a design decision with its own trade-offs:

**Pass as function parameters.** The renderer passes `x, y` coordinates each time it calls `render`. This is the simplest approach but can become unwieldy when the extrinsic state has many fields.

**Pass as a context object.** Wrap extrinsic state in a struct and pass it around. This groups related extrinsic data and makes it easier to add fields without changing every call site:

```cpp
struct RenderContext {
    int x, y;
    float opacity;
    Color tint;
};

void render(const RenderContext& ctx, Canvas& canvas) const;
```

**Store in a separate array.** The document stores positions in a `std::vector<Position>` parallel to the character sequence. This is cache-friendly (the renderer iterates positions sequentially) and separates the extrinsic state from the flyweight reference.

**Compute from context.** When the extrinsic state can be derived from context — for example, the position of a character in a monospace font can be computed from its index and line width — no storage is needed at all. The computation replaces the storage.

The choice depends on how the extrinsic state is produced and consumed. If it is produced once and consumed many times, storing it is worthwhile. If it is produced at the point of use (like character positions during layout), computing it may be cheaper than storing and loading it.

### Flyweight in the C++ Standard Library

The Flyweight pattern appears in several places in the standard library, though it is not always recognized by that name:

- **`std::type_info`** objects returned by `typeid` are singletons per type. The standard requires that `typeid(T) == typeid(T)` for each `T`, and implementations typically ensure this through a flyweight registry.

- **String literals** are flyweights by nature — the same string literal in multiple translation units typically refers to the same storage (though the standard does not guarantee this).

- **`std::locale` facets** are often shared across locale instances. The `std::locale` implementation uses a reference-counted pointer to a locale implementation object that contains shared facets.

- **`std::monostate`** for variant is a degenerate flyweight: zero intrinsic state, shared by all instances.

### When to Flyweight

The pattern is worth the complexity when:
- The number of objects is very large (tens of thousands or more) and each object stores data that is duplicated across instances.
- The intrinsic state dominates the per-object memory footprint — the bitmap data in the glyph, the pixel data in the texture, the character data in the string.
- The objects are immutable, or at least their intrinsic state is immutable. Sharing mutable state requires synchronization.

The pattern is not worth the complexity when:
- The objects are already small (a few integers or pointers) — sharing them adds the flyweight factory and indirection overhead without meaningful savings.
- The sharing pattern is already provided by the language or library (like string interning, type_info, or shared buffer implementations).
- The extrinsic state is as large as or larger than the intrinsic state — the savings are minimal and the indirection is pure overhead.
- The objects have short lifetimes — allocating and freeing them directly is simpler and the memory cost is amortized.

### Exercises

1. Implement flyweight for a particle system where each particle has a sprite (shared, immutable image) and a position (extrinsic). Compare memory usage for 100,000 particles with and without the flyweight pattern. Assume each image is 64×64 RGBA (16 KB).

2. A conference badge includes a name, company, and role. In a conference with 10,000 attendees, many share the same company and role. Design a flyweight that shares company and role strings, and measure the memory savings if 200 companies and 10 roles cover 90% of attendees.

3. Extend the `TextureCache` to support automatic eviction of least-recently-used (LRU) textures when the cache exceeds a memory limit. Discuss how the `shared_ptr`-based flyweight complicates eviction: how do you know if a texture is still in use?

## Decorator Patterns

The Decorator pattern attaches additional responsibilities to an object dynamically. It is an alternative to subclassing for extending behavior — compose rather than inherit.

The classic motivation is a UI component library. You have a `TextView` that displays text. You want to add a scrollbar to it. You also want to add a border. And maybe a drop shadow. And you want to combine these decorations freely: a `TextView` with a border, a `TextView` with a scrollbar and a border, a `TextView` with only a drop shadow. With subclassing, you would need `BorderedTextView`, `ScrollableTextView`, `BorderedScrollableTextView`, `ShadowedBorderedTextView` — the number of classes grows combinatorially. With decorators, each decoration is a class that wraps a component and adds its behavior, and you stack them at runtime.

```cpp
// The common interface for all components and decorators.
class VisualComponent {
public:
    virtual ~VisualComponent() = default;
    virtual void draw() = 0;
    virtual int width() const = 0;
};

// A concrete component — the thing being decorated.
class TextView : public VisualComponent {
    std::string text_;
public:
    explicit TextView(std::string text) : text_(std::move(text)) {}
    void draw() override { /* render text */ }
    int width() const override { return /* text width */; }
};

// Base decorator — wraps a component and forwards.
class Decorator : public VisualComponent {
    std::unique_ptr<VisualComponent> component_;
public:
    explicit Decorator(std::unique_ptr<VisualComponent> comp)
        : component_(std::move(comp)) {}
    void draw() override { component_->draw(); }
    int width() const override { return component_->width(); }
};

// Concrete decorators add behavior before or after the delegate.
class BorderDecorator : public Decorator {
    int thickness_;
public:
    BorderDecorator(std::unique_ptr<VisualComponent> comp, int t)
        : Decorator(std::move(comp)), thickness_(t) {}
    void draw() override {
        Decorator::draw();           // Draw the component.
        draw_border(thickness_);     // Add the border overlay.
    }
    int width() const override {
        return Decorator::width() + 2 * thickness_;
    }
};

class ScrollbarDecorator : public Decorator {
public:
    using Decorator::Decorator;
    void draw() override {
        Decorator::draw();
        draw_scrollbar();
    }
};

// Usage — stack decorators at runtime.
auto component = std::make_unique<ScrollbarDecorator>(
    std::make_unique<BorderDecorator>(
        std::make_unique<TextView>("Hello"),
        2
    )
);
component->draw();  // Draws text, then border, then scrollbar.
```

Each decorator extends the behavior of the component it wraps by adding its own logic before or after delegating to the wrapped component. The order of decoration matters — wrapping a `TextView` in a `BorderDecorator` and then in a `ScrollbarDecorator` is different from the reverse, because the layers are drawn sequentially.

The critical design element is that the decorator and the component share the same interface. The client has no way to know — and should not care — whether it is talking to a plain `TextView` or a `ScrollbarDecorator` wrapping a `BorderDecorator` wrapping a `TextView`. This transparency is what makes the pattern composable.

### C++ Idiomatic Decorator: Templates and CRTP

The classic decorator uses virtual dispatch and `unique_ptr` ownership, which works well when the composition is dynamic — configured at runtime from user preferences, plugin data, or configuration files. When the decoration stack is known at compile time, templates eliminate the runtime indirection:

```cpp
template <typename Component>
class Bordered : public Component {
    int thickness_;
public:
    template <typename... Args>
    explicit Bordered(int t, Args&&... args)
        : Component(std::forward<Args>(args)...), thickness_(t) {}

    void draw() {
        Component::draw();
        draw_border(thickness_);
    }
};

template <typename Component>
class Scrollable : public Component {
public:
    using Component::Component;
    void draw() {
        Component::draw();
        draw_scrollbar();
    }
};

// Usage — compile-time stack:
using MyWidget = Scrollable<Bordered<TextView>>;
MyWidget widget(2, "Hello");  // thickness=2, text="Hello"
widget.draw();
```

Each decorator extends the component through public inheritance, so `Scrollable<Bordered<TextView>>` is-a `TextView` in the sense that it inherits all public members. The `draw()` function in each layer explicitly calls the base's `draw()` and then adds its own — the compile-time analog of the runtime delegation.

The template approach generates no virtual calls, and the per-layer dispatch is fully inlined. The cost is that the decoration stack is fixed at compile time. If the user can decide at runtime whether to add a border — say from a settings dialog — you need either the runtime version or a combination of both (a compile-time library that offers all configurations as type aliases, selected by conditional compilation or an enum dispatch).

### Variadic Decorator Stack

A further refinement uses variadic templates to compose decorators in the type system:

```cpp
template <typename... Decorators>
struct Compose;

template <typename Component>
struct Compose<Component> {
    using type = Component;
};

template <typename Decorator, typename... Rest>
struct Compose<Decorator, Rest...> {
    using type = Decorator<typename Compose<Rest...>::type>;
};

// Usage:
using MyWidget = Compose<Scrollable, Bordered, TextView>::type;
```

This is primarily useful in library code where the set of decorators is parameterized. In application code, the direct template nesting `Scrollable<Bordered<TextView>>` is clearer and easier to debug.

### Functional Decorators with `std::function`

When you only need to augment a single function rather than an entire class interface, a `std::function`-based decorator is lighter than a full class hierarchy:

```cpp
// Logging decorator for any callable.
template <typename F>
auto with_logging(F fn, std::string_view name) {
    return [fn = std::move(fn), name = std::string(name)]
           (auto&&... args) {
        std::cout << "Entering: " << name << "\n";
        if constexpr (std::is_void_v<std::invoke_result_t<F, decltype(args)...>>) {
            fn(std::forward<decltype(args)>(args)...);
            std::cout << "Exiting: " << name << "\n";
        } else {
            auto result = fn(std::forward<decltype(args)>(args)...);
            std::cout << "Exiting: " << name << "\n";
            return result;
        }
    };
}

// Usage:
auto add = [](int a, int b) { return a + b; };
auto logged_add = with_logging(add, "add");
logged_add(3, 4);  // prints "Entering: add" and "Exiting: add"
```

This is a *functional decorator* — it wraps a callable with additional behavior without involving classes or virtual functions. The pattern is common in middleware, logging, profiling, and retry logic:

```cpp
template <typename F>
auto with_retry(F fn, int max_attempts) {
    return [fn = std::move(fn), max_attempts]
           (auto&&... args) {
        for (int attempt = 1; attempt <= max_attempts; ++attempt) {
            try {
                return fn(std::forward<decltype(args)>(args)...);
            } catch (const std::exception& e) {
                if (attempt == max_attempts) throw;
                // log and retry
            }
        }
        // unreachable in practice
    };
}
```

Functional decorators compose naturally because they return callables that can be further decorated:

```cpp
auto add = [](int a, int b) { return a + b; };
auto robust_add = with_retry(with_logging(add, "add"), 3);
```

### Policy-Based Decorators (Tag Dispatch)

When different decorations require different configurations (a border of thickness 2, a scrollbar with a specific style), the decorator pattern meets policy-based design. Each decorator can accept its configuration as a constructor argument, and the policy is selected by the type of the decorator:

```cpp
struct PlainBorder {
    int thickness;
};

struct RoundedBorder {
    int thickness;
    int radius;
};

template <typename Component, typename BorderPolicy>
class Bordered : public Component {
    BorderPolicy policy_;
public:
    template <typename... Args>
    explicit Bordered(BorderPolicy policy, Args&&... args)
        : Component(std::forward<Args>(args)...)
        , policy_(std::move(policy)) {}
    // draw() uses policy_ to decide how to draw the border
};
```

The `BorderPolicy` is a compile-time choice — each policy is a distinct type — but the border parameters (thickness, radius) are values determined at construction. This hybrid gives compile-time dispatch of the decoration kind with runtime configuration of the decoration parameters.

### Decorator vs. Inheritance vs. Strategy

The Decorator pattern is one of three approaches to extending behavior, and each fits a different design scenario:

- **Inheritance** extends behavior by subclassing. It is the simplest and most direct when the extension is fixed at compile time and applies uniformly to all instances of the base class. Its weakness is combinatorial explosion and the inability to change behavior per-instance at runtime.

- **Decorator** extends behavior by composition. It is flexible — you can layer extensions per-instance at runtime — but it introduces many small classes and a uniform interface that must support all operations the decorators might add or modify.

- **Strategy** replaces entire algorithms at runtime without extending them. A `TextView` with a `BorderStrategy` changes *how* the border is drawn but does not add a border to a component that has none. The Strategy pattern is for variation within an operation; the Decorator pattern is for adding operations.

The practical guideline: use inheritance when the extension is inherent to the type (a `SavingsAccount` *is a* `BankAccount`), use decorator when the extension is optional, per-instance, or combinatorial, and use strategy when you want to vary an algorithm at runtime without touching the object structure.

### Known Pitfalls

**Identity.** A decorator wraps the component but is not the component. If the client compares pointers or uses `dynamic_cast`, the decorator breaks the abstraction. A client that says `dynamic_cast<TextView*>(component)` expecting success will fail when `component` is a decorated wrapper. This is by design — the pattern deliberately hides the component's identity — but it catches out programmers who rely on RTTI.

**Interface alignment.** Every decorator must support the entire interface of the component, even if it does not modify most operations. This is manageable when the interface is small (like `draw()` and `width()`) but becomes a maintenance burden when the interface has many functions. In C++, a helper base decorator class (like `Decorator` in the earlier example) that forwards all operations to the wrapped component reduces the boilerplate, but each new function in the interface still requires checking whether any decorator needs to modify it.

**Depth and performance.** A deep stack of decorators — ten layers of wrapping — adds indirection on every call. In the runtime (virtual) version, each decorator adds a virtual call. In the template version, the depth is resolved at compile time and inlines away in optimized builds, but the binary size grows because the compiler generates distinct code for each combination.

**Stateful decorators.** A decorator that introduces state (like a caching decorator that stores computed results) must be careful about thread safety and about the fact that the component's copies and assignments may not propagate through the decorator. The decorator is not a container; it is a wrapper. Treating it as an object with its own identity is a category error.

### Exercises

1. Implement a `StreamDecorator` hierarchy: base `Stream` with `read()` and `write()` methods, and decorators `BufferedStream`, `EncryptedStream`, and `CompressedStream`. Show how they compose for a `CompressedEncryptedBufferedStream`. Compare the runtime-overhead-possible with the template decorator version.

2. A `Logger` interface has methods `log_debug`, `log_info`, `log_warn`, `log_error`. Implement decorators that add (a) timestamp prefix, (b) thread ID prefix, (c) rate limiting (skip messages if more than N per second). Stack them at runtime and discuss the call overhead.

3. The functional decorator `with_logging` logs before and after a call. Extend it to measure and log the call duration. Then compose it with `with_retry`. Show that the composition `with_retry(with_logging(with_timing(fn), "fn"), 3)` works correctly and discuss any order dependencies.

4. Identify a case in a codebase you know where a deep inheritance hierarchy could be replaced with decorators. Write the decorator version and estimate the reduction in classes. What existing coupling would the decorator version break?
