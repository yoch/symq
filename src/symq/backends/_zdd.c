/* Native core of the monomial ZDD (CPython extension, C API only).
 *
 * Same structure and recursions as ``symq.backends.zdd``: node 0 is the empty family, node 1
 * is {empty set}, nodes are hash-consed on (level, lo, hi), and the Boolean-ring product uses
 * PQ = P0Q0 + v(P0Q1 + P1Q0 + P1Q1). Exact: no garbage collection, no reordering, no
 * approximation. Budgets raise ``symq.resources.ResourceLimitExceeded`` like the Python guard.
 *
 * Invariants relied upon below:
 *   - children always have smaller ids than their parent, so any bottom-up quantity (term
 *     count, minimum monomial) can be computed in id order without recursion;
 *   - node ids are plain Python ints, so values stay comparable with the rest of the package;
 *   - no raw node pointer survives a call that can grow the table (reallocation).
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define NODE_NONE UINT32_MAX
#define MAX_WIDTH 64

typedef struct {
    uint32_t lo;
    uint32_t hi;
    uint32_t level;
    uint32_t pad;
    uint64_t var; /* variable bit mask of this level (terminals: 0) */
} Node;

typedef struct {
    uint32_t a;
    uint32_t b;
    uint32_t value;
    uint32_t op; /* 0 = xor, 1 = product */
} CacheEntry;

typedef struct {
    PyObject_HEAD

    Node *nodes;
    uint32_t count;
    uint32_t capacity;
    uint32_t *hash; /* open addressing; slot holds node id + 1, 0 is empty */
    uint32_t hash_capacity;
    uint32_t hash_used;
    CacheEntry *cache;
    uint32_t cache_capacity;
    uint32_t cache_used;
    int64_t *terms;   /* monomial count per node, maintained on insert */
    uint32_t width;
    int32_t *level_of;
    uint32_t *order;

    double started;
    double deadline; /* absolute perf_counter deadline; 0.0: none */
    double budget_seconds;
    int64_t max_nodes;
    int64_t max_terms;
    uint64_t ticks;

    /* Error tracking for safe GIL-free execution */
    const char *error_resource;
    double error_limit;
    double error_observed;
    int error_nomem;
} Manager;

static PyTypeObject NativeZDDManagerType;

/* ------------------------------------------------------------------ time & guard */

#if defined(_WIN32)
#include <windows.h>
static inline double get_c_time(void)
{
    LARGE_INTEGER freq, counter;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart / (double)freq.QuadPart;
}
#else
#include <time.h>
static inline double get_c_time(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}
#endif

static int raise_limit(const char *resource, double limit, double observed)
{
    /* Imports nothing but symq.resources, so no node id is live across it. */
    PyObject *module = PyImport_ImportModule("symq.resources");
    PyObject *cls, *args, *exc;

    if (module == NULL) {
        return -1;
    }
    cls = PyObject_GetAttrString(module, "ResourceLimitExceeded");
    Py_DECREF(module);
    if (cls == NULL) {
        return -1;
    }
    if (strcmp(resource, "seconds") == 0) {
        args = Py_BuildValue("(sdd)", resource, limit, observed);
    } else {
        args = Py_BuildValue("(sLL)", resource, (long long)limit, (long long)observed);
    }
    if (args == NULL) {
        Py_DECREF(cls);
        return -1;
    }
    exc = PyObject_CallObject(cls, args);
    Py_DECREF(args);
    Py_DECREF(cls);
    if (exc == NULL) {
        return -1;
    }
    PyErr_SetObject((PyObject *)Py_TYPE(exc), exc);
    Py_DECREF(exc);
    return -1;
}

static inline int record_limit(Manager *m, const char *resource, double limit, double observed)
{
    m->error_resource = resource;
    m->error_limit = limit;
    m->error_observed = observed;
    return -1;
}

static inline int handle_manager_error(Manager *m)
{
    if (m->error_nomem) {
        m->error_nomem = 0;
        PyErr_NoMemory();
        return -1;
    }
    if (m->error_resource != NULL) {
        raise_limit(m->error_resource, m->error_limit, m->error_observed);
        m->error_resource = NULL;
        return -1;
    }
    if (!PyErr_Occurred()) {
        PyErr_SetString(PyExc_RuntimeError, "native zdd operation failed");
    }
    return -1;
}

static int check_time(Manager *m)
{
    double now;

    if (m->deadline == 0.0) {
        return 0;
    }
    now = get_c_time();
    if (now > m->deadline) {
        return record_limit(m, "seconds", m->budget_seconds, now - m->started);
    }
    return 0;
}

static inline int tick(Manager *m)
{
    if (((++m->ticks) & 0x3FF) == 0) {
        return check_time(m);
    }
    return 0;
}

/* ----------------------------------------------------------- unique table */

static inline uint32_t hash_key(uint32_t level, uint32_t lo, uint32_t hi)
{
    uint64_t h = ((uint64_t)level << 43) ^ ((uint64_t)lo << 22) ^ (uint64_t)hi;
    h ^= h >> 31;
    h *= UINT64_C(0x9E3779B97F4A7C15);
    h ^= h >> 29;
    return (uint32_t)h;
}

