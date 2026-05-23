# Chapter 21: Cache-Friendly Patterns

Modern CPUs are fast — far faster than memory. A single cache miss can stall the processor for hundreds of cycles while data travels from DRAM through the memory bus. The gap between processor speed and memory latency has been growing for decades, and it is now the dominant bottleneck in most compute-intensive programs. Understanding how the cache works and writing code that respects it is no longer an optimization reserved for game engines and HPC kernels — it is a fundamental skill for any C++ programmer who cares about performance.

This chapter explores four interrelated topics: the data-oriented design philosophy that reorients your thinking from code to data flow, the mechanics of cache line alignment and false sharing, the choice between structure-of-arrays and array-of-structures layouts, and memory prefetching techniques that tell the hardware what data you will need before you need it.

## Data-Oriented Design

Data-oriented design (DOD) is a design philosophy that prioritizes data layout and access patterns over the traditional object-oriented decomposition of a problem into entities with behaviors. The central insight is simple: the cost of fetching data from memory to the CPU dominates the cost of operating on it. Therefore, the primary concern when designing a system should not be "what objects exist and how do they interact?" but rather "what data is accessed, in what order, and how can it be arranged to minimize cache misses?"

### The Problem with Objects

Consider a typical object-oriented game entity:

```cpp
class Entity {
    std::string name_;
    glm::vec3 position_;
    glm::vec3 velocity_;
    float health_;
    float armor_;
    Mesh* mesh_;
    AIState ai_state_;
    // ... more fields
public:
    virtual void update(float dt);
    virtual void render(const Camera& cam);
    // ...
};
```

An `Entity` object packs together all the data for a given conceptual entity. This seems natural — it is how we think about the world. But it is disastrous for cache performance. When the update loop iterates over all entities, it touches `position_`, `velocity_`, `health_`, `armor_`, `ai_state_`, and more — for every single entity. The cache line fetched for one entity contains not just the fields needed for the current operation, but also unrelated fields that will be used later (or not at all). Worse, the virtual `update` call means the CPU cannot predict which code path to prefetch, and the `std::string` field forces an indirection to the heap for every entity just to read the name that the update loop never even looks at.

If `sizeof(Entity)` is 128 bytes and a cache line is 64 bytes, iterating over 1000 entities touches at least 2000 cache lines — but the update loop may only need the position and velocity (24 bytes total per entity). The excess data dragged into cache pollutes it, evicting potentially useful data from other parts of the program.

### Thinking in Streams

Data-oriented design asks you to decompose the problem differently: not into objects, but into *streams of data* that are accessed together. What operations happen on what data? What is the access pattern? How can the data be arranged so that each cache line fetched contains only data that the current operation will actually use?

```cpp
struct EntityContainer {
    // Each field is a contiguous array — accessed only when needed
    std::vector<glm::vec3> positions;
    std::vector<glm::vec3> velocities;
    std::vector<float>     healths;
    std::vector<float>     armors;
    std::vector<Mesh*>     meshes;
    // AI state stored separately — only used by the AI system
    std::vector<AIState>   ai_states;
};
```

The update loop now operates on a single stream:

```cpp
void update_positions(EntityContainer& ec, float dt) {
    // Accesses only positions and velocities — contiguous in memory
    for (size_t i = 0; i < ec.positions.size(); ++i) {
        ec.positions[i] += ec.velocities[i] * dt;
    }
}
```

At the machine level, this loop streams through two arrays sequentially. The hardware prefetcher recognizes the stride pattern and brings in the next cache lines before they are needed. Every byte fetched is a byte that will be used — there is no wasted space in the cache line for `health_`, `armor_`, or the entity's `name_` string. The loop body is a few SIMD-friendly floating-point operations with no branches, no virtual dispatch, and no pointer chasing.

The consequences of this reorganization are dramatic. A system that spends 70% of its time waiting on memory in the object-oriented version can often see 2–10x speedups simply by rearranging data, without changing any algorithms. The operations are the same — addition, multiplication, assignment — but the data flows through the cache efficiently.

### Hot and Cold Splitting

Data-oriented design also reveals a simple but powerful optimization: separate frequently accessed data ("hot") from infrequently accessed data ("cold") into different arrays. This is called *hot/cold splitting*.

