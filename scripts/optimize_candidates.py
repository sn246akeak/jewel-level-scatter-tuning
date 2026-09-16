#!/usr/bin/env python3
"""Opt-in, bounded candidate search. Rankings are machine proxies, never art approval."""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import tempfile
import time
from collections import Counter
from html import escape
from pathlib import Path

from board_common import (DIR4, board_sha256, color_counts, color_family,
                          component_cells, palette_map, write_json)
from build_priority_profile import PROFILES
from validate_initial_board import validate


DEFAULTS = dict(enabled=False, max_evaluations=96, max_proposals=4096,
                max_seconds=8.0, max_rounds=2, max_candidates=3,
                preserve_regions=[])
LIMITS = dict(max_evaluations=(1, 1000), max_proposals=(1, 20000),
              max_rounds=(1, 4), max_candidates=(1, 3))


def configuration(spec):
    raw = spec.get('design', {}).get('optimizer', {})
    if not isinstance(raw, dict) or set(raw) - set(DEFAULTS):
        raise ValueError('E_OPTIMIZER_CONFIG: unknown optimizer option or invalid object')
    cfg = {**DEFAULTS, **raw}
    if type(cfg['enabled']) is not bool:
        raise ValueError('E_OPTIMIZER_CONFIG: enabled must be boolean')
    for key, (low, high) in LIMITS.items():
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f'E_OPTIMIZER_CONFIG: {key} must be an integer in {low}..{high}')
    if (type(cfg['max_seconds']) not in (int, float) or
            not math.isfinite(cfg['max_seconds']) or not 0 < cfg['max_seconds'] <= 60):
        raise ValueError('E_OPTIMIZER_CONFIG: max_seconds must be in (0, 60]')
    if not isinstance(cfg['preserve_regions'], list) or any(type(i) is not int for i in cfg['preserve_regions']):
        raise ValueError('E_OPTIMIZER_CONFIG: preserve_regions must contain analysis region IDs')
    return cfg


def validate_order(profile):
    primary = profile.get('primary_class')
    if primary not in PROFILES or profile.get('priority_order') != PROFILES[primary][1]:
        raise ValueError('E_OPTIMIZER_PROFILE: use the unchanged primary profile order')
    return profile['priority_order']


def rule_values(report, palette):
    """Reuse measured values; these tuples do not redefine the underlying R rules."""
    m = report['metrics']
    components = m['components']
    structural = [v for k, v in components.items()
                  if color_family(palette[int(k)]) in {'pale', 'dark', 'gray'}]
    boundary = m['boundary']
    return {
        'R1': (0 if report['hard_gates_passed'] else 1,),
        'R2': (m['same_base_conflict_count'],),
        'R3': (sum(max(0, r['target_color_count'] - 2) for r in m['large_source_regions']),
               sum(len(c['components4']) for c in components.values()),
               sum(m['target_groups_spanning_source_regions'].values())),
        'R4': (sum(max(0, len(c['components8']) - 1) for c in structural),),
        'R5': (sum(v.get('low', 0) for v in m['value_contrast_matrix'].values()),),
        'R6': (m['near_hue_coverage_area'], m['near_hue_jewel_adjacency_edges']),
        'R7': (m['saturated_color_adjacency_edges'], m['pale_to_bright_adjacency_edges']),
        'R8': (len(boundary['counts']), boundary['continuous_segment_count'],
               sum(v for v in boundary['counts'].values() if v == 1)),
        # Without exact symmetry, the source's art semantics remain unscored.
        'R9': (m['symmetry']['different_pairs'] if m['symmetry']['expected'] else 0,),
        'R10': (m['true_flying_points'],
                sum(sum(n for n in c['components8'] if n <= 3) for c in components.values())),
        'R11': (),
    }


def ranking_key(report, profile, palette):
    """Deterministic exploration order only; comparison determines dominance."""
    values = rule_values(report, palette)
    severity = {'pass': 0, 'warning': 1, 'fail': 2}
    return tuple((severity[report['rule_results'][r]['status']], *values[r])
                 for r in validate_order(profile) if r != 'R11')


