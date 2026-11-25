"""Practice 2: explicit contracts, short-circuit probes, stubs and drivers."""
import atexit
import json
import os
from pathlib import Path
import random
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.db import IntegrityError, OperationalError, transaction
from django.db.models.signals import post_save, pre_save
from django.test import SimpleTestCase, TestCase

from .domain import AdaptiveEngine, Candidate, QuestionSelector, StepAdaptiveStrategy
from .forms import TestForm
from .models import Answer, Attempt, AttemptQuestion, Option, Question, TestDefinition, Topic
from .services import AttemptManager, ScenarioError, valid_bank

EVIDENCE = []


def evidence(case, **data):
    EVIDENCE.append(dict(id=case, **data))


def save_evidence():
    if os.environ.get('PRACTICE2_EVIDENCE'):
        Path(os.environ['PRACTICE2_EVIDENCE']).write_text(
            json.dumps(EVIDENCE, ensure_ascii=False, indent=2), encoding='utf-8')


atexit.register(save_evidence)


class WhiteBoxTests(SimpleTestCase):
    def test_strategy_paths_and_clamps(self):
        for actual, correct, expected in [(1, False, 1), (1, True, 2), (5, True, 5), (5, False, 4)]:
            with self.subTest(actual=actual, correct=correct):
                fact = StepAdaptiveStrategy().next_target(actual, correct)
                self.assertEqual(fact, expected)
                evidence('WB-S', actual=actual, correct=correct, expected=expected, fact=fact, status='PASS')

    def test_bank_short_circuit(self):
        # A: four options, B: exactly one correct, C: >=1, D: <=5.
        # Out-of-range levels cannot be stored in the real DB; these are isolated probes.
        rows = [(3, 1, 3, [False, None, None, None], False),
                (4, 0, 3, [True, False, None, None], False),
                (4, 1, 0, [True, True, False, None], False),
                (4, 1, 6, [True, True, True, False], False),
                (4, 1, 1, [True, True, True, True], True),
                (4, 1, 5, [True, True, True, True], True)]
        for n, correct_count, level, expected_trace, accepted in rows:
            reads = []

            class ProbeOption:
                def __init__(self, correct): self.value = correct
                @property
                def correct(self):
                    reads.append('B')
                    return self.value

            class ProbeLevel(int):
                def __ge__(self, other):
                    reads.append('C')
                    return super().__ge__(other)
                def __le__(self, other):
                    reads.append('D')
                    return super().__le__(other)

            q = SimpleNamespace(difficulty=ProbeLevel(level), options=Mock())
            q.options.all.return_value = [ProbeOption(i < correct_count) for i in range(n)]
            query = Mock()
            query.filter.return_value.prefetch_related.return_value.order_by.return_value = [q]
            result = valid_bank(SimpleNamespace(questions=query, topic_id=1))
            trace = [n == 4, correct_count == 1 if 'B' in reads else None,
                     level >= 1 if 'C' in reads else None, level <= 5 if 'D' in reads else None]
            self.assertEqual(trace, expected_trace)
            self.assertEqual(bool(result), accepted)
            evidence('WB-B', n=n, correct_count=correct_count, level=level,
                     conditions=trace, observed_reads=reads, accepted=bool(result), status='PASS')
        query.filter.return_value.prefetch_related.return_value.order_by.return_value = []
        self.assertEqual(valid_bank(SimpleNamespace(questions=query, topic_id=1)), [])
        evidence('WB-B', n=0, correct_count=0, level=None, conditions=[], accepted=False, status='PASS')

    def test_selector_empty_and_permutation(self):
        with self.assertRaises(ValueError): QuestionSelector().choose([], 3)
        bank = [Candidate(4, 2), Candidate(1, 2), Candidate(2, 4)]
        a = QuestionSelector(random.Random(42)).choose(bank, 3)
        b = QuestionSelector(random.Random(42)).choose(list(reversed(bank)), 3)
        self.assertEqual(a, b)
        self.assertEqual(a[0].difficulty, 2)


class PracticeFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create(username='practice-student')
        cls.other = User.objects.create(username='practice-other')
        cls.topic = Topic.objects.create(name='Practice topic')
        cls.definition = TestDefinition.objects.create(topic=cls.topic, title='Practice', length=3, initial=3, published=True)
        for i in range(6):
            q = Question.objects.create(topic=cls.topic, text=f'Q{i}', difficulty=i % 5 + 1, explanation=f'E{i}')
            Option.objects.bulk_create([Option(question=q, text=f'O{j}', position=j, correct=j == 2) for j in range(4)])
            cls.definition.questions.add(q)

    def manager(self):
        return AttemptManager(AdaptiveEngine(selector=QuestionSelector(random.Random(42))))

    def state(self, a):
        a.refresh_from_db()
        return (a.revision, a.current_id, a.state, a.finished,
                list(a.bank.order_by('pk').values_list('pk', 'step', 'target', 'reason', 'shown')),
                list(Answer.objects.order_by('pk').values_list('question_id', 'selected')))


class BlackBoxTests(PracticeFixture):
    def test_form_boundaries_types_missing(self):
        payload = dict(title='Boundary', topic=self.topic.pk,
                       questions=list(self.definition.questions.values_list('pk', flat=True)), published=False,
                       initial=3, length=3)
        for field, cases in [('initial', [(0, False), (1, True), (2, True), (4, True), (5, True), (6, False)]),
                             ('length', [(0, False), (1, True), (2, True), (99, True), (100, True), (101, False)])]:
            for value, expected in cases + [('abc', False), ('1.5', False), ('', False), (None, False)]:
                with self.subTest(field=field, value=value):
                    data = dict(payload, **{field: value})
                    if value is None: data.pop(field)
                    form = TestForm(data=data)
                    fact = form.is_valid()
                    self.assertEqual(fact, expected, form.errors)
                    evidence('BB-F', field=field, value=value, expected=expected, fact=fact, status='PASS')
        self.assertEqual(TestDefinition.objects.count(), 1)

    def test_answer_decision_table_and_rollback(self):
        cases = [('accept', True, 'IN_PROGRESS', True, 0, True),
                 ('foreign', False, 'IN_PROGRESS', True, 0, False),
                 ('completed', True, 'COMPLETED', True, 0, False),
                 ('aborted', True, 'ABORTED', True, 0, False),
                 ('old_question', True, 'IN_PROGRESS', False, 0, False)]
        cases += [(f'option_{value}', True, 'IN_PROGRESS', True, value, value in [0, 1, 2, 3])
                  for value in [-1, 0, 1, 2, 3, 4]]
        for name, owner, state, current, selected, accepted in cases:
            with self.subTest(rule=name), transaction.atomic():
                manager = self.manager()
                a = manager.start(self.student, self.definition)
                Attempt.objects.filter(pk=a.pk).update(state=state)
                qid = a.current_id if current else a.bank.exclude(pk=a.current_id).first().pk
                before = self.state(a)
                if accepted:
                    manager.answer(a.pk, self.student, qid, selected)
                    self.assertEqual(Answer.objects.count(), 1)
                    a.refresh_from_db()
                    self.assertEqual(a.state, 'IN_PROGRESS')
                    self.assertNotEqual(a.current_id, qid)
                    self.assertEqual(a.revision, before[0] + 1)
                else:
                    with self.assertRaises(ScenarioError):
                        manager.answer(a.pk, self.student if owner else self.other, qid, selected)
                    self.assertEqual(self.state(a), before)
                evidence('BB-A', rule=name, expected=accepted, fact=accepted, status='PASS')
                transaction.set_rollback(True)

    def test_http_invalid_types_and_missing_do_not_mutate(self):
        a = self.manager().start(self.student, self.definition)
        self.client.force_login(self.student)
        before = self.state(a)
        for selected in ['abc', '1.0', '', None, '-1', '4']:
            with self.subTest(selected=selected):
                payload = {'question': a.current_id}
                if selected is not None: payload['selected'] = selected
                self.assertEqual(self.client.post(f'/attempts/{a.pk}/', payload).status_code, 302)
                self.assertEqual(self.state(a), before)
        for qid in ['abc', '', None]:
            payload = {'selected': 0}
            if qid is not None: payload['question'] = qid
            self.assertEqual(self.client.post(f'/attempts/{a.pk}/', payload).status_code, 302)
            self.assertEqual(self.state(a), before)

    def test_missing_attempt_rejected_and_last_answer_completed(self):
        with self.assertRaises(ScenarioError):
            self.manager().answer(999999, self.student, 999999, 0)
        self.assertFalse(Answer.objects.exists())
        self.definition.length = 1
        manager = self.manager()
        a = manager.start(self.student, self.definition)
        a = manager.answer(a.pk, self.student, a.current_id, 2)
        self.assertEqual(a.state, 'COMPLETED')
        self.assertIsNone(a.current_id)
        self.assertEqual(Answer.objects.count(), 1)
        evidence('BB-A', rule='last', expected='COMPLETED', fact=a.state, status='PASS')

    def test_database_error_translation_and_atomicity(self):
        manager = self.manager()
        a = manager.start(self.student, self.definition)
        before = self.state(a)
        for site in ['cas', 'load', 'insert', 'choose', 'save']:
            for error in [IntegrityError('injected write error'), OperationalError('injected lock')]:
                with self.subTest(site=site, error=type(error).__name__):
                    if site == 'cas':
                        query = Mock()
                        query.update.side_effect = error
                        fault = patch('testing.services.Attempt.objects.filter', return_value=query)
                    elif site == 'load':
                        fault = patch('testing.services.Attempt.objects.get', side_effect=error)
                    elif site == 'insert':
                        fault = patch('testing.services.Answer.objects.create', side_effect=error)
                    elif site == 'choose':
                        fault = patch.object(manager, '_choose', side_effect=error)
                    else:
                        fault = patch('testing.services.Attempt.save', side_effect=error)
                    with fault:
                        with self.assertRaises(ScenarioError) as caught:
                            manager.answer(a.pk, self.student, a.current_id, 0)
                    self.assertIs(caught.exception.__cause__, error)
                    self.assertEqual(self.state(a), before)
                    evidence('WB-A-error', site=site, error=type(error).__name__, rollback=True, status='PASS')