```cpp
// Before: every entity carries rarely-used data
struct Entity {
    glm::vec3 position;
    glm::vec3 velocity;
    std::string name;        // Cold: only used for debugging
    uint64_t creation_time;  // Cold: only used for statistics
    uint64_t last_access;    // Cold: only used for LRU eviction
    uint32_t flags;          // Cold: only checked in special cases
};

// After: hot data is dense, cold data is sparse
struct EntityHot {
    glm::vec3 position;
    glm::vec3 velocity;
};

struct EntityCold {
    std::string name;
    uint64_t creation_time;
    uint64_t last_access;
    uint32_t flags;
};

struct EntityManager {
    std::vector<EntityHot> hot_data;
    std::vector<EntityCold> cold_data;  // Same index, separate cache
};
```

The hot array is dense and cache-friendly. A single cache line holds several entities' positions and velocities. The cold array is accessed only when needed — name lookups for logging, flags for special-case handling — and those accesses are rare, so it does not pollute the cache during normal operations. The cost is a second indirection (looking up the cold data by index), but because cold accesses are infrequent, this cost is amortized and the cache benefit dominates.

Hot/cold splitting applies at many granularities. Even within a single struct, you can reorder fields so that hot fields are at the beginning of the struct, ensuring they share a cache line. The compiler cannot do this automatically because it must preserve declaration order within a translation unit — the rules of standard layout require it.

### Data-Oriented Design as a Mindset

Data-oriented design is not a library or a pattern you can import. It is a way of thinking about performance that starts with a question: what is the access pattern? Before writing any code, sketch the data flow: what data enters the system, how is it transformed, what intermediate results are produced, and what is the final output? Then design your data structures to serve that flow with minimal cache line traffic.

The approach is especially valuable in systems with predictable, repetitive access patterns: physics simulations, particle systems, collision detection, database query evaluation, network packet processing, audio synthesis, and image processing. In such systems, the access pattern is known at compile time and is largely data-independent, making DOD transformations safe and predictable.

DOD is less applicable in systems with chaotic, pointer-heavy access patterns — graph algorithms that chase random edges, interpreters that navigate ASTs, or UI frameworks where widgets are allocated independently and accessed via virtual calls. In these cases, fundamental algorithmic changes (e.g., switching from an adjacency list to an adjacency matrix) or data structure changes (e.g., using a flat vector of widgets instead of a tree of heap-allocated nodes) are needed before DOD can help.

### Limits

Data-oriented design is not without costs. Splitting data into parallel arrays increases code complexity — invariants like "position and health belong to the same entity" must be maintained manually, and operations that need both hot and cold data must manage two or more arrays. The approach also reduces encapsulation: there is no natural "entity" object that bundles its data, so interfaces must operate on arrays or indices rather than objects. For codebases that are not performance-critical, the complexity cost of DOD often exceeds the benefit.

DOD also assumes that the access pattern is known and stable. If the set of fields accessed per entity varies unpredictably at runtime, no static layout can optimize all paths. In such cases, an object-oriented layout (where all data for one entity is in one place) may actually be better because at least the entire entity is in the cache after the first miss.

The key is to apply DOD judiciously: identify the hot loops that dominate runtime, profile to confirm that cache misses are the bottleneck, and only then invest in data layout changes. Preemptive DOD without profiling is as wasteful as preemptive optimization of any other kind.

---

## Cache Line Alignment

Cache lines are the unit of data transfer between memory and the CPU cache. On virtually all modern x86 and ARM processors, a cache line is 64 bytes. When the CPU loads a single byte from memory, the entire 64-byte block containing that byte is fetched into the cache. This batching is what makes sequential access fast — subsequent accesses to nearby addresses hit the cache without touching main memory — but it is also what makes random or strided access expensive.

Cache line alignment is the practice of placing data at addresses that are multiples of the cache line size, ensuring that frequently accessed data does not straddle cache line boundaries. Misaligned access can double the number of cache lines needed for a single data item and, worse, can cause *false sharing* — a performance pathology where distinct cores invalidate each other's cache lines despite accessing different data.

### Aligning Structures

The `alignas` specifier (C++11) lets you control the alignment of a type or object:

```cpp
struct alignas(64) CacheAligned {
    int data[16];  // Exactly one cache line (16 * 4 = 64 bytes)
};
```

A `CacheAligned` object is guaranteed to start at a 64-byte boundary. When allocated on the stack, the compiler adjusts the stack pointer to satisfy the alignment. When allocated on the heap, `new` and `std::allocator` respect the alignment through `std::aligned_alloc` or equivalent platform-specific mechanisms. A `std::vector<CacheAligned>` ensures each element is also 64-byte aligned, because `std::vector` allocates storage with correct alignment for the element type.