def comparison(left, right, profile, palette):
    a, b = rule_values(left, palette), rule_values(right, palette)
    severity = {'pass': 0, 'warning': 1, 'fail': 2}
    changes, decisive, tradeoffs = {}, None, []
    for rule in validate_order(profile):
        if rule == 'R11':
            continue
        av = (severity[left['rule_results'][rule]['status']], *a[rule])
        bv = (severity[right['rule_results'][rule]['status']], *b[rule])
        if av != bv:
            improved = [i for i, (x, y) in enumerate(zip(av, bv)) if x < y]
            worsened = [i for i, (x, y) in enumerate(zip(av, bv)) if x > y]
            # No undocumented sub-priority between dimensions of the same rule.
            change = 'tradeoff' if improved and worsened else ('improved' if improved else 'worse')
            changes[rule] = {'change': change, 'before': list(bv), 'after': list(av),
                             'improved_dimensions': improved, 'worsened_dimensions': worsened}
            if worsened:
                tradeoffs.append(rule)
            decisive = decisive or rule
    return {'decision_rule': decisive, 'changes': changes, 'tradeoff_rules': tradeoffs,
            'relation': ('equivalent' if decisive is None else changes[decisive]['change'])}


def artifact_for(seed, board, regions):
    result = copy.deepcopy(seed)
    result['initialBoard'] = copy.deepcopy(board)
    result['initial'] = copy.deepcopy(board)
    result['candidate_sha256'] = board_sha256(board)
    result['region_allocations'] = {
        str(r['id']): {str(k): v for k, v in sorted(Counter(board[y][x] for x, y in r['cells']).items())}
        for r in regions}
    return result


def legal(board, seed, frozen):
    base, original = seed['completeBoard'], seed['initialBoard']
    if len(board) != len(base) or any(len(a) != len(b) for a, b in zip(board, base)):
        return False
    if color_counts(board) != color_counts(base):
        return False
    for y, row in enumerate(board):
        for x, color in enumerate(row):
            if ((color > 0) != (base[y][x] > 0) or
                    (color > 0 and color == base[y][x]) or
                    ((x, y) in frozen and color != original[y][x])):
                return False
    return True


def swapped(board, left, right):
    result = [row[:] for row in board]
    a, b = board[left[0][1]][left[0][0]], board[right[0][1]][right[0][0]]
    for x, y in left:
        result[y][x] = b
    for x, y in right:
        result[y][x] = a
    return result


def region_swaps(board, regions):
    uniform = [r for r in regions if len({board[y][x] for x, y in r['cells']}) == 1]
    for left, right in itertools.combinations(uniform, 2):
        if left['size'] == right['size']:
            yield swapped(board, left['cells'], right['cells']), {
                'operation': 'equal_region_swap', 'regions': [left['id'], right['id']]}
    # Whole-color swaps are legal only when inventory totals match.
    by_color = {}
    for y, row in enumerate(board):
        for x, c in enumerate(row):
            if c > 0:
                by_color.setdefault(c, []).append((x, y))
    for a, b in itertools.combinations(sorted(by_color), 2):
        if len(by_color[a]) == len(by_color[b]):
            yield swapped(board, by_color[a], by_color[b]), {
                'operation': 'equal_inventory_color_swap', 'colors': [a, b]}


def repartitions(board, regions):
    projections = (lambda p: (p[0], p[1]), lambda p: (-p[0], p[1]),
                   lambda p: (p[1], p[0]), lambda p: (-p[1], p[0]),
                   lambda p: (p[0] + p[1], p[1]), lambda p: (p[0] - p[1], p[1]))
    # Round robin over regions prevents the largest region consuming the entire budget.
    per_region = []
    for r in regions:
        counts = Counter(board[y][x] for x, y in r['cells'])
        if len(counts) < 2:
            continue
        colors = sorted(counts)
        orders = [colors, list(reversed(colors))]
        orders += [colors[i:] + colors[:i] for i in range(1, min(len(colors), 4))]
        def generate(region=r, quotas=counts, color_orders=orders):
            for index, projection in enumerate(projections):
                cells = sorted(region['cells'], key=projection)
                for order in color_orders:
                    result = [row[:] for row in board]
                    cursor = 0
                    for color in order:
                        for x, y in cells[cursor:cursor + quotas[color]]:
                            result[y][x] = color
                        cursor += quotas[color]
                    yield result, {'operation': 'region_repartition', 'region': region['id'],
                                   'projection': index, 'colors': order}
        per_region.append(generate())
    yield from interleave(per_region)


def small_patch_swaps(board):
    groups = component_cells(board)
    for small in sorted((r for r in groups if r['size'] <= 3), key=lambda r: (r['size'], r['id'])):
        sx, sy = small['cells'][0]
        neighbors = sorted((r for r in groups if r['color'] != small['color'] and r['size'] >= small['size']),
                           key=lambda r: (min(abs(x-sx)+abs(y-sy) for x,y in r['cells']), r['id']))
        for target in neighbors:
            allowed = set(map(tuple, target['cells']))
            start = min(allowed, key=lambda p: (abs(p[0]-sx)+abs(p[1]-sy), p[1], p[0]))
            patch, seen = [start], {start}
            for x, y in patch:
                if len(patch) >= small['size']:
                    break
                for dx, dy in DIR4:
                    cell = (x+dx, y+dy)
                    if cell in allowed and cell not in seen and len(patch) < small['size']:
                        patch.append(cell); seen.add(cell)
            if len(patch) == small['size']:
                yield swapped(board, small['cells'], patch), {
                    'operation': 'small_patch_swap', 'cells': small['cells'], 'other_cells': patch}


