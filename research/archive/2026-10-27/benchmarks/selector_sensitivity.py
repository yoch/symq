"""Threshold sensitivity measured on pinned MQT-QCEC circuits (no source modification)."""
from __future__ import annotations
import argparse, json, statistics, time, platform
from pathlib import Path
from src.corpus import read_corpus
from src.optimized import FastSetState
from src.zdd import AutoZDDState

THRESHOLDS=(100,200,300,400,600,850,1200,2500)

def measure(entry,threshold,reps):
    times=[];instance=None
    for _ in range(reps):
        start=time.perf_counter()
        instance=AutoZDDState(entry['n'],tuple(range(entry['n'])),threshold=threshold).run(entry['ops'])
        times.append(1000*(time.perf_counter()-start))
    baseline=FastSetState(entry['n'],tuple(range(entry['n']))).run(entry['ops'])
    assert instance.digest()==baseline.digest()
    return dict(median_ms=round(statistics.median(times),6),switch_at=instance.switch_op)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--rounds',type=int,default=5);args=ap.parse_args()
    result=[]
    for e in read_corpus():
        max_target=0; peak=0
        curr=FastSetState(e['n'],tuple(range(e['n'])))
        for op,qs,cond,out in e['ops']:
            curr.step(op,qs,cond,out)
            if op in ('CCX','MCX'):max_target=max(max_target,len(curr.get(qs[-1])))
            peak=max(peak,sum(map(len,curr.states.values())))
        result.append(dict(name=e['name'],number_gates=len(e['ops']),max_nonlinear_target_terms=max_target,max_alive_terms=peak,
                           train_group=e['name'] in ['c2_181','mod5adder_306','rd73_312','rd84_313','sym9_317'],
                           thresholds={str(t):measure(e,t,args.rounds) for t in THRESHOLDS}))
        print(e['name'],'max target',max_target,'switches',{t:d['switch_at'] for t,d in result[-1]['thresholds'].items()},flush=True)
    out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    out.write_text(json.dumps({'thresholds':THRESHOLDS,'results':result,'rounds':args.rounds,'platform':platform.platform()},indent=2)+'\n')
    print('WROTE',out)

if __name__=='__main__':main()
