#!/usr/bin/env python3
"""Assemble the existing website fragments without changing their contents."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTS = (
    '00.html', '01.html', '02a.html', '02b.html', '03.html', '04.html',
    '05a.html', '05b.html', '05c.html', '06a.html', '06b.html', '06c.html', '07.html',
)

if __name__ == '__main__':
    page = ''.join((ROOT / 'site' / name).read_text(encoding='utf-8') for name in PARTS)
    if not page.startswith('<!doctype html>') or not page.rstrip().endswith('</html>'):
        raise SystemExit('Website fragments do not form a complete HTML document.')
    (ROOT / 'index.template.html').write_text(page, encoding='utf-8')
    print(f'Assembled {len(PARTS)} fragments into index.template.html.')
