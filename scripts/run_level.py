#!/usr/bin/env python3
"""Only normal per-level CLI. AI authors design_spec.json and visual_review.json."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from analyze_source_board import analyze
from board_common import read_json, write_json, board_sha256
from build_priority_profile import build
from design_initial_board import design, render_svg
from fetch_kstage_source import fetch_bundle
from validate_initial_board import validate
from optimize_candidates import configuration, optimize, render_candidates

ROOT = Path(__file__).resolve().parents[1]
AUTHORED = {'design_spec.json', 'visual_review.json'}
GENERATED = {'source-state.json', 'kstage_blocks.json', 'source_analysis.json', 'priority_profile.json',
             'initial_board.json', 'initial_board.svg', 'source_board.svg', 'validation_report.json',
             'run_manifest.json', 'prepare_report.json', 'editor_execution_plan.json', 'editor_execution_report.json', 'editor_preview.png',
             'candidate_set.json', 'candidate_comparison.json', 'candidate_preview.svg'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_hashes():
    return {str(p.relative_to(ROOT)): digest(p) for folder in ['scripts', 'references', 'tests']
            for p in sorted((ROOT / folder).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.mjs','.json','.md'}} | {'SKILL.md': digest(ROOT / 'SKILL.md')}


def release_check():
    certificate = ROOT / '.runtime-validation.json'
    if not certificate.exists():
        raise ValueError('E_HELPER_UNTESTED: run python3 scripts/test_skill.py before using the skill')
    data = read_json(certificate)
    if data.get('status') != 'passed' or data.get('tool_hashes') != tool_hashes():
        raise ValueError('E_HELPER_CHANGED: helper/resources changed since regression tests; run scripts/test_skill.py')
    return data


def audit_directory(run):
    unexpected = [p.name for p in run.iterdir() if p.name not in AUTHORED | GENERATED and p.name != '.DS_Store']
    if unexpected:
        raise ValueError(f'E_RUN_FILES: use a clean run folder; unexpected files: {unexpected}')


def assert_generated(run, manifest):
    for name, expected in manifest.get('generated_hashes', {}).items():
        if not (run/name).exists() or digest(run/name) != expected:
            raise ValueError(f'E_ARTIFACT_CHANGED: {name} changed outside the pipeline')


def stamp(run, manifest, phase):
    manifest['phase'] = phase
    manifest['generated_hashes'] = {name:digest(run/name) for name in sorted(GENERATED)
        if name not in {'run_manifest.json','editor_execution_plan.json','editor_execution_report.json','editor_preview.png'}
        and (run/name).exists()}
    write_json(run/'run_manifest.json', manifest)


def _pipeline(command, run, url=None, source=None, blocks=None):
    run.mkdir(parents=True, exist_ok=True)
    audit_directory(run)
    certificate = release_check()
    if command == 'prepare':
        if (run/'run_manifest.json').exists():
            raise ValueError('E_RUN_EXISTS: use analyze/design/review on this run, or a new run directory')
        state, bundle = (read_json(source), read_json(blocks)) if source and blocks else fetch_bundle(url, run/'prepare_report.json')
        if bundle.get('identity') != state.get('identity') or bundle.get('completeBoard') != state['source']['completeBoard'] or bundle.get('source_revision') != state['source']['sourceSha256']:
            raise ValueError('E_SOURCE: block bundle does not belong to source state')
        write_json(run/'source-state.json', state)
        write_json(run/'kstage_blocks.json', bundle)
        # The final candidate compiler validates the complete block partition before UI use.
        art = {'width':state['source']['grid']['width'],'height':state['source']['grid']['height'],
               'colors':state['source']['colors'],'initialBoard':state['source']['completeBoard']}
        render_svg(art, run/'source_board.svg')
        manifest = {'schema':'jewel-run-v2', 'identity':state['identity'],
                    'source_revision':state['source']['sourceSha256'], 'tool_hashes':certificate['tool_hashes'],
                    'candidate_revision':0, 'accepted':False}
        stamp(run, manifest, 'prepared')
        return manifest
    manifest = read_json(run/'run_manifest.json')
    if manifest['tool_hashes'] != certificate['tool_hashes']:
        raise ValueError('E_HELPER_CHANGED: runtime changed during this level; start a new run after maintenance')
    assert_generated(run, manifest)
    if command == 'check':
        if manifest.get('accepted') is not True or manifest.get('phase') != 'accepted':
            raise ValueError('E_NOT_ACCEPTED: complete candidate and visual validation first')
        for name in AUTHORED:
            if digest(run/name) != manifest.get('input_hashes',{}).get(name):
                raise ValueError(f'E_INPUT_CHANGED: regenerate/review after changing {name}')
        return manifest
    if command in {'analyze','design'}:
        spec = read_json(run/'design_spec.json')
        # Invalidate acceptance before doing work, including a failed regeneration.
        manifest['accepted'] = False
        stamp(run, manifest, 'generating')
        analysis = analyze(run/'source-state.json', spec.get('ai_semantics'))
        if 'matched_classes' in spec and spec['matched_classes'] != analysis['matched_classes']:
            raise ValueError('E_CLASSES: omit matched_classes to derive from measured features and semantics')
        write_json(run/'source_analysis.json', analysis)
        if command == 'analyze':
            stamp(run, manifest, 'analyzed')
            return analysis
        profile = build(analysis, spec.get('primary_class'), spec.get('secondary_classes'))
        write_json(run/'priority_profile.json', profile)
        manifest['candidate_revision'] += 1
        artifact = design(run/'source-state.json', run/'priority_profile.json', spec, manifest['candidate_revision'])
        artifact['ai_semantics'] = analysis['ai_semantics']
        write_json(run/'initial_board.json', artifact)
        render_svg(artifact, run/'initial_board.svg')
        report, _ = validate(run/'initial_board.json', run/'priority_profile.json', run/'source_analysis.json')
        write_json(run/'validation_report.json', report)
        manifest['candidate_sha256'] = board_sha256(artifact['initialBoard'])
        manifest['input_hashes'] = {'design_spec.json':digest(run/'design_spec.json')}
        cfg = configuration(spec)
        manifest['optimizer_enabled'] = cfg['enabled']
        manifest.pop('candidate_selection', None)
        if cfg['enabled']:
            candidates, comparison = optimize(artifact, profile, analysis, spec)
            write_json(run/'candidate_set.json', candidates)
            write_json(run/'candidate_comparison.json', comparison)
            render_candidates(candidates, run/'candidate_preview.svg')
            stamp(run, manifest, 'awaiting_candidate_selection')
            return {'accepted':False, 'phase':manifest['phase'],
                    'candidate_set_sha256':candidates['candidate_set_sha256'],
                    'recommended_candidate_id':candidates['recommended_candidate_id'],
                    'candidates':[{'id':c['id'], 'candidate_sha256':c['artifact']['candidate_sha256']}
                                  for c in candidates['candidates']],
                    'stop_reason':comparison['stop_reason']}
        stamp(run, manifest, 'designed')
        return {'candidate_sha256':manifest['candidate_sha256'], 'warnings':report['warnings'],
                'errors':report['errors'], 'accepted':False}
    if command == 'select':
        if not manifest.get('optimizer_enabled') or manifest.get('phase') != 'awaiting_candidate_selection':
            raise ValueError('E_CANDIDATE_PHASE: select requires an unselected experimental candidate set')
        if digest(run/'design_spec.json') != manifest.get('input_hashes',{}).get('design_spec.json'):
            raise ValueError('E_INPUT_CHANGED: run design again after changing design_spec.json')
        candidates = read_json(run/'candidate_set.json')
        review = read_json(run/'visual_review.json')
        selection = review.get('candidate_selection', {})
        if selection.get('candidate_set_sha256') != candidates['candidate_set_sha256']:
            raise ValueError('E_CANDIDATE_SET: selection must identify the latest candidate set')
        chosen = next((c for c in candidates['candidates'] if c['id'] == selection.get('candidate_id')), None)
        if not chosen or not str(selection.get('reason', '')).strip():
            raise ValueError('E_CANDIDATE_SELECTION: select a listed candidate and explain the visual choice')
        tradeoff_reviews = selection.get('tradeoff_reviews', {})
        for rule in chosen['comparison_to_baseline']['tradeoff_rules']:
            evidence = tradeoff_reviews.get(rule, {}) if isinstance(tradeoff_reviews, dict) else {}
            if (not isinstance(evidence, dict) or evidence.get('status') != 'pass' or
                    not isinstance(evidence.get('evidence'), str) or not evidence['evidence'].strip()):
                raise ValueError(f'E_CANDIDATE_TRADEOFF: inspect and justify worsened metrics for {rule}')
        artifact = chosen['artifact']
        if review.get('candidate_sha256') != artifact['candidate_sha256']:
            raise ValueError('E_CANDIDATE_HASH: review must identify the selected board')
        manifest['accepted'] = False
        manifest['candidate_selection'] = selection
        manifest['candidate_sha256'] = artifact['candidate_sha256']
        write_json(run/'initial_board.json', artifact)
        render_svg(artifact, run/'initial_board.svg')
        # Choosing a board does not accept it; normal visual review still follows.
        report, _ = validate(run/'initial_board.json',run/'priority_profile.json',run/'source_analysis.json')
        write_json(run/'validation_report.json', report)
        stamp(run, manifest, 'designed')
        return {'accepted':False, 'phase':'designed', 'candidate_sha256':artifact['candidate_sha256']}
    if command == 'review':
        if manifest.get('optimizer_enabled') and not manifest.get('candidate_selection'):
            raise ValueError('E_CANDIDATE_SELECTION: inspect candidates and select one before review')
        if digest(run/'design_spec.json') != manifest.get('input_hashes',{}).get('design_spec.json'):
            raise ValueError('E_INPUT_CHANGED: run design again after changing design_spec.json')
        if manifest.get('optimizer_enabled'):
            review = read_json(run/'visual_review.json')
            if (review.get('candidate_selection') != manifest['candidate_selection'] or
                    review.get('candidate_sha256') != manifest['candidate_sha256']):
                raise ValueError('E_CANDIDATE_SELECTION: review does not match the selected candidate')
        report, _ = validate(run/'initial_board.json', run/'priority_profile.json', run/'source_analysis.json', run/'visual_review.json')
        write_json(run/'validation_report.json', report)
        manifest['accepted'] = report['accepted']
        manifest['input_hashes']['visual_review.json'] = digest(run/'visual_review.json')
        stamp(run, manifest, 'accepted' if report['accepted'] else 'review_failed')
        return {'accepted':report['accepted'], 'unresolved_warning_rules':report['unresolved_warning_rules'], 'errors':report['errors']}
    raise ValueError(f'Unknown command {command}')


def pipeline(command, run, url=None, source=None, blocks=None):
    try:
        return _pipeline(command, run, url, source, blocks)
    except Exception:
        # A generation failure must never leave an accepted candidate active, and
        # must still permit a corrected spec to be regenerated normally.
        manifest_path = run/'run_manifest.json'
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            if manifest.get('phase') == 'generating':
                manifest['accepted'] = False
                stamp(run, manifest, 'generation_failed')
        raise


def browser_code(run, action, browser_id='1', visual_matches=None):
    """Print exact CUA expressions; no hand-written session/logging wrapper is needed."""
    pipeline('check', run)
    if action == 'setup':
        module = json.dumps(str(ROOT/'scripts/kstage_executor.mjs'))
        options = '{runDir: ' + json.dumps(str(run.resolve())) + ', listTabs: () => cua.listTabs({browser: ' + json.dumps(browser_id) + ', emit: false})}'
        return (f'var kstageRuntime = await import({module});\n'
                f'var kstageOptions = {options};\n'
                'nodeRepl.write(await kstageRuntime.runStep(tab, kstageOptions));')
    if action == 'advance':
        return 'nodeRepl.write(await kstageRuntime.runStep(tab, kstageOptions));'
    if action == 'status':
        return 'nodeRepl.write(await kstageRuntime.runStep(tab, {...kstageOptions, action: "status"}));'
    if action == 'finish' and type(visual_matches) is bool:
        return 'nodeRepl.write(await kstageRuntime.runStep(tab, {...kstageOptions, action: "finish", visualMatches: ' + json.dumps(visual_matches) + '}));'
    raise ValueError('finish requires an explicit --visual-matches true or false')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','analyze','design','select','review','check','browser-code'])
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--url')
    parser.add_argument('--source',type=Path,help='Offline maintenance fixture only')
    parser.add_argument('--blocks',type=Path,help='Offline maintenance fixture only')
    parser.add_argument('--browser-action',choices=['setup','advance','status','finish'],default='setup')
    parser.add_argument('--browser-id',default='1')
    parser.add_argument('--visual-matches',choices=['true','false'])
    args=parser.parse_args()
    try:
        if args.command=='browser-code':
            print(browser_code(args.run,args.browser_action,args.browser_id,
                               None if args.visual_matches is None else args.visual_matches=='true'))
            return 0
        if args.command=='prepare' and not (args.url or (args.source and args.blocks)):
            parser.error('prepare requires --url or --source and --blocks')
        result=pipeline(args.command,args.run,args.url,args.source,args.blocks)
        print(json.dumps(result if args.command in {'analyze','design','review'} else
                         {'phase':result['phase'],'accepted':result['accepted']},ensure_ascii=False))
        return 1 if result.get('errors') or (args.command=='review' and not result['accepted']) else 0
    except (ValueError,KeyError,FileNotFoundError) as error:
        print(str(error))
        return 1

if __name__=='__main__':
    raise SystemExit(main())
