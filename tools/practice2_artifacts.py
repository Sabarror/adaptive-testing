"""Derive compact tables, CFGs, source fingerprints and benchmark comparisons."""
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/practice-2'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


GRAPHS = {
    'strategy': (
        {'e': 'entry', 'c': 'correct?', 'i': 'actual + 1', 'd': 'actual - 1', 'cl': 'max(1, min(5, value))', 'x': 'return / exit'},
        [('e','c',''), ('c','i','T'), ('c','d','F'), ('i','cl',''), ('d','cl',''), ('cl','x','')],
        ['e c i cl x', 'e c d cl x']),
    'valid-bank': (
        {'e': 'result = [] / entry', 'l': 'next question?', 'o': 'options = list(...)', 'a': 'A: len == 4?',
         'b': 'B: sum(correct) == 1?', 'c': 'C: 1 <= difficulty?', 'd': 'D: difficulty <= 5?',
         't': 'append(q, options)', 'r': 'return result', 'x': 'exit'},
        [('e','l',''), ('l','o','next'), ('l','r','end'), ('o','a',''), ('a','b','T'), ('a','l','F'),
         ('b','c','T'), ('b','l','F'), ('c','d','T'), ('c','l','F'), ('d','t','T'), ('d','l','F'),
         ('t','l',''), ('r','x','')],
        ['e l r x', 'e l o a l r x', 'e l o a b l r x', 'e l o a b c l r x',
         'e l o a b c d l r x', 'e l o a b c d t l r x']),
    'answer': (
        {'e': 'entry / atomic', 'cas': 'conditional revision UPDATE', 'u': 'updated != 0?',
         'stale': 'raise ScenarioError: stale', 'load': 'load attempt + current', 'v': 'selected in range(4)?',
         'invalid': 'raise ScenarioError: option', 'ans': 'create Answer', 'last': 'step >= length?',
         'complete': 'set COMPLETED, finished, current=None', 'choose': 'next_target + _choose',
         'save': 'save attempt', 'ret': 'return attempt / commit', 'handler': 'translate Integrity/Operational -> ScenarioError',
         'x': 'exit (rollback on exception)'},
        [('e','cas',''), ('cas','u','ok'), ('cas','handler','I/O'), ('u','stale','F'), ('stale','x',''),
         ('u','load','T'), ('load','v','ok'), ('load','handler','I/O'), ('v','invalid','F'), ('invalid','x',''),
         ('v','ans','T'), ('ans','last','ok'), ('ans','handler','I/O'), ('last','complete','T'),
         ('complete','save',''), ('last','choose','F'), ('choose','save','ok'), ('choose','handler','I/O'),
         ('save','ret','ok'), ('save','handler','I/O'), ('ret','x',''), ('handler','x','')],
        ['e cas u stale x', 'e cas u load v invalid x', 'e cas u load v ans last complete save ret x',
         'e cas u load v ans last choose save ret x', 'e cas handler x', 'e cas u load handler x',
         'e cas u load v ans handler x', 'e cas u load v ans last choose handler x',
         'e cas u load v ans last choose save handler x']),
}


def rank(vectors):
    basis = {}
    for vector in vectors:
        while vector:
            bit = vector.bit_length() - 1
            if bit in basis: vector ^= basis[bit]
            else:
                basis[bit] = vector
                break
    return len(basis)


