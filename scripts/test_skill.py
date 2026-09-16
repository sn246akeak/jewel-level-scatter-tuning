#!/usr/bin/env python3
"""Maintenance-only regression gate. No browser writes or network requests."""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from run_level import ROOT,tool_hashes
from board_common import write_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node',default=shutil.which('node'))
    args=parser.parse_args()
    if not args.node:
        parser.error('Node is required; supply --node /absolute/path/to/node')
    before=tool_hashes()
    commands=[[sys.executable,'-m','unittest','discover','-s','tests','-p','*_test.py'],
              [args.node,'--test','tests/executor.test.mjs']]
    for command in commands:
        result=subprocess.run(command,cwd=ROOT)
        if result.returncode:
            write_json(ROOT/'.runtime-validation.json',{'status':'failed'})
            return result.returncode
    if before!=tool_hashes():
        print('Runtime changed during tests; rerun maintenance validation');return 1
    write_json(ROOT/'.runtime-validation.json',{'status':'passed','tool_hashes':before,
        'validated_at':datetime.now(timezone.utc).isoformat(),
        'scope':'offline real-response fixture, plan simulation, execution state machine, and artifact pipeline',
        'live_browser_validation':'not_run'})
    result=subprocess.run([sys.executable,str(ROOT/'scripts/smoke_candidate_handoff.py'),'--node',args.node],cwd=ROOT)
    if result.returncode:
        write_json(ROOT/'.runtime-validation.json',{'status':'failed'})
        return result.returncode
    print('Runtime regression gate passed. Live browser validation: not_run.')
    return 0
if __name__=='__main__':raise SystemExit(main())
