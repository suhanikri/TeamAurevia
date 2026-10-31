from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    path('', views.subscription_list, name='subscription_list'),
    path('subscriptions/<int:id>/', views.subscription_detail, name='subscription_detail'),
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:id>/', views.invoice_detail, name='invoice_detail'),
    path('payments/', views.payment_list, name='payment_list'),
]
