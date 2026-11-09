#!/usr/bin/env python3
"""Build a self-contained radar website. Python standard library only.

Production builds require the actual upstream recording and a supported reuse
license in the authors' linked Zenodo/DataCite metadata. There is no generated
waveform fallback, no runtime fetch, and no credential embedded in the output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
MAX_CSV_BYTES = 16 * 1024 * 1024
REPOSITORY = 'nesl/MobiVital-dataset'
ALLOWED_LICENSES = {
    'cc-by-4.0': ('Creative Commons Attribution 4.0 International',
                  'https://creativecommons.org/licenses/by/4.0/'),
    'cc0-1.0': ('Creative Commons CC0 1.0 Universal',
                'https://creativecommons.org/publicdomain/zero/1.0/'),
}


class BuildError(RuntimeError):
    """Fail closed: a site without a real verified source must not deploy."""


def get_bytes(url: str, max_bytes: int = MAX_CSV_BYTES) -> bytes:
    headers = {'User-Agent': 'ChestRadar-Classroom-Build/1.0',
               'Accept': 'application/vnd.github+json' if urlparse(url).hostname == 'api.github.com'
                         else '*/*'}
    token = os.environ.get('GITHUB_TOKEN')
    if token and urlparse(url).hostname == 'api.github.com':
        headers['Authorization'] = 'Bearer ' + token
    last = None
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise BuildError(f'Source is larger than the allowed {max_bytes:,} bytes: {url}')
            return data
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last = exc
            if isinstance(exc, HTTPError) and exc.code in (400, 401, 404, 410):
                break
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise BuildError(f'Could not retrieve {url}: {last}')


def get_json(url: str) -> dict:
    try:
        obj = json.loads(get_bytes(url, 2 * 1024 * 1024))
    except (ValueError, UnicodeError) as exc:
        raise BuildError(f'Invalid JSON response from {url}') from exc
    if not isinstance(obj, dict):
        raise BuildError(f'Expected a JSON object from {url}')
    return obj


def validate_csv(raw: bytes) -> str:
    """Validate the documented format without altering even a byte of input."""
    if not raw or len(raw) > MAX_CSV_BYTES:
        raise BuildError('CSV is empty or too large.')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise BuildError('CSV must be valid UTF-8.') from exc
    if '"' in text or '_' in text:
        raise BuildError('Expected unquoted decimal numeric CSV, matching the browser parser.')
    count = 0
    for count, row in enumerate(csv.reader(io.StringIO(text.lstrip('\ufeff'))), 1):
        if count > 1500:
            raise BuildError('CSV has more than 1,500 rows.')
        if len(row) != 254:
            raise BuildError(f'CSV row {count}: expected 254 columns; got {len(row)}.')
        for column, value in enumerate(row, 1):
            try:
                number = float(value)
            except ValueError as exc:
                raise BuildError(f'Non-numeric value in row {count}, column {column}.') from exc
            if not value.strip() or not math.isfinite(number):
                raise BuildError(f'Missing/nonfinite value in row {count}, column {column}.')
    if count != 1500:
        raise BuildError(f'Expected 1,500 rows; got {count}.')
    return text


def normalize_license(value: str) -> str | None:
    value = value.strip().lower().rstrip('/')
    if value in ALLOWED_LICENSES:
        return value
    if value in ('cc-zero', 'cc0', 'cc0-1.0') or value.endswith('creativecommons.org/publicdomain/zero/1.0'):
        return 'cc0-1.0'
    if value.endswith('creativecommons.org/licenses/by/4.0'):
        return 'cc-by-4.0'
    return None


def license_from_metadata(obj: dict, provider: str, evidence_url: str) -> dict:
    """Read the dataset's explicit license; never infer it from availability."""
    values: list[str] = []
    if provider == 'zenodo':
        meta = obj.get('metadata', {})
        title = meta.get('title', '')
        entries = [meta.get('license', {})] + list(meta.get('rights', []))
        for entry in entries:
            if isinstance(entry, str):
                values.append(entry)
            elif isinstance(entry, dict):
                values.extend(str(entry[k]) for k in ('id', 'url', 'link') if entry.get(k))
        names = [c.get('name', '') for c in meta.get('creators', [])]
    else:
        meta = obj.get('data', {}).get('attributes', {})
        title = ' '.join(t.get('title', '') for t in meta.get('titles', []))
        for entry in meta.get('rightsList', []):
            values.extend(str(entry[k]) for k in ('rightsIdentifier', 'rightsUri') if entry.get(k))
        names = [c.get('name', '') for c in meta.get('creators', [])]
    if 'mobivital' not in title.lower():
        raise BuildError('License metadata does not identify the MobiVital dataset.')
    supported = {normalize_license(value) for value in values} - {None}
    if len(supported) != 1:
        raise BuildError('No unambiguous supported dataset license was found. No public-data site will be built.')
    code = supported.pop()
    name, url = ALLOWED_LICENSES[code]
    return {'id': code, 'name': name, 'url': url, 'evidence_url': evidence_url,
            'dataset_title': title, 'creators': [name for name in names if name]}


def verify_reuse(record_id: str) -> tuple[dict, dict]:
    candidates = [
        ('zenodo', f'https://zenodo.org/api/records/{record_id}'),
        ('datacite', f'https://api.datacite.org/dois/10.5281/zenodo.{record_id}'),
    ]
    errors = []
    for provider, url in candidates:
        try:
            metadata = get_json(url)
        except BuildError as exc:
            errors.append(str(exc))
            continue
        # A retrieved explicit unsupported license must not be bypassed by
        # falling back to potentially stale metadata from another provider.
        license_info = license_from_metadata(metadata, provider, url)
        return license_info, {'provider': provider, 'source_url': url, 'record': metadata}
    raise BuildError('Could not verify the dataset reuse terms. Nothing will deploy. ' + ' | '.join(errors))


