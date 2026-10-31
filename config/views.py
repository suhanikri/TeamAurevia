from django.shortcuts import redirect


def home(request):
    if not request.user.is_authenticated:
        return redirect('/accounts/login/')
    if getattr(request.user, 'role', None) in ('admin', 'staff'):
        return redirect('/dashboard/')
    return redirect('/portal/')

