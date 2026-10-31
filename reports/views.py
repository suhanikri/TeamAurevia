from django.shortcuts import render
from accounts.permissions import staff_or_admin


@staff_or_admin
def dashboard(request):
    return render(request, 'reports/dashboard.html')
