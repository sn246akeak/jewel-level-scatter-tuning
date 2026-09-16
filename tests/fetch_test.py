import copy
import io
import json
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fetch_kstage_source import fetch_bundle, KStageAPIError
from run_level import pipeline, tool_hashes

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/asset-2748.json').read_text())
URL = 'https://example.test/pixel-beads-editor-v2/?open_token=private-open-token'


class Response(io.BytesIO):
    status = 200

    def __init__(self, data):
        super().__init__(json.dumps(data).encode())


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.report = self.root / 'prepare_report.json'
        self.boot = {'ok': True, 'contextToken': 'private-context-token', 'state': copy.deepcopy(FIXTURE['state'])}

    def tearDown(self):
        self.temp.cleanup()

    def test_live_envelope_matches_editor_timestamp_revision_and_state(self):
        before = datetime.now(timezone.utc)

        def server(request, timeout):
            body = json.loads(request.data)
            if request.full_url.endswith('/bootstrap'):
                self.assertEqual(body, {'openToken': 'private-open-token'})
                return Response(self.boot)
            self.assertEqual(body['expectedRevision'], self.boot['state']['revision'])
            self.assertEqual(body['state'], self.boot['state'])
            self.assertEqual(body['contextToken'], self.boot['contextToken'])
            uuid.UUID(body['requestId'])
            occurred = datetime.fromisoformat(body['operation']['occurredAt'].replace('Z', '+00:00'))
            # Millisecond wire precision can round down the initial instant.
            self.assertGreaterEqual(occurred.timestamp(), before.timestamp() - .001)
            self.assertLessEqual(occurred, datetime.now(timezone.utc))
            return Response({'ok': True, 'result': {'blocks': FIXTURE['blocks']['blocks']}})

        with patch('fetch_kstage_source.urlopen', side_effect=server) as send:
            state, blocks = fetch_bundle(URL, self.report)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(state, FIXTURE['state'])
        self.assertEqual(blocks, FIXTURE['blocks'])
        report = json.loads(self.report.read_text())
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['block_count'], 19)
        self.assertTrue(all(r['status'] == 'passed' and r['elapsed_seconds'] >= 0 for r in report['requests']))
        self.assertNotIn('private-', self.report.read_text())

    def test_observed_400_retains_reason_and_source_context_without_retry(self):
        body = json.dumps({'ok': False, 'code': 'operation_invalid', 'error': 'operation.occurredAt 不能为空。'}).encode()
        failure = HTTPError('https://example.test/api/v2/prefill/start', 400, 'Bad Request', {}, io.BytesIO(body))
        with patch('fetch_kstage_source.urlopen', side_effect=[Response(self.boot), failure]) as send:
            with self.assertRaisesRegex(KStageAPIError, 'prefill/start: HTTP 400 operation_invalid: operation.occurredAt'):
                fetch_bundle(URL, self.report)
        report = json.loads(self.report.read_text())
        self.assertEqual(send.call_count, 2)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['source']['source_sha256'], FIXTURE['state']['source']['sourceSha256'])
        event = report['requests'][-1]
        self.assertEqual(event['http_status'], 400)
        self.assertEqual(json.loads(event['response_body'])['code'], 'operation_invalid')
        self.assertIn('occurredAt', event['operation'])

    def test_failure_log_redacts_echoed_credentials(self):
        error = {'ok': False, 'code': 'invalid', 'error': 'private-open-token private-context-token'}
        with patch('fetch_kstage_source.urlopen', side_effect=[Response(self.boot), Response(error)]):
            with self.assertRaises(KStageAPIError) as raised:
                fetch_bundle(URL, self.report)
        self.assertNotIn('private-', str(raised.exception))
        self.assertNotIn('private-', self.report.read_text())

    def test_non_json_and_network_failures_are_recorded(self):
        failures = [HTTPError('https://example.test', 502, 'Bad Gateway', {}, io.BytesIO(b'<html>gateway</html>')),
                    URLError('connection refused')]
        for failure in failures:
            with self.subTest(failure=failure), patch('fetch_kstage_source.urlopen', side_effect=failure) as send:
                with self.assertRaises(KStageAPIError):
                    fetch_bundle(URL, self.report)
                report = json.loads(self.report.read_text())
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['requests'][0]['endpoint'], 'bootstrap')
                self.assertEqual(send.call_count, 1)

    def test_normal_pipeline_writes_diagnostics_before_any_artifact_exists(self):
        run = self.root / 'run'
        release = {'status': 'passed', 'tool_hashes': tool_hashes()}
        with patch('run_level.release_check', return_value=release), patch('fetch_kstage_source.urlopen', side_effect=URLError('offline')):
            with self.assertRaises(KStageAPIError):
                pipeline('prepare', run, url=URL)
        self.assertEqual([p.name for p in run.iterdir()], ['prepare_report.json'])
        # After maintenance, this known generated diagnostic is allowed by the run audit.
        with patch('run_level.release_check', return_value=release), patch('fetch_kstage_source.urlopen',
                side_effect=[Response(self.boot), Response({'result': {'blocks': FIXTURE['blocks']['blocks']}})]):
            manifest = pipeline('prepare', run, url=URL)
        self.assertEqual(manifest['phase'], 'prepared')
        self.assertIn('prepare_report.json', manifest['generated_hashes'])


if __name__ == '__main__':
    unittest.main()
