# Appendix C: Code Style and Conventions

This appendix documents the code style and conventions used throughout this book, explains the rationale behind them, and provides a reference for writing idiomatic C++ code that is consistent, readable, and maintainable.

Code style is not merely aesthetic. In C++, naming conventions communicate ownership semantics, visibility, and lifetime at a glance. File organization directly affects compilation time and dependency management. Documentation style determines whether a library is usable or inscrutable.

---

## Naming Conventions

### Types (classes, structs, enums, concepts, type aliases)

**PascalCase** (also called UpperCamelCase), no prefix:

```
class FileSystem;
struct Point2D;
enum class Color;
template <typename T>
concept Swappable = requires(T& a, T& b) { a.swap(b); };
using StringVector = std::vector<std::string>;
```

Why PascalCase? It visually distinguishes type names from variable and function names, which use camelCase or snake_case. This is also the convention used by the C++ standard library for non-standard types and by most major C++ projects (Boost, Qt, LLVM, Google). The absence of a prefix (no `C` for class, no `T` for template) avoids Hungarian notation and keeps names concise. The template parameter `T` is a historical exception — it is terse and ubiquitous.

### Functions and methods

**camelCase** (lowercase first letter):

```
void openFile(const std::string& path);
int computeChecksum(std::span<const std::byte> data);
[[nodiscard]] bool tryLock();
```

Why camelCase? It distinguishes functions from types (PascalCase) and does not collide with standard library conventions (which use snake_case). CamelCase is shorter than snake_case for compound names and reads naturally after the verb that starts most function names.

Member functions follow the same rule:

```
class Socket {
    void connect(const std::string& host, int port);
    void disconnect();
    [[nodiscard]] bool isConnected() const;
};
```

Get/set accessors are named `getFieldName()` / `setFieldName()` when they perform non-trivial work. For trivial member access, prefer the member name directly (`socket.fd`) or a named accessor without `get` (`socket.fileDescriptor()`).

### Variables and parameters

**snake_case**, no prefix:

```
std::size_t buffer_size;
const char* file_path;
double max_temperature;
```

Why snake_case? It is the most readable for multi-word names in lowercase, and it avoids the ambiguity between types and variables that would arise with camelCase. Underscores make boundaries between words clear even in narrow monospace environments.

Function parameters follow the same convention:

```
void resize(std::size_t new_capacity);
void sort(std::vector<int>& values, bool ascending = true);
```

### Class data members

**`snake_case_`** with trailing underscore:

```
class Person {
    std::string name_;
    int age_;
    double height_;
};
```

The trailing underscore distinguishes member variables from local variables and function parameters. This convention is used by the C++ Core Guidelines (C.128) and avoids the verbosity of `m_` prefixes or `this->` disambiguation. The underscore is *after* the name because leading underscores collide with reserved names (identifiers beginning with `_[A-Z]` or `__` are reserved for the implementation).

Static data members follow the same convention with a `s_` prefix to distinguish from instance members:

```
class Logger {
    static std::mutex s_mutex_;
    static std::ofstream s_log_file_;
    int verbosity_;
};
```

### Constants and enumerators

Constants  are `snake_case` (following variable convention). Enumerators are `PascalCase`:

```
constexpr std::size_t default_buffer_size = 4096;

enum class Color {
    Red,
    Green,
    Blue
};

enum class Flags {
    None       = 0,
    ReadOnly   = 1 << 0,
    WriteOnly  = 1 << 1,
    ReadWrite  = ReadOnly | WriteOnly
};
```

Why PascalCase for enumerators? It is the standard library convention (`std::errc`, `std::io_errc`) and clearly marks them as named constants. SCREAMING_CASE (ALL_CAPS) is avoided because it is visually loud, reads poorly in mixed contexts, and is conventionally reserved for preprocessor macros, where the distinct style warns the reader that the identifier is subject to textual substitution.

### Template parameters

