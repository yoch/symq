"""Bench pinned 2026 GitHub snapshot, strict real reversible test-circuit subset.

Methodology: each row identifies whether the circuit is original/full-input or
restricted to q0..q(free-1) as variables with all other qubits fixed to zero.
No claim of MQT QCEC tool benchmarking; only our Python representations are timed.
A separate tracemalloc run measures Python peak allocations; timings EXCLUDE tracing.
"""
from __future__ import annotations
import argparse,collections,json,platform,signal,statistics,sys,time,tracemalloc,random
from pathlib import Path
from src.corpus import read_corpus
from src.optimized import SetState,FastSetState,MixedState,TruthState,ResourceLimit,DegreeOverflow
from src.circuits import gf12_instructions
from src.zdd import ZDDState,AutoZDDState

class LocalTimeout(Exception):pass

def signal_timeout(*a):raise LocalTimeout('time budget reached')
signal.signal(signal.SIGALRM,signal_timeout)

def new_machine(name,free,ids):
    if name=='qant_set':return SetState(free,ids)
    if name=='fast_set':return FastSetState(free,ids)
    if name=='adaptive':return MixedState(free,ids)
    if name=='packed_only':return MixedState(free,ids,mode='packed')
    if name=='truth':return TruthState(free,ids)
    if name=='zdd':return ZDDState(free,ids)
    if name=='auto_zdd':return AutoZDDState(free,ids)
    raise ValueError(name)

def run_one(name,free,ids,ops,timeout=4,classical_inputs=()):
    t=time.perf_counter()
    signal.setitimer(signal.ITIMER_REAL,timeout)
    try:
        engine=new_machine(name,free,ids)
        for label in classical_inputs:engine.new_classical_input(label)
        engine.run(ops)
        return engine,time.perf_counter()-t,None
    except (LocalTimeout,ResourceLimit,DegreeOverflow,ValueError) as e:
        return None,time.perf_counter()-t,f'{type(e).__name__}: {e}'
    finally:signal.setitimer(signal.ITIMER_REAL,0)

def check_truth(truth,ref,seed=20261027,samples=2048):
    n=truth.n
    # Fast consistency check across independent implementations without rebuilding
    # each truth-table vector from scratch; exhaustive up to n<=12.
    rng=random.Random(seed)
    assignments=range(1<<n) if n<=12 else sorted(set(rng.randrange(1<<n) for _ in range(samples)))
    for assignment in assignments:
        bit=1<<assignment
        for q,terms in ref.states.items():
            expected=0
            for term in terms:expected^=int((term&assignment)==term)
            if bool(truth.get(q)&bit)!=bool(expected):raise AssertionError(f'truth mismatch at q{q}, x={assignment}')
        for mask,terms in ref.phase.items():
            expected=0
            for term in terms:expected^=int((term&assignment)==term)
            if bool(truth.phase.get(mask,0)&bit)!=bool(expected):raise AssertionError(f'phase mismatch at {mask}, x={assignment}')
    if set(truth.phase)!=set(ref.phase):raise AssertionError('phase key mismatch')
    return dict(assignments_checked=len(assignments),exhaustive=n<=12)