static int hash_rebuild(Manager *m, uint32_t capacity)
{
    uint32_t *table = calloc(capacity, sizeof(uint32_t));

    if (table == NULL) {
        m->error_nomem = 1;
        return -1;
    }
    for (uint32_t id = 2; id < m->count; id++) {
        const Node *node = &m->nodes[id];
        uint32_t mask = capacity - 1;
        uint32_t slot = hash_key(node->level, node->lo, node->hi) & mask;

        while (table[slot] != 0) {
            slot = (slot + 1) & mask;
        }
        table[slot] = id + 1;
    }
    free(m->hash);
    m->hash = table;
    m->hash_capacity = capacity;
    m->hash_used = m->count - 2;
    return 0;
}

static int grow_nodes(Manager *m)
{
    uint32_t capacity = m->capacity * 2;
    Node *nodes = realloc(m->nodes, (size_t)capacity * sizeof(Node));
    int64_t *terms;

    if (nodes == NULL) {
        m->error_nomem = 1;
        return -1;
    }
    m->nodes = nodes;
    terms = realloc(m->terms, (size_t)capacity * sizeof(int64_t));
    if (terms == NULL) {
        m->error_nomem = 1;
        return -1;
    }
    m->terms = terms;
    m->capacity = capacity;
    return 0;
}

static int mk(Manager *m, uint32_t level, uint32_t lo, uint32_t hi, uint32_t *out)
{
    const Node *node;
    uint32_t mask, slot;

    if (hi == 0) {
        *out = lo;
        return 0;
    }
    mask = m->hash_capacity - 1;
    slot = hash_key(level, lo, hi) & mask;
    for (;;) {
        uint32_t stored = m->hash[slot];

        if (stored == 0) {
            break;
        }
        node = &m->nodes[stored - 1];
        if (node->level == level && node->lo == lo && node->hi == hi) {
            *out = stored - 1;
            return 0;
        }
        slot = (slot + 1) & mask;
    }
    if (m->max_nodes > 0 && (int64_t)m->count + 1 > m->max_nodes) {
        return record_limit(m, "nodes", (double)m->max_nodes, (double)m->count + 1);
    }
    if (m->count == m->capacity && grow_nodes(m) < 0) {
        return -1;
    }
    if ((uint64_t)(m->hash_used + 1) * 4 >= (uint64_t)m->hash_capacity * 3) {
        if (hash_rebuild(m, m->hash_capacity * 2) < 0) {
            return -1;
        }
        mask = m->hash_capacity - 1;
        slot = hash_key(level, lo, hi) & mask;
        while (m->hash[slot] != 0) {
            slot = (slot + 1) & mask;
        }
    }
    m->nodes[m->count].level = level;
    m->nodes[m->count].var = UINT64_C(1) << m->order[level];
    m->nodes[m->count].lo = lo;
    m->nodes[m->count].hi = hi;
    m->terms[m->count] = m->terms[lo] + m->terms[hi];
    m->hash[slot] = m->count + 1;
    m->hash_used++;
    *out = m->count;
    m->count++;
    return 0;
}

/* ------------------------------------------------------------ op cache */

static inline uint32_t cache_hash(uint32_t op, uint32_t a, uint32_t b)
{
    uint64_t h = ((uint64_t)b << 33) ^ ((uint64_t)a << 2) ^ (uint64_t)op;
    h ^= h >> 30;
    h *= UINT64_C(0xBF58476D1CE4E5B9);
    h ^= h >> 27;
    return (uint32_t)h;
}

static CacheEntry *cache_slot(CacheEntry *table, uint32_t capacity, uint32_t op, uint32_t a,
                              uint32_t b)
{
    uint32_t mask = capacity - 1;
    uint32_t slot = cache_hash(op, a, b) & mask;

    while (table[slot].value != NODE_NONE) {
        if (table[slot].a == a && table[slot].b == b && table[slot].op == op) {
            break;
        }
        slot = (slot + 1) & mask;
    }
    return &table[slot];
}

static int cache_grow(Manager *m)
{
    uint32_t capacity = m->cache_capacity * 2;
    CacheEntry *table = malloc((size_t)capacity * sizeof(CacheEntry));

    if (table == NULL) {
        m->error_nomem = 1;
        return -1;
    }
    for (uint32_t i = 0; i < capacity; i++) {
        table[i].value = NODE_NONE;
    }
    for (uint32_t i = 0; i < m->cache_capacity; i++) {
        CacheEntry *old = &m->cache[i];

        if (old->value != NODE_NONE) {
            *cache_slot(table, capacity, old->op, old->a, old->b) = *old;
        }
    }
    free(m->cache);
    m->cache = table;
    m->cache_capacity = capacity;
    return 0;
}

static inline int cache_get(Manager *m, uint32_t op, uint32_t a, uint32_t b, uint32_t *out)
{
    CacheEntry *entry = cache_slot(m->cache, m->cache_capacity, op, a, b);

    if (entry->value == NODE_NONE) {
        return 0;
    }
    *out = entry->value;
    return 1;
}

static inline int cache_put(Manager *m, uint32_t op, uint32_t a, uint32_t b, uint32_t value)
{
    CacheEntry *entry;

    if ((uint64_t)(m->cache_used + 1) * 4 >= (uint64_t)m->cache_capacity * 3) {
        if (cache_grow(m) < 0) {
            return -1;
        }
    }
    entry = cache_slot(m->cache, m->cache_capacity, op, a, b);
    if (entry->value == NODE_NONE) {
        entry->a = a;
        entry->b = b;
        entry->op = op;
        entry->value = value;
        m->cache_used++;
    }
    return 0;
}

