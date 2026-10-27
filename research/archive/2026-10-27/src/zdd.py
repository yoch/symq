"""Pure-Python zero-suppressed decision diagrams for GF2 polynomial monomial sets.

This is an independently implemented ZDD-style comparator, **not** PolyBoRi,
CUDD, or a representative of C++ ZDD performance. Order: highest variable
first. The unique table and memoized operations provide canonical structure.
An algebraic polynomial f is represented by family of its monomial supports;
XOR = symmetric difference; multiplication = OR-convolution with XOR parity.
"""
from __future__ import annotations
from functools import lru_cache
from .optimized import ResourceLimit

class ZDD:
    def __init__(self,n,limit=200_000):
        self.n=n;self.limit=limit
        self.vars=[(-1,0,0),(-1,0,0)]
        self.unique={}
        self._top=[-1,-1]
        self._mkcache={}
        self.mul_calls=0;self.xor_calls=0

    def node(self,v,lo,hi):
        if not hi:return lo
        key=v,lo,hi
        old=self.unique.get(key)
        if old is not None:return old
        if len(self.vars)>=self.limit:raise ResourceLimit('ZDD nodes > limit')
        pos=len(self.vars)
        self.vars.append(key);self.unique[key]=pos;self._top.append(v)
        return pos
    def variable(self,i):return self.node(i,0,1)
    def cofactor(self,root,v):
        if root>1 and self._top[root]==v:
            _,lo,hi=self.vars[root];return lo,hi
        return root,0
    @lru_cache(maxsize=200_000)
    def xor(self,a,b):
        if a==b:return 0
        if a==0:return b
        if b==0:return a
        if b<a:a,b=b,a
        v=max(self._top[a],self._top[b]);a0,a1=self.cofactor(a,v);b0,b1=self.cofactor(b,v)
        return self.node(v,self.xor(a0,b0),self.xor(a1,b1))
    @lru_cache(maxsize=200_000)
    def mul(self,a,b):
        if not a or not b:return 0
        if a==1:return b
        if b==1:return a
        if b<a:a,b=b,a
        v=max(self._top[a],self._top[b]);a0,a1=self.cofactor(a,v);b0,b1=self.cofactor(b,v)
        lo=self.mul(a0,b0)
        hi=self.xor(self.xor(self.mul(a0,b1),self.mul(a1,b0)),self.mul(a1,b1))
        return self.node(v,lo,hi)
    def as_set(self,root):
        @lru_cache(maxsize=None)
        def rec(u):
            if u==0:return frozenset()
            if u==1:return frozenset({0})
            v,lo,hi=self.vars[u]
            return rec(lo)|frozenset(t|(1<<v) for t in rec(hi))
        result=set(rec(root)); rec.cache_clear(); return result
    def count_terms(self,root):
        @lru_cache(maxsize=None)
        def rec(u):
            if u==0:return 0
            if u==1:return 1
            _,lo,hi=self.vars[u]
            return rec(lo)+rec(hi)
        return rec(root)
    def statistics(self):
        return {'allocated_nodes':len(self.vars)-2,'unique_table':len(self.unique),
                'xor_cache':self.xor.cache_info()._asdict(),'mul_cache':self.mul.cache_info()._asdict()}

