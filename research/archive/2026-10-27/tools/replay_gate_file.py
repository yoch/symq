"""Offline differential replay of a line-oriented gate-text file.

Two symbolic engines execute the same file and their snapshots are compared.
The caller supplies the expected Git blob SHA-1 of the input file:

PYTHONPATH=. python tools/replay_gate_file.py circuit.gates <git-blob-sha> --out result_NEW.json

This is a differential comparison of implementations, NOT a quantum proof.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
from src.anf_backends import ANFMachine
from src.circuits import parse_gate_text


def git_blob_sha(contents:bytes)->str:
    return hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()


def run(path:str,expected_blob:str,inputs=24,start=0,degree=2,every=1):
    buf=Path(path).read_bytes();sha=git_blob_sha(buf)
    if sha!=expected_blob:raise ValueError(f'Git blob SHA mismatch: actual={sha} expected={expected_blob}')
    ops=parse_gate_text(buf.decode('utf-8'))
    a=ANFMachine(inputs,tuple(range(start,start+inputs)),backend='sparse')
    b=ANFMachine(inputs,tuple(range(start,start+inputs)),backend='packed',degree=degree)
    started=time.perf_counter();checks=0
    for index,op in enumerate(ops,1):
        a.step(*op);b.step(*op)
        if every and (index%every==0 or index==len(ops)):
            if a.snapshot()!=b.snapshot():raise AssertionError(f'differential mismatch at {index}')
            checks+=1
    return {'verdict':'DIFFERENTIAL_EQUALITY_IN_DECLARED_SYMBOLIC_SUBSET',
            'not_a_quantum_proof':True,'source_path':str(path),
            'expected_git_blob':expected_blob,'actual_git_blob':sha,
            'operations':len(ops),'snapshot_checks':checks,'formal_inputs':inputs,
            'assumed_qubit_ids':list(range(start,start+inputs)),'max_degree_limit':degree,
            'hmr_outcomes':a.hmr_count,'residual_phase_classical_monomials':len(a.phase.data),
            'elapsed_both_engines_s':time.perf_counter()-started}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('gate_file',type=Path);p.add_argument('expected_blob')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--inputs',type=int,default=24);p.add_argument('--degree',type=int,default=2)
    args=p.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    report=run(str(args.gate_file),args.expected_blob,inputs=args.inputs,degree=args.degree)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
