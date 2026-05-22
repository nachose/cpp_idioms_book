# Chapter 3: Object Creation and Destruction

Object creation and destruction form the foundation of any C++ program. How you create objects determines their lifetime, initialization guarantees, and ultimately the correctness and performance of your code. This chapter explores idioms that give you fine-grained control over object creation, enabling polymorphic cloning, enforcing initialization constraints, and providing flexible factory mechanisms that go beyond what the language provides by default.

The idioms in this chapter address common challenges: creating objects when the concrete type isn't known at compile time, ensuring objects are constructed with meaningful names rather than ambiguous overloaded constructors, enabling polymorphic copying without sacrificing type safety, and creating new objects by copying existing prototypes. Each idiom solves a distinct problem andTogether, they form a toolkit for managing object lifecycle in ways that raw constructors alone cannot achieve.

## Factory Methods and Virtual Constructors

When you need to create objects dynamically based on runtime conditions, regular constructors fall short. A constructor always creates an instance of the exact type it's called on—you cannot call a constructor polymorphically. Factory methods solve this by delegating object creation to functions that can choose the concrete type at runtime. But what if you need the factory itself to be polymorphic, creating different derived types based on the object's actual type? This is where the virtual constructor idiom, implemented through factory methods in a class hierarchy, becomes valuable.

The fundamental limitation is that constructors cannot be virtual. You cannot write `base->newInstance()` and expect it to create a derived instance. Instead, you achieve this effect through a polymorphic factory method—a member function that creates and returns objects of the appropriate derived type. Each derived class overrides this method to return instances of itself, effectively giving you "virtual constructors."

Consider a document processing system where different document types need different parsers:

```cpp
class Document {
public:
    virtual ~Document() = default;
    
    // Virtual constructor: creates a new document of the same derived type
    virtual std::unique_ptr<Document> create() const = 0;
    
    // Virtual clone: creates a copy of this specific derived type
    virtual std::unique_ptr<Document> clone() const = 0;
    
    virtual void parse(std::istream& input) = 0;
    virtual void serialize(std::ostream& output) const = 0;
};

class PDFDocument : public Document {
public:
    std::unique_ptr<Document> create() const override {
        return std::make_unique<PDFDocument>();
    }
    
    std::unique_ptr<Document> clone() const override {
        return std::make_unique<PDFDocument>(*this);
    }
    
    void parse(std::istream& input) override;
    void serialize(std::ostream& output) const override;
};

class WordDocument : public Document {
public:
    std::unique_ptr<Document> create() const override {
        return std::make_unique<WordDocument>();
    }
    
    std::unique_ptr<Document> clone() const override {
        return std::make_unique<WordDocument>(*this);
    }
    
    void parse(std::istream& input) override;
    void serialize(std::ostream& output) const override;
};
```

This pattern enables several powerful operations. You can serialize a container of base class pointers, and when deserializing, each object knows how to create a fresh instance of its own type. You can copy any document without knowing its concrete type. You can implement prototype-based patterns where new document types register themselves as factories.

The factory method idiom extends beyond simple creation. You can build parameterized factories that accept configuration, registration systems where types dynamically register themselves, and dependency injection frameworks where factories manage object lifecycle. The key insight is that by returning `std::unique_ptr<Base>`, you give callers a clean ownership transfer while maintaining flexibility about the actual type.

A common variation uses a separate factory class rather than factory methods in the product class itself. This separates creation logic from the product's core responsibility:

```cpp
class DocumentFactory {
public:
    virtual ~DocumentFactory() = default;
    virtual std::unique_ptr<Document> create(const std::string& type) = 0;
};

class PDFDocumentFactory : public DocumentFactory {
public:
    std::unique_ptr<Document> create(const std::string& type) override {
        if (type == "pdf") {
            return std::make_unique<PDFDocument>();
        }
        return nullptr;
    }
};
```

The tradeoff between these approaches involves coupling. Inline factory methods tightly couple creation to the product class, which works well when creation is inherently tied to the object's identity. Separate factory classes decouple them, enabling different creation strategies without modifying the product. Choose inline methods when each derived class naturally knows how to create itself; choose separate factories when creation logic is complex or needs configuration.

One limitation of the virtual constructor pattern is that you cannot enforce a specific interface across all derived classes—you rely on convention (all derived classes implement `create()` and `clone()`). Modern C++ alternatives include type-erased wrappers or concepts that can express requirements more formally, though at the cost of additional complexity.

## Named Constructor Idiom