The benefit appears when you access fields of the struct in a hot loop. If `CacheAligned` is stored in an array, each element occupies exactly one cache line and no element's data spills into the next line. Iterating over the array touches `N` cache lines for `N` elements — the minimum possible.

Without alignment, an array of 64-byte structures might have elements straddling cache line boundaries. Element 0 starts at offset 0 (aligned), but if its actual size is 64 bytes and the allocation happens at a misaligned address, element 1 might start at offset 64 (still aligned), but element 2 at offset 128, and so on — in practice, compilers insert padding to satisfy natural alignment, so `alignas(64)` is needed only when you want alignment greater than the natural alignment of the largest member.

### False Sharing

False sharing is one of the most insidious performance problems in multithreaded C++. It occurs when two threads on different cores modify variables that happen to reside on the same cache line. Even though the threads are accessing different memory addresses and no true sharing (data race) exists, the cache coherence protocol forces the cache line to bounce between the two cores as if the threads were competing for the same data.

```cpp
struct SharedCounter {
    int counter_a = 0;  // Thread 1 writes here
    int counter_b = 0;  // Thread 2 writes here
    // Both on the same cache line (assuming no padding)
};

// Thread 1:
for (int i = 0; i < 100000000; ++i) ++counter.counter_a;

// Thread 2:
for (int i = 0; i < 100000000; ++i) ++counter.counter_b;
```

Despite there being no data race — `counter_a` and `counter_b` are different integers — each increment by thread 1 invalidates the cache line on thread 2's core, and vice versa. The cache line shuttles back and forth between the two L1 caches on every write, potentially slowing the program by an order of magnitude. The performance impact increases with the number of cores contending for the cache line.

The fix is to ensure that variables modified by different threads reside on different cache lines:

```cpp
struct alignas(64) PaddedCounter {
    int value = 0;
};

static_assert(sizeof(PaddedCounter) == 64);

// Now each counter occupies its own cache line
PaddedCounter counter_a;  // Core 1
PaddedCounter counter_b;  // Core 2
// No false sharing: different cache lines
```

The padding guarantees that `counter_a` and `counter_b` are at least 64 bytes apart — they cannot fall on the same cache line regardless of their absolute addresses. The `static_assert` confirms the size.

In practice, you can use a helper to avoid manual padding:

```cpp
template <typename T>
struct alignas(64) CachePadded {
    T value;
private:
    char padding_[64 - sizeof(T)];
};

static_assert(sizeof(CachePadded<int>) == 64);
```

The cost of padding is memory. A `CachePadded<int>` occupies 64 bytes to store 4 bytes of useful data. If you have a million such counters, you pay 64 MB instead of 4 MB. False sharing mitigation is a trade-off between memory and performance — apply it only to variables that are both (a) written by multiple threads and (b) on the hot path.

### Detecting False Sharing

False sharing is notoriously difficult to diagnose because it does not produce wrong results — only poor performance. Profiling tools like Linux `perf` can report cache misses per function:

```bash
perf stat -e cache-misses,cache-references,cycles ./program
```

If cache miss rates are high (above 5–10%) and the program is multi-threaded, false sharing is a likely suspect. Intel VTune and AMD uProf have dedicated false-sharing analysis that highlights cache lines bouncing between cores. Valgrind's `cachegrind` tool simulates cache behavior and can indicate where cache misses are concentrated.

A simpler diagnostic is the "halving" test: reduce the number of threads and measure the speedup. If the program scales sub-linearly (e.g., 4 threads give only 1.5x speedup), false sharing or lock contention is a likely cause. Lock contention can be confirmed by profiling lock wait times; if locks are not the problem, false sharing is the next candidate.

### Struct Reordering for Cache Locality

Even in single-threaded code, field ordering within a struct affects cache utilization. Fields that are accessed together should be adjacent, and fields that are accessed in different hot paths should be separated (or placed in different structs via hot/cold splitting).

```cpp
// Bad: hot fields interleaved with cold fields
struct ParticleBad {
    glm::vec3 position;    // Hot
    std::string label;     // Cold — each access drags in position's cache line
    glm::vec3 velocity;    // Hot
    double mass;           // Hot
    uint64_t id;           // Cold
};

// Good: hot fields grouped together, cold fields after
struct ParticleGood {
    glm::vec3 position;    // Hot
    glm::vec3 velocity;    // Hot
    double mass;           // Hot
    std::string label;     // Cold
    uint64_t id;           // Cold
};
```

In the "bad" layout, accessing `velocity` after `position` may require a second cache line because `label` separates them. In the "good" layout, `position`, `velocity`, and `mass` are contiguous and fit in the same cache line (assuming 64-byte lines and 4-byte floats). The cold fields are at the end and are only loaded when explicitly accessed.

