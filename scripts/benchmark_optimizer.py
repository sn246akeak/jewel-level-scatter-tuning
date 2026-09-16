#!/usr/bin/env python3
"""Read-only historical comparison; outputs to a fresh directory, never to old runs."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from html import escape
from pathlib import Path

from analyze_source_board import analyze
from board_common import board_sha256, palette_map, read_json, source_payload, write_json
from build_priority_profile import build
from design_initial_board import design
from optimize_candidates import comparison, optimize, render_candidates


def snapshot(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and not any(s in {'.git', '__pycache__'} for s in p.relative_to(root).parts)
            and p.name != '.DS_Store'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history',type=Path,required=True)
    p.add_argument('--baseline-skill',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-evaluations',type=int,default=96)
    p.add_argument('--max-seconds',type=float,default=8)
    p.add_argument('--profile-ablation',action='store_true',help='Also compare valid F3/F4 on identical seeds')
    args=p.parse_args()
    args.history=args.history.resolve();args.baseline_skill=args.baseline_skill.resolve();args.output=args.output.resolve()
    if args.output.exists():p.error('Use a new output directory to retain previous evidence')
    if args.output.is_relative_to(args.history) or args.output.is_relative_to(args.baseline_skill):
        p.error('Output must be outside the historical and installed Skill directories')
    args.output.mkdir(parents=True)
    before=snapshot(args.baseline_skill)
    write_json(args.output/'stable_before.json',before)
    # Deduplicate source revisions; prefer the final managed-entry dog run.
    sources={}
    for source in sorted(args.history.glob('*/source-state.json')):
        data=read_json(source)
        identity=source_payload(data)[:2]
        sources[identity]=source
    results=[]
    for _,source in sorted(sources.items()):
        directory=source.parent
        old_analysis=read_json(directory/'source_analysis.json') if (directory/'source_analysis.json').exists() else {}
        old_profile=read_json(directory/'priority_profile.json') if (directory/'priority_profile.json').exists() else {}
        spec=read_json(directory/'design_spec.json') if (directory/'design_spec.json').exists() else {
            'ai_semantics':old_analysis.get('ai_semantics',{}), 'primary_class':old_profile.get('primary_class'),'design':{}}
        spec=copy.deepcopy(spec)
        # Historical class lists can be stale; measured classes are rebuilt on both sides.
        spec.pop('matched_classes',None);spec.pop('secondary_classes',None)
        spec.setdefault('design',{}).pop('optimizer',None)
        case=args.output/directory.name;case.mkdir()
        record={'case':directory.name,'source':str(source),
                'input_provenance':'historical_design_spec' if (directory/'design_spec.json').exists() else 'historical_analysis_and_profile',
                'visual_review':'not_run','editor_execution':'not_run'}
        watched={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in directory.glob('*.json')}
        try:
            analysis=analyze(source,spec.get('ai_semantics'))
            profile=build(analysis,spec.get('primary_class'))
            write_json(case/'source_analysis.json',analysis);write_json(case/'priority_profile.json',profile)
            write_json(case/'baseline_spec.json',spec)
            # Run the installed generator in its own interpreter: no accidental import of new code.
            command=[sys.executable,str(args.baseline_skill/'scripts/design_initial_board.py'),
                     str(source),'--profile',str(case/'priority_profile.json'),
                     '--spec',str(case/'baseline_spec.json'),'--output',str(case/'legacy_board.json')]
            old=subprocess.run(command,capture_output=True,text=True)
            if old.returncode:raise ValueError('legacy_generation: '+old.stderr[-1500:])
            baseline=design(source,case/'priority_profile.json',spec)
            legacy=read_json(case/'legacy_board.json')
            record['default_board_equal']=baseline==legacy
            if not record['default_board_equal']:raise ValueError('disabled output differs from installed generator')
            spec['design']['optimizer']={'enabled':True,'max_evaluations':args.max_evaluations,'max_seconds':args.max_seconds}
            write_json(case/'experimental_spec.json',spec)
            began=time.monotonic()
            candidates,summary=optimize(baseline,profile,analysis,spec)
            write_json(case/'candidate_set.json',candidates);write_json(case/'candidate_comparison.json',summary)
            render_candidates(candidates,case/'candidate_preview.svg')
            recommended=next(c for c in candidates['candidates'] if c['id']==candidates['recommended_candidate_id'])
            b=candidates['candidates'][0]
            record.update(status='ok',primary=profile['primary_class'],matched=analysis['matched_classes'],
                          art_cells=analysis['dimensions']['art_cells'],elapsed_seconds=round(time.monotonic()-began,4),
                          evaluations=summary['evaluations'],stop_reason=summary['stop_reason'],
                          candidate_count=len(candidates['candidates']),
                          hard_gates_passed=all(c['report']['hard_gates_passed'] for c in candidates['candidates']),
                          baseline_sha256=baseline['candidate_sha256'],recommended_sha256=recommended['artifact']['candidate_sha256'],
                          comparison=recommended['comparison_to_baseline'],
                          before=b['report']['metrics'],after=recommended['report']['metrics'])
            if args.profile_ablation and {'F3','F4'}.issubset(analysis['matched_classes']):
                ablation=[]
                for primary in ['F3','F4']:
                    cp=build(analysis,primary)
                    cs,cr=optimize(baseline,cp,analysis,spec)
                    pick=next(c for c in cs['candidates'] if c['id']==cs['recommended_candidate_id'])
                    write_json(case/f'ablation_{primary}.json',cr)
                    ablation.append({'primary':primary,'recommended_sha256':pick['artifact']['candidate_sha256'],
                                     'evaluations':cr['evaluations'],'stop_reason':cr['stop_reason']})
                record['profile_ablation']=ablation
                record['profile_changed_board']=ablation[0]['recommended_sha256']!=ablation[1]['recommended_sha256']
        except Exception as exc:
            record.update(status='failed',error=str(exc))
        record['historical_inputs_unchanged']=all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in watched.items())
        results.append(record)
        write_json(args.output/'benchmark_summary.json',{'cases':results,'status':'running'})
        print(json.dumps({k:record.get(k) for k in ['case','status','primary','default_board_equal','candidate_count','elapsed_seconds','error']},ensure_ascii=False),flush=True)
    after=snapshot(args.baseline_skill)
    write_json(args.output/'stable_after.json',after)
    summary={'status':'passed' if all(r['status']=='ok' and r['historical_inputs_unchanged'] for r in results) and before==after else 'failed',
             'case_count':len(results),'stable_unchanged':before==after,
             'primary_coverage':dict(Counter(r.get('primary','failed') for r in results)),
             'measured_improvements':sum(r.get('comparison',{}).get('relation')=='improved' for r in results),
             'visual_improvement':'not_established','human_edit_time':'not_measured',
             'cases':results}
    write_json(args.output/'benchmark_summary.json',summary)
    rows=['# 历史图离线对照','', '基线为相同输入由已安装脚本重新生成的初稿。机器指标改善不等于审美通过。',
          '', '| 图片 | 主分类 | 默认输出一致 | 候选数 | 首个改善规则 | 搜索秒数 | 状态 |', '|---|---|---|---|---|---|---|']
    html=['<!doctype html><meta charset="utf-8"><title>配色候选离线对照</title>',
          '<style>body{font-family:system-ui;margin:32px;color:#222}img{max-width:100%;image-rendering:pixelated}section{margin:32px 0}p{max-width:1000px}</style>',
          '<h1>配色候选离线对照</h1><p>左起为原图、旧算法初稿和实验候选。机器推荐尚未经人工盲评，全部停止在视觉选择之前。</p>']
    for r in results:
        rows.append(f"| {r['case']} | {r.get('primary','')} | {r.get('default_board_equal','')} | {r.get('candidate_count','')} | {r.get('comparison',{}).get('decision_rule') or '无'} | {r.get('elapsed_seconds','')} | {r['status']} |")
        if r['status']=='ok':
            html.append(f"<section><h2>{escape(r['case'])} {escape(r['primary'])}</h2><p>推荐变化：{escape(str(r['comparison']))}</p><img src=\"{escape(r['case'])}/candidate_preview.svg\"></section>")
    rows+=['',f"稳定版内容未变：{summary['stable_unchanged']}。机器指标改善：{summary['measured_improvements']}/{len(results)}。",
           '尚未完成：用户盲评、人工修改耗时、留出集、实验版线上保存。']
    (args.output/'benchmark_report.md').write_text('\n'.join(rows)+'\n')
    (args.output/'index.html').write_text('\n'.join(html))
    return 0 if summary['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