class ZDDState:
    def __init__(self,n,inputs):
        self.n=n;self.manager=ZDD(n)
        self.states={qid:self.manager.variable(i) for i,qid in enumerate(inputs)}
        self.phase={};self.classical={};self.nextclassical=0;self.hmrs=0
    def new_classical_input(self,name):
        if name in self.classical:raise ValueError('duplicate classical bit')
        self.classical[name]=1<<self.nextclassical;self.nextclassical+=1
    def get(self,q):return self.states.get(q,0)
    def addphase(self,v,mask):
        val=self.manager.xor(self.phase.get(mask,0),v)
        if val:self.phase[mask]=val
        else:self.phase.pop(mask,None)
    def step(self,op,qs,condition=None,outcome=None):
        m=self.manager
        if op in ('X','CX','CCX','MCX'):
            if condition is not None or len(qs)!={'X':1,'CX':2,'CCX':3,'MCX':len(qs)}[op] or len(set(qs))!=len(qs) or (op=='MCX' and len(qs)<4):raise ValueError('unsupported condition / aliasing')
            t=1
            for q in qs[:-1]:t=m.mul(t,self.get(q))
            target=qs[-1];self.states[target]=m.xor(self.get(target),t)
        elif op in ('Z','CZ','CCZ','NEG'):
            if len(qs)!={'Z':1,'CZ':2,'CCZ':3,'NEG':0}[op]:raise ValueError('phase arity')
            v=1
            for q in qs:v=m.mul(v,self.get(q))
            if condition is not None and condition not in self.classical:raise ValueError('unknown condition')
            self.addphase(v,0 if condition is None else self.classical[condition])
        elif op=='HMR':
            if condition is not None or len(qs)!=1 or not outcome or outcome in self.classical:raise ValueError('HMR')
            mask=1<<self.nextclassical;self.nextclassical+=1;self.hmrs+=1;self.classical[outcome]=mask
            self.addphase(self.get(qs[0]),mask);self.states[qs[0]]=0
        else:raise ValueError('unsupported operation '+op)
    def run(self,ops):
        for op,qs,cond,out in ops:self.step(op,qs,cond,out)
        return self
    def digest(self):
        return (tuple(sorted((q,tuple(sorted(self.manager.as_set(v)))) for q,v in self.states.items() if v)),
            tuple(sorted((k,tuple(sorted(self.manager.as_set(v)))) for k,v in self.phase.items())))
    def statistics(self):
        return dict(allocated_nodes=len(self.manager.vars)-2,live_wire_monomials=sum(self.manager.count_terms(v) for v in self.states.values()),
                    live_phase_monomials=sum(self.manager.count_terms(v) for v in self.phase.values()),hmr=self.hmrs,
                    caches=self.manager.statistics())

def _zdd_from_terms(self,terms):
    """Build a ZDD from a sparse monomial set, preserving every term exactly."""
    @lru_cache(maxsize=100_000)
    def build(ts:frozenset[int]):
        if not ts:return 0
        if ts==frozenset((0,)):return 1
        top=max(x.bit_length()-1 for x in ts)
        flag=1<<top
        lo=frozenset(x for x in ts if not x&flag)
        hi=frozenset(x^flag for x in ts if x&flag)
        return self.node(top,build(lo),build(hi))
    root=build(frozenset(terms))
    build.cache_clear()
    return root

ZDD.from_terms=_zdd_from_terms

@classmethod
def _from_sparse(cls,src):
    inputs=tuple(range(src.n)) # only used for initial allocation, later overwritten
    dst=cls(src.n,inputs)
    dst.states={q:dst.manager.from_terms(poly) for q,poly in src.states.items()}
    dst.phase={k:dst.manager.from_terms(poly) for k,poly in src.phase.items()}
    dst.classical=dict(src.classical);dst.nextclassical=src.nextclassical;dst.hmrs=src.hmrs
    return dst
ZDDState.from_sparse=_from_sparse

class AutoZDDState:
    """Exact sparse-to-ZDD switching; keep sparse for ordinary low-term circuits.

    Switch at a prescribed CCX/MCX target term count, or on a sparse
    ResourceLimit during a nonlinear/phase product; the latter is retried in
    ZDD form. This cannot silently discard polynomial terms.
    """
    def __init__(self,n,inputs,threshold=850,cap=150000):
        from .optimized import FastSetState
        self.machine=FastSetState(n,inputs,cap=cap)
        self.n=n;self.threshold=threshold;self.switch_op=None;self.ops=0
        self.switch_reason=None
    def new_classical_input(self,name):return self.machine.new_classical_input(name)
    def step(self,op,qs,condition=None,outcome=None):
        try:
            self.machine.step(op,qs,condition,outcome)
        except ResourceLimit:
            # The sparse backend raises before updating the target or the
            # phase. Never retry gates outside the exact supported family.
            if self.switch_op is not None or op not in ('CCX','MCX','CZ','CCZ'):
                raise
            self.machine=ZDDState.from_sparse(self.machine)
            self.switch_reason='sparse resource cap'
            self.switch_op=self.ops+1
            self.machine.step(op,qs,condition,outcome)
        self.ops+=1
        if self.switch_op is None and op in ('CCX','MCX'):
            target=qs[-1]
            if len(self.machine.states.get(target,set()))>=self.threshold:
                self.machine=ZDDState.from_sparse(self.machine)
                self.switch_reason='nonlinear target term threshold'
                self.switch_op=self.ops
    def run(self,ops):
        for op,qs,cond,out in ops:self.step(op,qs,cond,out)
        return self
    def digest(self):return self.machine.digest()
    def statistics(self):
        return {'strategy':'ZDD' if self.switch_op is not None else 'fast_set',
                'switch_operation_index':self.switch_op,'switch_reason':self.switch_reason,
                'backend_statistics':self.machine.statistics()}