def interleave(iterators):
    pending = [iter(i) for i in iterators]
    while pending:
        following = []
        for it in pending:
            try:
                yield next(it)
                following.append(it)
            except StopIteration:
                pass
        pending = following


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def optimize(seed, profile, analysis, spec, *, clock=time.monotonic):
    cfg = configuration(spec)
    if not cfg['enabled']:
        raise ValueError('E_OPTIMIZER_DISABLED: opt in explicitly before searching')
    validate_order(profile)
    regions = component_cells(seed['completeBoard'])
    by_id = {r['id']: r for r in regions}
    preserved = set(cfg['preserve_regions']) | {int(k) for k in spec.get('design', {}).get('region_targets', {})}
    if preserved - set(by_id):
        raise ValueError('E_OPTIMIZER_REGION: unknown preserved analysis region')
    frozen = {tuple(cell) for i in preserved for cell in by_id[i]['cells']}
    palette = palette_map(seed['colors'])
    started = clock()
    evaluations = proposals = invalid = duplicates = 0
    stop_reason, records, seen = 'neighborhood_exhausted', [], set()
    with tempfile.TemporaryDirectory(prefix='jewel-candidates-') as tmp:
        root = Path(tmp)
        write_json(root/'profile.json', profile); write_json(root/'analysis.json', analysis)
        def evaluate(artifact):
            write_json(root/'board.json', artifact)
            report = validate(root/'board.json', root/'profile.json', root/'analysis.json')[0]
            # Temporary paths must not enter immutable IDs or reproducible outputs.
            report['profile']['path'] = artifact['profile_path']
            return report
        baseline_report = evaluate(seed)
        if not baseline_report['mechanical_validation_passed'] or not legal(seed['initialBoard'], seed, frozen):
            raise ValueError('E_OPTIMIZER_BASELINE: initial candidate must pass mechanical validation')
        baseline = {'id': 'baseline', 'artifact': copy.deepcopy(seed), 'report': baseline_report,
                    'path': [], 'comparison_to_baseline': comparison(baseline_report, baseline_report, profile, palette)}
        pool = [baseline]
        seen.add(seed['candidate_sha256'])
        def key(c):
            return ranking_key(c['report'], profile, palette), c['artifact']['candidate_sha256']
        current = baseline
        for round_index in range(cfg['max_rounds']):
            before = current
            board = current['artifact']['initialBoard']
            generators = [region_swaps(board, regions), repartitions(board, regions), small_patch_swaps(board)]
            round_limit = max(1, math.ceil(cfg['max_evaluations'] * (round_index+1) / cfg['max_rounds']))
            for changed, operation in interleave(generators):
                if clock() - started >= cfg['max_seconds']:
                    stop_reason = 'time_budget'; break
                if proposals >= cfg['max_proposals']:
                    stop_reason = 'proposal_budget'; break
                if evaluations >= cfg['max_evaluations']:
                    stop_reason = 'evaluation_budget'; break
                if evaluations >= round_limit:
                    stop_reason = 'round_budget'; break
                proposals += 1
                if not legal(changed, seed, frozen):
                    invalid += 1; continue
                h = board_sha256(changed)
                if h in seen:
                    duplicates += 1; continue
                seen.add(h)
                artifact = artifact_for(seed, changed, regions)
                report = evaluate(artifact); evaluations += 1
                if not report['mechanical_validation_passed']:
                    invalid += 1; continue
                relation = comparison(report, baseline_report, profile, palette)
                step = {'parent_sha256': current['artifact']['candidate_sha256'], **operation}
                record = {'candidate_sha256': h, 'round': round_index+1, **step, **relation}
                records.append(record)
                # Do not silently replace the baseline with a mechanically worse alternative.
                if relation['relation'] != 'worse':
                    candidate = {'id': 'candidate_' + h[:12], 'artifact': artifact, 'report': report,
                                 'path': [*current['path'], step], 'comparison_to_baseline': relation}
                    pool.append(candidate)
            improvements = [c for c in pool if comparison(c['report'], before['report'], profile, palette)['relation'] == 'improved']
            current = min(improvements, key=key) if improvements else before
            if stop_reason in {'time_budget', 'proposal_budget', 'evaluation_budget'}:
                break
            if current['artifact']['candidate_sha256'] == before['artifact']['candidate_sha256']:
                stop_reason = 'no_improving_move'; break
            if round_index+1 == cfg['max_rounds']:
                stop_reason = 'round_limit'
        # Baseline remains selectable even when all computed metrics prefer another board.
        alternatives = sorted((c for c in pool if c['id'] != 'baseline'), key=key)
        chosen = [baseline]
        if cfg['max_candidates'] > 1 and alternatives:
            chosen.append(alternatives.pop(0))
        # Reserve the last slot for a visually distinct, non-regressing measured alternative.
        if cfg['max_candidates'] > 2 and alternatives:
            def distance(c):
                a = c['artifact']['initialBoard']
                return min(sum(x != y for ar, br in zip(a, b['artifact']['initialBoard']) for x,y in zip(ar,br))
                           for b in chosen)
            alternatives.sort(key=key)
            different = max(alternatives[:12], key=lambda c: (distance(c), -len(c['path'])))
            if distance(different):
                chosen.append(different)
        improved = [c for c in chosen if c['comparison_to_baseline']['relation'] == 'improved']
        recommendation = min(improved, key=key)['id'] if improved else 'baseline'
    result = {'schema': 'jewel-candidates-v1', 'level_id': seed['level_id'],
              'source_revision': seed['source_revision'], 'candidate_revision': seed['candidate_revision'],
              'baseline_sha256': seed['candidate_sha256'], 'profile': profile,
              'candidates': chosen, 'recommended_candidate_id': recommendation,
              'status': 'awaiting_candidate_selection'}
    result['candidate_set_sha256'] = content_hash(result)
    summary = {'schema': result['schema'], 'candidate_set_sha256': result['candidate_set_sha256'],
               'status': result['status'], 'config': cfg, 'preserved_regions': sorted(preserved),
               'priority_order': profile['priority_order'], 'recommended_candidate_id': recommendation,
               'stop_reason': stop_reason, 'elapsed_seconds': round(clock()-started, 6),
               'evaluations': evaluations, 'proposals': proposals, 'invalid': invalid, 'duplicates': duplicates,
               'scope': 'Profile-ordered partial comparison; recommendation is a search suggestion, not a unique or artistic winner.',
               'metric_dimensions': {
                   'prefix': 'dimension 0 is existing validation severity',
                   'R3': ['excess region colors', '4-way components', 'source regions spanned'],
                   'R4': ['structural color fragmentation'], 'R5': ['low contrast cells'],
                   'R6': ['near hue coverage', 'near hue adjacency edges'],
                   'R7': ['saturated adjacency edges', 'pale-bright adjacency edges'],
                   'R8': ['boundary colors', 'boundary segments', 'singleton boundary colors'],
                   'R9': ['exact symmetry mismatches'], 'R10': ['flying cells', 'small component cells']},
               'unscored_semantics': ['face', 'containment', 'recognizability', 'R11 visual/play judgment'],
               'candidates': [{'id': c['id'], 'candidate_sha256': c['artifact']['candidate_sha256'],
                               'metrics': c['report']['metrics'], 'comparison_to_baseline': c['comparison_to_baseline'],
                               'path': c['path'], 'accepted': False} for c in chosen],
               'evaluated_moves': records, 'visual_review': 'not_run', 'editor_execution': 'not_run'}
    return result, summary


def render_candidates(candidate_set, path):
    seed = candidate_set['candidates'][0]['artifact']
    palette = palette_map(seed['colors'])
    panels = [('source', seed['completeBoard'])] + [(c['id'], c['artifact']['initialBoard']) for c in candidate_set['candidates']]
    scale, gap, title = 12, 24, 38
    w, h = seed['width'] * scale, seed['height'] * scale
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{(w+gap)*len(panels)+gap}" height="{h+title+gap}">',
             '<rect width="100%" height="100%" fill="#f2f2f2"/>']
    for index, (label, board) in enumerate(panels):
        ox = gap + index * (w+gap)
        parts.append(f'<text x="{ox}" y="24" font-size="14" font-family="sans-serif">{escape(label)}</text>')
        for y, row in enumerate(board):
            for x, color in enumerate(row):
                if color > 0:
                    parts.append(f'<rect x="{ox+x*scale}" y="{title+y*scale}" width="{scale}" height="{scale}" fill="{escape(palette[color])}"/>')
    parts.append('</svg>')
    path.write_text('\n'.join(parts)+'\n', encoding='utf-8')
