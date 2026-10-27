"""Opt-in original-source audit for pinned public MQT QCEC QASM files.

The corpus is self-contained and normalized. This optional source verification
fetches each original QASM file, checks its actual Git blob SHA-1 and compares
all decoded gates, refusing any newly unsupported instruction. No git required.

Usage:
  PYTHONPATH=. python tools/verify_qcec_sources.py
  PYTHONPATH=. python tools/verify_qcec_sources.py --offline-dir /path/to/qcec

The network is attempted only when invoked explicitly. It never writes to qant.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from urllib.request import Request, urlopen

from src.corpus import read_corpus, parse_qasm_strict

REPO='munich-quantum-toolkit/qcec'
REF='98d6784176bfeb6ef923d4d0220e8d486dc1982f'


def git_blob_sha(contents: bytes)->str:
    return hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline-dir',type=Path,help='local QCEC checkout root; no network')
    p.add_argument('--timeout',type=int,default=20)
    args=p.parse_args();report=[]
    for entry in read_corpus():
        path=f"test/circuits/original/{entry['name']}.qasm"
        if args.offline_dir:
            data=(args.offline_dir/path).read_bytes()
        else:
            url=f'https://raw.githubusercontent.com/{REPO}/{REF}/{path}'
            with urlopen(Request(url,headers={'User-Agent':'anf-corpus-audit/1.0'}),timeout=args.timeout) as response:
                data=response.read(2_000_000)
        blob=git_blob_sha(data)
        if blob!=entry['sha']:
            raise AssertionError(f'Git blob mismatch {path}: {blob} != {entry["sha"]}')
        width,ops=parse_qasm_strict(data.decode('utf-8'))
        if width!=entry['n'] or ops!=entry['ops']:
            raise AssertionError(f'Gate or width mismatch {path}')
        report.append({'file':path,'git_blob_sha':blob,'number_operations':len(ops),'status':'MATCH'})
    print(json.dumps({'repository':REPO,'commit_sha':REF,'count':len(report),'results':report},indent=2))

if __name__=='__main__': main()
