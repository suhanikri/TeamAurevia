from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.subscription_list, name='list'),
    path('new/', views.subscription_create_manual, name='create_manual'),
    path('from-template/', views.subscription_create_from_template, name='create_from_template'),
    path('<int:pk>/', views.subscription_detail, name='detail'),
    path('<int:pk>/action/<str:action>/', views.subscription_action, name='action'),
]
