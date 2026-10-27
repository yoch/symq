"""Experimental exact symbolic backend for reversible Boolean/phase circuits.

This is NOT a general quantum simulator. HMR uses a phase-ledger
semantics for a restricted class of basis-state/measurement circuits.
Supported operations: X,CX,CCX,Z,CZ,CCZ,NEG,HMR; conditional phase only.

Backends:
- copy_set: conventional mutable Python set of ANF monomial masks (baseline)
- packed: bounded-degree coefficient bitset, refusing overflow (no truncation)
- adaptive: per-wire packed/sparse mix; on overflow falls back EXACTLY to sparse
- truth: basis-domain exhaustive truth-table bitsets, with at most 2**18 inputs

A polynomial is sum of squarefree monomials (masks) over F2. The ring
F2[x]/(x^2-x) makes monomial multiplication equivalent to bitwise OR.
"""
from __future__ import annotations
from functools import lru_cache
from math import comb

class ResourceLimit(RuntimeError):
    pass
class DegreeOverflow(RuntimeError):
    pass


def set_add(a:set[int], b:set[int])->set[int]:
    return a.symmetric_difference(b)

def set_mul(a:set[int], b:set[int], cap:int=150_000)->set[int]:
    if not a or not b: return set()
    if a=={0}:return set(b)
    if b=={0}:return set(a)
    if len(a)>len(b):a,b=b,a
    out=set()
    for x in a:
        for y in b:
            z=x|y
            if z in out:out.remove(z)
            else:out.add(z)
        if len(out)>cap: raise ResourceLimit(f'{len(out)} ANF terms > {cap} cap')
    return out

