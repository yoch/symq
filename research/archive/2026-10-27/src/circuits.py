"""Deterministic small circuit generators and a strict subset-KMx parser.

Only for experimental X/CX/CCX/Z/CZ/CCZ/NEG/HMR and conditional phase gates;
no general circuit semantics are claimed. Generated GF multiplier is exact on
input computational basis states and may XOR into a dirty C target.
"""
from __future__ import annotations
from .field_phase import gf_mul

def gf12_instructions(*, echo_pairs=0, with_hmr=True):
    # Quantum inputs q0..q35 = A,B,C; masks b0..b11 are unconstrained classical inputs.
    ops=[]
    for i in range(12):
        for j in range(12):
            basis=gf_mul(1<<i,1<<j)
            for k in range(12):
                if (basis>>k)&1:ops.append(('CCX',(i,12+j,24+k),None,None))
    # Symbolic total phase XOR_k m_k * (C XOR A*B)_k
    for k in range(12):ops.append(('Z',(24+k,),f'm{k}',None))
    if with_hmr:
        # An outcome-cancelled non-unitary gadget under the supported semantics.
        ops.extend([('CCX',(0,12,48),None,None),('HMR',(48,),None,'h0'),('CZ',(0,12),'h0',None)])
    for j in range(echo_pairs):
        control=j%24
        target=36+(j%12)
        ops.append(('CX',(control,target),None,None))
        ops.append(('CX',(control,target),None,None))
    return ops

def parse_kmx_subset(text):
    out=[]
    for lineno,line in enumerate(text.splitlines(),1):
        tokens=line.split()
        if not tokens or tokens[0].startswith('#') or tokens[0] in {'REGISTER','APPEND_TO_REGISTER','INFO_TAG'}:continue
        op=tokens[0];tail=tokens[1:]
        condition=None
        if len(tail)>=2 and tail[-2]=='if':condition=tail[-1];tail=tail[:-2]
        if op=='HMR':
            if len(tail)!=2 or not tail[0].startswith('q'):raise ValueError(f'bad HMR {lineno}')
            out.append((op,(int(tail[0][1:]),),condition,tail[1]));continue
        if op not in {'X','CX','CCX','Z','CZ','CCZ','NEG'}:
            raise ValueError(f'unsupported KMx operation at {lineno}: {op}')
        if not all(x.startswith('q') for x in tail):raise ValueError(f'bad operand {lineno}')
        out.append((op,tuple(int(x[1:]) for x in tail),condition,None))
    return out