/* ------------------------------------------------------------- recursions */

/* Depth is bounded by the number of levels: every call strictly descends in the level of at
 * least one operand, and both operands are below the result level. */
static int xor_rec(Manager *m, uint32_t left, uint32_t right, uint32_t *out)
{
    uint32_t ll, lh, rl, rh, level, lo, hi;

    if (left == 0) {
        *out = right;
        return 0;
    }
    if (right == 0) {
        *out = left;
        return 0;
    }
    if (left == right) {
        *out = 0;
        return 0;
    }
    if (left > right) {
        uint32_t swap = left;
        left = right;
        right = swap;
    }
    if (cache_get(m, 0, left, right, out)) {
        return 0;
    }
    if (tick(m) < 0) {
        return -1;
    }
    ll = m->nodes[left].level;
    rl = m->nodes[right].level;
    if (ll == rl) {
        lh = m->nodes[left].hi;
        rh = m->nodes[right].hi;
        level = ll;
        if (xor_rec(m, m->nodes[left].lo, m->nodes[right].lo, &lo) < 0
            || xor_rec(m, lh, rh, &hi) < 0) {
            return -1;
        }
    } else if (ll < rl) {
        level = ll;
        if (xor_rec(m, m->nodes[left].lo, right, &lo) < 0) {
            return -1;
        }
        hi = m->nodes[left].hi;
    } else {
        level = rl;
        if (xor_rec(m, left, m->nodes[right].lo, &lo) < 0) {
            return -1;
        }
        hi = m->nodes[right].hi;
    }
    if (mk(m, level, lo, hi, out) < 0) {
        return -1;
    }
    return cache_put(m, 0, left, right, *out);
}

static int product_rec(Manager *m, uint32_t left, uint32_t right, uint32_t *out)
{
    uint32_t ll, rl, level, l0, l1, r0, r1, low, high, t1, t2, t3;

    if (left == 0 || right == 0) {
        *out = 0;
        return 0;
    }
    if (left == 1) {
        *out = right;
        return 0;
    }
    if (right == 1 || left == right) {
        *out = left;
        return 0;
    }
    if (left > right) {
        uint32_t swap = left;
        left = right;
        right = swap;
    }
    if (cache_get(m, 1, left, right, out)) {
        return 0;
    }
    if (tick(m) < 0) {
        return -1;
    }
    ll = m->nodes[left].level;
    rl = m->nodes[right].level;
    level = ll < rl ? ll : rl;
    if (ll == level) {
        l0 = m->nodes[left].lo;
        l1 = m->nodes[left].hi;
    } else {
        l0 = left;
        l1 = 0;
    }
    if (rl == level) {
        r0 = m->nodes[right].lo;
        r1 = m->nodes[right].hi;
    } else {
        r0 = right;
        r1 = 0;
    }
    if (product_rec(m, l0, r0, &low) < 0 || product_rec(m, l0, r1, &t1) < 0
        || product_rec(m, l1, r0, &t2) < 0 || product_rec(m, l1, r1, &t3) < 0) {
        return -1;
    }
    if (xor_rec(m, t1, t2, &t1) < 0 || xor_rec(m, t1, t3, &high) < 0) {
        return -1;
    }
    if (mk(m, level, low, high, out) < 0) {
        return -1;
    }
    return cache_put(m, 1, left, right, *out);
}

/* --------------------------------------------------------- construction */

static int build_rec(Manager *m, uint64_t *terms, uint32_t count, uint32_t level,
                     uint32_t *out)
{
    uint32_t split = 0, lo, hi;
    uint64_t bit;

    if (count == 0) {
        *out = 0;
        return 0;
    }
    if (level >= m->width) {
        *out = 1;
        return 0;
    }
    bit = UINT64_C(1) << m->order[level];
    for (uint32_t i = 0; i < count; i++) {
        if (terms[i] & bit) {
            split++;
        }
    }
    if (split == 0) {
        return build_rec(m, terms, count, level + 1, out);
    }
    if (split == count) {
        for (uint32_t i = 0; i < count; i++) {
            terms[i] ^= bit;
        }
        if (build_rec(m, terms, count, level + 1, &lo) < 0) {
            return -1;
        }
        if (lo == 0) {
            *out = 0;
            return 0;
        }
        return mk(m, level, 0, lo, out);
    }    {
        uint64_t *lower = malloc((size_t)(count - split) * sizeof(uint64_t));
        uint64_t *upper = malloc((size_t)split * sizeof(uint64_t));

        if (lower == NULL || upper == NULL) {
            free(lower);
            free(upper);
            PyErr_NoMemory();
            return -1;
        }
        for (uint32_t i = 0, a = 0, b = 0; i < count; i++) {
            if (terms[i] & bit) {
                upper[b++] = terms[i] ^ bit;
            } else {
                lower[a++] = terms[i];
            }
        }
        if (build_rec(m, lower, count - split, level + 1, &lo) < 0
            || build_rec(m, upper, split, level + 1, &hi) < 0) {
            free(lower);
            free(upper);
            return -1;
        }
        free(lower);
        free(upper);
        return mk(m, level, lo, hi, out);
    }
}

