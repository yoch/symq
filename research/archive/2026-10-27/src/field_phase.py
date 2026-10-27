"""Exact GF(2^12) and a factorized phase ANF oracle for the inverse function.

   phi(x,m) = parity(inv(x) & m), with inv(0)=0 by convention in this TEST ORACLE.
   ANF is factorized as XOR_k m_k * f_k(x); 12*4096 possible coefficients.
"""
from __future__ import annotations
from math import comb
from sys import getsizeof

def gf_mul(a:int,b:int,poly:int=0x1053,n:int=12)->int:
    out=0
    while b:
        if b&1:out ^= a
        b >>= 1;a <<= 1
        if a&(1<<n):a ^= poly
    return out

def gf_pow(a:int,p:int)->int:
    out=1
    while p:
        if p&1:out=gf_mul(out,a)
        a=gf_mul(a,a);p>>=1
    return out

def gf_inverse_or_zero(x:int)->int:
    return gf_pow(x,4094) if x else 0

def inverse_factorized()->tuple[int,...]:
    """Return 12 coefficient bitsets. Bit s of vector k means monomial x^s in output bit k."""
    values=[gf_inverse_or_zero(x) for x in range(4096)]
    # Boolean Möbius inversion on the truth table, in-place; same transform inverted.
    for bit in range(12):
        for mask in range(4096):
            if mask&(1<<bit):values[mask] ^= values[mask^(1<<bit)]
    ans=[0]*12
    for mon,val in enumerate(values):
        for bit in range(12):
            if (val>>bit)&1:ans[bit] |= 1<<mon
    return tuple(ans)

def eval_anf(coeffs:int,x:int)->int:
    out=0
    # Enumerate subsets of input bits; monomial true iff subset of input.
    sub=x
    while True:
        out^=(coeffs>>sub)&1
        if sub==0:break
        sub=(sub-1)&x
    return out

def eval_masked_phase(factorized:tuple[int,...],x:int,mask:int)->int:
    result=0
    for k in range(12):
        if (mask>>k)&1:result ^= eval_anf(factorized[k],x)
    return result

def flat_terms(factorized:tuple[int,...])->set[int]:
    """ANF monomial support over x0..x11,m0..m11, for comparison only."""
    out=set()
    for k,v in enumerate(factorized):
        while v:
            low=v&-v; mon=low.bit_length()-1
            out.add(mon | (1<<(12+k)));v^=low
    return out

def shallow_memory(obj)->int:
    if isinstance(obj,set):return getsizeof(obj)+sum(getsizeof(v) for v in obj)
    if isinstance(obj,tuple):return getsizeof(obj)+sum(getsizeof(v) for v in obj)
    return getsizeof(obj)
