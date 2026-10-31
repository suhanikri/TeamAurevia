from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import SignupForm, LoginForm, StaffCreationForm
from .permissions import admin_only

User = get_user_model()


def get_redirect_url_for_user(user, next_url=None):
    """
    Role-based redirect:
    - If next_url is a safe relative URL, honour it.
    - admin or staff -> /dashboard/
    - customer -> /portal/
    """
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    if getattr(user, 'role', None) in ('admin', 'staff'):
        return '/dashboard/'
    return '/portal/'


def signup(request):
    if request.user.is_authenticated:
        return redirect(get_redirect_url_for_user(request.user))

    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome to SubSentry! Your account has been created.")
        return redirect(get_redirect_url_for_user(user))

    return render(request, 'accounts/signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(get_redirect_url_for_user(request.user, request.GET.get('next')))

    next_url = request.POST.get('next') or request.GET.get('next') or ''
    form = LoginForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        password = form.cleaned_data['password']
        user = authenticate(request, username=email, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                messages.success(request, f"Welcome back, {user.email}!")
                return redirect(get_redirect_url_for_user(user, next_url))
            else:
                form.add_error(None, "This account is currently inactive.")
        else:
            form.add_error(None, "Invalid email or password.")

    return render(request, 'accounts/login.html', {
        'form': form,
        'next': next_url,
    })


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.info(request, "You have been logged out.")
        return redirect(settings.LOGOUT_REDIRECT_URL)
    # If accessed via GET, log out and redirect to login
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect(settings.LOGOUT_REDIRECT_URL)


@admin_only
def staff_list(request):
    staff_members = User.objects.filter(role=User.ROLE_STAFF).order_by('-date_joined')
    return render(request, 'accounts/staff_list.html', {
        'staff_members': staff_members,
    })


@admin_only
def staff_create(request):
    form = StaffCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f"Staff account {user.email} created successfully.")
        return redirect('accounts:staff_list')

    return render(request, 'accounts/staff_new.html', {
        'form': form,
    })