class Ring2:
    """Canonical colex degree<=2 encoding: 0, variables, pairs ranked by hi*(hi-1)/2+lo."""
    def __init__(self,n:int):
        if not 1<=n<=64: raise ValueError('1<=n<=64')
        self.n=n; self.length=1+n+n*(n-1)//2
        self.masks=(0,)+tuple(1<<i for i in range(n))+tuple((1<<i)|(1<<j) for j in range(1,n) for i in range(j))
        self.index={m:i for i,m in enumerate(self.masks)}
        self.linear_mask=(1<<n)-1
        self.allones=(1<<self.length)-1
        self.pairbits=tuple(tuple(0 if i==j else (1 << (1+n+max(i,j)*(max(i,j)-1)//2+min(i,j))) for j in range(n)) for i in range(n))
    def monomials(self,p:int):
        if p<0 or p>>self.length: raise ValueError('bad polynomial capacity')
        while p:
            low=p&-p
            yield self.masks[low.bit_length()-1]
            p^=low
    def packed(self,terms:set[int])->int:
        v=0
        for m in terms:
            i=self.index.get(m)
            if i is None: raise DegreeOverflow('degree >2')
            v^=1<<i
        return v
    def sparse(self,p:int)->set[int]:
        return set(self.monomials(p))
    def var(self,i:int)->int:
        return 1<<(i+1)
    def mul(self,a:int,b:int)->int:
        if not a or not b:return 0
        if a==1:return b
        if b==1:return a
        if a.bit_count()>b.bit_count():a,b=b,a
        # Most CCX controls are affine: no term above linear degree.
        if a.bit_length()<=self.n+1 and b.bit_length()<=self.n+1:
            a0,b0=a&1,b&1
            av=(a>>1)&self.linear_mask; bv=(b>>1)&self.linear_mask
            linear=(av&bv) ^ (av if b0 else 0) ^ (bv if a0 else 0)
            out=(a0&b0)|(linear<<1)
            x=av
            while x:
                lb=x&-x; i=lb.bit_length()-1;x^=lb
                row=self.pairbits[i];y=bv&~lb
                while y:
                    rb=y&-y; j=rb.bit_length()-1;y^=rb
                    out^=row[j]
            return out
        out=0
        for m in self.monomials(a):
            for t in self.monomials(b):
                pos=self.index.get(m|t)
                if pos is None: raise DegreeOverflow('product degree >2')
                out^=1<<pos
        return out

@lru_cache(maxsize=12)
def ring2(n:int)->Ring2:return Ring2(n)

class SetState:
    """Mutable sets: conventional copy-on-XOR ANF baseline."""
    def __init__(self,n:int,inputs:tuple[int,...],cap:int=150000):
        self.states={qid:{1<<i} for i,qid in enumerate(inputs)}
        self.zero=set();self.one={0};self.cap=cap
        self.phase={};self.classical={};self.hmrs=0;self.nextclassical=0;self.n=n;self.ops=0
    def new_classical_input(self,name):
        if name in self.classical:raise ValueError('duplicate classical name')
        self.classical[name]=1<<self.nextclassical;self.nextclassical+=1
    def get(self,q):return self.states.get(q,self.zero)
    def mul(self,a,b):return set_mul(a,b,self.cap)
    def xor(self,a,b):return set_add(a,b)
    def addphase(self,val,mask):
        self.phase[mask]=self.xor(self.phase.get(mask,set()),val)
        if not self.phase[mask]:del self.phase[mask]
    def step(self,op,qs,condition=None,outcome=None):
        self.ops+=1
        if op in ('X','CX','CCX','MCX'):
            if condition is not None:raise ValueError('conditional data unsupported')
            need={'X':1,'CX':2,'CCX':3,'MCX':len(qs)}[op]
            if len(qs)!=need or len(set(qs))!=len(qs) or (op=='MCX' and len(qs)<4):raise ValueError('gate arity/aliasing')
            p=self.one
            for q in qs[:-1]:p=self.mul(p,self.get(q))
            q=qs[-1];self.states[q]=self.xor(self.get(q),p)
        elif op in ('Z','CZ','CCZ','NEG'):
            need={'Z':1,'CZ':2,'CCZ':3,'NEG':0}[op]
            if len(qs)!=need:raise ValueError('phase arity')
            p=self.one
            for q in qs:p=self.mul(p,self.get(q))
            if condition and condition not in self.classical:raise ValueError('unknown classical')
            mask=0 if condition is None else self.classical[condition]
            self.addphase(p,mask)
        elif op=='HMR':
            if condition or len(qs)!=1 or not outcome:raise ValueError('HMR args')
            if outcome in self.classical:raise ValueError('duplicate measurement bit')
            mask=1<<self.nextclassical;self.nextclassical+=1;self.hmrs+=1;self.classical[outcome]=mask
            self.addphase(self.get(qs[0]),mask);self.states[qs[0]]=set()
        else:raise ValueError('unsupported '+op)
    def run(self,ops):
        for op,qs,cond,out in ops:self.step(op,qs,cond,out)
        return self
    def digest(self):
        return (tuple(sorted((q,tuple(sorted(v))) for q,v in self.states.items() if v)),
                tuple(sorted((k,tuple(sorted(v))) for k,v in self.phase.items())))
    def statistics(self):
        return dict(total_terms=sum(map(len,self.states.values()))+sum(map(len,self.phase.values())),
                    wires_sparse=sum(bool(v) for v in self.states.values()),hmr=self.hmrs)

class MixedState(SetState):
    """Convert only changed wires after degree overflow; classical phase remains sparse.

    Packed representation uses int; sparse uses set. Conversions cannot discard any monomial;
    a degree>2 product always computes the exact sparse result with explicit cap.
    """
    def __init__(self,n,inputs,cap=150000,threshold=0,mode='adaptive'):
        if mode not in ('adaptive','packed'): raise ValueError('mode')
        super().__init__(n,inputs,cap)
        self.ring=ring2(n);self.mode=mode;self.threshold=threshold;self.demotions=0;self.promotions=0
        self.states={qid:self.ring.var(i) for i,qid in enumerate(inputs)}
        self.zero=0;self.one=1
    def as_set(self,a):return self.ring.sparse(a) if isinstance(a,int) else a
    def encode(self,a):
        if self.mode=='adaptive' and len(a)<self.threshold:return set(a)
        try:
            x=self.ring.packed(a)
            self.promotions+=1
            return x
        except DegreeOverflow:
            if self.mode=='packed':raise
            self.demotions+=1
            return set(a)
    def mul(self,a,b):
        if isinstance(a,int) and isinstance(b,int):
            try:
                return self.ring.mul(a,b)
            except DegreeOverflow:
                if self.mode=='packed':raise
                self.demotions+=1
                return set_mul(self.ring.sparse(a),self.ring.sparse(b),self.cap)
        # Once outside degree<=2, keep sparse until an explicit future conversion
        # is justified. Avoid attempting a known-impossible re-encoding on each CX.
        return set_mul(self.as_set(a),self.as_set(b),self.cap)
    def xor(self,a,b):
        if isinstance(a,int) and isinstance(b,int):return a^b
        return set_add(self.as_set(a),self.as_set(b))
    def addphase(self,val,mask):
        # Phase can have high degree, independent of the packed degree bound.
        vs=self.as_set(val)
        self.phase[mask]=set_add(self.phase.get(mask,set()),vs)
        if not self.phase[mask]:del self.phase[mask]
    def digest(self):
        return (tuple(sorted((q,tuple(sorted(self.as_set(v)))) for q,v in self.states.items() if v)),
                tuple(sorted((k,tuple(sorted(v))) for k,v in self.phase.items())))
    def statistics(self):
        return dict(total_terms=sum(len(self.as_set(v)) for v in self.states.values())+sum(map(len,self.phase.values())),
                    wires_packed=sum(isinstance(v,int) for v in self.states.values()),
                    wires_sparse=sum(isinstance(v,set) for v in self.states.values()),
                    promotions=self.promotions,demotions=self.demotions,hmr=self.hmrs)

class TruthState:
    """Existing exact-domain style: bit-per-assignment, all inputs in parallel.

    This is a *different algorithmic representation*; it scales exponentially
    in the number of free input bits. It does not carry HMR unless the classical
    key is separate, as supported here.
    """
    def __init__(self,n:int,inputs:tuple[int,...]):
        if n>18:raise ResourceLimit('truth table would require >2**18 assignments')
        width=1<<n; self.ones=(1<<width)-1; self.states={}
        for i,qid in enumerate(inputs):
            block=1<<i;piece=((1<<block)-1)<<block
            chunk=2*block
            while chunk<width:
                piece|=piece<<chunk
                chunk*=2
            self.states[qid]=piece
        self.phase={};self.classical={};self.hmrs=0;self.nextclassical=0;self.ops=0;self.n=n
    def new_classical_input(self,name):
        if name in self.classical:raise ValueError('duplicate classical name')
        self.classical[name]=1<<self.nextclassical;self.nextclassical+=1
    def get(self,q):return self.states.get(q,0)
    def addphase(self,val,mask):
        out=self.phase.get(mask,0)^val
        if out:self.phase[mask]=out
        else:self.phase.pop(mask,None)
    def step(self,op,qs,condition=None,outcome=None):
        self.ops+=1
        if op in ('X','CX','CCX','MCX'):
            if condition is not None:raise ValueError('conditional data unsupported')
            if len(qs)!={'X':1,'CX':2,'CCX':3,'MCX':len(qs)}[op] or len(set(qs))!=len(qs) or (op=='MCX' and len(qs)<4):raise ValueError('aliasing/arity')
            p=self.ones
            for q in qs[:-1]:p&=self.get(q)
            target=qs[-1];self.states[target]=self.get(target)^p
        elif op in ('Z','CZ','CCZ','NEG'):
            if len(qs)!={'Z':1,'CZ':2,'CCZ':3,'NEG':0}[op]:raise ValueError('phase arity')
            p=self.ones
            for q in qs:p&=self.get(q)
            if condition is not None and condition not in self.classical:raise ValueError('unknown classical')
            self.addphase(p,0 if condition is None else self.classical[condition])
        elif op=='HMR':
            if condition or len(qs)!=1 or not outcome or outcome in self.classical:raise ValueError('HMR')
            mask=1<<self.nextclassical;self.nextclassical+=1;self.hmrs+=1;self.classical[outcome]=mask
            self.addphase(self.get(qs[0]),mask);self.states[qs[0]]=0
        else:raise ValueError('unsupported '+op)
    def run(self,ops):
        for op,qs,cond,out in ops:self.step(op,qs,cond,out)
        return self
    def compare(self,ref:SetState,all_bits=18):
        # Exact all-input semantic comparison, not just random samples.
        if self.n>all_bits:raise ValueError('too many inputs')
        for q,p in ref.states.items():
            expected=0
            for assignment in range(1<<self.n):
                v=0
                for monomial in p:v^=int((monomial&assignment)==monomial)
                expected|=v<<assignment
            if expected!=self.states[q]:raise AssertionError('state mismatch '+str(q))
        for key,p in ref.phase.items():
            expected=0
            for assignment in range(1<<self.n):
                v=0
                for monomial in p:v^=int((monomial&assignment)==monomial)
                expected|=v<<assignment
            if expected!=self.phase.get(key,0):raise AssertionError('phase mismatch '+str(key))
        if set(self.phase)!=set(ref.phase):raise AssertionError('phase keys mismatch')
        return True

class FastSetState(SetState):
    """Exact inplace set baseline: no monomial format change, no scientific novelty.

    The copy_set baseline creates fresh sets on every CX. In-place
    symmetric_difference_update is legal because aliased operands are rejected.
    """
    def step(self,op,qs,condition=None,outcome=None):
        self.ops+=1
        if op in ('X','CX','CCX','MCX'):
            if condition is not None: raise ValueError('conditional data unsupported')
            if len(qs)!={'X':1,'CX':2,'CCX':3,'MCX':len(qs)}[op] or len(set(qs))!=len(qs) or (op=='MCX' and len(qs)<4):raise ValueError('gate aliasing')
            if op=='X':
                q=qs[0];self.states.setdefault(q,set()).symmetric_difference_update((0,))
            elif op=='CX':
                a,b=qs;self.states.setdefault(b,set()).symmetric_difference_update(self.get(a))
            else:
                q=qs[-1];product=self.one
                for control in qs[:-1]:product=self.mul(product,self.get(control))
                self.states.setdefault(q,set()).symmetric_difference_update(product)
        elif op in ('Z','CZ','CCZ','NEG'):
            if len(qs)!={'Z':1,'CZ':2,'CCZ':3,'NEG':0}[op]:raise ValueError('phase arity')
            v=self.one
            for q in qs:v=self.mul(v,self.get(q))
            if condition is not None and condition not in self.classical:raise ValueError('unknown classical')
            mask=0 if condition is None else self.classical[condition]
            self.phase.setdefault(mask,set()).symmetric_difference_update(v)
            if not self.phase[mask]:del self.phase[mask]
        elif op=='HMR':
            if condition or len(qs)!=1 or not outcome or outcome in self.classical:raise ValueError('HMR args')
            mask=1<<self.nextclassical;self.nextclassical+=1;self.hmrs+=1;self.classical[outcome]=mask
            self.phase.setdefault(mask,set()).symmetric_difference_update(self.get(qs[0]))
            if not self.phase[mask]:del self.phase[mask]
            self.states[qs[0]]=set()
        else:raise ValueError('unsupported '+op)
