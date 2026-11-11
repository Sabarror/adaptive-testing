from django import forms
from django.db import transaction
from .models import Question, Option, TestDefinition
from .services import valid_bank

class QuestionForm(forms.ModelForm):
    option_0 = forms.CharField(label='Вариант 1', widget=forms.Textarea(attrs={'rows':2}))
    option_1 = forms.CharField(label='Вариант 2', widget=forms.Textarea(attrs={'rows':2}))
    option_2 = forms.CharField(label='Вариант 3', widget=forms.Textarea(attrs={'rows':2}))
    option_3 = forms.CharField(label='Вариант 4', widget=forms.Textarea(attrs={'rows':2}))
    correct = forms.TypedChoiceField(label='Правильный вариант', choices=[(i, str(i+1)) for i in range(4)], coerce=int)
    class Meta:
        model = Question
        fields = ['topic','text','difficulty','explanation','active']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:
            for i,o in enumerate(self.instance.options.all()):
                self.initial[f'option_{i}'] = o.text
                if o.correct: self.initial['correct'] = i
    @transaction.atomic
    def save(self, commit=True):
        q = super().save(commit=True)
        q.options.all().delete()
        Option.objects.bulk_create([Option(question=q, position=i, text=self.cleaned_data[f'option_{i}'], correct=i==self.cleaned_data['correct']) for i in range(4)])
        return q

class TestForm(forms.ModelForm):
    class Meta:
        model = TestDefinition
        fields = ['title','description','topic','questions','length','initial','published']
        widgets = {'questions': forms.CheckboxSelectMultiple()}
    def clean(self):
        data = super().clean()
        questions, topic = data.get('questions'), data.get('topic')
        if questions is not None and topic:
            if any(q.topic_id != topic.pk for q in questions): self.add_error('questions','Все вопросы должны относиться к выбранной теме.')
            if data.get('published'):
                count = sum(q.active and q.options.count()==4 and q.options.filter(correct=True).count()==1 for q in questions)
                if count < data.get('length',1): self.add_error('published','Для публикации недостаточно активных корректных вопросов.')
        return data

class SandboxForm(forms.Form):
    initial = forms.IntegerField(label='Начальная сложность', min_value=1, max_value=5, initial=3)
    outcomes = forms.CharField(label='Ответы: 1 — верно, 0 — неверно', initial='111000', max_length=100, help_text='Последовательность из 1 и 0, до 100 ответов.')
    counts = forms.CharField(label='Количество вопросов уровней 1–5', initial='10,10,10,10,10', help_text='Пять чисел через запятую, каждое от 0 до 100.')
    seed = forms.IntegerField(label='Seed', initial=42)
    def clean_outcomes(self):
        value = self.cleaned_data['outcomes'].replace(' ','')
        if not value or set(value)-{'0','1'}: raise forms.ValidationError('Введите только 1 и 0.')
        return [c=='1' for c in value]
    def clean_counts(self):
        try:
            values = [int(v.strip()) for v in self.cleaned_data['counts'].split(',')]
            if len(values)!=5 or any(v<0 or v>100 for v in values): raise ValueError
            return values
        except ValueError: raise forms.ValidationError('Нужны пять целых чисел от 0 до 100 через запятую.')
