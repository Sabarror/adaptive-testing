import random
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase, Client, TransactionTestCase
from .domain import AdaptiveEngine, StepAdaptiveStrategy, QuestionSelector, Candidate, simulate
from .models import Topic, Question, Option, TestDefinition, Attempt, Answer
from .services import AttemptManager, ScenarioError, ResultBuilder
from .forms import QuestionForm, TestForm

class AlgorithmTests(SimpleTestCase):
    def test_increase_decrease_and_boundaries(self):
        s = StepAdaptiveStrategy()
        for level in range(1,6):
            self.assertEqual(s.next_target(level,True),min(5,level+1))
            self.assertEqual(s.next_target(level,False),max(1,level-1))
    def test_nearest_and_lower_tie(self):
        selector = QuestionSelector(random.Random(42))
        bank = [Candidate(1,2),Candidate(2,5)]
        self.assertEqual(selector.choose(bank,4)[0].difficulty,5)
        self.assertEqual(selector.choose([Candidate(1,2),Candidate(2,4)],3)[0].difficulty,2)
    def test_exact_level_preferred(self):
        self.assertEqual(QuestionSelector().choose([Candidate(1,2),Candidate(2,3)],3)[0].id,2)
    def test_seed_reproducible_and_no_repeats(self):
        bank = [Candidate(i,3) for i in range(30)]
        def run():
            selector = QuestionSelector(random.Random(19)); remaining=bank.copy(); selected=[]
            while remaining:
                q,_ = selector.choose(remaining,3); remaining.remove(q); selected.append(q.id)
            return selected
        self.assertEqual(run(),run()); self.assertEqual(len(set(run())),30)
        self.assertNotEqual(run(),list(range(30)))
    def test_actual_level_determines_next_target(self):
        rows,_ = simulate(4,[False,True],[0,1,0,0,1],42)
        self.assertEqual((rows[0]['target'],rows[0]['actual'],rows[0]['following']),(4,5,4))
        self.assertEqual(rows[1]['actual'],2)
    def test_empty_bank_stops(self):
        rows,message = simulate(3,[True]*3,[0,0,1,0,0],42)
        self.assertEqual(len(rows),1); self.assertIn('закончились',message)
    def test_strategy_polymorphism(self):
        class FixedStrategy(StepAdaptiveStrategy):
            def next_target(self,actual,correct): return 3
        self.assertEqual(AdaptiveEngine(strategy=FixedStrategy()).next_target(5,True),3)
    def test_sandbox_uses_shared_engine(self):
        with patch('testing.domain.StepAdaptiveStrategy.next_target',return_value=2) as strategy, patch('testing.domain.QuestionSelector.choose',wraps=QuestionSelector(random.Random(1)).choose) as selector:
            rows,_ = simulate(3,[True,False],[2]*5,1)
            self.assertEqual(strategy.call_count,2); self.assertEqual(selector.call_count,2)
            self.assertEqual(rows[0]['following'],2)

class ScenarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('s',password='StudentPassword123!')
        cls.other = User.objects.create_user('other',password='OtherPassword123!')
        cls.teacher = User.objects.create_user('t',password='TeacherPassword123!')
        cls.teacher.groups.add(Group.objects.create(name='Преподаватели'))
        cls.topic = Topic.objects.create(name='Тема')
        cls.test = TestDefinition.objects.create(title='Тест',topic=cls.topic,length=3,initial=3,published=True)
        for i in range(10):
            q = Question.objects.create(topic=cls.topic,text=f'Вопрос {i}',difficulty=i%5+1,explanation=f'СЕКРЕТНОЕ ПОЯСНЕНИЕ {i}')
            for j in range(4): Option.objects.create(question=q,text=f'Вариант {i}-{j}',position=j,correct=j==2)
            cls.test.questions.add(q)
    def setUp(self):
        self.manager = AttemptManager(AdaptiveEngine(selector=QuestionSelector(random.Random(4))))
    def start(self): return self.manager.start(self.student,self.test)
    def answer(self,a,correct=True):
        a.refresh_from_db(); q=a.current
        return self.manager.answer(a.pk,self.student,q.pk,q.correct if correct else (q.correct+1)%4)
    def test_snapshot_entire_bank(self):
        a=self.start(); self.assertEqual(a.bank.count(),10)
        q=a.current; text=q.text; options=q.options.copy(); explanation=q.explanation
        source=Question.objects.get(pk=q.source_id)
        source.text='Изменено'; source.difficulty=1; source.explanation='Другое'; source.active=False; source.save()
        source.options.all().delete()
        self.test.length=1; self.test.initial=1; self.test.title='Новое'; self.test.save(); self.test.questions.clear()
        q.refresh_from_db(); a.refresh_from_db()
        self.assertEqual((q.text,q.options,q.explanation),(text,options,explanation))
        self.assertEqual((a.length,a.initial,a.title),(3,3,'Тест'))
        self.answer(a); self.assertEqual(a.bank.count(),10)
    def test_insufficient_bank(self):
        self.test.length=11
        with self.assertRaises(ScenarioError): self.start()
        self.assertFalse(Attempt.objects.exists())
    def test_invalid_and_inactive_questions_excluded(self):
        q=self.test.questions.first(); q.options.first().delete()
        q=self.test.questions.last(); q.active=False; q.save()
        self.test.length=9
        with self.assertRaises(ScenarioError): self.start()
    def test_unpublished_cannot_start(self):
        self.test.published=False
        with self.assertRaises(ScenarioError): self.start()
    def test_single_active_attempt_and_database_constraint(self):
        a=self.start(); self.assertEqual(self.start().pk,a.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attempt.objects.create(student=self.student,test=self.test,title='Дубликат',length=3,initial=3)
    def test_complete_and_no_repeated_questions(self):
        a=self.start(); ids=[]
        for _ in range(3):
            a.refresh_from_db(); ids.append(a.current_id); a=self.answer(a)
        self.assertEqual(a.state,'COMPLETED'); self.assertIsNone(a.current)
        self.assertEqual(len(set(ids)),3); self.assertEqual(Answer.objects.count(),3)
        self.assertIsNotNone(a.finished)
    def test_repeat_submission_has_no_effect(self):
        a=self.start(); q=a.current
        self.answer(a); a.refresh_from_db(); current=a.current_id; revision=a.revision
        with self.assertRaises(ScenarioError): self.manager.answer(a.pk,self.student,q.pk,0)
        a.refresh_from_db(); self.assertEqual((a.current_id,a.revision),(current,revision)); self.assertEqual(Answer.objects.count(),1)
    def test_non_current_answer_rejected(self):
        a=self.start(); q=a.bank.exclude(pk=a.current_id).first()
        with self.assertRaises(ScenarioError): self.manager.answer(a.pk,self.student,q.pk,0)
        self.assertEqual(Answer.objects.count(),0)
    def test_invalid_option_rolls_back(self):
        a=self.start()
        with self.assertRaises(ScenarioError): self.manager.answer(a.pk,self.student,a.current_id,9)
        a.refresh_from_db(); self.assertEqual(a.revision,0); self.assertEqual(Answer.objects.count(),0)
    def test_no_answer_after_completed(self):
        a=self.start(); first=a.current_id
        for _ in range(3): a=self.answer(a)
        with self.assertRaises(ScenarioError): self.manager.answer(a.pk,self.student,first,0)
        self.assertEqual(Answer.objects.count(),3)
    def test_abort_zero_answers(self):
        a=self.start(); q=a.current_id; self.manager.abort(a.pk,self.student); a.refresh_from_db()
        self.assertEqual(a.state,'ABORTED'); self.assertIsNone(ResultBuilder().build(a)['percent'])
        with self.assertRaises(ScenarioError): self.manager.answer(a.pk,self.student,q,0)
    def test_abort_with_answers_and_result(self):
        a=self.start(); self.answer(a); self.manager.abort(a.pk,self.student); a.refresh_from_db()
        result=ResultBuilder().build(a)
        self.assertEqual((result['count'],result['correct'],result['percent']),(1,1,100))
        self.assertEqual(sum(d['correct'] for d in result['distribution']),1)
        self.assertEqual(a.state,'ABORTED')
    def test_answer_records_actual_difficulty_and_time(self):
        a=self.start(); level=a.current.difficulty; self.answer(a)
        answer=Answer.objects.get(); self.assertEqual(answer.difficulty,level); self.assertGreaterEqual(answer.elapsed_seconds,0)
    def test_refresh_login_and_resume(self):
        a=self.start(); self.client.force_login(self.student)
        for _ in range(2): self.assertContains(self.client.get(f'/attempts/{a.pk}/'),a.current.text)
        self.client.logout(); self.client.force_login(self.student)
        self.assertContains(self.client.get('/'),'Продолжить тестирование')
        response=self.client.post(f'/tests/{self.test.pk}/start/')
        self.assertRedirects(response,f'/attempts/{a.pk}/'); self.assertEqual(Attempt.objects.count(),1)
    def test_active_response_does_not_expose_secrets(self):
        a=self.start(); self.client.force_login(self.student)
        response=self.client.get(f'/attempts/{a.pk}/')
        self.assertNotContains(response,'СЕКРЕТНОЕ ПОЯСНЕНИЕ')
        self.assertNotContains(response,'correct'); self.assertNotContains(response,'explanation')
        self.assertNotIn('question',response.context)
    def test_roles_and_foreign_attempts(self):
        a=self.start(); self.client.force_login(self.other)
        for suffix in ['', 'abort/']:
            self.assertEqual(self.client.get(f'/attempts/{a.pk}/{suffix}').status_code,404)
        self.assertEqual(self.client.post(f'/attempts/{a.pk}/',{'question':a.current_id,'selected':2}).status_code,404)
        self.assertEqual(self.client.get(f'/attempts/{a.pk}/result/').status_code,403)
        for path in ['/teacher/','/teacher/results/','/teacher/sandbox/','/teacher/questions/new/','/teacher/tests/new/']:
            self.assertEqual(self.client.get(path).status_code,403)
            self.assertEqual(self.client.post(path,{}).status_code,403)
    def test_get_requests_do_not_mutate_attempt(self):
        a=self.start(); self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/tests/{self.test.pk}/start/').status_code,405)
        self.client.get(f'/attempts/{a.pk}/abort/'); self.client.get(f'/attempts/{a.pk}/')
        a.refresh_from_db(); self.assertEqual((a.state,a.revision),('IN_PROGRESS',0)); self.assertEqual(Answer.objects.count(),0)
    def test_csrf_enforced(self):
        client=Client(enforce_csrf_checks=True); client.force_login(self.student)
        self.assertEqual(client.post(f'/tests/{self.test.pk}/start/').status_code,403)
    def test_teacher_screens_and_sandbox(self):
        self.client.force_login(self.teacher)
        for path in ['/teacher/','/teacher/results/','/teacher/sandbox/','/teacher/questions/new/','/teacher/tests/new/']:
            self.assertEqual(self.client.get(path).status_code,200)
        before=Attempt.objects.count()
        response=self.client.post('/teacher/sandbox/',dict(initial=4,outcomes='01',counts='0,1,0,0,1',seed=42))
        self.assertEqual(response.status_code,200); self.assertEqual(response.context['rows'][0]['actual'],5)
        self.assertEqual(Attempt.objects.count(),before)
    def test_teacher_creates_and_edits_question(self):
        self.client.force_login(self.teacher)
        payload=dict(topic=self.topic.pk,text='Новый вопрос',difficulty=2,explanation='Объяснение',active='on',correct=1,**{f'option_{i}':f'Ответ {i}' for i in range(4)})
        self.assertRedirects(self.client.post('/teacher/questions/new/',payload),'/teacher/')
        q=Question.objects.get(text='Новый вопрос'); self.assertEqual(q.options.count(),4); self.assertEqual(q.options.get(correct=True).position,1)
        payload['correct']=3; payload['text']='Редакция'
        self.assertRedirects(self.client.post(f'/teacher/questions/{q.pk}/',payload),'/teacher/')
        q.refresh_from_db(); self.assertEqual(q.text,'Редакция'); self.assertEqual(q.options.get(correct=True).position,3)
    def test_teacher_creates_publishes_unpublishes_test(self):
        self.client.force_login(self.teacher)
        payload=dict(title='Новый тест',topic=self.topic.pk,questions=list(self.test.questions.values_list('pk',flat=True)),length=2,initial=4,published='on')
        self.assertRedirects(self.client.post('/teacher/tests/new/',payload),'/teacher/')
        t=TestDefinition.objects.get(title='Новый тест'); self.assertTrue(t.published)
        payload.pop('published'); self.client.post(f'/teacher/tests/{t.pk}/',payload); t.refresh_from_db(); self.assertFalse(t.published)
    def test_test_validation_rejects_foreign_topic_and_insufficient_bank(self):
        topic=Topic.objects.create(name='Другая')
        form=TestForm(data=dict(title='Некорректный',topic=topic.pk,questions=[self.test.questions.first().pk],length=2,initial=3,published=True))
        self.assertFalse(form.is_valid()); self.assertIn('questions',form.errors); self.assertIn('published',form.errors)
    def test_student_full_http_flow(self):
        self.assertTrue(self.client.login(username='s',password='StudentPassword123!'))
        self.client.post(f'/tests/{self.test.pk}/start/')
        a=Attempt.objects.get()
        for _ in range(3):
            a.refresh_from_db(); self.client.post(f'/attempts/{a.pk}/',{'question':a.current_id,'selected':a.current.correct})
        response=self.client.get(f'/attempts/{a.pk}/result/')
        self.assertContains(response,'100,0%'); self.assertContains(response,'СЕКРЕТНОЕ ПОЯСНЕНИЕ')
        self.client.logout(); self.client.force_login(self.student)
        self.assertContains(self.client.get('/history/'),'Завершена')
        self.client.force_login(self.teacher); self.assertContains(self.client.get(f'/attempts/{a.pk}/result/'),'Разбор ответов')
    def test_sandbox_validation(self):
        self.client.force_login(self.teacher)
        response=self.client.post('/teacher/sandbox/',dict(initial=9,outcomes='abc',counts='-1,0',seed=42))
        self.assertEqual(response.status_code,200); self.assertEqual(len(response.context['form'].errors),3)

class DemoTests(TestCase):
    def test_seed_idempotent_and_preserves_edits(self):
        call_command('seed_demo',verbosity=0)
        q=Question.objects.first(); q.text='Пользовательская редакция'; q.save()
        user=User.objects.get(username='student1'); user.set_password('ChangedPassword123!'); user.save()
        extra=Topic.objects.create(name='Собственная тема')
        call_command('seed_demo',verbosity=0)
        self.assertEqual(Question.objects.count(),50); self.assertEqual(TestDefinition.objects.count(),1); self.assertEqual(User.objects.count(),3)
        q.refresh_from_db(); self.assertEqual(q.text,'Пользовательская редакция')
        user.refresh_from_db(); self.assertTrue(user.check_password('ChangedPassword123!')); self.assertTrue(Topic.objects.filter(pk=extra.pk).exists())
        for level in range(1,6): self.assertEqual(Question.objects.filter(difficulty=level).count(),10)
        for q in Question.objects.all(): self.assertEqual(q.options.count(),4); self.assertEqual(q.options.filter(correct=True).count(),1)

class ConcurrentAnswerTests(TransactionTestCase):
    def test_two_simultaneous_answers_accept_only_one(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        student=User.objects.create_user('parallel')
        topic=Topic.objects.create(name='Конкурентность')
        test=TestDefinition.objects.create(title='Параллельный тест',topic=topic,length=2,published=True)
        for i in range(3):
            q=Question.objects.create(topic=topic,text=str(i),difficulty=3,explanation='Пояснение')
            Option.objects.bulk_create([Option(question=q,text=str(j),position=j,correct=j==0) for j in range(4)])
            test.questions.add(q)
        a=AttemptManager().start(student,test); qid=a.current_id
        barrier=Barrier(2)
        def submit():
            try:
                barrier.wait(timeout=10)
                AttemptManager().answer(a.pk,student,qid,0)
                return True
            except ScenarioError:
                return False
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:submit(),range(2)))
        self.assertEqual(sum(results),1)
        self.assertEqual(Answer.objects.count(),1)
        a.refresh_from_db(); self.assertEqual(a.revision,1); self.assertEqual(a.current.step,2)