- **Type template parameters**: single uppercase letter for generic code (`T`, `U`, `V`); descriptive PascalCase for constrained concepts (`Container`, `Predicate`).
- **Non-type template parameters**: snake_case (e.g., n, size) or PascalCase (e.g., N, Size), but simpler is better: std::size_t N for trivial cases.
- **Template template parameters**: PascalCase.

```
template <typename T>
T square(T x);

template <std::ranges::range Container>
typename Container::value_type sum(const Container& c);

template <typename T, std::size_t N>
struct Array { T data[N]; };
```

### Namespaces

**snake_case**, short and lowercase:

```
namespace file_system { ... }
namespace compression { ... }
namespace detail { ... }     // internal implementation details
```

Why snake_case? Namespaces are implicitly nested in fully qualified names, and underscoring avoids ambiguity with type names. The `detail` or `impl` namespace is standard for implementation details that are not part of the public API. No indentation is added for namespace contents (the standard convention in most style guides, as the extra indentation would push code far to the right for deeply nested namespaces).

### Macros

**`SCREAMING_CASE`** with a project-specific prefix:

```
#define MYLIB_VERSION_MAJOR 1
#define MYLIB_MAX_BUFFER_SIZE 4096
```

Macros are not scoped, so the prefix is essential to avoid collisions. The ALL_CAPS convention warns the reader that this identifier behaves differently from normal C++ entities. Avoid macros where possible; prefer `constexpr`, `inline const`, or constraints.

---

## Code Organization

### File naming

Source files use **snake_case** with a `.h` or `.hpp` extension for headers and `.cpp` or `.cc` for implementation:

```
file_system.h
file_system.cpp
socket_connection.hh
socket_connection.cc
```

Header file names match the primary class or utility they define. For a class `FileSystem`, the files are `file_system.h` and `file_system.cpp`. One class per file is the recommended convention, though closely related small classes (e.g., `FileSystem` and `FileSystemError`) may share a file.

### Header structure

Every header follows a consistent structure:

```cpp
// file_system.h
#ifndef MYLIB_FILE_SYSTEM_H
#define MYLIB_FILE_SYSTEM_H

#include <vector>        // standard library headers first
#include <string>

#include "error.h"       // project headers second

namespace mylib {

class FileSystem {
public:
    explicit FileSystem(const std::string& root_path);
    ~FileSystem();

    FileSystem(const FileSystem&) = delete;
    FileSystem& operator=(const FileSystem&) = delete;
    FileSystem(FileSystem&&) = default;
    FileSystem& operator=(FileSystem&&) = default;

    [[nodiscard]] bool exists(const std::string& path) const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace mylib

#endif // MYLIB_FILE_SYSTEM_H
```

Include guard format: `PROJECT_FILE_PATH_H`. Path-style guards (e.g., `MYLIB_FILE_SYSTEM_H`) make the guard self-documenting. `#pragma once` is widely supported and simpler, but the `#ifndef` form is maximally portable. Both are acceptable; the book uses `#ifndef` for maximum compatibility.

Include ordering: standard library first, then third-party libraries, then project headers. This ordering catches missing includes — if a project header relies on a standard library include that it does not directly include, the compilation will fail when it is listed first, revealing the dependency.

The Rule of Five is explicit even when defaulted or deleted, making the class's intent clear. `explicit` is used for single-argument constructors to prevent implicit conversions.

### Implementation file structure

```cpp
// file_system.cpp
#include "file_system.h"

#include <fstream>
#include <system_error>

namespace mylib {

class FileSystem::Impl {
public:
    void createDirectory(const std::string& path) {
        // ... actual platform-specific logic
    }
private:
    std::string root_path_;
};

bool FileSystem::exists(const std::string& path) const {
    return impl_ ? std::filesystem::exists(path) : false;
}

} // namespace mylib
```

The Pimpl class is defined in the `.cpp` file, invisible to the header's consumers. Member function definitions are ordered by their declaration order in the header.

### Forward declarations

Forward declare in limited, specific situations:

```cpp
namespace std {
    template <typename T>
    class unique_ptr;           // Forward declare only
}
```

