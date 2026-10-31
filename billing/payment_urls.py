from django.urls import path
from . import payment_views

app_name = 'payments'

urlpatterns = [
    path('', payment_views.payment_list, name='list'),
    path('invoice/<int:invoice_id>/new/', payment_views.record_invoice_payment, name='record'),
    path('outstanding/', payment_views.paid_vs_outstanding, name='outstanding'),
]
