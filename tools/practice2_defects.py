"""Two educational mutations and one real-handler regression, in child memory.

No application source file is modified. Each mutant and its corrected control
run execute the SAME test; sys.settrace provides actual localization evidence.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'docs/practice-2/results'
DEFECTS = {
    'D1': ('testing.domain', 'max(1, min(5,', 'max(2, min(5,',
           'testing.test_practice2.WhiteBoxTests.test_strategy_paths_and_clamps'),
    'D2': ('testing.services',
           "except IntegrityError as exc:\n            existing = Attempt.objects.filter(student=student, test=test, state='IN_PROGRESS').first()\n            if existing:\n                return existing\n            raise ScenarioError('Не удалось создать попытку. Повторите действие.') from exc",
           "except IntegrityError:\n            return Attempt.objects.get(student=student, test=test, state='IN_PROGRESS')",
           'testing.test_practice2.IntegrationTests.test_start_integrity_failure_reports_scenario_and_rolls_back'),
    'D3': ('testing.services', 'if q.step >= a.length:', 'if q.step > a.length:',
           'testing.tests.ScenarioTests.test_complete_and_no_repeated_questions'),
}


def child(identifier, mutated):
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', SECRET_KEY='practice2-isolated-only')
    os.environ.pop('PRACTICE2_EVIDENCE', None)  # Do not overwrite the full-suite evidence.
    # Force an in-memory TEST database even when a developer has set TEST_DATABASE_PATH.
    os.environ.pop('TEST_DATABASE_PATH', None)
    import django
    django.setup()
    from django.conf import settings
    settings.DATABASES['default']['TEST']['NAME'] = ':memory:'
    from django.test.runner import DiscoverRunner
    import importlib
    name, old, new, test = DEFECTS[identifier]
    module = importlib.import_module(name)
    path = Path(module.__file__)
    source = path.read_text(encoding='utf-8')
    if mutated:
        assert source.count(old) == 1, (identifier, 'mutation target changed')
        source = source.replace(old, new)
        exec(compile(source, str(path), 'exec'), module.__dict__)
    count = 0

    def trace(frame, event, arg):
        nonlocal count
        if (frame.f_code.co_filename == str(path) and frame.f_code.co_name in
                ['next_target', 'start', 'answer'] and event in ['line', 'return', 'exception'] and count < 250):
            count += 1
            local = frame.f_locals
            values = {k: local[k] for k in ['actual', 'correct', 'selected', 'updated'] if k in local}
            for key in ['q', 'a']:
                value = local.get(key)
                if value is not None:
                    values[key] = {attr: getattr(value, attr) for attr in ['pk', 'step', 'length', 'state'] if hasattr(value, attr)}
            line = source.splitlines()[frame.f_lineno - 1].strip()
            print('TRACE', json.dumps(dict(event=event, line=frame.f_lineno, code=line, locals=values), ensure_ascii=False))
        return trace

    sys.settrace(trace)
    try:
        failures = DiscoverRunner(verbosity=2).run_tests([test])
    finally:
        sys.settrace(None)
    return int(bool(failures))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', choices=DEFECTS)
    parser.add_argument('--mutated', action='store_true')
    args = parser.parse_args()
    if args.child:
        raise SystemExit(child(args.child, args.mutated))
    OUT.mkdir(parents=True, exist_ok=True)
    patchdir = ROOT / 'docs/practice-2/defects'
    patchdir.mkdir(exist_ok=True)
    files = [ROOT / 'testing/domain.py', ROOT / 'testing/services.py']
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    summary = []
    for identifier, (module, old, new, test) in DEFECTS.items():
        path = ROOT / (module.replace('.', '/') + '.py')
        source = path.read_text(encoding='utf-8')
        assert source.count(old) == 1
        altered = source.replace(old, new)
        relative = path.relative_to(ROOT).as_posix()
        patch = ''.join(difflib.unified_diff(source.splitlines(True), altered.splitlines(True),
                                            fromfile='a/' + relative, tofile='b/' + relative))
        origin = 'real' if identifier == 'D2' else 'educational'
        (patchdir / f'{identifier}-{origin}.patch').write_text(patch, encoding='utf-8')
        results = {}
        for mutated in [True, False]:
            stage = 'before' if mutated else 'after'
            cmd = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--child', identifier]
            if mutated: cmd.append('--mutated')
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding='utf-8',
                                    env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'))
            (OUT / f'{identifier}-{stage}.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
            results[stage] = result.returncode
        assert results == {'before': 1, 'after': 0}, (identifier, results)
        summary.append(dict(id=identifier, origin=origin, test=test, **results))
        print(identifier, results)
    after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert before == after, 'Source files must remain unchanged'
    (OUT / 'defects.json').write_text(json.dumps(dict(results=summary, source_hashes=after,
        source_unchanged=True), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
