"""Read-only final audit of saved evidence against the current source tree."""
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/practice-2'


def read_json(name):
    return json.loads((DOCS / 'results' / name).read_text(encoding='utf-8'))


def main():
    manifest = read_json('source-manifest.json')
    for name, expected in manifest.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    for name in ['baseline-tests', 'final-tests', 'coverage-summary', 'django-check',
                 'migrations-check', 'pip-check', 'benchmark-baseline-run',
                 'benchmark-final-run', 'defects-run', 'D2-fixed']:
        assert read_json(name + '.status.json')['exit_code'] == 0, name
    assert read_json('D2-discovery.status.json')['exit_code'] == 1
    defects = read_json('defects.json')
    assert defects['source_unchanged']
    for row in defects['results']:
        assert row['before'] == 1 and row['after'] == 0
    for name, expected in defects['source_hashes'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    before, after = read_json('benchmark-baseline.json'), read_json('benchmark-final.json')
    assert after['services_sha256'] == hashlib.sha256(
        (ROOT / 'testing/services.py').read_text(encoding='utf-8').encode()).hexdigest()
    for b,a in zip(before['results'], after['results'], strict=True):
        assert b['size'] == a['size'] and b['behavior_sha256'] == a['behavior_sha256']
    with (DOCS / 'white-box-results.csv').open(encoding='utf-8-sig', newline='') as handle:
        white = list(csv.DictReader(handle))
    expected_routes = {f'{prefix}{i}' for prefix,n in [('S',2), ('B',6), ('A',9)] for i in range(1,n+1)}
    assert {row['path'].split(':')[0] for row in white} == expected_routes
    assert all(row['status'] == 'PASS' for row in white)
    for markdown in [ROOT / 'README.md', *DOCS.glob('*.md')]:
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', markdown.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'): continue
            assert (markdown.parent / target.split('#')[0]).exists(), (markdown, target)
    assert not list(DOCS.rglob('*.sqlite3'))
    assert not list(DOCS.rglob('.env'))
    for name in ['strategy', 'valid-bank', 'answer', 'answer-causes']:
        for suffix in ['dot', 'svg']:
            assert (DOCS / 'diagrams' / f'{name}.{suffix}').is_file()
    final = (DOCS / 'results/final-tests.txt').read_text(encoding='utf-8')
    assert 'Ran 51 tests' in final and '\nOK\n' in final
    print(f'PASS: {len(manifest)} source hashes; saved exit codes; 3 fail/pass defects; '
          '3 equal benchmark signatures; all 17 CFG basis paths; document links; '
          'diagram sources/SVG; no database or .env in artifacts; 51-test final log.')


if __name__ == '__main__':
    main()
