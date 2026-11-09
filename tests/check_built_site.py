#!/usr/bin/env python3
"""Check a fully built artifact using stdlib plus the runner's Node executable."""
from __future__ import annotations
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.attributes = None
        self.text = []
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.attributes = dict(attrs)
            self.text = []
    def handle_data(self, data):
        if self.attributes is not None:
            self.text.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.attributes is not None:
            self.scripts.append((self.attributes, ''.join(self.text)))
            self.attributes = None

if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 tests/check_built_site.py _site/index.html')
page = Path(sys.argv[1]).read_text()
parser = Scripts()
parser.feed(page)
recording = next(json.loads(text) for attrs, text in parser.scripts if attrs.get('id') == 'recordingData')
if not recording or not recording.get('rawText'):
    raise SystemExit('No embedded recording; deployment must stop.')
if hashlib.sha256(recording['rawText'].encode()).hexdigest() != recording['sha256']:
    raise SystemExit('Embedded checksum mismatch; deployment must stop.')
if recording['source'].get('kind') != 'github-build':
    raise SystemExit('A test fixture or local import must not be deployed as public research data.')
count = 0
with tempfile.TemporaryDirectory() as temp:
    for attrs, text in parser.scripts:
        if 'src' in attrs:
            raise SystemExit('External script dependency detected.')
        if attrs.get('type') == 'application/json':
            json.loads(text)
            continue
        count += 1
        path = Path(temp) / f'script-{count}.js'
        path.write_text(text)
        subprocess.run(['node', '--check', str(path)], check=True)
if count != 3:
    raise SystemExit(f'Unexpected number of executable scripts: {count}')
print(f'PASS: {count} scripts; embedded recording checksum; public-source provenance; no external scripts.')
