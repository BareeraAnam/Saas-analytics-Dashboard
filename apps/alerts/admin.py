from django.contrib import admin
from .models import AlertLog, AlertRule

admin.site.register(AlertRule)
admin.site.register(AlertLog)
