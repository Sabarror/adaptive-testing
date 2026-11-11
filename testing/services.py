from django.db import transaction, IntegrityError, OperationalError
from django.db.models import F
from django.utils import timezone
from .models import Attempt, AttemptQuestion, Answer
from .domain import AdaptiveEngine, Candidate

class ScenarioError(ValueError): pass

def valid_bank(test):
    result = []
    for q in test.questions.filter(active=True, topic_id=test.topic_id).prefetch_related('options').order_by('pk'):
        options = list(q.options.all())
        if len(options) == 4 and sum(o.correct for o in options) == 1 and 1 <= q.difficulty <= 5:
            result.append((q, options))
    return result

class AttemptManager:
    def __init__(self, engine=None): self.engine = engine or AdaptiveEngine()
    def _choose(self, attempt, target, step):
        bank = list(attempt.bank.filter(step__isnull=True))
        selected, reason = self.engine.choose([Candidate(q.pk, q.difficulty) for q in bank], target)
        q = next(q for q in bank if q.pk == selected.id)
        q.step, q.target, q.reason, q.shown = step, target, reason, timezone.now()
        q.save(update_fields=['step', 'target', 'reason', 'shown'])
        attempt.current = q
    def start(self, student, test):
        existing = Attempt.objects.filter(student=student, test=test, state='IN_PROGRESS').first()
        if existing: return existing
        if not test.published: raise ScenarioError('Тест снят с публикации.')
        bank = valid_bank(test)
        if len(bank) < test.length: raise ScenarioError(f'Недостаточно активных корректных вопросов: {len(bank)}, требуется {test.length}.')
        try:
            with transaction.atomic():
                a = Attempt.objects.create(student=student, test=test, title=test.title, length=test.length, initial=test.initial)
                for q, options in bank:
                    AttemptQuestion.objects.create(attempt=a, source_id=q.pk, text=q.text, difficulty=q.difficulty, options=[o.text for o in options], correct=next(i for i,o in enumerate(options) if o.correct), explanation=q.explanation)
                self._choose(a, a.initial, 1)
                a.save(update_fields=['current'])
                return a
        except IntegrityError:
            return Attempt.objects.get(student=student, test=test, state='IN_PROGRESS')
        except OperationalError as exc: raise ScenarioError('База занята. Повторите действие.') from exc
    def answer(self, attempt_id, student, question_id, selected):
        try:
            with transaction.atomic():
                # Первое действие — условная запись, сериализующая писателей SQLite.
                updated = Attempt.objects.filter(pk=attempt_id, student=student, state='IN_PROGRESS', current_id=question_id).update(revision=F('revision')+1)
                if not updated: raise ScenarioError('Ответ уже принят или вопрос больше не является текущим.')
                a = Attempt.objects.get(pk=attempt_id)
                q = a.current
                if selected not in range(4): raise ScenarioError('Выберите один из четырёх вариантов.')
                Answer.objects.create(question=q, selected=selected, correct=selected == q.correct, difficulty=q.difficulty, elapsed_seconds=max(0, (timezone.now()-q.shown).total_seconds()))
                if q.step >= a.length:
                    a.state, a.finished, a.current = 'COMPLETED', timezone.now(), None
                else:
                    self._choose(a, self.engine.next_target(q.difficulty, selected == q.correct), q.step+1)
                a.save(update_fields=['state', 'finished', 'current'])
                return a
        except (IntegrityError, OperationalError) as exc:
            raise ScenarioError('Ответ не принят: повторная отправка или база занята. Обновите страницу.') from exc
    def abort(self, attempt_id, student):
        with transaction.atomic():
            Attempt.objects.filter(pk=attempt_id, student=student, state='IN_PROGRESS').update(state='ABORTED', finished=timezone.now(), current=None)

class ResultBuilder:
    def build(self, attempt):
        questions = list(attempt.bank.filter(answer__isnull=False).select_related('answer').order_by('step'))
        correct = sum(q.answer.correct for q in questions)
        distribution = [{'level': i, 'correct': sum(q.answer.correct for q in questions if q.difficulty == i), 'wrong': sum(not q.answer.correct for q in questions if q.difficulty == i)} for i in range(1,6)]
        rows = [dict(step=q.step, text=q.text, selected=q.options[q.answer.selected], correct_text=q.options[q.correct], correct=q.answer.correct, explanation=q.explanation, actual=q.difficulty, target=q.target, reason=q.reason, elapsed=round(q.answer.elapsed_seconds,1)) for q in questions]
        return dict(rows=rows, count=len(rows), correct=correct, percent=round(correct/len(rows)*100,1) if rows else None, distribution=distribution, chart=chart(rows))

def chart(rows):
    return [{'x': 35+i*max(1, 630/max(1,len(rows)-1)), 'y': 170-(r['actual']-1)*35, 'level': r['actual'], 'step': i+1} for i,r in enumerate(rows)]
