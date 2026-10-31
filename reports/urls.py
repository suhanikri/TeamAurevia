from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/summary/', views.summary_report, name='summary'),
]
