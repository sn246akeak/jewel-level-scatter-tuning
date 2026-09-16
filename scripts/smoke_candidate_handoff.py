#!/usr/bin/env python3
"""Offline integration: real pipeline -> unchanged JS loader -> paint simulation.

Synthetic review evidence is confined to a disposable test directory, never a level.
Run after the runtime regression certificate is written. No network or browser use.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from board_common import read_json, write_json
from run_level import ROOT, pipeline
from validate_initial_board import AI_CHECK_KEYS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    args = parser.parse_args()
    fixture = read_json(ROOT/'tests/fixtures/asset-2748.json')
    with tempfile.TemporaryDirectory(prefix='jewel-offline-handoff-') as temp:
        root = Path(temp); run = root/'run'
        write_json(root/'source.json', fixture['state'])
        write_json(root/'blocks.json', fixture['blocks'])
        pipeline('prepare', run, source=root/'source.json', blocks=root/'blocks.json')
        write_json(run/'design_spec.json', {
            'primary_class':'F9', 'ai_semantics':{'contains_face_or_expression':True},
            'design':{'optimizer':{'enabled':True, 'max_evaluations':12, 'max_seconds':30}}})
        pipeline('design', run)
        script = '''
import assert from 'node:assert/strict';
import {loadAcceptedRun} from './scripts/kstage_executor.mjs';
import {buildHybridPaintPlan,simulatePlan} from './scripts/kstage_prefill_helpers.mjs';
const [run, mode]=process.argv.slice(1);
if(mode==='blocked') assert.throws(()=>loadAcceptedRun(run),{code:'E_NOT_ACCEPTED'});
else {
 const {board,source}=loadAcceptedRun(run);
 const plan=buildHybridPaintPlan(board,{sourceBlocks:source.blocks});
 assert.deepEqual(simulatePlan(board,source.blocks,plan),board.initialBoard);
 console.log(JSON.stringify({candidate:board.candidate_sha256,totalCells:plan.totalCells,simulated:true}));
}
'''
        def check(mode):
            subprocess.run([args.node,'--input-type=module','-e',script,str(run),mode], cwd=ROOT, check=True)
        check('blocked')
        candidates = read_json(run/'candidate_set.json')
        chosen = candidates['candidates'][-1]
        assert chosen['id'] != 'baseline', 'fixture must exercise an experimental board'
        evidence = {'status':'pass','evidence':'Synthetic disposable integration test only; not visual approval'}
        write_json(run/'visual_review.json', {
            'candidate_sha256':chosen['artifact']['candidate_sha256'],
            'candidate_selection':{'candidate_set_sha256':candidates['candidate_set_sha256'],
                'candidate_id':chosen['id'], 'reason':'Synthetic offline handoff',
                'tradeoff_reviews':{r:evidence for r in chosen['comparison_to_baseline']['tradeoff_rules']}},
            'ai_visual_checks':{r:evidence for r in AI_CHECK_KEYS},
            'warning_reviews':{r:evidence for r in chosen['report']['unresolved_warning_rules']}})
        pipeline('select', run)
        check('blocked')
        assert pipeline('review', run)['accepted']
        pipeline('check', run)
        check('accepted')
    print('Offline candidate handoff passed; temporary synthetic approvals removed.')


if __name__ == '__main__':
    main()