However, forward declarations of standard library types are fragile and non-portable. In general, prefer including the full header. The only case where forward declarations are clearly justified is for Pimpl/Pointer-to-Implementation, where the header includes only `std::unique_ptr<Impl>` and the `Impl` type is left incomplete.

### Namespace organization

Use a single top-level namespace for the project:

```cpp
namespace mylib {
    // all public API
} // namespace mylib
```

Nested namespaces for subsystems:

```cpp
namespace mylib::network {
    // networking code
} // namespace mylib::network

namespace mylib::compression {
    // compression code
} // namespace mylib::compression
```

C++17 inline namespaces (`namespace inline v1 { ... }`) are reserved for ABI compatibility boundaries.

### Access level ordering

Class members are ordered by access level:

1. **public** — the interface.
2. **protected** — extension points for derived classes (rare in idiomatic C++; prefer composition).
3. **private** — implementation details.

Within each section: type aliases and nested types first, then constructors/destructor, then member functions, then data members. This ordering makes it easy to find the public interface at the top of the class definition.

---

## Documentation Patterns

### When to document

Not every line or function needs a comment. The goal of documentation is to communicate *why* something exists or behaves in a particular way, not to restate *what* the code does. Comments are justified when:

- The function's contract (preconditions, postconditions, invariants) is not trivially obvious from its signature and name.
- The code implements a non-obvious algorithm or a workaround for an external limitation.
- The code compensates for a bug in another library, a standard library implementation detail, or a platform quirk.
- A choice between several reasonable alternatives was made, and the reader should know why.

Comments are not justified when they merely repeat the code in English:

```cpp
// Bad: restates the obvious
// Increment the counter
++counter;

// Good: explains a non-obvious constraint
// Counter must be incremented before the notification is sent,
// because the receiver checks the counter.
++counter;
```

### Doxygen / Javadoc style

Public API functions use a Doxygen-compatible comment block:

```cpp
/**
 * Opens a file for reading or writing.
 *
 * The file is opened exclusively; no other process can access it
 * while the FileHandle exists. Use `close()` to release the lock.
 *
 * @param path Absolute or relative file path.
 * @param mode One of Read, Write, or Append.
 * @return A FileHandle on success.
 * @throws FileSystemError if the path does not exist or access is denied.
 */
[[nodiscard]] FileHandle openFile(const std::string& path, AccessMode mode);
```

The triple-slash (`///`) form is equally valid and less visually heavy:

```cpp
/// Opens a file for reading or writing.
/// @param path Absolute or relative file path.
/// @return A FileHandle on success.
[[nodiscard]] FileHandle openFile(const std::string& path, AccessMode mode);
```

Tags used consistently: `@param` for each parameter, `@return` for the return value, `@throws` for each exception type (or `@note`, `@warning`, `@see` for cross-references).

### Inline comments

Inline comments explain blocks within function bodies:

```cpp
void sendPacket(const Packet& pkt) {
    // Serialize header first to ensure alignment
    serializeHeader(pkt.header);

    // Payload may be empty; the receiver interprets zero length
    // as an end-of-stream signal.
    if (pkt.hasPayload()) {
        serializePayload(pkt.payload);
    }

    // Flush is needed because the underlying socket buffers
    // are not sent until the buffer is full or flush() is called.
    flush();
}
```

Each comment precedes the code it explains. Trailing comments on the same line are used only for short annotations:

```cpp
int total = 0;          // running total of processed bytes
```

### Documentation of preconditions

Preconditions are documented as `@pre` tags or in the function's prose:

```cpp
/**
 * Computes the dot product of two vectors.
 * @pre v1.size() == v2.size()
 */
double dotProduct(std::span<const double> v1, std::span<const double> v2);
```

In C++26, contract attributes provide a formal mechanism:

```cpp
double dotProduct(std::span<const double> v1, std::span<const double> v2)
    [[pre: v1.size() == v2.size()]];
```

### Documenting template parameters

Template parameters receive a `@tparam` tag:

