from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('catalog/', include('catalog.urls')),
    path('subscriptions/', include('subscriptions.urls')),
    path('invoices/', include('billing.invoice_urls')),
    path('payments/', include('billing.payment_urls')),
    path('billing/', include('billing.engine_urls')),
    path('portal/', include('portal.urls')),
    path('', views.home, name='home'),
    path('', include('reports.urls')),
]
