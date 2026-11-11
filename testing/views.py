from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Attempt, Question, TestDefinition
from .forms import QuestionForm, TestForm, SandboxForm
from .services import AttemptManager, ResultBuilder, ScenarioError, chart
from .domain import simulate

def teacher(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.groups.filter(name='Преподаватели').exists(): raise PermissionDenied
        return view(request,*args,**kwargs)
    return wrapped

@login_required
def home(request):
    return render(request,'home.html',{'tests':TestDefinition.objects.filter(published=True), 'active':Attempt.objects.filter(student=request.user,state='IN_PROGRESS').select_related('test')})

@login_required
@require_POST
def start(request,pk):
    test = get_object_or_404(TestDefinition,pk=pk)
    try: a = AttemptManager().start(request.user,test)
    except ScenarioError as e:
        messages.error(request,str(e)); return redirect('home')
    return redirect('attempt',pk=a.pk)

def own(request,pk): return get_object_or_404(Attempt,pk=pk,student=request.user)

@login_required
def attempt(request,pk):
    a = own(request,pk)
    if a.state!='IN_PROGRESS': return redirect('result',pk=a.pk)
    if request.method=='POST':
        try:
            qid = int(request.POST.get('question','0'))
            selected = int(request.POST.get('selected','-1'))
            AttemptManager().answer(a.pk,request.user,qid,selected)
        except (ScenarioError,ValueError) as e: messages.error(request,str(e) if isinstance(e,ScenarioError) else 'Выберите вариант ответа.')
        return redirect('attempt',pk=a.pk)
    q = a.current
    return render(request,'attempt.html',{'attempt':a, 'question_id':q.pk,'text':q.text,'options':list(enumerate(q.options)), 'step':q.step,'difficulty':q.difficulty,'progress':round((q.step-1)/a.length*100)})

@login_required
def abort(request,pk):
    a = own(request,pk)
    if request.method=='POST':
        AttemptManager().abort(a.pk,request.user)
        return redirect('result',pk=a.pk)
    return render(request,'abort.html',{'attempt':a})

@login_required
def history(request):
    return render(request,'history.html',{'attempts':Attempt.objects.filter(student=request.user).order_by('-started')})

@login_required
def result(request,pk):
    a = get_object_or_404(Attempt,pk=pk)
    is_teacher = request.user.groups.filter(name='Преподаватели').exists()
    if a.student_id!=request.user.pk and not is_teacher: raise PermissionDenied
    if a.state=='IN_PROGRESS':
        if a.student_id==request.user.pk: return redirect('attempt',pk=a.pk)
        return render(request,'pending.html',{'attempt':a})
    return render(request,'result.html',{'attempt':a,**ResultBuilder().build(a)})

@teacher
def manage(request):
    return render(request,'manage.html',{'questions':Question.objects.select_related('topic').order_by('difficulty','pk'), 'tests':TestDefinition.objects.all()})

@teacher
def edit_question(request,pk=None): return edit(request,Question,QuestionForm,pk,'Вопрос')
@teacher
def edit_test(request,pk=None): return edit(request,TestDefinition,TestForm,pk,'Тест')

def edit(request,model,formclass,pk,title):
    obj = get_object_or_404(model,pk=pk) if pk else None
    form = formclass(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save(); messages.success(request,'Изменения сохранены.'); return redirect('manage')
    return render(request,'form.html',{'form':form,'title':title})

@teacher
def results(request):
    return render(request,'history.html',{'attempts':Attempt.objects.select_related('student').order_by('-started'),'all_students':True})

@teacher
def sandbox(request):
    form = SandboxForm(request.POST or None)
    context = {'form':form}
    if request.method=='POST' and form.is_valid():
        rows,message = simulate(**form.cleaned_data)
        context.update(rows=rows,simulation_message=message,chart=chart(rows))
    return render(request,'sandbox.html',context)
