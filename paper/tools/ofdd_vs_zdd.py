"""Exhaustively check that, for a fixed variable order, the reduced positive-Davio
OFDD of f (pD-deletion: drop a node whose Davio/high child is the 0-terminal,
plus merging of isomorphic nodes) is the same graph as the ZDD of the monomial set
of f's ANF (positive-polarity Reed-Muller form)."""
from itertools import product


def anf_monomials(tt, n):
    """Moebius transform of a truth table (index bit i = x_i) -> set of monomials (frozensets)."""
    a = list(tt)
    for i in range(n):
        for m in range(1 << n):
            if m >> i & 1:
                a[m] ^= a[m ^ (1 << i)]
    return {frozenset(i for i in range(n) if m >> i & 1) for m in range(1 << n) if a[m]}


class Store:
    def __init__(self):
        self.table = {}

    def mk(self, var, lo, hi):
        if hi == 0:  # pD-deletion == zero-suppression
            return lo
        key = (var, lo, hi)
        if key not in self.table:
            self.table[key] = len(self.table) + 2
        return self.table[key]


def ofdd(store, tt, var, n):
    """Build from the function: low = f|x=0, high = f|x=0 XOR f|x=1 (Boolean difference)."""
    if var == n:
        return tt[0]
    f0 = tt[0::2]
    f1 = tt[1::2]
    d = [x ^ y for x, y in zip(f0, f1)]
    return store.mk(var, ofdd(store, f0, var + 1, n), ofdd(store, d, var + 1, n))


def zdd(store, family, var, n):
    """Build from the set family: low = sets without var, high = sets with var (var removed)."""
    if var == n:
        return 1 if frozenset() in family else 0
    lo = {s for s in family if var not in s}
    hi = {s - {var} for s in family if var in s}
    return store.mk(var, zdd(store, lo, var + 1, n), zdd(store, hi, var + 1, n))


def canon(store, root):
    inv = {v: k for k, v in store.table.items()}
    out, seen = [], set()

    def walk(u):
        if u in (0, 1) or u in seen:
            return
        seen.add(u)
        v, lo, hi = inv[u]
        out.append((u, v, lo, hi))
        walk(lo)
        walk(hi)

    walk(root)
    return root, sorted(out)


def main() -> None:
    for n in range(1, 5):
        count = 0
        for tt in product((0, 1), repeat=1 << n):
            s = Store()  # one shared unique table: identical graphs => identical node ids
            r1 = ofdd(s, list(tt), 0, n)
            r2 = zdd(s, anf_monomials(tt, n), 0, n)
            assert r1 == r2, (n, tt)
            assert canon(s, r1) == canon(s, r2)
            count += 1
        print(f"n={n}: {count} functions, OFDD(pD) root == ZDD(ANF monomials) root in a shared unique table")


if __name__ == "__main__":
    main()
