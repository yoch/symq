"""Produce a concise numeric overview from raw v3 benchmark results."""
from __future__ import annotations
import json,statistics,sys
from pathlib import Path

def summary(path:Path):
    raw=json.loads(path.read_text())
    full=[x for x in raw['experiments'] if x['case'].startswith('MQT-QCEC/') and '/full_' in x['case']]
    other=[x for x in full if 'c2_181' not in x['case']]
    c2=next(x for x in full if 'c2_181' in x['case'])
    m=lambda x,k:x['result'][k]['median_ms']
    return {
        'real_source_circuits_full_inputs':len(full),
        'experiments_including_restricted_and_synthetic':len(raw['experiments']),
        'pathological_c2_181':{
            'baseline_set_ms':m(c2,'copy_set'),'fast_set_ms':m(c2,'fast_set'),
            'pure_python_zdd_ms':m(c2,'zdd'),'adaptive_zdd_ms':m(c2,'auto_zdd'),
            'adaptive_speedup_over_set':round(m(c2,'copy_set')/m(c2,'auto_zdd'),2),
            'sparse_python_peak_bytes':c2['result']['copy_set']['python_peak_bytes_with_tracemalloc'],
            'auto_zdd_python_peak_bytes':c2['result']['auto_zdd']['python_peak_bytes_with_tracemalloc']
        },
        'other_10_full_circuits':{
            'median_fast_set_speedup_over_set':round(statistics.median(m(x,'copy_set')/m(x,'fast_set') for x in other),2),
            'median_zdd_slowdown_vs_fast_set':round(statistics.median(m(x,'zdd')/m(x,'fast_set') for x in other),2),
            'median_auto_speedup_over_set':round(statistics.median(m(x,'copy_set')/m(x,'auto_zdd') for x in other),2)
        },
        'all_algorithms_checked_differentially':['copy_set','fast_set','adaptive','zdd','auto_zdd'],
        'notes':['MR soundness is restricted to the supported Boolean/phase model',
                 'No external industrial MQT QCEC or PolyBoRi binary performance measured',
                 'Tracemalloc peak is not OS RSS']
    }

if __name__=='__main__':
    input=Path(sys.argv[1]) if len(sys.argv)>1 else Path('results/bench_public_final_v3.json')
    print(json.dumps(summary(input),indent=2))
