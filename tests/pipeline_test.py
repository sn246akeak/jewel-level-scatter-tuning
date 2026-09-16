import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_source_board import analyze
from build_priority_profile import build
from board_common import write_json,board_sha256,component_cells
from validate_initial_board import validate,AI_CHECK_KEYS
from run_level import pipeline,tool_hashes
F=json.loads((Path(__file__).parent/'fixtures'/'asset-2748.json').read_text())

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source.json';self.blocks=self.root/'blocks.json'
        write_json(self.source,F['state']);write_json(self.blocks,F['blocks'])
        self.run=self.root/'run'
        self.release=patch('run_level.release_check',return_value={'status':'passed','tool_hashes':tool_hashes()})
        self.release.start()
    def tearDown(self):
        self.release.stop();self.temp.cleanup()
    def make_run(self):
        pipeline('prepare',self.run,source=self.source,blocks=self.blocks)
        spec={'ai_semantics':{'visual_pairing':True,'contains_face_or_expression':True,
              'containment_structure':True,'outline_or_linework_dominant':True},'primary_class':'F9','design':{}}
        write_json(self.run/'design_spec.json',spec)
        pipeline('design',self.run)
    def review(self):
        report=json.loads((self.run/'validation_report.json').read_text())
        review={'candidate_sha256':report['candidate_sha256'],
          'ai_visual_checks':{k:{'status':'pass','evidence':'Synthetic test evidence; not a human art approval'} for k in AI_CHECK_KEYS},
          'warning_reviews':{r:{'status':'pass','evidence':'Synthetic metric review'} for r in report['unresolved_warning_rules']}}
        write_json(self.run/'visual_review.json',review)
        return review
    def test_visual_pairing_does_not_request_exact_symmetry(self):
        a=analyze(self.source,{'visual_pairing':True})
        self.assertIn('F5',a['matched_classes'])
        self.assertFalse(a['objective_metrics']['left_right_mask_symmetric'])
        self.assertFalse(a['ai_semantics']['exact_pixel_symmetry'])
        self.assertEqual(len(component_cells(F['state']['source']['completeBoard'])),57)
        self.assertEqual(len(F['blocks']['blocks']),19)
        # The fixture is consistent with eight-way connectivity; code never assumes it.
        self.assertEqual(len(component_cells(F['state']['source']['completeBoard'],diagonal=True)),19)
        with self.assertRaisesRegex(ValueError,'E_SYMMETRY'):
            analyze(self.source,{'exact_pixel_symmetry':True})
    def test_only_two_authored_inputs_complete_all_pipeline_stages(self):
        self.make_run();self.review()
        result=pipeline('review',self.run)
        self.assertTrue(result['accepted']);self.assertTrue(pipeline('check',self.run)['accepted'])
        self.assertTrue((self.run/'source_analysis.json').exists())
        self.assertFalse((self.run/'semantics.json').exists())
    def test_warnings_cannot_be_accepted_with_blanket_visual_pass(self):
        self.make_run();review=self.review();review.pop('warning_reviews')
        write_json(self.run/'visual_review.json',review)
        result=pipeline('review',self.run)
        self.assertFalse(result['accepted']);self.assertTrue(result['unresolved_warning_rules'])
    def test_wrong_hash_and_face_not_applicable_cannot_pass(self):
        self.make_run();review=self.review()
        for change in ['hash','face','boundary']:
            r=copy.deepcopy(review)
            if change=='hash':r['candidate_sha256']='old'
            elif change=='face':r['ai_visual_checks']['face_and_expression']['status']='not_applicable'
            else:r['ai_visual_checks'].pop('boundary_quality')
            write_json(self.run/'visual_review.json',r)
            self.assertFalse(pipeline('review',self.run)['accepted'])
    def test_generated_edits_and_extra_per_level_programs_are_blocked(self):
        self.make_run();self.review();pipeline('review',self.run)
        generated=self.run/'initial_board.json';generated.write_text(generated.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'E_ARTIFACT_CHANGED'):pipeline('check',self.run)
        (self.run/'custom.py').write_text('print(1)')
        with self.assertRaisesRegex(ValueError,'E_RUN_FILES'):pipeline('check',self.run)
    def test_spec_edits_require_regeneration_and_new_review(self):
        self.make_run();self.review();pipeline('review',self.run)
        spec=self.run/'design_spec.json';spec.write_text(spec.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'E_INPUT_CHANGED'):pipeline('check',self.run)
        pipeline('design',self.run)
        self.assertFalse(json.loads((self.run/'run_manifest.json').read_text())['accepted'])
    def test_failed_design_can_be_corrected_without_stale_acceptance(self):
        self.make_run();self.review();pipeline('review',self.run)
        p=self.run/'design_spec.json';spec=json.loads(p.read_text())
        spec['design']={'region_targets':{'0':{'22':-1}}};write_json(p,spec)
        with self.assertRaisesRegex(ValueError,'nonnegative'):pipeline('design',self.run)
        self.assertFalse(json.loads((self.run/'run_manifest.json').read_text())['accepted'])
        spec['design']={};write_json(p,spec);pipeline('design',self.run)
        self.assertEqual(json.loads((self.run/'run_manifest.json').read_text())['phase'],'designed')
    def test_profile_order_tampering_is_rejected(self):
        self.make_run()
        p=self.run/'priority_profile.json';data=json.loads(p.read_text());data['priority_order'][2:4]=reversed(data['priority_order'][2:4]);write_json(p,data)
        report,ok=validate(self.run/'initial_board.json',p,self.run/'source_analysis.json')
        self.assertFalse(ok);self.assertFalse(report['accepted'])
    def test_old_dog_approval_is_not_accepted_under_new_contract(self):
        self.make_run()
        write_json(self.run/'initial_board.json',F['candidate'])
        write_json(self.run/'visual_review.json',{'ai_visual_checks':{k:{'status':'pass','evidence':'looks fine'} for k in AI_CHECK_KEYS if k!='boundary_quality'}})
        report,ok=validate(self.run/'initial_board.json',self.run/'priority_profile.json',self.run/'source_analysis.json',self.run/'visual_review.json')
        self.assertFalse(report['accepted'])

if __name__=='__main__':unittest.main()