C++ allows multiple constructors with different parameter types, but all share the same name—the class name. This works well when parameters clearly distinguish the construction mode, but can lead to ambiguous or error-prone interfaces when multiple constructors do similar things or when the parameter types don't clearly communicate intent. The Named Constructor Idiom solves this by providing static member functions with descriptive names that internally call private or protected constructors.

The primary motivation is clarity. Consider a class representing a point in 2D space that can be created from polar or Cartesian coordinates:

```cpp
class Point {
public:
    // Named constructors provide clear intent
    static Point cartesian(double x, double y) {
        return Point(x, y, CoordinateSystem::Cartesian);
    }
    
    static Point polar(double radius, double angle) {
        return Point(radius * std::cos(angle), 
                     radius * std::sin(angle), 
                     CoordinateSystem::Polar);
    }
    
    double x() const { return x_; }
    double y() const { return y_; }
    
private:
    // Private constructor enforces use of named constructors
    Point(double x, double y, CoordinateSystem system)
        : x_(x), y_(y), system_(system) {}
    
    double x_, y_;
    CoordinateSystem system_;
};
```

Without named constructors, you might have `Point(double, double)` and `Point(double, double, bool)` or worse, overloaded constructors with ambiguous signatures. Call sites become unclear: `Point(3, 4)` doesn't tell readers whether it's Cartesian or polar. The named constructors make intent explicit: `Point::cartesian(3, 4)` versus `Point::polar(5, 0.927)`.

Beyond clarity, this idiom enables enforcement of invariants that regular constructors cannot express. You can prevent direct construction in favor of factory methods that guarantee certain preprocessing, validation, or transformation:

```cpp
class Percentage {
public:
    // Enforce 0-100 range through named constructor
    static Percentage fromValue(double value) {
        if (value < 0 || value > 100) {
            throw std::invalid_argument("Percentage must be 0-100");
        }
        return Percentage(value);  // Calls private constructor
    }
    
    // Alternative construction from ratio (0.0 - 1.0)
    static Percentage fromRatio(double ratio) {
        return fromValue(ratio * 100);
    }
    
    double value() const { return value_; }
    
private:
    explicit Percentage(double v) : value_(v) {}
    double value_;
};
```

By making the constructor private, you force callers through the named constructors, ensuring validation always occurs. This is impossible to bypass with regular constructors—C++ has no way to make a constructor conditional on runtime checks.

Another common use case involves returning different internal representations based on construction parameters while presenting a unified interface. A timestamp might store internally as either UTC or local time depending on how it's constructed, with the named constructor choosing the appropriate representation.

The tradeoff is added verbosity—each named constructor adds a static function. For simple cases with unambiguous constructors, the idiom adds unnecessary complexity. Use it when constructors genuinely have unclear semantics, when you need to enforce construction-time validation, or when you want to communicate intent at call sites.

Modern alternatives include tagged constructors using `std::tagged_static`, or simply clear documentation and consistent parameter ordering. The named constructor remains valuable when you need to prevent direct construction entirely.

## Virtual Clone Idiom

Copying polymorphic objects presents a fundamental challenge. If you have a `std::unique_ptr<Base>` pointing to a `Derived` object, and you want to make a copy, the naive approach fails:

```cpp
std::unique_ptr<Base> base = std::make_unique<Derived>();
auto copy = *base;  // Calls Base::copy constructor - slices to Base!
```

This "slicing" problem occurs because the copy constructor always has the static type of the variable, not the dynamic type of the actual object. The derived part gets discarded, leaving you with a Base object that isn't really a Derived.

The Virtual Clone Idiom solves this by providing a virtual cloning function that each derived class implements to return a copy of itself. Since the function is virtual, the correct override runs based on the actual dynamic type, producing a proper polymorphic copy:

```cpp
class Shape {
public:
    virtual ~Shape() = default;
    
    // Virtual clone idiom: each derived class returns a copy of itself
    virtual std::unique_ptr<Shape> clone() const = 0;
    
    virtual void draw(std::ostream& out) const = 0;
    virtual double area() const = 0;
};

class Circle : public Shape {
public:
    Circle(double r) : radius_(r) {}
    
    std::unique_ptr<Shape> clone() const override {
        return std::make_unique<Circle>(*this);  // Copy of this Circle
    }
    
    void draw(std::ostream& out) const override;
    double area() const override { return M_PI * radius_ * radius_; }
    
private:
    double radius_;
};

class Rectangle : public Shape {
public:
    Rectangle(double w, double h) : width_(w), height_(h) {}
    
    std::unique_ptr<Shape> clone() const override {
        return std::make_unique<Rectangle>(*this);  // Copy of this Rectangle
    }
    
    void draw(std::ostream& out) const override;
    double area() const override { return width_ * height_; }
    
private:
    double width_, height_;
};
```