Compiler reordering (`-fstrict-aliasing`, structure layout optimizations in LTO) can move fields around, but the C++ standard requires that fields within a standard-layout struct appear in declaration order — the compiler may not rearrange them. This means the programmer has full control over field order, and must exercise it wisely.

### Large Pages and Transparent Huge Pages

Cache line alignment operates at the 64-byte granularity of the L1 cache. At the TLB (translation lookaside buffer) level, the granularity is the virtual memory page — typically 4 KB. When a program accesses a large working set, TLB misses can become as costly as cache misses because the CPU must walk the page tables to translate a virtual address.

The solution is to use larger page sizes. Linux supports Transparent Huge Pages (THP), which automatically promotes contiguous groups of 4 KB pages to 2 MB (or 1 GB) pages. C++ programs can also explicitly allocate with `mmap` and the `MAP_HUGETLB` flag.

```cpp
#include <sys/mman.h>

// Allocate 2 MB of huge page memory
void* ptr = mmap(nullptr, 2 * 1024 * 1024,
                 PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANONYMOUS | MAP_HUGETLB,
                 -1, 0);
```

Large pages reduce TLB pressure because one TLB entry covers 2 MB instead of 4 KB. For a program with a 200 MB working set, THP reduces TLB misses from roughly 50,000 entries to 100 entries — a dramatic improvement. The cost is that huge pages must be contiguous in physical memory, which can fail if memory is fragmented. Most Linux systems handle this with THP's opportunistic promotion, which silently falls back to 4 KB pages when promotion is not possible.

### Alignment and the ABI

When writing library code, care is needed with alignment in public interfaces. A type with `alignas(64)` imposes alignment requirements on every object that contains it and every array that stores it. If a user of the library places your `alignas(64)` type inside their own struct, their struct becomes over-aligned, increasing its size and potentially causing ABI breaks between compilation units compiled with and without the alignment attribute.

The general guideline is: use aggressive alignment only in internal, translation-unit-local types, not in public API types. For public APIs, prefer `std::unique_ptr` with aligned allocation (using `std::aligned_alloc` or platform APIs) and return pointers rather than over-aligned value types.

---

## Structure of Arrays (SoA) vs Array of Structures (AoS)

The choice between Array of Structures (AoS) and Structure of Arrays (SoA) is the most concrete, measurable expression of the data-oriented design philosophy. These two layouts represent fundamentally different ways of organizing the same data, and the performance difference between them can exceed an order of magnitude for bandwidth-bound operations.

### The Two Layouts

AoS is the default layout in most C++ code. Each struct holds all the fields for one entity, and entities are stored in a contiguous array:

```cpp
// Array of Structures
struct Particle {
    float x, y, z;   // position
    float vx, vy, vz; // velocity
    float mass;
    uint32_t id;
};

std::vector<Particle> particles_aos(1000000);
```

SoA inverts the nesting: each field becomes a separate array, and the "entity" is implicit in the shared index:

```cpp
// Structure of Arrays
struct ParticleSystem {
    std::vector<float> x, y, z;       // positions (contiguous)
    std::vector<float> vx, vy, vz;    // velocities (contiguous)
    std::vector<float> mass;
    std::vector<uint32_t> id;
};

ParticleSystem particles_soa;
particles_soa.x.resize(1000000);
particles_soa.y.resize(1000000);
// ...
```

### Memory Access Patterns

The layouts produce dramatically different memory access patterns. Consider an update that moves particles by their velocity:

```cpp
// AoS update: accesses x, y, z, vx, vy, vz for each entity
void update_aos(std::span<Particle> particles, float dt) {
    for (auto& p : particles) {
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.z += p.vz * dt;
    }
}

// SoA update: accesses only x and vx in one stream, y and vy in another
void update_soa(ParticleSystem& ps, float dt) {
    for (size_t i = 0; i < ps.x.size(); ++i) {
        ps.x[i] += ps.vx[i] * dt;
        ps.y[i] += ps.vy[i] * dt;
        ps.z[i] += ps.vz[i] * dt;
    }
}
```

At the cache level, the AoS version loads one cache line containing, say, 4 particles (each 64 bytes). Of those 4 particles, it reads all 6 float fields plus mass and id — but it only writes to x, y, z. The mass and id fields are wastefully dragged into cache. The next iteration reads the next 4 particles, and so on. The memory bandwidth utilization (useful bytes divided by total bytes fetched) is about 50% for this operation — half of every cache line is field data that is not needed.

