from django.contrib import admin

from .models import QuizItem, QuizRound, SystemQuizQuestion, TeamQuizSettings


admin.site.register(SystemQuizQuestion)
admin.site.register(TeamQuizSettings)
admin.site.register(QuizRound)
admin.site.register(QuizItem)