/* ------------------------------------------------------------- methods */

static Manager *manager_alloc(void)
{
    Manager *m = PyObject_New(Manager, &NativeZDDManagerType);

    if (m == NULL) {
        return NULL;
    }
    m->nodes = NULL;
    m->count = 0;
    m->capacity = 0;
    m->hash = NULL;
    m->hash_capacity = 0;
    m->hash_used = 0;
    m->cache = NULL;
    m->cache_capacity = 0;
    m->cache_used = 0;
    m->terms = NULL;
    m->width = 0;
    m->level_of = NULL;
    m->order = NULL;
    m->started = 0.0;
    m->deadline = 0.0;
    m->budget_seconds = 0.0;
    m->max_nodes = 0;
    m->max_terms = 0;
    m->ticks = 0;
    m->error_resource = NULL;
    m->error_limit = 0.0;
    m->error_observed = 0.0;
    m->error_nomem = 0;
    return m;
}

static void manager_clear(Manager *m)
{
    free(m->nodes);
    free(m->hash);
    free(m->cache);
    free(m->terms);
    free(m->level_of);
    free(m->order);
    m->nodes = NULL;
    m->hash = NULL;
    m->cache = NULL;
    m->terms = NULL;
    m->level_of = NULL;
    m->order = NULL;
}

static void manager_dealloc(PyObject *self)
{
    manager_clear((Manager *)self);
    PyObject_Del(self);
}

static PyObject *manager_new(PyTypeObject *type, PyObject *args, PyObject *kwargs)
{
    static char *keywords[] = {"width",    "order",     "deadline", "started",
                               "max_seconds", "max_nodes", "max_terms", NULL};
    int width = 0;
    PyObject *order_obj = Py_None;
    double deadline = 0.0, started = 0.0, max_seconds = 0.0;
    long long max_nodes = 0, max_terms = 0;
    Manager *m;
    unsigned char *seen = NULL;

    (void)type;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "i|OdddLL:NativeZDDManager", keywords,
                                     &width, &order_obj, &deadline, &started, &max_seconds,
                                     &max_nodes, &max_terms)) {
        return NULL;
    }
    if (width < 1 || width > MAX_WIDTH) {
        PyErr_Format(PyExc_ValueError, "width must be between 1 and %d", MAX_WIDTH);
        return NULL;
    }
    m = manager_alloc();
    if (m == NULL) {
        return NULL;
    }
    m->width = (uint32_t)width;
    m->capacity = 32;
    m->hash_capacity = 128;
    m->cache_capacity = 2048;
    m->nodes = malloc((size_t)m->capacity * sizeof(Node));
    m->hash = calloc(m->hash_capacity, sizeof(uint32_t));
    m->cache = malloc((size_t)m->cache_capacity * sizeof(CacheEntry));
    m->terms = malloc((size_t)m->capacity * sizeof(int64_t));
    m->level_of = malloc((size_t)width * sizeof(int32_t));
    m->order = malloc((size_t)width * sizeof(uint32_t));
    if (m->nodes == NULL || m->hash == NULL || m->cache == NULL || m->terms == NULL
        || m->level_of == NULL || m->order == NULL) {
        PyErr_NoMemory();
        Py_DECREF(m);
        return NULL;
    }
    for (uint32_t i = 0; i < m->cache_capacity; i++) {
        m->cache[i].value = NODE_NONE;
    }
    memset(m->nodes, 0, (size_t)m->capacity * sizeof(Node));
    /* Terminals sit below every level; the Python backend uses ``width`` for them and the
     * recursions rely on that ordering. */
    m->nodes[0].level = (uint32_t)width;
    m->nodes[1].level = (uint32_t)width;
    m->terms[0] = 0;
    m->terms[1] = 1;
    m->count = 2;
    m->hash_used = 0;
    m->max_nodes = max_nodes;
    m->max_terms = max_terms;
    if (order_obj == Py_None) {
        for (uint32_t i = 0; i < m->width; i++) {
            m->order[i] = i;
        }
    } else {
        PyObject *fast = PySequence_Fast(order_obj, "order must be a sequence of ints");
        Py_ssize_t n;

        if (fast == NULL) {
            Py_DECREF(m);
            return NULL;
        }
        n = PySequence_Fast_GET_SIZE(fast);
        if (n != (Py_ssize_t)width) {
            Py_DECREF(fast);
            Py_DECREF(m);
            PyErr_SetString(PyExc_ValueError, "order must be a permutation of the variables");
            return NULL;
        }
        seen = calloc((size_t)width, 1);
        if (seen == NULL) {
            Py_DECREF(fast);
            Py_DECREF(m);
            PyErr_NoMemory();
            return NULL;
        }
        for (Py_ssize_t level = 0; level < n; level++) {
            long variable = PyLong_AsLong(PySequence_Fast_GET_ITEM(fast, level));

            if (variable < 0 || variable >= width || seen[variable]) {
                if (!PyErr_Occurred()) {
                    PyErr_SetString(PyExc_ValueError,
                                    "order must be a permutation of the variables");
                }
                free(seen);
                Py_DECREF(fast);
                Py_DECREF(m);
                return NULL;
            }
            seen[variable] = 1;
            m->order[level] = (uint32_t)variable;
        }
        free(seen);
        Py_DECREF(fast);
    }
    for (uint32_t level = 0; level < m->width; level++) {
        m->level_of[m->order[level]] = (int32_t)level;
    }
    if (deadline > 0.0) {
        m->started = started;
        m->deadline = deadline;
        m->budget_seconds = max_seconds;
    }
    return (PyObject *)m;
}