def main():
    diagramdir = OUT / 'diagrams'
    diagramdir.mkdir(exist_ok=True)
    complexities = {}
    for name, (nodes, edges, paths) in GRAPHS.items():
        dot = ['digraph CFG {', '  rankdir=TB;', '  node [shape=box,fontname="Arial"];']
        dot += [f'  {key} [label={json.dumps(key + ": " + label)}];' for key, label in nodes.items()]
        dot += [f'  {a} -> {b} [label={json.dumps(label)}];' for a,b,label in edges]
        dot += ['}']
        path = diagramdir / f'{name}.dot'
        path.write_text('\n'.join(dot) + '\n', encoding='utf-8')
        if shutil.which('dot'):
            subprocess.run(['dot', '-Tsvg', str(path), '-o', str(path.with_suffix('.svg'))], check=True)
        edgeids = {(a,b): i for i,(a,b,_) in enumerate(edges)}
        vectors = []
        for description in paths:
            route = description.split()
            vector = 0
            for a,b in zip(route, route[1:]): vector ^= 1 << edgeids[a,b]
            vectors.append(vector)
        complexity = len(edges) - len(nodes) + 2
        assert len(paths) == complexity == rank(vectors)
        complexities[name] = dict(N=len(nodes), E=len(edges), P=1, V=complexity,
                                  independent_path_rank=rank(vectors), basis_paths=paths)
    write_json(OUT / 'results/cfg-complexity.json', complexities)
    before = json.loads((OUT / 'results/benchmark-baseline.json').read_text(encoding='utf-8'))
    after = json.loads((OUT / 'results/benchmark-final.json').read_text(encoding='utf-8'))
    comparison = []
    assert before['seed'] == after['seed'] and before['repeats'] == after['repeats']
    for key in ['python', 'django', 'sqlite', 'debug', 'sqlite_pragmas']:
        assert before[key] == after[key], ('incomparable settings', key)
    for b,a in zip(before['results'], after['results'], strict=True):
        assert a['size'] == b['size'] and a['behavior_sha256'] == b['behavior_sha256']
        comparison.append(dict(size=b['size'], before_ms=round(b['median_seconds']*1000,3),
            after_ms=round(a['median_seconds']*1000,3), time_improvement_percent=round((1-a['median_seconds']/b['median_seconds'])*100,2),
            before_python_peak_bytes=b['python_peak_bytes'], after_python_peak_bytes=a['python_peak_bytes'],
            before_sql=b['sql']['total'], after_sql=a['sql']['total'],
            before_snapshot_inserts=b['sql']['snapshot_insert'], after_snapshot_inserts=a['sql']['snapshot_insert'],
            before_calls=b['profiled_python_calls'], after_calls=a['profiled_python_calls'], behavior_equal=True))
    write_csv(OUT / 'results/benchmark-comparison.csv', comparison)
    print(json.dumps(comparison, indent=2))
    coverage = json.loads((OUT / 'results/coverage.json').read_text(encoding='utf-8'))
    summaries = {}
    for module, method in [('domain.py','StepAdaptiveStrategy.next_target'), ('services.py','valid_bank'), ('services.py','AttemptManager.answer')]:
        file = next(v for k,v in coverage['files'].items() if k.replace('\\','/') == 'testing/' + module)
        function = file['functions'][method]
        summaries[method] = {k: function[k] for k in ['start_line', 'summary', 'missing_lines', 'missing_branches']}
    write_json(OUT / 'results/coverage-selected.json', summaries)
    evidence = json.loads((OUT / 'results/test-evidence.json').read_text(encoding='utf-8'))
    white = []
    black = []
    for i,row in enumerate(evidence, 1):
        target = white if row['id'].startswith('WB') else black
        if row['id'] == 'WB-S':
            route = 'S1: e c i cl x' if row['correct'] else 'S2: e c d cl x'
        elif row['id'] == 'WB-B':
            conditions = row['conditions']
            number = 1 if not conditions else (6 if all(conditions) else 2 + conditions.index(False))
            route = 'B' + str(number) + ': ' + GRAPHS['valid-bank'][2][number-1]
        elif row['id'] == 'WB-A-error':
            number = {'cas':5, 'load':6, 'insert':7, 'choose':8, 'save':9}[row['site']]
            route = 'A' + str(number) + ': ' + GRAPHS['answer'][2][number-1]
        else:
            route = row.get('rule', 'field validation')
        target.append(dict(ID=f"{row['id']}-{i}", method={'WB-S':'StepAdaptiveStrategy.next_target', 'WB-B':'valid_bank',
            'WB-A-error':'AttemptManager.answer', 'BB-F':'TestForm', 'BB-A':'AttemptManager.answer'}[row['id']],
            input=json.dumps({k:v for k,v in row.items() if k not in ['status','fact','id']}, ensure_ascii=False),
            expected=row.get('expected', row.get('accepted', 'ScenarioError, rollback')),
            path=route,
            fact=row.get('fact', row.get('accepted', row.get('rollback'))), status=row['status']))
        if row['id'] == 'BB-A':
            if row['rule'] == 'last':
                number, outcome = 3, 'COMPLETED'
            elif row['expected']:
                number, outcome = 4, 'accepted; next question'
            elif row['rule'] in ['option_-1', 'option_4']:
                number, outcome = 2, 'ScenarioError; unchanged'
            else:
                number, outcome = 1, 'ScenarioError; unchanged'
            white.append(dict(ID=f'WB-A{i}', method='AttemptManager.answer',
                input=json.dumps(row, ensure_ascii=False), expected=outcome,
                path=f'A{number}: ' + GRAPHS['answer'][2][number-1], fact=outcome, status=row['status']))
    write_csv(OUT / 'white-box-results.csv', white)
    write_csv(OUT / 'black-box-results.csv', black)
    versions = dict(python=sys.version, platform=platform.platform(),
                    packages={name: importlib.metadata.version(name) for name in
                              ['Django','coverage','pypdf','asgiref','sqlparse','python-dotenv','tzdata']},
                    baseline_commit=before['baseline_commit'], branch=subprocess.check_output(
                        ['git','branch','--show-current'], cwd=ROOT, text=True).strip())
    import sqlite3
    versions['sqlite'] = sqlite3.sqlite_version
    versions['graphviz'] = subprocess.run(['dot','-V'], capture_output=True, text=True).stderr.strip() if shutil.which('dot') else 'unavailable'
    write_json(OUT / 'results/environment.json', versions)
    sources = sorted([*ROOT.glob('testing/*.py'), *ROOT.glob('tools/practice2*.py'), ROOT/'requirements.txt',
                      ROOT/'requirements-practice2.txt', ROOT/'config/settings.py'])
    write_json(OUT / 'results/source-manifest.json', {
        str(path.relative_to(ROOT).as_posix()): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})


if __name__ == '__main__':
    main()