The SoA version accesses three separate arrays: `x`, `vx`, and (for the write) `x` again through the store buffer. Each access is sequential. When the loop reads `vx[i]`, the hardware prefetcher recognizes the stride and starts loading `vx[i+1]`, `vx[i+2]`, etc. The memory bandwidth utilization approaches 100% — every byte fetched from the `x` array is an `x` coordinate that will be read and written. The `y` and `z` accesses also stream sequentially.

### SIMD Vectorization

The SoA layout is far more amenable to SIMD (Single Instruction, Multiple Data) vectorization. Compilers can auto-vectorize the SoA loop more easily because the load and store operations are contiguous and aligned:

```cpp
// SoA with explicit SIMD (using x86 SSE/AVX intrinsics):
void update_soa_simd(ParticleSystem& ps, float dt) {
    const __m128 dt_vec = _mm_set1_ps(dt);
    for (size_t i = 0; i + 3 < ps.x.size(); i += 4) {
        __m128 x  = _mm_load_ps(&ps.x[i]);
        __m128 vx = _mm_load_ps(&ps.vx[i]);
        x = _mm_add_ps(x, _mm_mul_ps(vx, dt_vec));
        _mm_store_ps(&ps.x[i], x);
        // Same for y and z
    }
}
```

Each `_mm_load_ps` loads four contiguous floats from one array. The AoS version would need gather instructions (`_mm_i32gather_ps`) to collect non-contiguous floats from the struct array, which are significantly slower than contiguous loads — typically 2–3x higher latency and lower throughput.

The difference is stark when measured. On a modern x86 processor with AVX2, the SoA update of 1 million particles can run at memory bandwidth limits (~40 GB/s), processing roughly 200 million particles per second. The AoS version, limited by cache efficiency and gather penalties, typically achieves 30–50 million particles per second — a 4–6x difference for the same arithmetic.

### When AoS Wins

SoA is not always superior. AoS has advantages when:

1. **Operations access all or most fields of each entity**. If you are serializing a particle to disk, you need all its fields. AoS allows a single sequential write; SoA requires gathering from multiple arrays.

2. **Data is accessed by entity, not by field**. A UI that displays particle information for a single selected entity prefers AoS because it reads all fields for one entity from a single cache line.

3. **Dynamic allocation per field is costly**. If particles are added and removed frequently, SoA requires inserting or removing elements from multiple arrays in sync — an error-prone operation that AoS handles with a single `vector::erase`.

4. **Code simplicity matters more than performance**. AoS is the natural C++ layout; SoA adds complexity to function signatures, iterator support, and data structure invariants.

### Hybrid Layouts

Real-world systems often use hybrid layouts that combine the benefits of both. A common intermediate is the Array of Structs of Arrays (AoSoA) layout, which groups a small number of entities (typically 4–8) into a struct that holds arrays of fields:

```cpp
template <size_t N = 8>
struct ParticleBlock {
    alignas(64) float x[N];
    alignas(64) float y[N];
    alignas(64) float z[N];
    alignas(64) float vx[N];
    alignas(64) float vy[N];
    alignas(64) float vz[N];
    alignas(64) float mass[N];
    alignas(64) uint32_t id[N];
};

// The full system is an array of blocks
std::vector<ParticleBlock<8>> particle_blocks;
```

For operations that touch a subset of fields, each block's data for that field is contiguous in a small, cache-resident chunk. For operations that touch all fields (like serialization or copying), the block structure allows sequential access through each field array. The AoSoA layout is the standard choice for high-performance particle systems, physics engines, and ECS (Entity Component System) frameworks.

Modern ECS libraries like EnTT take this further by managing component storage in a SoA-like fashion internally, while exposing an interface that feels like AoS to the user. The storage is an array of sparse sets, each holding one component type contiguously, and the ECS queries iterate over the hot components while skipping cold ones.

### Measuring the Difference

The choice between AoS and SoA should always be guided by measurement, not intuition. A simple microbenchmark can reveal the difference for your specific workload:

```cpp
// Measure AoS throughput
auto aos_start = std::chrono::steady_clock::now();
update_aos(particles_aos, 0.016f);
auto aos_end = std::chrono::steady_clock::now();

// Measure SoA throughput
auto soa_start = std::chrono::steady_clock::now();
update_soa(particles_soa, 0.016f);
auto soa_end = std::chrono::steady_clock::now();

std::cout << "AoS: " << (count / std::chrono::duration<double>(aos_end - aos_start).count()) << " particles/s\n";
std::cout << "SoA: " << (count / std::chrono::duration<double>(soa_end - soa_start).count()) << " particles/s\n";
```