def timed_case(label,free,ids,ops,rounds=7,timeout=4,classical_inputs=(),memory=True):
    engines=['qant_set','fast_set','adaptive','packed_only','zdd','auto_zdd']+(['truth'] if free<=18 else [])
    results={};ref=None
    for engine in engines:
        times=[];last=None;error=None
        for _ in range(rounds):
            got,elapsed,issue=run_one(engine,free,ids,ops,timeout,classical_inputs)
            if issue:
                error=issue;break
            times.append(elapsed)
            last=got
        if error:
            results[engine]={'status':'UNSUPPORTED_OR_LIMIT','reason':error,'elapsed_until_failure_s':elapsed}
            continue
        payload={'status':'PASS','median_ms':round(statistics.median(times)*1000,6),
                 'all_ms':[round(x*1000,6) for x in times]}
        if engine!='truth':
            if ref is None:ref=last.digest()
            else:
                if last.digest()!=ref:raise AssertionError(f'differential mismatch {label} {engine}')
            payload['states']=last.statistics()
        elif ref is not None:
            a,dt,e=run_one('qant_set',free,ids,ops,timeout,classical_inputs)
            if e:raise ValueError(e)
            payload['independent_truth_check']=check_truth(last,a)
        if memory:
            tracemalloc.start()
            mem_engine,_,issue=run_one(engine,free,ids,ops,timeout*2,classical_inputs)
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            payload['python_peak_bytes_with_tracemalloc']=peak if not issue else None
        results[engine]=payload
    return {'case':label,'free_input_bits':free,'source_gate_count':len(ops),'result':results,
            'verification':'differential exact formal state comparison (and truth-table checks when available)',
            'source_contract':'Boolean basis-state X/CX/CCX etc; no general quantum-state equivalence'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--rounds',type=int,default=7)
    p.add_argument('--timeout',type=float,default=4);p.add_argument('--memory',action='store_true')
    p.add_argument('--stress',action='store_true',help='derived repetition of real source, NOT original corpus')
    args=p.parse_args();result=[]
    for item in read_corpus():
        for free in dict.fromkeys([6, 12, 18, item['n']]):
            if free>item['n']:continue
            label=f"MQT-QCEC/{item['name']}/"+(f"full_{free}" if free==item['n'] else f"restricted_{free}")
            ops=item['ops']
            result.append({**timed_case(label,free,tuple(range(free)),ops,args.rounds,args.timeout,memory=args.memory),
                           'source_repo':'munich-quantum-toolkit/qcec','source_git_blob':item['sha'],
                           'source_ref':'98d6784176bfeb6ef923d4d0220e8d486dc1982f',
                           'domain':'full all-qubit inputs' if free==item['n'] else 'subdomain: q0..qN-1 free; all other qubits fixed to zero'})
            print(label, ' '.join(f"{k}:{v.get('median_ms','-'+v.get('reason',''))}" for k,v in result[-1]['result'].items()),flush=True)
            if args.stress and free==12:
                ops=ops*32
                label2=f"MQT-QCEC/{item['name']}/REPEATED32_restricted12"
                result.append({**timed_case(label2,free,tuple(range(free)),ops,args.rounds,args.timeout,memory=args.memory),
                    'source_git_blob':item['sha'],'source_ref':'98d6784176bfeb6ef923d4d0220e8d486dc1982f',
                    'domain':'SYNTHETIC STRESS: source instructions repeated 32x, restricted inputs'})
    # The GF12 laboratory uses actual qant arithmetic identities but this circuit was
    # constructed for the experiment; mark it SYNTHETIC separately from real datasets.
    for echo in [0,2000,10000]:
        ops=gf12_instructions(echo_pairs=echo,with_hmr=True)
        r=timed_case(f'GF12_SYNTH/echo_{echo}',36,tuple(range(36)),ops,args.rounds,args.timeout,
                     classical_inputs=[f'm{k}' for k in range(12)],memory=args.memory)
        r['domain']='synthetic generated arithmetic and HMR phase fixture; NOT qant native circuit'
        result.append(r)
        print(r['case'],' '.join(f"{k}:{v.get('median_ms','--')}" for k,v in r['result'].items()),flush=True)
    out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    payload={'method':'pure perf_counter timings, optional independent tracemalloc peak run, medians of repeated identical executions',
      'python':sys.version,'platform':platform.platform(),'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
      'source_commit':'MQT-QCEC 98d6784176bfeb6ef923d4d0220e8d486dc1982f','experiments':result,
      'limitations':['QCEC is not executed: no mqt.qcec package available','No ZDD/PolyBoRi installed','QCEC fixtures are older algorithms in a 2026 repository snapshot','Some runs use restricted input domains','Synthetic echoes are not independent source circuits']}
    out.write_text(json.dumps(payload,indent=2)+'\n');print('saved',out)
if __name__=='__main__':main()
