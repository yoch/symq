"""Offline strict source-level replay of the pinned private qant HMR fragment.

On a user-controlled authorized checkout, run (without writing to qant):
PYTHONPATH=. python tools/replay_qant_fixture.py \
  /path/to/qant/experiments/dqi/argon_norm_review_20261026/fixtures/84-core-forward.kmx \
  --out results/fixture_replay_NEW.json

The script checks the exact Git blob SHA of the source, then runs *our* two
independent restricted symbolic models, comparing their result. Assumptions:
q0..q23 are free Boolean inputs, all other qids initially zero, HMR outcomes
independent. These are not automatically extracted from the native circuit.
This is NOT an official Kickmix proof or a replacement for qant certificate.
"""
from __future__ import annotations
import argparse, hashlib, json, time, tracemalloc
from pathlib import Path
from src.circuits import parse_kmx_subset
from src.optimized import FastSetState
from src.zdd import AutoZDDState

EXPECTED_BLOB='bea34e578bfa8a0984329c5201ba62ad3572af23'
QANT_COMMIT='48bd7edd2f8c2f1ac2deb5209eb772eb9484d128'


def git_sha(b:bytes)->str:
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()


def replay(data:bytes,input_count=24,checks_each=100):
    sha=git_sha(data)
    if sha!=EXPECTED_BLOB:raise ValueError(f'uncertified source: {sha} != {EXPECTED_BLOB}')
    ops=parse_kmx_subset(data.decode('utf-8'))
    baseline=FastSetState(input_count,tuple(range(input_count)))
    adapted=AutoZDDState(input_count,tuple(range(input_count)))
    t0=time.perf_counter(); checks=0
    for i,(op,qs,condition,outcome) in enumerate(ops,1):
        baseline.step(op,qs,condition,outcome)
        adapted.step(op,qs,condition,outcome)
        if checks_each and (i%checks_each==0 or i==len(ops)):
            if baseline.digest()!=adapted.digest():raise AssertionError(f'differential discrepancy after instruction {i}')
            checks+=1
    return {'status':'DIFFERENTIAL_MATCH_ONLY','source_git_blob_sha':sha,'source_commit':QANT_COMMIT,
            'operations':len(ops),'assumed_free_inputs':list(range(input_count)),'other_qubits':'assumed initially zero',
            'measurements':baseline.hmrs,'phase_keys':len(baseline.phase),'num_snapshots':checks,
            'fast_set':baseline.statistics(),'adaptive':adapted.statistics(),
            'time_both_s':round(time.perf_counter()-t0,6),
            'limitations':['Not an official Kickmix verifier execution','This equality compares implementations under the same initial-state assumptions',
                'The classical phase representation does not cover all hybrid-control behavior']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('fixture',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--input-count',type=int,default=24);p.add_argument('--checks-every',type=int,default=100)
    args=p.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    report=replay(args.fixture.read_bytes(),args.input_count,args.checks_every)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

# Legacy API retained for reproducing the separately archived October-27
# degree-bounded comparison. Unlike CLI 'replay', this explicitly accepts an
# arbitrary expected Git blob; it never implies official qant validation.
git_blob_sha=git_sha

def run(path:str,expected_blob:str,inputs=24,start=0,degree=2,every=1):
    from src.anf_backends import ANFMachine
    buf=Path(path).read_bytes();sha=git_blob_sha(buf)
    if sha!=expected_blob:raise ValueError(f'Git blob SHA mismatch: actual={sha} expected={expected_blob}')
    ops=parse_kmx_subset(buf.decode('utf-8'))
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