It is important to test with realistic data sizes — the difference may be negligible for small arrays that fit entirely in L1 cache (32 KB) but become dramatic when the working set exceeds L2 (256 KB) or L3 (several MB). The prefetcher also needs a certain stream length to activate; benchmarks with tiny arrays (a few hundred elements) may show little difference because all data fits in cache regardless of layout.

### The AoSoA Trade-Off

The AoSoA layout introduces a design tension. The block size `N` determines the granularity of the hybrid. A small `N` (e.g., 4) brings the layout closer to SoA — good SIMD utilization, good spatial locality for field-wise operations. A large `N` (e.g., 64) brings the layout closer to AoS — better per-entity locality when all fields are needed, but worse cache efficiency for field-wise operations.

The optimal `N` depends on the cache line size (64 bytes), the size of each field, and the number of fields accessed per operation. A common heuristic is to set `N` so that one block's worth of a single field fits in a cache line — e.g., `N = 64/sizeof(float)` for float arrays, which gives `N = 16`. This ensures that a single cache line load covers an entire block's worth of one field, maximizing useful data per cache line.

---

## Memory Prefetching Idioms

Prefetching is the mechanism by which the CPU speculatively loads data into cache before it is explicitly requested. Modern processors have sophisticated hardware prefetchers that recognize regular access patterns — sequential strides, strided offsets, and even some irregular patterns — and fetch ahead of the program counter. When the access pattern is predictable, the hardware prefetcher hides memory latency almost entirely. When it is not, the programmer can issue explicit prefetch instructions to tell the CPU what to load next.

Understanding what the hardware can do automatically, and when to help it with software prefetching, is the fourth pillar of cache-friendly programming.

### Hardware Prefetching

The hardware prefetcher observes the stream of cache misses and looks for patterns. The most common is the sequential prefetcher: when it detects a stream of ascending or descending addresses (as in a tight loop over an array), it prefetches the next few cache lines ahead. On modern Intel and AMD CPUs, the prefetcher can track up to 32 independent streams simultaneously.

The sequential prefetcher is why simple loops over arrays are fast: the hardware automatically brings in the next cache line while the CPU is processing the current one, so the latency of the load is hidden. For a loop that processes 64 bytes per iteration (one cache line), the hardware prefetcher can keep the pipeline full as long as the loop body takes fewer cycles than the memory latency (roughly 200–300 cycles for DRAM).

More advanced prefetchers handle strided access:

```cpp
// Strided access: the prefetcher can learn the stride
for (size_t i = 0; i < n; i += stride) {
    process(data[i]);
}
```

If `stride` is constant (or varies within a small set of patterns), the hardware can detect it and prefetch accordingly. However, the stride must be small enough that the prefetcher's lookahead (typically 4–8 cache lines) covers the next useful address. If `stride * sizeof(element)` exceeds the prefetcher's window, the prefetcher falls behind and every access becomes a cache miss.

The hardware prefetcher cannot help with truly random access patterns — pointer chasing through a linked list, hash table lookups with unpredictable keys, or traversing a binary tree. These patterns require either algorithmic changes (to make access sequential) or software prefetching (to hide the latency of the inevitable misses).

### Software Prefetching: `__builtin_prefetch` and `_mm_prefetch`

Software prefetching uses a CPU instruction (e.g., `PREFETCHT0` on x86) that tells the memory subsystem to load a cache line into a specific level of cache. In C++, the most portable way to issue a prefetch is through compiler built-ins:

```cpp
// GCC and Clang
__builtin_prefetch(address, rw, locality);
// rw: 0 = read, 1 = write
// locality: 0 = no temporal locality (drop after use), 3 = high temporal locality (keep in all caches)

// MSVC and x86 intrinsic
_mm_prefetch(reinterpret_cast<const char*>(address), _MM_HINT_T0);
// _MM_HINT_T0: prefetch to all cache levels
// _MM_HINT_T1: prefetch to L2 and L3
// _MM_HINT_T2: prefetch to L3 only
// _MM_HINT_NTA: prefetch to L1 only, mark as non-temporal
```

The `locality` hint tells the CPU how long to keep the data in cache. Data with high temporal locality (accessed again soon) should be placed in all cache levels. Data accessed only once should use non-temporal hints (`_MM_HINT_NTA`) to avoid evicting other useful data.

### Prefetching in Linked Data Structures

