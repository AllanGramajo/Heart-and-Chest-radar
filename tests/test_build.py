"""Packaging tests only. Any generated arrays are synthetic software fixtures.

No fixture is published by the production build or substituted for source data.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_site as build


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = ((','.join(['0'] * 254) + '\n') * 1500).encode()
        cls.template = (build.ROOT / 'index.template.html').read_text()
        cls.source = {'name': 'SYNTHETIC-PACKAGING-TEST.csv',
                      'kind': 'synthetic-software-fixture',
                      'sha256': hashlib.sha256(cls.raw).hexdigest()}

    def test_valid_shape_and_exact_bytes(self):
        self.assertEqual(build.validate_csv(self.raw).encode(), self.raw)

    def test_utf8_bom_preserved(self):
        data = b'\xef\xbb\xbf' + self.raw
        self.assertEqual(build.validate_csv(data).encode(), data)

    def test_crlf_preserved(self):
        data = self.raw.replace(b'\n', b'\r\n')
        self.assertEqual(build.validate_csv(data).encode(), data)

    def test_wrong_row_count_rejected(self):
        with self.assertRaises(build.BuildError):
            build.validate_csv(self.raw.split(b'\n', 1)[1])

    def test_wrong_column_count_rejected(self):
        with self.assertRaises(build.BuildError):
            build.validate_csv(self.raw.replace(b'0,0', b'0', 1))

    def test_missing_value_rejected(self):
        with self.assertRaises(build.BuildError):
            build.validate_csv(self.raw.replace(b'0,0', b',0', 1))

    def test_nonfinite_rejected(self):
        for marker in (b'NaN', b'Infinity', b'-inf'):
            with self.subTest(marker=marker), self.assertRaises(build.BuildError):
                build.validate_csv(marker + self.raw[1:])

    def test_html_error_response_rejected(self):
        with self.assertRaises(build.BuildError):
            build.validate_csv(b'<html>Access denied</html>')

    def test_checksum_mismatch_rejected(self):
        with self.assertRaises(build.BuildError):
            build.build_document(self.template, self.raw, {**self.source, 'sha256': 'wrong'})

    def test_embedded_bytes_and_no_runtime_fetch(self):
        page = build.build_document(self.template, self.raw, self.source)
        block = re.search(r'<script id="recordingData"[^>]*>(.*?)</script>', page, re.S)
        stored = json.loads(block.group(1))
        self.assertEqual(stored['rawText'].encode(), self.raw)
        self.assertEqual(stored['sha256'], self.source['sha256'])
        self.assertNotIn('fetch(', page)
        self.assertIn("connect-src 'none'", page)
        self.assertNotIn('id="fetchSample"', page)

    def test_synthetic_test_does_not_claim_human_origin(self):
        page = build.build_document(self.template, self.raw, self.source)
        block = re.search(r'<script id="sourceData"[^>]*>(.*?)</script>', page, re.S)
        self.assertFalse(json.loads(block.group(1))['raw_human_recordings_bundled'])

    def test_json_script_cannot_close_with_metadata(self):
        page = build.build_document(self.template, self.raw,
                                   {**self.source, 'name': '</script><script>bad()</script>'})
        self.assertNotIn('<script>bad()', page)
        self.assertIn('\\u003c/script>', page)

    def test_zenodo_explicit_license(self):
        obj = {'metadata': {'title': 'MobiVital dataset', 'license': {'id': 'cc-by-4.0'},
                            'creators': [{'name': 'Example, Test'}]}}
        result = build.license_from_metadata(obj, 'zenodo', 'test-only')
        self.assertEqual(result['id'], 'cc-by-4.0')

    def test_datacite_explicit_license(self):
        obj = {'data': {'attributes': {'titles': [{'title': 'MobiVital dataset'}],
                                       'rightsList': [{'rightsUri': 'https://creativecommons.org/licenses/by/4.0/'}]}}}
        result = build.license_from_metadata(obj, 'datacite', 'test-only')
        self.assertEqual(result['id'], 'cc-by-4.0')

    def test_unrelated_dataset_rejected(self):
        obj = {'metadata': {'title': 'Unrelated dataset', 'license': {'id': 'cc-by-4.0'}}}
        with self.assertRaises(build.BuildError):
            build.license_from_metadata(obj, 'zenodo', 'test-only')

    def test_unknown_license_rejected(self):
        obj = {'metadata': {'title': 'MobiVital dataset'}}
        with self.assertRaises(build.BuildError):
            build.license_from_metadata(obj, 'zenodo', 'test-only')

    def test_license_network_failure_stops_build(self):
        with patch.object(build, 'get_json', side_effect=build.BuildError('offline')):
            with self.assertRaises(build.BuildError):
                build.verify_reuse('15022885')

    def test_unsupported_explicit_license_not_bypassed(self):
        obj = {'metadata': {'title': 'MobiVital dataset', 'license': {'id': 'custom-restricted'}}}
        with patch.object(build, 'get_json', return_value=obj) as call:
            with self.assertRaises(build.BuildError):
                build.verify_reuse('15022885')
            self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
