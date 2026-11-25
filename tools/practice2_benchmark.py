"""Isolated SQLite benchmark: no reads/writes to the user's database."""
import argparse
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import pstats
import random
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = 'b45d5c667cbaf7d1d2d89f6ecfebd3ca4b617dde'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=['baseline', 'final'], required=True)
    parser.add_argument('--sizes', nargs='+', type=int, default=[50, 500, 2000])
    parser.add_argument('--repeats', type=int, default=7)
    args = parser.parse_args()
    output = ROOT / 'docs/practice-2/results'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='adaptive-practice2-') as directory:
        os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', SECRET_KEY='practice2-isolated-only', DEBUG='False',
                          DATABASE_PATH=str(Path(directory) / 'benchmark.sqlite3'))
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connection
        from django.contrib.auth.models import User
        from testing.domain import AdaptiveEngine, QuestionSelector
        from testing.models import Topic, Question, Option, TestDefinition, Attempt
        import testing.services as services
        if args.variant == 'baseline':
            source = subprocess.check_output(['git', 'show', BASELINE + ':testing/services.py'], cwd=ROOT).decode('utf-8')
            module = types.ModuleType('testing._practice2_baseline')
            module.__package__ = 'testing'
            exec(compile(source, 'baseline-services.py', 'exec'), module.__dict__)
            manager_type = module.AttemptManager
        else:
            source = (ROOT / 'testing/services.py').read_text(encoding='utf-8')
            manager_type = services.AttemptManager
        call_command('migrate', verbosity=0)
        user = User.objects.create(username='benchmark')
        results = []
        for size in args.sizes:
            topic = Topic.objects.create(name=f'bank-{size}')
            test = TestDefinition.objects.create(topic=topic, title='Benchmark', length=10, initial=3, published=True)
            questions = Question.objects.bulk_create([Question(topic=topic, text=f'Q{i}',
                difficulty=i % 5 + 1, explanation=f'E{i}') for i in range(size)])
            Option.objects.bulk_create([Option(question=q, position=j, text=f'O{j}', correct=j == 2)
                                        for q in questions for j in range(4)])
            test.questions.add(*questions)

            def run():
                manager = manager_type(AdaptiveEngine(selector=QuestionSelector(random.Random(42))))
                return manager.start(user, test)

            def cleanup():
                Attempt.objects.filter(student=user, test=test).delete()

            run()  # warm ORM, connection, filesystem cache; not in measurements
            cleanup()
            times = []
            for _ in range(args.repeats):
                started = time.perf_counter()
                attempt = run()
                times.append(time.perf_counter() - started)
                assert attempt.bank.count() == size
                cleanup()
            tracemalloc.start()
            run()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            cleanup()
            sql = {'total': 0, 'insert': 0, 'snapshot_insert': 0}

            def count_sql(execute, statement, params, many, context):
                sql['total'] += 1
                if statement.lstrip().upper().startswith('INSERT'):
                    sql['insert'] += 1
                    if 'testing_attemptquestion' in statement:
                        sql['snapshot_insert'] += 1
                return execute(statement, params, many, context)

            with connection.execute_wrapper(count_sql):
                run()
            cleanup()
            profile = cProfile.Profile()
            attempt = profile.runcall(run)
            stream = io.StringIO()
            stats = pstats.Stats(profile, stream=stream).sort_stats('cumulative')
            stats.print_stats(35)
            (output / f'profile-{args.variant}-{size}.txt').write_text(stream.getvalue(), encoding='utf-8')
            # Behavior signature includes all snapshots and a complete 10-answer trajectory.
            snapshots = list(attempt.bank.order_by('source_id').values_list(
                'source_id', 'text', 'difficulty', 'options', 'correct', 'explanation'))
            trajectory = []
            manager = manager_type(AdaptiveEngine(selector=QuestionSelector(random.Random(42))))
            while attempt.current_id:
                q = attempt.current
                trajectory.append([q.source_id, q.difficulty, q.target, q.reason])
                attempt = manager.answer(attempt.pk, user, q.pk, q.correct)
            assert attempt.state == 'COMPLETED' and len(trajectory) == 10
            assert len({row[0] for row in trajectory}) == 10
            signature = hashlib.sha256(json.dumps([snapshots, trajectory], ensure_ascii=False,
                                                  sort_keys=True).encode()).hexdigest()
            cleanup()
            row = dict(size=size, seconds=times, median_seconds=statistics.median(times),
                       python_peak_bytes=peak, sql=sql, profiled_python_calls=stats.total_calls,
                       snapshots=size, behavior_sha256=signature)
            results.append(row)
            print(json.dumps(row))
        from django.conf import settings
        pragmas = {}
        with connection.cursor() as cursor:
            for pragma in ['journal_mode', 'synchronous', 'foreign_keys']:
                cursor.execute('PRAGMA ' + pragma)
                pragmas[pragma] = cursor.fetchone()[0]
        data = dict(variant=args.variant, baseline_commit=BASELINE, services_sha256=hashlib.sha256(source.encode()).hexdigest(),
                    python=sys.version, django=django.get_version(), sqlite=connection.Database.sqlite_version,
                    platform=platform.platform(), debug=settings.DEBUG, sqlite_pragmas=pragmas,
                    seed=42, warmups=1, repeats=args.repeats, results=results)
        (output / f'benchmark-{args.variant}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        connection.close()  # Windows requires closing SQLite before removing its temp directory.


if __name__ == '__main__':
    main()