Linked data structures (linked lists, trees, hash tables with chaining) are the worst case for cache performance because the address of the next node is unknown until the current node is dereferenced. This is called a *pointer chase*: the CPU cannot prefetch the next node because it does not know its address until it reads the current node's pointer.

Software prefetching can help by speculatively loading the node after next while processing the current node:

```cpp
struct Node {
    int data;
    Node* next;
};

void process_list(Node* head) {
    // Prefetch two nodes ahead to hide latency
    Node* prefetch_target = head;
    if (head) {
        __builtin_prefetch(head->next, 0, 0);
        // Prefetch depth: advance a few steps ahead
        for (int i = 0; i < PREFETCH_DEPTH && prefetch_target; ++i) {
            prefetch_target = prefetch_target->next;
            if (prefetch_target) {
                __builtin_prefetch(prefetch_target->next, 0, 0);
            }
        }
    }

    // Main processing loop
    while (head) {
        process(head->data);

        head = head->next;
        if (head) {
            __builtin_prefetch(head->next, 0, 0);
        }
    }
}
```

The prefetch in the main loop tells the CPU to load `head->next` into cache while `process(head->data)` executes. By the time the loop advances to the next node, its data is already in cache. The initial loop advances `PREFETCH_DEPTH` nodes ahead to "warm up" the pipeline — without it, the first few iterations would still suffer cache misses.

The `PREFETCH_DEPTH` constant must be tuned experimentally. Too shallow, and the prefetch does not arrive in time. Too deep, and the prefetched data may be evicted before it is used (by the prefetches for subsequent nodes). On modern CPUs, a depth of 2–4 iterations ahead typically works well.

The benefit depends on the cost of `process` relative to memory latency. If `process` is fast (a few arithmetic operations), the prefetch may not have enough time to complete, and the effect is small. If `process` is moderately expensive (a few dozen cycles), the prefetch can hide most of the memory latency. If `process` is very expensive (thousands of cycles), the hardware may already hide the latency without software prefetching.

### Prefetching Traversal Orders

Sometimes the access pattern is known at compile time but is not sequential — for example, a tiled traversal of a matrix, a Morton-order (Z-order) curve, or a tree traversal with a known visitation order. In these cases, you can prefetch based on the computed address of the next access:

```cpp
void traverse_quadtree(QuadNode* node, double x, double y) {
    if (!node->is_leaf()) {
        int quadrant = determine_quadrant(x, y);
        QuadNode* child = node->children[quadrant];

        // Prefetch the child's data while we process this node
        __builtin_prefetch(child, 0, 3);

        // Also prefetch next sibling in case of backtracking
        int next_quadrant = (quadrant + 1) % 4;
        __builtin_prefetch(node->children[next_quadrant], 0, 1);

        traverse_quadtree(child, x, y);
    } else {
        process(node->data);
    }
}
```

This technique is specific to the data structure and traversal order. It requires the programmer to understand exactly which nodes will be accessed next and in what order — which is possible for deterministic traversals of known data structures but not for arbitrary graph traversals.

### Prefetching for Random Access

When you know the access pattern in advance (e.g., you have an array of indices to process in a known order), you can prefetch ahead by indexing into the data array:

```cpp
void gather_with_prefetch(const float* data, const int* indices,
                          float* output, size_t n) {
    // Prefetch ahead
    const size_t prefetch_distance = 8;

    for (size_t i = 0; i < n; ++i) {
        // Prefetch future random accesses
        if (i + prefetch_distance < n) {
            __builtin_prefetch(&data[indices[i + prefetch_distance]], 0, 0);
        }

        output[i] = data[indices[i]];
    }
}
```

This is effective when the index array itself is in cache (so reading `indices[i+8]` does not itself cause a miss) and when the random accesses from `data` would otherwise be independent misses. By clustering the prefetches, you hide the latency of multiple random loads behind the processing of earlier results.

The technique works best when `prefetch_distance` is large enough to overlap with memory latency but small enough that the prefetched data is not evicted by subsequent prefetches. Tuning the distance is the central challenge.

### Non-Temporal Stores

Prefetching is about bringing data *into* cache. The opposite operation — writing data that will not be read again soon — also benefits from a cache hint. A non-temporal store (e.g., `_mm_stream_si32` or `_mm_stream_ps`) writes data directly to memory without loading the cache line first, avoiding cache pollution:

```cpp
#include <xmmintrin.h>

void write_stream(float* dest, const float* src, size_t n) {
    // Non-temporal stores: bypass cache for the output
    for (size_t i = 0; i < n; i += 4) {
        __m128 data = _mm_load_ps(&src[i]);
        _mm_stream_ps(&dest[i], data);  // Write directly to memory
    }
}
```

