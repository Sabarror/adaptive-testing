from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.db import transaction
from testing.models import Topic, Question, Option, TestDefinition
from testing.demo_data import QUESTIONS

class Command(BaseCommand):
    help = 'Создать локальные демонстрационные данные без перезаписи существующих объектов.'
    @transaction.atomic
    def handle(self,*args,**options):
        teacher,_ = Group.objects.get_or_create(name='Преподаватели')
        students,_ = Group.objects.get_or_create(name='Студенты')
        teacher.permissions.add(*Permission.objects.filter(content_type__app_label='testing',codename__in=['add_question','change_question','view_question','add_testdefinition','change_testdefinition','view_testdefinition','view_attempt']))
        for username,password,group in [('teacher','TeacherDemo2026!',teacher),('student1','StudentDemo2026!',students),('student2','StudentDemo2026!',students)]:
            user,created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password); user.save(); user.groups.add(group)
            else:
                self.stdout.write(f'Учётная запись {username} уже существует: пароль и группы сохранены.')
        topic,_ = Topic.objects.get_or_create(name='Основы программирования на Python')
        bank=[]
        for level,rows in QUESTIONS.items():
            for i,(text,answers,explanation) in enumerate(rows,1):
                q,created = Question.objects.get_or_create(demo_key=f'python-{level}-{i}', defaults=dict(topic=topic,text=text,difficulty=level,explanation=explanation))
                if created:
                    shift = (level+i) % 4
                    variants = answers[shift:] + answers[:shift]
                    Option.objects.bulk_create([Option(question=q,text=a,position=j,correct=a==answers[0]) for j,a in enumerate(variants)])
                bank.append(q)
        test,created = TestDefinition.objects.get_or_create(demo_key='python-demo',defaults=dict(title='Основы Python: адаптивный контроль',description='Десять вопросов с подбором сложности по вашим ответам.',topic=topic,length=10,initial=3,published=True))
        if created: test.questions.set(bank)
        self.stdout.write(self.style.SUCCESS('Демонстрационные данные готовы. Существующие объекты сохранены.'))