```cpp
/**
 * A type-safe wrapper around a C-style callback.
 *
 * @tparam T The argument type the callback accepts.
 * @tparam F A callable with signature void(T).
 */
template <typename T, typename F>
class Callback { ... };
```

### Documenting namespace-level functions and variables

Free functions at namespace scope follow the same pattern as member functions. Global constants are documented with a brief purpose note:

```cpp
/// Maximum number of concurrent connections.
constexpr int max_connections = 256;
```

### What not to document

- **Trivial getters and setters** — their purpose is obvious.
- **Implementation details in the public header** — keep Doxygen comments focused on the public contract. Private or `detail`-namespace items typically need no Doxygen.
- **Obvious parameters** — `@param count The count` adds nothing. If the parameter's name is self-explanatory (`size`, `count`, `index`), a Doxygen tag is not needed.
- **Blame or history** — "Changed to fix bug #1234" belongs in version control, not in source code.

### Documenting the "why not"

When a seemingly obvious approach was rejected, document it:

```cpp
// Using std::mutex here instead of std::shared_mutex because
// writes are not rare enough to justify the higher overhead
// of shared_mutex. Profiling showed a 15% regression with
// shared_mutex.
```

This comment prevents future refactoring attempts that would repeat the same analysis.

---

## Formatting Conventions

### Indentation

4 spaces per level. No tabs. Tabs render differently in different editors and tools; spaces are universal.

### Line length

80 characters maximum for code, 100 for comments and string literals. The 80-character limit ensures the code is readable in side-by-side diffs, on narrow terminals, and in code review interfaces.

### Braces

Opening brace on the same line (K&R / Stroustrup style):

```cpp
class Person {
public:
    Person(const std::string& name) : name_(name) {}

private:
    std::string name_;
};

void sort(std::vector<int>& v) {
    std::sort(v.begin(), v.end());
}
```

Control flow statements follow the same convention:

```cpp
if (condition) {
    doSomething();
} else {
    doSomethingElse();
}

for (const auto& item : items) {
    process(item);
}

while (running) {
    tick();
}
```

Single-statement blocks may omit braces for very short conditions, but only if the statement fits on one line:

```cpp
if (condition) return;

if (condition)
    return;     // unacceptable — no braces, two lines

if (condition) {
    return;     // acceptable — braces clarify scope
}
```

The rule of thumb: if the body does not fit on the same line as the `if`, it needs braces.

### Switch statements

```cpp
switch (color) {
case Color::Red:
    handleRed();
    break;
case Color::Green:
    handleGreen();
    break;
default:
    handleUnknown();
    break;
}
```

The `default` case is always present, even if it is `default: break;`, to handle unanticipated enumerator additions.

### Alignment of declarations

Group related declarations by their purpose, not by type:

```cpp
int x, y, z;                     // coordinates
double temperature, pressure;    // sensor readings
```

Avoid aligning the type names across lines; it creates a maintenance burden when a longer type name is introduced and all other lines must be re-aligned. Instead, one declaration per line if the types differ:

```cpp
int         x;        // bad — alignment fragile
double      pressure; // bad

int x;
double pressure;
```

### Forward declarations of template specializations

Specializations are annotated with a brief comment:

```cpp
template <>
struct hash<MyType>;   // forward declaration only
```

---

## Summary

Consistent style reduces cognitive load. When every file follows the same conventions, the reader can focus on the logic rather than parsing local idiosyncrasies. The conventions in this appendix are chosen to align with the C++ Core Guidelines and common practice in open-source C++ projects, but any consistent style that enforces the same invariants is preferable to no style at all.

The most important conventions are:

1. **Names communicate semantics**: types are PascalCase, variables are snake_case, members have trailing underscores.
2. **Headers are self-contained**: each header includes what it needs and has a valid include guard.
3. **Document why, not what**: comments explain rationale, not mechanics.
4. **Format consistently**: 4-space indentation, 80-character lines, K&R braces.

A project-wide `.clang-format` and `.clang-tidy` configuration enforces these conventions mechanically and should be part of every C++ codebase's CI pipeline.