static int parse_node(Manager *m, PyObject *arg, uint32_t *out)
{
    unsigned long value = PyLong_AsUnsignedLong(arg);

    if (value == (unsigned long)-1 && PyErr_Occurred()) {
        return -1;
    }
    if (value >= m->count) {
        PyErr_SetString(PyExc_ValueError, "node id outside this manager");
        return -1;
    }
    *out = (uint32_t)value;
    return 0;
}

static PyObject *manager_variable(Manager *m, PyObject *arg)
{
    long index = PyLong_AsLong(arg);
    uint32_t out;

    if (index == -1 && PyErr_Occurred()) {
        return NULL;
    }
    if (index < 0 || index >= (long)m->width) {
        PyErr_SetString(PyExc_ValueError, "variable index outside algebra width");
        return NULL;
    }
    if (mk(m, (uint32_t)m->level_of[index], 0, 1, &out) < 0) {
        handle_manager_error(m);
        return NULL;
    }
    return PyLong_FromUnsignedLong(out);
}

static PyObject *manager_xor(Manager *m, PyObject *args)
{
    unsigned long left, right;
    uint32_t out;
    int status;

    if (!PyArg_ParseTuple(args, "kk:xor", &left, &right)) {
        return NULL;
    }
    if (left >= m->count || right >= m->count) {
        PyErr_SetString(PyExc_ValueError, "node id outside this manager");
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    status = xor_rec(m, (uint32_t)left, (uint32_t)right, &out);
    Py_END_ALLOW_THREADS
    if (status < 0) {
        handle_manager_error(m);
        return NULL;
    }
    return PyLong_FromUnsignedLong(out);
}

static PyObject *manager_product(Manager *m, PyObject *args)
{
    unsigned long left, right;
    uint32_t out;
    int status;

    if (!PyArg_ParseTuple(args, "kk:product", &left, &right)) {
        return NULL;
    }
    if (left >= m->count || right >= m->count) {
        PyErr_SetString(PyExc_ValueError, "node id outside this manager");
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS
    status = product_rec(m, (uint32_t)left, (uint32_t)right, &out);
    Py_END_ALLOW_THREADS
    if (status < 0) {
        handle_manager_error(m);
        return NULL;
    }
    return PyLong_FromUnsignedLong(out);
}

static PyObject *manager_terms(Manager *m, PyObject *arg)
{
    uint32_t node;

    if (parse_node(m, arg, &node) < 0) {
        return NULL;
    }
    return PyLong_FromLongLong(m->terms[node]);
}

static PyObject *manager_anf(Manager *m, PyObject *arg)
{
    uint32_t node;
    uint32_t capacity, used = 0;
    uint32_t *stack_nodes;
    uint64_t *stack_masks;
    PyObject *result;

    if (parse_node(m, arg, &node) < 0) {
        return NULL;
    }
    if (m->max_terms > 0 && m->terms[node] > m->max_terms) {
        if (raise_limit("terms", (double)m->max_terms, (double)m->terms[node]) < 0) {
            return NULL;
        }
    }
    result = PyFrozenSet_New(NULL);
    if (result == NULL) {
        return NULL;
    }
    if (node < 2) {
        if (node == 1) {
            PyObject *item = PyLong_FromLong(0);

            if (item == NULL || PySet_Add(result, item) < 0) {
                Py_XDECREF(item);
                Py_CLEAR(result);
                return NULL;
            }
            Py_DECREF(item);
        }
        return result;
    }
    capacity = 64;
    stack_nodes = malloc((size_t)capacity * sizeof(uint32_t));
    stack_masks = malloc((size_t)capacity * sizeof(uint64_t));
    if (stack_nodes == NULL || stack_masks == NULL) {
        free(stack_nodes);
        free(stack_masks);
        Py_CLEAR(result);
        PyErr_NoMemory();
        return NULL;
    }
    stack_nodes[0] = node;
    stack_masks[0] = 0;
    used = 1;
    while (used > 0) {
        uint32_t current;
        uint64_t mask;
        PyObject *item;

        used--;
        current = stack_nodes[used];
        mask = stack_masks[used];
        if (current == 0) {
            continue;
        }
        if (current == 1) {
            item = PyLong_FromUnsignedLongLong(mask);
            if (item == NULL || PySet_Add(result, item) < 0) {
                Py_XDECREF(item);
                free(stack_nodes);
                free(stack_masks);
                Py_CLEAR(result);
                return NULL;
            }
            Py_DECREF(item);
            continue;
        }
        if (used + 2 > capacity) {
            uint32_t bigger = capacity * 2;
            uint32_t *nodes = realloc(stack_nodes, (size_t)bigger * sizeof(uint32_t));
            uint64_t *masks;

            if (nodes != NULL) {
                stack_nodes = nodes;
            }
            masks = realloc(stack_masks, (size_t)bigger * sizeof(uint64_t));
            if (masks != NULL) {
                stack_masks = masks;
            }
            if (nodes == NULL || masks == NULL) {
                free(stack_nodes);
                free(stack_masks);
                Py_CLEAR(result);
                PyErr_NoMemory();
                return NULL;
            }
            capacity = bigger;
        }
        stack_nodes[used] = m->nodes[current].lo;
        stack_masks[used] = mask;
        used++;
        stack_nodes[used] = m->nodes[current].hi;
        stack_masks[used] = mask | m->nodes[current].var;
        used++;
    }
    free(stack_nodes);
    free(stack_masks);
    return result;
}

static int compare_uint64(const void *left, const void *right)
{
    uint64_t a = *(const uint64_t *)left;
    uint64_t b = *(const uint64_t *)right;

    return (a > b) - (a < b);
}

static PyObject *manager_from_terms(Manager *m, PyObject *arg)
{
    PyObject *fast = PySequence_Fast(arg, "terms must be a sequence of monomial masks");
    Py_ssize_t n;
    uint64_t *terms = NULL;
    uint32_t count = 0, out = 0;

    if (fast == NULL) {
        return NULL;
    }
    n = PySequence_Fast_GET_SIZE(fast);
    if (n > 0) {
        terms = malloc((size_t)n * sizeof(uint64_t));
        if (terms == NULL) {
            Py_DECREF(fast);
            PyErr_NoMemory();
            return NULL;
        }
    }
    for (Py_ssize_t i = 0; i < n; i++) {
        unsigned long long term =
            PyLong_AsUnsignedLongLong(PySequence_Fast_GET_ITEM(fast, i));

        if (term == (unsigned long long)-1 && PyErr_Occurred()) {
            free(terms);
            Py_DECREF(fast);
            return NULL;
        }
        if (term >> m->width) {
            free(terms);
            Py_DECREF(fast);
            PyErr_SetString(PyExc_ValueError, "monomial outside algebra width");
            return NULL;
        }
        terms[count++] = (uint64_t)term;
    }
    Py_DECREF(fast);
    if (count > 0) {
        qsort(terms, (size_t)count, sizeof(uint64_t), compare_uint64);
        /* Duplicates would need parity cancellation; the caller passes distinct masks. */
        {
            uint32_t unique = 1;

            for (uint32_t i = 1; i < count; i++) {
                if (terms[i] != terms[unique - 1]) {
                    terms[unique++] = terms[i];
                }
            }
            count = unique;
        }
        if (build_rec(m, terms, count, 0, &out) < 0) {
            free(terms);
            handle_manager_error(m);
            return NULL;
        }
    }
    free(terms);
    return PyLong_FromUnsignedLong(out);
}

static PyObject *manager_min_monomial(Manager *m, PyObject *arg)
{
    uint32_t node;

    if (parse_node(m, arg, &node) < 0) {
        return NULL;
    }
    if (node < 2) {
        if (node == 0) {
            Py_RETURN_NONE;
        }
        return PyLong_FromLong(0);
    }
    /* Children have smaller ids, so one ascending pass gives every node its minimum-degree
     * monomial, compared as (degree, mask) like the Python implementation. */
    {
        uint32_t *degrees = malloc((size_t)m->count * sizeof(uint32_t));
        uint64_t *masks = malloc((size_t)m->count * sizeof(uint64_t));
        uint32_t degree;
        uint64_t mask;

        if (degrees == NULL || masks == NULL) {
            free(degrees);
            free(masks);
            PyErr_NoMemory();
            return NULL;
        }
        degrees[0] = UINT32_MAX;
        masks[0] = 0;
        degrees[1] = 0;
        masks[1] = 0;
        for (uint32_t id = 2; id <= node; id++) {
            const Node *current = &m->nodes[id];
            uint32_t hi_degree = degrees[current->hi];
            uint64_t hi_mask = masks[current->hi] | (uint64_t)current->var;
            uint32_t best;

            if (hi_degree == UINT32_MAX) {
                best = UINT32_MAX;
            } else {
                best = hi_degree + 1;
            }
            if (current->lo != 0) {
                uint32_t lo_degree = degrees[current->lo];
                uint64_t lo_mask = masks[current->lo];

                if (lo_degree < best || (lo_degree == best && lo_mask < hi_mask)) {
                    best = lo_degree;
                    masks[id] = lo_mask;
                    degrees[id] = best;
                    continue;
                }
            }
            degrees[id] = best;
            masks[id] = hi_mask;
        }
        degree = degrees[node];
        mask = masks[node];
        free(degrees);
        free(masks);
        if (degree == UINT32_MAX) {
            Py_RETURN_NONE;
        }
        return PyLong_FromUnsignedLongLong(mask);
    }
}

static PyObject *manager_size(Manager *m, PyObject *arg)
{
    uint32_t node;
    unsigned char *seen;
    uint32_t *stack;
    uint32_t used = 0, visited = 0;

    if (parse_node(m, arg, &node) < 0) {
        return NULL;
    }
    if (node < 2) {
        return PyLong_FromLong(0);
    }
    seen = calloc((size_t)m->count, 1);
    stack = malloc((size_t)m->count * sizeof(uint32_t));
    if (seen == NULL || stack == NULL) {
        free(seen);
        free(stack);
        PyErr_NoMemory();
        return NULL;
    }
    stack[used++] = node;
    while (used > 0) {
        uint32_t current = stack[--used];

        if (current < 2 || seen[current]) {
            continue;
        }
        seen[current] = 1;
        visited++;
        stack[used++] = m->nodes[current].lo;
        stack[used++] = m->nodes[current].hi;
    }
    free(stack);
    free(seen);
    return PyLong_FromUnsignedLong(visited);
}

static PyObject *manager_node_count(Manager *m, PyObject *unused)
{
    /* Same definition as the Python backend: internal nodes in the unique table. */
    (void)unused;
    return PyLong_FromUnsignedLong(m->count - 2);
}

typedef struct {
    Py_buffer view;
    int has_view;
    uint32_t *allocated;
    const uint32_t *data;
    Py_ssize_t size;
} BufferReader;

static int buffer_reader_init(BufferReader *reader, PyObject *obj, const char *name)
{
    reader->has_view = 0;
    reader->allocated = NULL;
    reader->data = NULL;
    reader->size = 0;

    if (PyObject_GetBuffer(obj, &reader->view, PyBUF_SIMPLE) == 0) {
        if (reader->view.len % sizeof(uint32_t) != 0) {
            PyBuffer_Release(&reader->view);
            PyErr_Format(PyExc_ValueError, "%s buffer size must be a multiple of %zu bytes",
                         name, sizeof(uint32_t));
            return -1;
        }
        reader->has_view = 1;
        reader->data = (const uint32_t *)reader->view.buf;
        reader->size = reader->view.len / sizeof(uint32_t);
        return 0;
    }
    PyErr_Clear();

    PyObject *fast = PySequence_Fast(obj, name);
    if (fast == NULL) {
        return -1;
    }
    reader->size = PySequence_Fast_GET_SIZE(fast);
    if (reader->size > 0) {
        reader->allocated = malloc((size_t)reader->size * sizeof(uint32_t));
        if (reader->allocated == NULL) {
            Py_DECREF(fast);
            PyErr_NoMemory();
            return -1;
        }
        for (Py_ssize_t i = 0; i < reader->size; i++) {
            long value = PyLong_AsLong(PySequence_Fast_GET_ITEM(fast, i));
            if (value < 0 || (unsigned long)value > UINT32_MAX) {
                if (!PyErr_Occurred()) {
                    PyErr_Format(PyExc_ValueError, "value outside uint32 range");
                }
                free(reader->allocated);
                reader->allocated = NULL;
                Py_DECREF(fast);
                return -1;
            }
            reader->allocated[i] = (uint32_t)value;
        }
    }
    Py_DECREF(fast);
    reader->data = reader->allocated;
    return 0;
}

static void buffer_reader_cleanup(BufferReader *reader)
{
    if (reader->has_view) {
        PyBuffer_Release(&reader->view);
        reader->has_view = 0;
    }
    if (reader->allocated != NULL) {
        free(reader->allocated);
        reader->allocated = NULL;
    }
}

/* Applies a batch of X/CX/MCX gates to a state list and returns the new state. ``controls``
 * and ``offsets`` delimit the control indices of each gate in the flat ``control_indices``
 * array. Uses the buffer protocol when available for zero-copy arguments and releases the GIL
 * during the simulation loop to allow multi-core concurrency. */
static PyObject *manager_simulate(Manager *m, PyObject *args)
{
    PyObject *state_obj, *indices_obj, *offsets_obj, *targets_obj;
    BufferReader reader_state = {0}, reader_indices = {0}, reader_offsets = {0}, reader_targets = {0};
    PyObject *result = NULL;
    uint32_t state[MAX_WIDTH];
    uint32_t order[MAX_WIDTH];
    Py_ssize_t nstate, nindices, ngates;
    int64_t peak_terms = -1;
    int sim_status = 0;

    if (!PyArg_ParseTuple(args, "OOOO:simulate", &state_obj, &indices_obj, &offsets_obj,
                          &targets_obj)) {
        return NULL;
    }
    if (buffer_reader_init(&reader_state, state_obj, "state must be a sequence of node ids") < 0) {
        goto done;
    }
    if (buffer_reader_init(&reader_indices, indices_obj, "control indices must be a sequence") < 0) {
        goto done;
    }
    if (buffer_reader_init(&reader_offsets, offsets_obj, "offsets must be a sequence") < 0) {
        goto done;
    }
    if (buffer_reader_init(&reader_targets, targets_obj, "targets must be a sequence") < 0) {
        goto done;
    }

    nstate = reader_state.size;
    nindices = reader_indices.size;
    ngates = reader_targets.size;

    if (nstate != (Py_ssize_t)m->width) {
        PyErr_SetString(PyExc_ValueError, "state length must equal the manager width");
        goto done;
    }
    if (reader_offsets.size != ngates + 1) {
        PyErr_SetString(PyExc_ValueError, "offsets must have one more entry than gates");
        goto done;
    }
    for (Py_ssize_t i = 0; i < nstate; i++) {
        uint32_t value = reader_state.data[i];
        if (value >= m->count) {
            PyErr_SetString(PyExc_ValueError, "node id outside this manager");
            goto done;
        }
        state[i] = value;
    }
    for (Py_ssize_t i = 0; i < nindices; i++) {
        if (reader_indices.data[i] >= m->width) {
            PyErr_SetString(PyExc_ValueError, "control outside algebra width");
            goto done;
        }
    }

    const uint32_t *c_offsets = reader_offsets.data;
    const uint32_t *c_targets = reader_targets.data;
    const uint32_t *c_indices = reader_indices.data;

    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t gate = 0; gate < ngates; gate++) {
        uint32_t start = c_offsets[gate];
        uint32_t stop = c_offsets[gate + 1];
        uint32_t target = c_targets[gate];
        uint32_t control = 1;
        uint32_t updated;

        if (((gate + 1) & 63) == 0 && check_time(m) < 0) {
            sim_status = -1;
            break;
        }
        if (stop < start || (Py_ssize_t)stop > nindices || target >= m->width) {
            sim_status = -2;
            break;
        }
        if (stop > start) {
            uint32_t count = stop - start;
            if (count > MAX_WIDTH) {
                sim_status = -2;
                break;
            }
            for (uint32_t i = 0; i < count; i++) {
                order[i] = i;
            }
            for (uint32_t i = 1; i < count; i++) {
                uint32_t position = order[i];
                int64_t weight = m->terms[state[c_indices[start + position]]];
                uint32_t j = i;

                while (j > 0 && m->terms[state[c_indices[start + order[j - 1]]]] > weight) {
                    order[j] = order[j - 1];
                    j--;
                }
                order[j] = position;
            }
            for (uint32_t i = 0; i < count; i++) {
                uint32_t slot = order[i];

                if (product_rec(m, control, state[c_indices[start + slot]], &control) < 0) {
                    sim_status = -1;
                    break;
                }
            }
            if (sim_status < 0) {
                break;
            }
        }
        if (xor_rec(m, state[target], control, &updated) < 0) {
            sim_status = -1;
            break;
        }
        state[target] = updated;
        int64_t wire_terms = m->terms[updated];
        if (wire_terms > peak_terms) {
            peak_terms = wire_terms;
        }
    }
    Py_END_ALLOW_THREADS

    if (sim_status == -2) {
        PyErr_SetString(PyExc_ValueError, "gate description outside bounds");
        goto done;
    }
    if (sim_status == -1) {
        handle_manager_error(m);
        goto done;
    }

    PyObject *list_obj = PyList_New(nstate);
    if (list_obj == NULL) {
        goto done;
    }
    for (Py_ssize_t i = 0; i < nstate; i++) {
        PyObject *item = PyLong_FromUnsignedLong(state[i]);
        if (item == NULL) {
            Py_DECREF(list_obj);
            goto done;
        }
        PyList_SET_ITEM(list_obj, i, item);
    }
    PyObject *peak_obj = (peak_terms >= 0)
        ? PyLong_FromLongLong(peak_terms)
        : (Py_INCREF(Py_None), Py_None);
    if (peak_obj == NULL) {
        Py_DECREF(list_obj);
        goto done;
    }
    result = PyTuple_Pack(2, list_obj, peak_obj);
    Py_DECREF(list_obj);
    Py_DECREF(peak_obj);

done:
    buffer_reader_cleanup(&reader_state);
    buffer_reader_cleanup(&reader_indices);
    buffer_reader_cleanup(&reader_offsets);
    buffer_reader_cleanup(&reader_targets);
    return result;
}

static PyMethodDef manager_methods[] = {
    {"variable", (PyCFunction)manager_variable, METH_O, "Node id of a variable."},
    {"xor", (PyCFunction)manager_xor, METH_VARARGS, "XOR of two node ids."},
    {"product", (PyCFunction)manager_product, METH_VARARGS, "Boolean-ring product of two nodes."},
    {"simulate", (PyCFunction)manager_simulate, METH_VARARGS,
     "Apply a batch of controlled-X gates to a state; returns the new state."},
    {"terms", (PyCFunction)manager_terms, METH_O, "Number of monomials."},
    {"anf", (PyCFunction)manager_anf, METH_O, "Frozenset of monomial masks."},
    {"from_terms", (PyCFunction)manager_from_terms, METH_O, "Build from distinct masks."},
    {"min_monomial", (PyCFunction)manager_min_monomial, METH_O,
     "Minimum-degree monomial mask, or None for zero."},
    {"size", (PyCFunction)manager_size, METH_O, "Number of reachable internal nodes."},
    {"node_count", (PyCFunction)manager_node_count, METH_NOARGS, "Internal nodes in the table."},
    {NULL, NULL, 0, NULL},
};

static PyTypeObject NativeZDDManagerType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "symq.backends._zdd.NativeZDDManager",
    .tp_basicsize = sizeof(Manager),
    .tp_dealloc = manager_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "Exact monomial ZDD manager (native core of the zdd backends).",
    .tp_methods = manager_methods,
    .tp_new = manager_new,
};

static struct PyModuleDef zdd_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "symq.backends._zdd",
    .m_doc = "Native monomial ZDD used by symq.backends.zdd_native.",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit__zdd(void)
{
    PyObject *module;

    if (PyType_Ready(&NativeZDDManagerType) < 0) {
        return NULL;
    }
    module = PyModule_Create(&zdd_module);
    if (module == NULL) {
        return NULL;
    }
    Py_INCREF(&NativeZDDManagerType);
    if (PyModule_AddObject(module, "NativeZDDManager", (PyObject *)&NativeZDDManagerType) < 0) {
        Py_DECREF(&NativeZDDManagerType);
        Py_DECREF(module);
        return NULL;
    }
    return module;
}
