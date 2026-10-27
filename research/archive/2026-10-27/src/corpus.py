"""Lossless supported-gate extraction from eleven pinned public MQT QCEC QASM files.

For external verification, fetch original OpenQASM 3.0 from pinned commit and
compare all normalized operations; unsupported gates cause a hard error.
"""
from __future__ import annotations
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent

def read_corpus(path=None):
    p=Path(path) if path else ROOT/'corpus/qcec_packed.tsv'
    for row in p.read_text().splitlines():
        if not row.strip():continue
        name,n,sha,serialized=row.strip().split('|')
        n=int(n); ops=[]
        for item in serialized.split(','):
            op={'a':'X','b':'CX','c':'CCX','d':'MCX'}.get(item[0])
            if op is None:raise ValueError('unsupported opcode')
            if op=='MCX':
                declared_ctrl=int(item[1],36)
                qs=tuple(int(x,36) for x in item[2:].split('.'))
                if declared_ctrl<3 or len(qs)!=declared_ctrl+1:raise ValueError('bad MCX arity')
            else:
                qs=tuple(int(x,36) for x in item[1:].split('.'))
                if len(qs)!={'X':1,'CX':2,'CCX':3}[op]:raise ValueError('bad gate arity')
            if any(not 0<=q<n for q in qs) or len(set(qs))!=len(qs):raise ValueError('bad qid/alias')
            ops.append((op,qs,None,None))
        yield dict(name=name,n=n,sha=sha,ops=ops)

_PATTERN=re.compile(r'^(x|cx|ccx)\s+(.+);$')
_MCX=re.compile(r'^ctrl\((\d+)\)\s*@\s*x\s+(.+);$')

def parse_qasm_strict(text):
    ops=[];width=None
    for i,row in enumerate(text.splitlines(),1):
        line=row.strip()
        if not line or line.startswith('//') or line in ('OPENQASM 3.0;','include "stdgates.inc";'):
            continue
        m=re.fullmatch(r'qubit\[(\d+)\]\s+q;',line)
        if m:
            if width is not None:
                raise ValueError('multiple registers')
            width = int(m[1])
            continue
        m=_PATTERN.fullmatch(line)
        if not m:
            mm=_MCX.fullmatch(line)
            if not mm:raise ValueError(f'unsupported QASM at line {i}: {line[:80]}')
            op='MCX';qs=tuple(int(x) for x in re.findall(r'q\[(\d+)\]',mm[2]))
            if len(qs)!=int(mm[1])+1 or len(qs)<4:raise ValueError('MCX declared controls mismatch')
        else:
            qs=tuple(int(x) for x in re.findall(r'q\[(\d+)\]',m[2]))
            op=m[1].upper()
            if len(qs)!={'X':1,'CX':2,'CCX':3}[op]:raise ValueError('gate arity')
        if len(set(qs))!=len(qs):raise ValueError('aliased gate')
        ops.append((op,qs,None,None))
    if width is None:raise ValueError('missing qubit register')
    return width,ops

def restrict_to_domain(item,free):
    if not 0<=free<=item['n']:raise ValueError('free bits out of range')
    return free,tuple(range(free)),item['ops']
