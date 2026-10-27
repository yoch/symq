"""A small exact Boolean-ring laboratory: sparse reference and degree-bounded packed ANF.

This is NOT a full quantum simulator or a certified interpreter of any circuit language.
An ANF is a polynomial over F2 with x_i**2 = x_i, represented by a set of bitmask monomials.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from math import comb

class DegreeOverflow(ValueError):
    """A product would leave the sound degree-bounded representation."""

@dataclass(frozen=True)
class Sparse:
    terms: frozenset[int] = frozenset()
    @staticmethod
    def const(v: bool) -> 'Sparse':
        return Sparse(frozenset({0}) if v else frozenset())
    @staticmethod
    def variable(i: int) -> 'Sparse':
        return Sparse(frozenset({1 << i}))
    def __xor__(self, other: 'Sparse') -> 'Sparse':
        return Sparse(self.terms ^ other.terms)
    def __mul__(self, other: 'Sparse') -> 'Sparse':
        if not self.terms or not other.terms:
            return Sparse()
        if self.terms == frozenset({0}):
            return other
        if other.terms == frozenset({0}):
            return self
        acc = set()
        for a in self.terms:
            for b in other.terms:
                v = a | b
                if v in acc: acc.remove(v)
                else: acc.add(v)
        return Sparse(frozenset(acc))
    def eval(self, bits: int) -> int:
        return sum((m & bits) == m for m in self.terms) & 1
    def max_degree(self) -> int:
        return max((m.bit_count() for m in self.terms), default=0)

class PackedRing:
    """Exact graded-colex coefficient bitset for all monomials of degree <= max_degree.

    Coordinates have deterministic ranks; reject any term above max_degree. Such
    refusal is essential: silently discarding degree overflow is unsound.
    """
    def __init__(self, n: int, max_degree: int):
        if n <= 0 or not (0 <= max_degree <= n):
            raise ValueError("bad n / degree")
        self.n = n
        self.k = max_degree
        self.count = sum(comb(n,d) for d in range(max_degree+1))
        if self.count > 2_000_000:
            raise ValueError("packed coordinate universe too large for this reference engine")
        masks = [0]
        for d in range(1,max_degree+1):
            masks.extend(sum(1<<i for i in chosen) for chosen in combinations(range(n),d))
        self.masks = tuple(masks)
        self.index = {m:i for i,m in enumerate(masks)}
        self.one = 1
        self.vars = tuple(1 << self.index[1 << i] for i in range(n)) if max_degree >= 1 else tuple()
        self.max_mask = (1 << self.count) - 1
    def encode(self, s: Sparse | frozenset[int] | set[int]) -> int:
        terms = s.terms if isinstance(s, Sparse) else s
        v = 0
        for m in terms:
            idx = self.index.get(m)
            if idx is None: raise DegreeOverflow(f"monomial degree {m.bit_count()} > {self.k}")
            v ^= 1<<idx
        return v
    def decode(self, v: int) -> Sparse:
        if v < 0 or v >> self.count:
            raise ValueError("invalid packed coefficient vector")
        s = set()
        while v:
            low = v & -v
            idx = low.bit_length()-1
            s.add(self.masks[idx]);v ^= low
        return Sparse(frozenset(s))
    def mul(self, a: int, b: int) -> int:
        if not a or not b:return 0
        if a==1:return b
        if b==1:return a
        # Decode the shorter operand, then toggle resulting monomials. Exact OR is idempotent multiplication.
        if a.bit_count()>b.bit_count():a,b=b,a
        aa=self.decode(a).terms;bb=self.decode(b).terms
        out=0
        for x in aa:
            for y in bb:
                z=x|y
                idx=self.index.get(z)
                if idx is None: raise DegreeOverflow(f"{z.bit_count()} > {self.k}")
                out ^= 1<<idx
        return out
    def eval(self, a: int, bits: int) -> int:
        return self.decode(a).eval(bits)

class PhaseState:
    """Formal phase sum in F2: classical monomial -> ANF of quantum inputs.

    A classical monomial can include independent input mask bits and HMR outcome bits.
    This is a mathematical bookkeeping model for the subset of HMR circuits supported below;
    it is NOT automatically sound for arbitrary quantum states/measurements.
    """
    def __init__(self, ring=None):
        self.ring=ring
        self.data={}
    def add(self, quantum, classical_mask=0):
        zero = Sparse() if self.ring is None else 0
        value = self.data.get(classical_mask,zero) ^ quantum
        if value==zero:self.data.pop(classical_mask,None)
        else:self.data[classical_mask]=value
    def as_sparse(self):
        if self.ring is None:return dict(self.data)
        return {c:self.ring.decode(q) for c,q in self.data.items()}

class ANFMachine:
    """Exact formal replay for X,CX,CCX,Z,CZ,CCZ,NEG,HMR and gated phases.

    Rules: qubit data operations cannot depend on classical conditions; each HMR
    outcome is a fresh unconstrained formal bit, and the measured qubit must be
    an initially-zero scratch (not a named original input). An HMR implements
    the bookkeeping update phase ^= value(q)*outcome, q:=0.
    An unsupported instruction or degree growth fails closed.
    """
    def __init__(self, data_bits: int, input_qubits: tuple[int,...], backend: str='sparse', degree: int=2):
        if backend not in {'sparse','packed'}:raise ValueError('backend')
        if len(set(input_qubits))!=len(input_qubits) or len(input_qubits)!=data_bits:
            raise ValueError('input bits/qubits')
        self.backend=backend
        self.ring=PackedRing(data_bits,degree) if backend=='packed' else None
        self.zero=Sparse() if self.ring is None else 0
        self.one=Sparse.const(True) if self.ring is None else 1
        self.states={q:(Sparse.variable(i) if self.ring is None else self.ring.vars[i]) for i,q in enumerate(input_qubits)}
        self.inputs=set(input_qubits)
        self.phase=PhaseState(self.ring)
        self.classical={}
        self.next_classical=0
        self.hmr_count=0
        self.opcount=0
    def get(self,q):return self.states.get(q,self.zero)
    def _mul(self,a,b):return a*b if self.ring is None else self.ring.mul(a,b)
    def new_classical(self,name):
        if name in self.classical:raise ValueError(f'duplicate classical bit {name}')
        self.classical[name]=1<<self.next_classical
        self.next_classical+=1
    def _condition_mask(self,condition):
        if condition is None:return 0
        if condition not in self.classical:raise ValueError('unknown classical condition '+str(condition))
        return self.classical[condition]
    def step(self,op,qubits=(),condition=None,outcome=None):
        self.opcount+=1
        q=qubits
        if op in {'X','CX','CCX'}:
            if condition is not None:raise ValueError('conditional data operation outside scope')
            sizes={'X':1,'CX':2,'CCX':3}
            if len(q)!=sizes[op]:raise ValueError('arity')
            ctrl=self.one
            for qi in q[:-1]:ctrl=self._mul(ctrl,self.get(qi))
            if len(set(q)) != len(q):raise ValueError('same qubit appears in one gate')
            target=q[-1];self.states[target]=self.get(target)^ctrl
        elif op in {'Z','CZ','CCZ','NEG'}:
            sizes={'Z':1,'CZ':2,'CCZ':3,'NEG':0}
            if len(q)!=sizes[op]:raise ValueError('arity')
            v=self.one
            for qi in q:v=self._mul(v,self.get(qi))
            self.phase.add(v,self._condition_mask(condition))
        elif op=='HMR':
            if len(q)!=1 or outcome is None or condition is not None:raise ValueError('HMR arguments')
            if q[0] in self.inputs:raise ValueError('measuring an original input')
            self.new_classical(outcome)
            self.phase.add(self.get(q[0]),self.classical[outcome])
            self.states[q[0]]=self.zero
            self.hmr_count+=1
        else:raise ValueError(f'unsupported operation {op}')
    def execute(self,sequence):
        for op,q,condition,outcome in sequence:self.step(op,q,condition,outcome)
        return self
    def comparable_state(self):
        if self.ring is None:return dict(self.states)
        return {q:self.ring.decode(v) for q,v in self.states.items()}
    def snapshot(self):
        return ({q:x.terms for q,x in self.comparable_state().items() if x.terms},
                {mask:p.terms for mask,p in self.phase.as_sparse().items()})