Now polymorphic copying works correctly:

```cpp
void drawAndCopy(const Shape& shape) {
    auto copy = shape.clone();  // Correct type, regardless of dynamic type
    copy->draw(std::cout);
}

std::unique_ptr<Shape> circle = std::make_unique<Circle>(5.0);
drawAndCopy(*circle);  // Creates a Circle copy, not a Shape
```

The return type `std::unique_ptr<Shape>` enables flexible ownership transfer. Callers can move the clone into containers, store it, or take ownership as needed. If you prefer value semantics, you can alternatively return `std::unique_ptr<Shape>` or provide both variants.

The idiom appears throughout object-oriented frameworks. Component frameworks use it for duplicating components. Document editors use it for copy-paste functionality. Serialization systems use it to reconstruct objects from stored data. Any system requiring polymorphic duplication benefits from this pattern.

One important consideration is the "curiously recurring template pattern" variant that simplifies implementation when you don't need runtime polymorphism for cloning itself:

```cpp
template<typename Derived>
class Cloneable {
public:
    std::unique_ptr<Derived> clone() const {
        return std::make_unique<Derived>(static_cast<const Derived&>(*this));
    }
};

class Shape : public Cloneable<Shape> {
    // Inherited clone() returns std::unique_ptr<Shape>
};
```

This reduces boilerplate but doesn't give you the type-specific return types—the caller gets `std::unique_ptr<Shape>` regardless of the actual type. Choose based on whether callers need to know the precise derived type.

The tradeoff involves the cloning interface. You must remember to override `clone()` in every derived class; forgetting causes slicing. Alternative approaches include type erasure with `std::function`, abstract factory patterns, or serialization frameworks—but these add complexity. The virtual clone idiom remains the most direct solution for polymorphic copying.

## Prototype Pattern Implementation

The Prototype Pattern provides a mechanism for creating new objects by copying existing "prototype" objects rather than constructing them from scratch. Unlike the Virtual Clone Idiom, which focuses on polymorphic copying, the Prototype Pattern emphasizes a registry of prototype objects from which new instances are created. This becomes valuable when object creation is expensive, when you need many objects with similar but not identical state, or when you want to avoid subclassing to create new object types.

The classic implementation maintains a collection of prototype instances. When you need a new object, you clone an existing prototype and optionally modify the copy:

```cpp
class Unit {
public:
    virtual ~Unit() = default;
    virtual std::unique_ptr<Unit> clone() const = 0;
    virtual void setPosition(int x, int y) = 0;
    virtual int health() const = 0;
    virtual std::string name() const = 0;
};

class Soldier : public Unit {
public:
    Soldier(int health = 100, int damage = 10) 
        : health_(health), damage_(damage) {}
    
    std::unique_ptr<Unit> clone() const override {
        return std::make_unique<Soldier>(*this);
    }
    
    void setPosition(int x, int y) override { x_ = x; y_ = y; }
    int health() const override { return health_; }
    std::string name() const override { return "Soldier"; }
    
    void setDamage(int d) { damage_ = d; }
    
private:
    int x_, y_;
    int health_;
    int damage_;
};

class UnitFactory {
public:
    // Register prototypes
    void registerPrototype(const std::string& name, std::unique_ptr<Unit> unit) {
        prototypes_[name] = std::move(unit);
    }
    
    // Create by cloning and customizing
    std::unique_ptr<Unit> create(const std::string& name, 
                                 int healthOverride = -1) {
        auto it = prototypes_.find(name);
        if (it == prototypes_.end()) {
            return nullptr;
        }
        
        auto unit = it->second->clone();
        if (healthOverride >= 0) {
            // We need type-specific setters or a more general approach
            // For demonstration, we assume all units support health
            // In practice, you'd use a more sophisticated customization API
            unit->setPosition(0, 0);  // placeholder for customization
        }
        return unit;
    }
    
private:
    std::unordered_map<std::string, std::unique_ptr<Unit>> prototypes_;
};
```

This basic form works but has limitations—the factory can't easily customize the cloned object without knowing its concrete type. More sophisticated implementations provide customization through a prototype configuration object or by returning a builder that can modify the clone before finalization.

The pattern shines when prototyping state that would be expensive to compute or when you have many similar objects:

```cpp
class NetworkPacketPrototype {
public:
    NetworkPacketPrototype() 
        : header_(defaultHeader()), payload_(defaultPayload()) {}
    
    std::unique_ptr<NetworkPacket> clone() const {
        return std::make_unique<NetworkPacket>(*this);
    }
    
    void setHeader(const PacketHeader& h) { header_ = h; }
    void setPayload(const std::vector<uint8_t>& p) { payload_ = p; }
    
private:
    PacketHeader header_;
    std::vector<uint8_t> payload_;
    
    static PacketHeader defaultHeader();
    static std::vector<uint8_t> defaultPayload();
};

// Usage: create many packets from a configured prototype
NetworkPacketPrototype httpResponse;
httpResponse.setHeader(makeSuccessHeader());

std::vector<std::unique_ptr<NetworkPacket>> responses;
for (const auto& response : data) {
    auto packet = httpResponse.clone();
    packet->setPayload(response);
    responses.push_back(std::move(packet));
}
```

A more advanced variant uses prototype registration with runtime type discovery. Instead of just cloning, you can ask the factory for a "new" object of a given type, and the factory maintains a prototype that it clones. This is essentially a registry-based factory:

```cpp
template<typename Base>
class PrototypeRegistry {
public:
    template<typename Derived>
    void registerType(const std::string& name) {
        static_assert(std::is_base_of_v<Base, Derived>);
        prototypes_[name] = []() -> std::unique_ptr<Base> {
        creators_[name] = []() -> std::unique_ptr<Base> {
        };
    }
    
    std::unique_ptr<Base> create(const std::string& name) const {
        auto it = creators_.find(name);
        if (it != creators_.end()) {
            return it->second();
        }
        return nullptr;
    }
    
    // Alternative: clone a registered prototype
    std::unique_ptr<Base> clone(const std::string& name) const {
        auto it = prototypes_.find(name);
        if (it != prototypes_.end()) {
            return it->second->clone();
        }
        return nullptr;
    }
    
private:
    std::unordered_map<std::string, std::unique_ptr<Base>> prototypes_;
    std::unordered_map<std::string, std::function<std::unique_ptr<Base>()>> creators_;
};
```

This approach combines the Virtual Clone Idiom with a factory, giving you flexibility to either construct fresh instances or clone existing prototypes.

The Prototype Pattern trades off between flexibility and complexity. It's valuable when you have expensive-to-create objects, many variants of similar objects, or when object types should be configurable at runtime. For simple cases where all objects of a type are identical, regular factory methods suffice. The pattern's power comes from its ability to treat object creation as data-driven, enabling configuration-based systems without code changes.

## Summary

This chapter explored four interrelated idioms for controlling object creation and destruction. Factory methods and virtual constructors enable polymorphic creation—objects that know how to create copies of themselves regardless of the static type handling them. The Named Constructor Idiom addresses interface clarity and invariant enforcement by replacing ambiguous constructor overloads with descriptive static methods. The Virtual Clone Idiom provides the foundation for polymorphic copying, solving the slicing problem that otherwise destroys derived class data. The Prototype Pattern extends this idea into a full creation pattern where existing objects serve as blueprints for new instances.

These idioms share a common theme: they give you control over object creation beyond what constructors alone provide. They enable polymorphism where C++ doesn't natively support it (virtual construction), communicate intent where constructors are ambiguous (named constructors), preserve type information during copying (virtual clone), and treat object creation as data-driven rather than code-driven (prototype).

As you build larger systems, you'll find yourself reaching for these patterns repeatedly. Factory methods appear in nearly every polymorphic hierarchy. Named constructors clarify interfaces for classes with complex initialization. Virtual clones enable undo/redo, serialization, and copy operations. Prototypes power configuration-driven systems. Master these patterns, and you'll have a robust toolkit for managing object lifecycle in C++.

### Exercises

1. **Factory Method Extension**: Extend the Document hierarchy from the factory method section to include an `HTMLDocument` class. Add a method that can serialize any document to any other document type by using the virtual constructor pattern.

2. **Named Constructor Safety**: Implement a `Temperature` class that can only be created through named constructors `celsius()`, `fahrenheit()`, and `kelvin()`. Ensure all internal storage is normalized to one representation, and add conversion methods that return new instances in different scales.

3. **Deep Clone Challenge**: Implement a `Scene` class containing a `std::vector<std::unique_ptr<Shape>>` of polymorphic shapes. Implement a deep clone that correctly clones all shapes within the scene. Consider what happens when shapes reference other objects.

4. **Prototype Registry**: Build a unit test system where test fixtures can be registered as prototypes. Clients can clone fixtures and then customize the cloned tests with specific assertions, avoiding the need to create new test classes for each variation.

5. **Comparison**: Compare the virtual clone idiom with C++20's `std::uninitialized_copy` algorithm for copying containers of polymorphic objects. When would each approach be preferable?