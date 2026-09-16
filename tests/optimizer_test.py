import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_source_board import analyze
from board_common import board_sha256, color_counts, component_cells, palette_map, write_json
from build_priority_profile import build, PROFILES
from design_initial_board import design
from optimize_candidates import (comparison, configuration, legal, optimize,
                                 ranking_key, region_swaps, repartitions, small_patch_swaps)
from run_level import pipeline, tool_hashes, browser_code
from validate_initial_board import AI_CHECK_KEYS, validate

FIXTURE = json.loads((Path(__file__).parent/'fixtures/asset-2748.json').read_text())


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source, self.blocks = self.root/'source.json', self.root/'blocks.json'
        write_json(self.source, FIXTURE['state']); write_json(self.blocks, FIXTURE['blocks'])
        self.spec = {'primary_class':'F9', 'ai_semantics':{'contains_face_or_expression':True},
                     'design':{'optimizer':{'enabled':True, 'max_evaluations':12,
                                            'max_proposals':200, 'max_rounds':1, 'max_seconds':30}}}
        self.analysis = analyze(self.source, self.spec['ai_semantics'])
        self.profile = build(self.analysis, 'F9')
        self.profile_path = self.root/'priority_profile.json';write_json(self.profile_path, self.profile)
        self.baseline = design(self.source, self.profile_path, self.spec)
        self.palette = palette_map(self.baseline['colors'])
        self.run = self.root/'run'
        self.release = patch('run_level.release_check', return_value={'status':'passed','tool_hashes':tool_hashes()})
        self.release.start()

    def tearDown(self):
        self.release.stop();self.tmp.cleanup()

    def make_run(self, spec=None):
        pipeline('prepare', self.run, source=self.source, blocks=self.blocks)
        write_json(self.run/'design_spec.json', spec or self.spec)
        return pipeline('design', self.run)

    def review_input(self, candidate=None, candidate_set=None):
        candidate_set = candidate_set or json.loads((self.run/'candidate_set.json').read_text())
        candidate = candidate or candidate_set['candidates'][0]
        review = {'candidate_sha256':candidate['artifact']['candidate_sha256'],
                  'candidate_selection':{'candidate_set_sha256':candidate_set['candidate_set_sha256'],
                                         'candidate_id':candidate['id'], 'reason':'Synthetic test selection'},
                  'ai_visual_checks':{k:{'status':'pass','evidence':'Synthetic test evidence, not artistic approval'}
                                      for k in AI_CHECK_KEYS},
                  'warning_reviews':{r:{'status':'pass','evidence':'Synthetic warning evidence'}
                                     for r in candidate['report']['unresolved_warning_rules']}}
        write_json(self.run/'visual_review.json', review)
        return review

    def test_default_and_disabled_match_existing_generator_exactly(self):
        for optimizer in [None, {'enabled':False}]:
            with self.subTest(optimizer=optimizer):
                spec = copy.deepcopy(self.spec)
                spec['design'] = {} if optimizer is None else {'optimizer':optimizer}
                self.run = self.root/('off'+str(optimizer is None))
                self.make_run(spec)
                generated = json.loads((self.run/'initial_board.json').read_text())
                expected = design(self.source, self.profile_path, spec)
                expected['ai_semantics'] = self.analysis['ai_semantics']
                self.assertEqual(generated, expected)
                self.assertFalse((self.run/'candidate_set.json').exists())

    def test_every_selected_candidate_keeps_inventory_mask_and_hard_gates(self):
        candidates, report = optimize(self.baseline, self.profile, self.analysis, self.spec)
        self.assertLessEqual(report['evaluations'], 12)
        self.assertLessEqual(report['proposals'], 200)
        self.assertEqual(candidates['candidates'][0]['id'], 'baseline')
        self.assertLessEqual(len(candidates['candidates']), 3)
        hashes = set()
        for c in candidates['candidates']:
            board = c['artifact']['initialBoard']
            self.assertTrue(legal(board, self.baseline, set()))
            self.assertTrue(c['report']['hard_gates_passed'])
            self.assertFalse(c['report']['accepted'])
            self.assertEqual(color_counts(board), color_counts(self.baseline['completeBoard']))
            self.assertNotEqual(c['comparison_to_baseline']['relation'], 'worse')
            hashes.add(board_sha256(board))
        self.assertEqual(len(hashes),len(candidates['candidates']))

    def test_same_inputs_reproduce_candidate_boards_and_decisions(self):
        a, ar = optimize(self.baseline, self.profile, self.analysis, self.spec)
        b, br = optimize(self.baseline, self.profile, self.analysis, self.spec)
        self.assertEqual(a, b)
        ar.pop('elapsed_seconds');br.pop('elapsed_seconds')
        self.assertEqual(ar, br)

    def test_real_priority_conflict_selects_different_winner(self):
        # Hold every other measured dimension equal and isolate R6 vs R7.
        candidates, _ = optimize(self.baseline, self.profile, self.analysis, self.spec)
        a = copy.deepcopy(candidates['candidates'][0]['report']);b=copy.deepcopy(a)
        for report in [a,b]:
            report['rule_results']['R6']['status']='warning'
            report['rule_results']['R7']['status']='warning'
        a['metrics']['near_hue_coverage_area']=1;b['metrics']['near_hue_coverage_area']=100
        a['metrics']['saturated_color_adjacency_edges']=100;b['metrics']['saturated_color_adjacency_edges']=1
        p3={'primary_class':'F3','priority_order':PROFILES['F3'][1]}
        p4={'primary_class':'F4','priority_order':PROFILES['F4'][1]}
        self.assertLess(ranking_key(a,p3,self.palette),ranking_key(b,p3,self.palette))
        self.assertLess(ranking_key(b,p4,self.palette),ranking_key(a,p4,self.palette))
        self.assertEqual(comparison(a,b,p3,self.palette)['decision_rule'],'R6')
        self.assertEqual(comparison(b,a,p4,self.palette)['decision_rule'],'R7')
        # Arbitrarily large improvements later cannot erase the first-rule loss.
        b['metrics']['true_flying_points']=0;a['metrics']['true_flying_points']=10000
        self.assertLess(ranking_key(a,p3,self.palette),ranking_key(b,p3,self.palette))

    def test_declared_regions_and_region_targets_are_preserved(self):
        regions = component_cells(self.baseline['completeBoard'])
        spec=copy.deepcopy(self.spec)
        spec['design']['optimizer']['preserve_regions']=[r['id'] for r in regions]
        cs, report = optimize(self.baseline,self.profile,self.analysis,spec)
        self.assertEqual(len(cs['candidates']),1)
        self.assertEqual(cs['candidates'][0]['artifact'],self.baseline)
        # A design constraint freezes its region even without preserve_regions.
        r=regions[0]
        spec=copy.deepcopy(self.spec)
        spec['design']['region_targets']={str(r['id']):self.baseline['region_allocations'][str(r['id'])]}
        cs,_=optimize(self.baseline,self.profile,self.analysis,spec)
        for c in cs['candidates']:
            self.assertTrue(all(c['artifact']['initialBoard'][y][x]==self.baseline['initialBoard'][y][x]
                                for x,y in r['cells']))

    def test_same_rule_tradeoff_cannot_be_hidden_by_metric_order(self):
        cs, _ = optimize(self.baseline, self.profile, self.analysis, self.spec)
        before = cs['candidates'][0]['report']; after = copy.deepcopy(before)
        after['metrics']['saturated_color_adjacency_edges'] -= 1
        after['metrics']['pale_to_bright_adjacency_edges'] += 1
        after['metrics']['true_flying_points'] = 0
        result = comparison(after, before, {'primary_class':'F4','priority_order':PROFILES['F4'][1]}, self.palette)
        self.assertEqual(result['relation'], 'tradeoff')
        self.assertEqual(result['decision_rule'], 'R7')
        self.assertIn('R7', result['tradeoff_rules'])
        self.assertEqual(result['changes']['R7']['worsened_dimensions'], [2])

    def test_select_requires_explicit_review_of_every_measured_sacrifice(self):
        self.make_run()
        cs = json.loads((self.run/'candidate_set.json').read_text())
        candidates = [c for c in cs['candidates'] if c['comparison_to_baseline']['tradeoff_rules']]
        self.assertTrue(candidates, 'fixture must exercise a real measured tradeoff')
        chosen = candidates[0]
        review = self.review_input(chosen, cs)
        for evidence in [None, {}, {'status':'fail','evidence':'Rejected'}, {'status':'pass','evidence':' '}]:
            review['candidate_selection']['tradeoff_reviews'] = {r:evidence for r in chosen['comparison_to_baseline']['tradeoff_rules']}
            write_json(self.run/'visual_review.json', review)
            with self.assertRaisesRegex(ValueError, 'E_CANDIDATE_TRADEOFF'):
                pipeline('select', self.run)
        review['candidate_selection']['tradeoff_reviews'] = {
            r:{'status':'pass','evidence':'Synthetic targeted test evidence only'}
            for r in chosen['comparison_to_baseline']['tradeoff_rules']}
        write_json(self.run/'visual_review.json', review)
        self.assertFalse(pipeline('select', self.run)['accepted'])

    def test_deadline_stops_without_fabricating_success(self):
        ticks=iter([0, 100, 101])
        cs,report=optimize(self.baseline,self.profile,self.analysis,self.spec,clock=lambda:next(ticks))
        self.assertEqual(report['stop_reason'],'time_budget')
        self.assertEqual(report['evaluations'],0)
        self.assertEqual(len(cs['candidates']),1)
        self.assertEqual(cs['status'],'awaiting_candidate_selection')

    def test_invalid_config_profile_baseline_and_unknown_region_rejected(self):
        for opt in [{'enabled':'true'}, {'max_evaluations':0}, {'max_seconds':float('nan')},
                    {'weights':{}}, {'preserve_regions':['one']}]:
            with self.subTest(opt=opt), self.assertRaisesRegex(ValueError,'E_OPTIMIZER_CONFIG'):
                configuration({'design':{'optimizer':opt}})
        profile=copy.deepcopy(self.profile);profile['priority_order'][2:4]=reversed(profile['priority_order'][2:4])
        with self.assertRaisesRegex(ValueError,'E_OPTIMIZER_PROFILE'):
            optimize(self.baseline,profile,self.analysis,self.spec)
        spec=copy.deepcopy(self.spec);spec['design']['optimizer']['preserve_regions']=[999999]
        with self.assertRaisesRegex(ValueError,'E_OPTIMIZER_REGION'):
            optimize(self.baseline,self.profile,self.analysis,spec)
        bad=copy.deepcopy(self.baseline);bad['initialBoard']=bad['completeBoard'];bad['initial']=bad['initialBoard']
        bad['candidate_sha256']=board_sha256(bad['initialBoard'])
        with self.assertRaisesRegex(ValueError,'E_OPTIMIZER_BASELINE'):
            optimize(bad,self.profile,self.analysis,self.spec)

    def test_operations_preserve_inventory_and_mask_before_r2_filter(self):
        board=[[2,2,3,3],[2,1,1,3],[1,1,-1,-1]]
        regions=component_cells(board)
        for generator in [region_swaps(board,regions),repartitions(board,[{'id':0,'size':10,'cells':[(x,y) for y,r in enumerate(board) for x,c in enumerate(r) if c>0]}]),small_patch_swaps(board)]:
            for changed,_ in generator:
                self.assertEqual(color_counts(changed),color_counts(board))
                self.assertEqual([[c>0 for c in row] for row in changed],[[c>0 for c in row] for row in board])

    def test_checkpoint_blocks_review_check_and_browser_setup(self):
        result=self.make_run()
        self.assertEqual(result['phase'],'awaiting_candidate_selection')
        self.assertFalse(result['accepted'])
        self.review_input()
        with self.assertRaisesRegex(ValueError,'E_CANDIDATE_SELECTION'):pipeline('review',self.run)
        with self.assertRaisesRegex(ValueError,'E_NOT_ACCEPTED'):pipeline('check',self.run)
        with self.assertRaisesRegex(ValueError,'E_NOT_ACCEPTED'):browser_code(self.run,'setup')

    def test_select_then_review_and_check_bind_one_candidate(self):
        self.make_run();cs=json.loads((self.run/'candidate_set.json').read_text())
        chosen=cs['candidates'][-1];self.review_input(chosen,cs)
        result=pipeline('select',self.run)
        self.assertFalse(result['accepted'])
        self.assertEqual(json.loads((self.run/'initial_board.json').read_text()),chosen['artifact'])
        with self.assertRaisesRegex(ValueError,'E_NOT_ACCEPTED'):pipeline('check',self.run)
        self.assertTrue(pipeline('review',self.run)['accepted'])
        self.assertTrue(pipeline('check',self.run)['accepted'])

    def test_stale_set_unknown_candidate_wrong_hash_and_missing_reason_rejected(self):
        self.make_run();valid=self.review_input()
        for item in ['set','id','hash','reason']:
            review=copy.deepcopy(valid)
            if item=='set':review['candidate_selection']['candidate_set_sha256']='old'
            if item=='id':review['candidate_selection']['candidate_id']='unknown'
            if item=='hash':review['candidate_sha256']='old'
            if item=='reason':review['candidate_selection']['reason']=' '
            write_json(self.run/'visual_review.json',review)
            with self.assertRaisesRegex(ValueError,'E_CANDIDATE'):pipeline('select',self.run)

    def test_candidate_edit_and_regeneration_invalidate_previous_selection(self):
        self.make_run();self.review_input();pipeline('select',self.run);pipeline('review',self.run)
        previous=json.loads((self.run/'visual_review.json').read_text())
        pipeline('design',self.run)
        self.assertFalse(json.loads((self.run/'run_manifest.json').read_text())['accepted'])
        write_json(self.run/'visual_review.json',previous)
        with self.assertRaisesRegex(ValueError,'E_CANDIDATE_SET'):pipeline('select',self.run)
        p=self.run/'candidate_set.json';p.write_text(p.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'E_ARTIFACT_CHANGED'):pipeline('select',self.run)

    def test_selection_does_not_bypass_visual_rejection(self):
        self.make_run();review=self.review_input()
        review['ai_visual_checks']['face_and_expression']['status']='fail'
        write_json(self.run/'visual_review.json',review)
        pipeline('select',self.run)
        self.assertFalse(pipeline('review',self.run)['accepted'])
        with self.assertRaisesRegex(ValueError,'E_NOT_ACCEPTED'):pipeline('check',self.run)


if __name__=='__main__':unittest.main()
