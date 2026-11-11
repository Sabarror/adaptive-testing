from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q

class Topic(models.Model):
    name = models.CharField('Название', max_length=200, unique=True)
    def __str__(self): return self.name

class Question(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, verbose_name='Тема')
    text = models.TextField('Текст вопроса')
    difficulty = models.PositiveSmallIntegerField('Сложность', validators=[MinValueValidator(1), MaxValueValidator(5)])
    explanation = models.TextField('Пояснение')
    active = models.BooleanField('Активен', default=True)
    demo_key = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(difficulty__gte=1, difficulty__lte=5), name='question_level')]
    def __str__(self): return f'[{self.difficulty}] {self.text[:80]}'

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.TextField('Вариант')
    position = models.PositiveSmallIntegerField()
    correct = models.BooleanField(default=False)
    class Meta:
        ordering = ['position']
        constraints = [models.UniqueConstraint(fields=['question', 'position'], name='option_position'), models.UniqueConstraint(fields=['question'], condition=Q(correct=True), name='one_correct_option')]

class TestDefinition(models.Model):
    title = models.CharField('Название', max_length=200)
    description = models.TextField('Описание', blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, verbose_name='Тема')
    questions = models.ManyToManyField(Question, verbose_name='Вопросы')
    length = models.PositiveSmallIntegerField('Длина попытки', default=10, validators=[MinValueValidator(1), MaxValueValidator(100)])
    initial = models.PositiveSmallIntegerField('Начальная сложность', default=3, validators=[MinValueValidator(1), MaxValueValidator(5)])
    published = models.BooleanField('Опубликован', default=False)
    demo_key = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(initial__gte=1, initial__lte=5, length__gte=1, length__lte=100), name='test_settings')]
    def __str__(self): return self.title

class Attempt(models.Model):
    class State(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'В процессе'
        COMPLETED = 'COMPLETED', 'Завершена'
        ABORTED = 'ABORTED', 'Завершена досрочно'
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    test = models.ForeignKey(TestDefinition, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    length = models.PositiveSmallIntegerField()
    initial = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=15, choices=State.choices, default=State.IN_PROGRESS)
    started = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(null=True)
    current = models.ForeignKey('AttemptQuestion', null=True, on_delete=models.SET_NULL, related_name='+')
    revision = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'test'], condition=Q(state='IN_PROGRESS'), name='one_active_attempt')]

class AttemptQuestion(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='bank')
    source_id = models.PositiveBigIntegerField()
    text = models.TextField()
    difficulty = models.PositiveSmallIntegerField()
    options = models.JSONField()
    correct = models.PositiveSmallIntegerField()
    explanation = models.TextField()
    step = models.PositiveSmallIntegerField(null=True)
    target = models.PositiveSmallIntegerField(null=True)
    reason = models.TextField(blank=True)
    shown = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'source_id'], name='snapshot_source'), models.UniqueConstraint(fields=['attempt', 'step'], name='snapshot_step')]

class Answer(models.Model):
    question = models.OneToOneField(AttemptQuestion, on_delete=models.CASCADE, related_name='answer')
    selected = models.PositiveSmallIntegerField()
    correct = models.BooleanField()
    difficulty = models.PositiveSmallIntegerField()
    answered = models.DateTimeField(auto_now_add=True)
    elapsed_seconds = models.FloatField()
