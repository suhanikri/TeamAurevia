from django.urls import path
from . import invoice_views

app_name = 'invoices'

urlpatterns = [
    path('', invoice_views.invoice_list, name='list'),
    path('<int:id>/', invoice_views.invoice_detail, name='detail'),
    path('<int:id>/confirm/', invoice_views.invoice_confirm, name='confirm'),
    path('<int:id>/cancel/', invoice_views.invoice_cancel, name='cancel'),
    path('<int:id>/send/', invoice_views.invoice_send, name='send'),
    path('<int:id>/print/', invoice_views.invoice_print, name='print'),
]
