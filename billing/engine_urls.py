from django.urls import path
from . import engine_views

app_name = 'billing_run'

urlpatterns = [
    path('', engine_views.billing_home, name='home'),
    path('preview/', engine_views.billing_preview, name='preview'),
    path('run/', engine_views.billing_run_action, name='run'),
    path('review/', engine_views.review_queue, name='review'),
    path('review/<int:flag_id>/resolve/', engine_views.resolve_flag, name='resolve_flag'),
]