class IntegrationTests(PracticeFixture):
    def test_top_down_http_with_service_stub(self):
        a = self.manager().start(self.student, self.definition)
        self.client.force_login(self.student)
        before = self.state(a)
        stub = Mock(spec=AttemptManager)
        stub.answer.return_value = a
        with patch('testing.views.AttemptManager', return_value=stub):
            self.assertEqual(self.client.post(f'/attempts/{a.pk}/', {'question': str(a.current_id), 'selected': '2'}).status_code, 302)
            stub.answer.assert_called_once_with(a.pk, self.student, a.current_id, 2)
            stub.answer.side_effect = ScenarioError('stub failure')
            response = self.client.post(f'/attempts/{a.pk}/', {'question': a.current_id, 'selected': 2}, follow=True)
            self.assertContains(response, 'stub failure')
        self.assertEqual(self.state(a), before)
        stub.start.return_value = a
        with patch('testing.views.AttemptManager', return_value=stub):
            response = self.client.post(f'/tests/{self.definition.pk}/start/')
            self.assertEqual(response.url, f'/attempts/{a.pk}/')
            stub.start.assert_called_once_with(self.student, self.definition)

    def test_top_down_service_with_engine_stub(self):
        class EngineStub:
            def __init__(self): self.calls = []
            def choose(self, bank, target):
                self.calls.append(('choose', bank, target))
                return bank[0], 'stub reason'
            def next_target(self, actual, correct):
                self.calls.append(('next_target', actual, correct))
                return 4

        stub = EngineStub()
        manager = AttemptManager(stub)
        a = manager.start(self.student, self.definition)
        self.assertEqual(stub.calls[0][2], 3)
        self.assertTrue(all(isinstance(q, Candidate) for q in stub.calls[0][1]))
        self.assertEqual(len(stub.calls[0][1]), 6)
        first, level = a.current_id, a.current.difficulty
        a = manager.answer(a.pk, self.student, first, a.current.correct)
        self.assertEqual(stub.calls[1], ('next_target', level, True))
        self.assertEqual(stub.calls[2][2], 4)
        self.assertNotIn(first, [q.id for q in stub.calls[2][1]])
        self.assertEqual(a.current.reason, 'stub reason')
        before = self.state(a)
        with patch.object(stub, 'choose', side_effect=ValueError('engine failure')):
            with self.assertRaisesRegex(ValueError, 'engine failure'):
                manager.answer(a.pk, self.student, a.current_id, 0)
        self.assertEqual(self.state(a), before)

    def test_bottom_up_domain_driver(self):
        def driver(strategy, selector):
            target = strategy.next_target(3, False)
            return selector.choose([Candidate(10, 1), Candidate(11, 3)], target)
        question, reason = driver(StepAdaptiveStrategy(), QuestionSelector(random.Random(42)))
        self.assertEqual(question, Candidate(10, 1))
        self.assertIn('2', reason)

    def test_bottom_up_orm_driver_then_real_service_and_http(self):
        def bank_driver(definition):
            return [(q.pk, q.difficulty, [o.text for o in options]) for q, options in valid_bank(definition)]
        bank = bank_driver(self.definition)
        self.assertEqual(len(bank), 6)
        q = self.definition.questions.first()
        q.options.first().delete()
        self.assertEqual(len(bank_driver(self.definition)), 5)
        manager = self.manager()
        a = manager.start(self.student, self.definition)
        self.assertEqual(a.bank.count(), 5)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(f'/attempts/{a.pk}/'), a.current.text)
        for _ in range(3):
            a.refresh_from_db()
            self.client.post(f'/attempts/{a.pk}/', {'question': a.current_id, 'selected': a.current.correct})
        a.refresh_from_db()
        self.assertEqual(a.state, 'COMPLETED')
        self.assertContains(self.client.get(f'/attempts/{a.pk}/result/'), '100,0%')

    def test_snapshot_source_contract(self):
        a = self.manager().start(self.student, self.definition)
        expected = list(self.definition.questions.order_by('pk').values_list('pk', 'text', 'difficulty', 'explanation'))
        actual = list(a.bank.order_by('source_id').values_list('source_id', 'text', 'difficulty', 'explanation'))
        self.assertEqual(actual, expected)
        self.assertIsNotNone(a.current_id)
        for snapshot in a.bank.all():
            self.assertEqual(snapshot.options, ['O0', 'O1', 'O2', 'O3'])
            self.assertEqual(snapshot.correct, 2)

    def test_start_rollback_when_selection_fails(self):
        with patch.object(AttemptManager, '_choose', side_effect=ValueError('selection failure')):
            with self.assertRaisesRegex(ValueError, 'selection failure'):
                self.manager().start(self.student, self.definition)
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(AttemptQuestion.objects.exists())

    def test_start_integrity_failure_reports_scenario_and_rolls_back(self):
        # Fault injection at the storage boundary, not a change to application code.
        # A genuine constraint violation is raised after rows have been inserted.
        original = AttemptQuestion.objects.bulk_create

        def insert_then_violate(objects, **kwargs):
            objects = list(objects)
            original(objects, **kwargs)
            q = objects[0]
            original([AttemptQuestion(attempt_id=q.attempt_id, source_id=q.source_id,
                text=q.text, difficulty=q.difficulty, options=q.options,
                correct=q.correct, explanation=q.explanation)])

        with patch('testing.services.AttemptQuestion.objects.bulk_create', side_effect=insert_then_violate):
            with self.assertRaises(ScenarioError) as caught:
                self.manager().start(self.student, self.definition)
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(AttemptQuestion.objects.exists())

    def test_snapshot_orm_contract(self):
        # No overridden save or registered application save signals are bypassed.
        from django.db.models import Model
        self.assertIs(AttemptQuestion.save, Model.save)
        self.assertFalse(pre_save.has_listeners(AttemptQuestion))
        self.assertFalse(post_save.has_listeners(AttemptQuestion))
        a = self.manager().start(self.student, self.definition)
        self.assertTrue(all(q.pk is not None for q in a.bank.all()))
        first = a.bank.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttemptQuestion.objects.bulk_create([AttemptQuestion(attempt=a, source_id=first.source_id,
                text='duplicate', difficulty=1, options=['a'] * 4, correct=0, explanation='e')])
        self.assertEqual(a.bank.count(), 6)

    def test_start_concurrent_recovery_and_operational_error(self):
        manager = self.manager()
        existing = manager.start(self.student, self.definition)
        query = Mock()
        query.first.side_effect = [None, existing]
        with patch('testing.services.Attempt.objects.filter', return_value=query), patch(
                'testing.services.Attempt.objects.create', side_effect=IntegrityError('competing insert')):
            self.assertEqual(manager.start(self.student, self.definition).pk, existing.pk)
        Attempt.objects.all().delete()
        error = OperationalError('database locked')
        with patch('testing.services.Attempt.objects.create', side_effect=error):
            with self.assertRaises(ScenarioError) as caught:
                manager.start(self.student, self.definition)
        self.assertIs(caught.exception.__cause__, error)
        self.assertFalse(Attempt.objects.exists())

