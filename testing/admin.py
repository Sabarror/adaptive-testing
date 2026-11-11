from django.contrib import admin
from .models import Topic, Question, TestDefinition
admin.site.register([Topic,Question,TestDefinition])