def replace_json_script(document: str, identifier: str, payload: dict) -> str:
    pattern = re.compile(r'(<script\b[^>]*\bid="' + re.escape(identifier) + r'"[^>]*>).*?(</script>)', re.S)
    safe = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c')
    result, count = pattern.subn(lambda match: match.group(1) + safe + match.group(2), document)
    if count != 1:
        raise BuildError(f'Expected exactly one embedded {identifier} block; found {count}.')
    return result


def build_document(template: str, raw: bytes, source: dict) -> str:
    text = validate_csv(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if source.get('sha256') != digest:
        raise BuildError('Manifest checksum does not match the supplied recording.')
    payload = {'rawText': text, 'source': source, 'selectedBin': None, 'sha256': digest}
    result = replace_json_script(template, 'recordingData', payload)
    match = re.search(r'<script\b[^>]*\bid="sourceData"[^>]*>(.*?)</script>', result, re.S)
    if not match:
        raise BuildError('Published-results source manifest is missing.')
    sources = json.loads(match.group(1))
    sources['raw_human_recordings_bundled'] = source.get('kind') == 'github-build'
    sources['bundled_recording_count'] = 1
    sources['bundled_recording'] = {key: value for key, value in source.items() if key != 'rawText'}
    result = replace_json_script(result, 'sourceData', sources)
    if 'fetch(' in result or re.search(r'<script\b[^>]*\bsrc=', result, re.I):
        raise BuildError('Website contains a runtime fetch or external script.')
    if 'connect-src \'none\'' not in result:
        raise BuildError('Runtime network-blocking policy is missing.')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    try:
        config = json.loads((ROOT / 'dataset.json').read_text())
        filename = config['filename']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.csv', filename):
            raise BuildError('Unsafe CSV filename in dataset.json.')
        ref = config.get('ref', 'master')
        record_id = str(config['zenodo_record_id'])
        if not record_id.isdecimal():
            raise BuildError('Zenodo record ID must be numeric.')
        print('Checking the dataset reuse terms...', flush=True)
        license_info, evidence = verify_reuse(record_id)
        print(f"Verified metadata license: {license_info['id']}", flush=True)
        print('Resolving the official source revision...', flush=True)
        commit_info = get_json(f'https://api.github.com/repos/{REPOSITORY}/commits/{quote(ref, safe="")}')
        commit = commit_info.get('sha', '')
        if not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise BuildError('GitHub did not return a valid source commit.')
        metadata = get_json(f'https://api.github.com/repos/{REPOSITORY}/contents/{quote(filename)}?ref={commit}')
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{quote(filename)}'
        print(f'Downloading {filename} at {commit}...', flush=True)
        raw = get_bytes(url)
        expected_blob = metadata.get('sha')
        actual_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        if actual_blob != expected_blob or len(raw) != metadata.get('size'):
            raise BuildError('Downloaded bytes do not match the GitHub source object.')
        validate_csv(raw)
        attribution = '; '.join(license_info['creators']) or 'MobiVital dataset authors, UCLA NESL'
        source = {
            'name': filename, 'kind': 'github-build', 'url': url,
            'repository': f'https://github.com/{REPOSITORY}', 'commit': commit,
            'git_blob_sha1': actual_blob, 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'license': license_info, 'attribution': attribution,
            'dataset_doi': f'https://doi.org/10.5281/zenodo.{record_id}',
            'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
            'rows': 1500, 'columns': 254, 'sample_rate_hz': 50,
            'raw_samples_modified': False,
            'limitations': 'One public segment; not a full-cohort replication or clinical validation.',
        }
        page = build_document((ROOT / 'index.template.html').read_text(), raw, source)
        out = args.output.resolve()
        if out == ROOT or out == ROOT.parent or out == Path('/'):
            raise BuildError('Output must be a dedicated build directory.')
        out.mkdir(parents=True, exist_ok=True)
        data_dir = out / 'data'
        data_dir.mkdir(exist_ok=True)
        (out / 'index.html').write_text(page, encoding='utf-8')
        (out / '.nojekyll').write_text('')
        (data_dir / filename).write_bytes(raw)
        (data_dir / 'manifest.json').write_text(json.dumps(source, indent=2) + '\n')
        (data_dir / 'license-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        (out / 'ATTRIBUTION.md').write_text(
            '# Bundled recording attribution\n\n' + attribution + '\n\n' +
            license_info['dataset_title'] + '\n\nDataset: ' + source['dataset_doi'] +
            '\n\nSource snapshot: ' + url + '\n\nReuse license: ' + license_info['name'] +
            '\n' + license_info['url'] + '\n\nLicense evidence: ' + license_info['evidence_url'] +
            '\n\nThe raw CSV is unmodified. This site performs separate teaching-baseline analysis; '
            'the authors have not endorsed this site. Published research statistics and simulations '
            'remain distinctly labeled.\n\nSHA-256: `' + source['sha256'] + '`\n', encoding='utf-8')
        print(f'BUILT: {out / "index.html"} ({len(page.encode("utf-8")):,} bytes)', flush=True)
        print('The complete recording is embedded. No browser data fetch, CDN or import is required.')
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a', encoding='utf-8') as stream:
                stream.write(f'## Recording embedded\n\n`{filename}` · 1,500 × 254 · 50 Hz\n\n'
                             f'Source revision: `{commit}`\n\nSHA-256: `{source["sha256"]}`\n\n'
                             f'Reuse: {license_info["id"]}. Browser data requests: **zero**.\n')
        return 0
    except (BuildError, OSError, KeyError, ValueError) as exc:
        print(f'BUILD STOPPED — {exc}\nNo incomplete site should be deployed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