Without `_mm_stream_ps`, the store instruction first loads the destination cache line into L1 (a *read-for-ownership*), modifies it in place, and eventually writes it back. If the destination is large and will not be re-read soon, the initial load is wasted work and it pollutes the cache. The non-temporal store eliminates the initial load, writing directly to the write-combining buffer and main memory.

This pattern is most beneficial for large (greater than L3 cache size) sequential writes — for example, computing a large frame buffer, generating a large particle output, or copying a large array to a destination that will not be read by the same core. For small or frequently re-read buffers, non-temporal stores can hurt because subsequent reads must fetch from main memory instead of cache.

### Prefetching in Practice

The general principle for software prefetching is: do not guess, measure. The hardware prefetcher is already excellent at sequential and simple strided patterns. Adding explicit prefetch to such loops adds instruction overhead and can even hurt by consuming instruction decode bandwidth or by prefetching past the end of an array (causing a page fault on some platforms).

Software prefetching is most useful in three scenarios:

1. **Pointer-chasing data structures** (linked lists, trees, hash chains) where the hardware cannot predict the next address.
2. **Irregular but known-access patterns** (random lookups with known indices, tiled traversals, stencil operations) where the addresses of future accesses can be computed ahead of time.
3. **Streaming writes** where non-temporal stores can avoid cache pollution for large output buffers.

In all cases, the prefetch distance must be tuned. Too short: the data arrives too late (the CPU stalls anyway). Too long: the prefetched data is evicted before use, or the prefetch itself consumes memory bandwidth that could serve demand loads.

A good starting distance on modern CPUs is 8–16 cache lines ahead for sequential access (which the hardware prefetcher already handles) and 2–4 nodes ahead for linked structures. Profiling with hardware counters (`perf stat -e cache-misses,prefetch-misses` on Linux) can guide the tuning.

### The Cost of Prefetching

Every prefetch instruction consumes a slot in the CPU's issue queue and may trigger a page walk if the address is not resident in the TLB. Issuing a prefetch to an invalid address (past the end of a valid mapping) can cause a fault on some architectures (though on x86, it is silently ignored). The instruction also consumes decode and execution bandwidth.

For these reasons, software prefetching should be applied only to hot loops that are already measured to be memory-bound. Applying prefetch speculatively throughout a codebase adds code complexity and can degrade performance. As with all optimizations in this chapter, measurement comes first.

### Summary

Cache-friendly programming is not about exotic tricks — it is about understanding the hardware model and arranging data to fit it. Data-oriented design reorients problem decomposition around data flow rather than object interactions. Cache line alignment and false sharing mitigation ensure that threads do not inadvertently compete for the same cache line. The SoA vs AoS choice determines whether each cache line fetched contains useful data or wasteful padding. And memory prefetching, both hardware and software, hides the latency of fetching data that the program is about to use.

The unifying theme across all four sections is that memory, not computation, is the bottleneck — and that small changes to data layout can yield larger performance gains than algorithmic improvements. A better algorithm that touches memory randomly can be slower than a worse algorithm that accesses memory sequentially. The implications of this fact extend beyond the four patterns in this chapter: they should inform how you design every data structure, every interface, and every hot loop in performance-sensitive C++.

## Exercises

1. **Hot/cold splitting**: Take a struct with at least 8 fields, identify which are accessed together in a hot loop, and split it into hot and cold parts. Measure the throughput improvement for the hot loop.

2. **False sharing reproduction**: Write a multi-threaded program with two threads incrementing adjacent `int` variables. Measure the throughput with and without `alignas(64)` padding. Vary the number of threads to observe the scaling difference.

3. **AoS vs SoA benchmark**: Implement a particle simulation (position + velocity + mass + lifetime) in both AoS and SoA layouts. Benchmark update and render throughput for 10,000, 100,000, and 1,000,000 particles. Identify the crossover point where SoA overtakes AoS.

4. **Linked list prefetching**: Implement a singly linked list traversal. Compare the performance of a naive traversal with a version that uses `__builtin_prefetch` one node ahead. Measure the cache miss rate using `perf stat -e cache-misses`.

5. **Non-temporal stores**: Implement a large buffer copy using `memcpy`, `std::copy`, and `_mm_stream_ps` (with appropriate alignment). Measure the throughput and L1 cache miss rate for a buffer size of 100 MB. Explain the difference in cache behavior.
