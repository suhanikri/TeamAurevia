from functools import wraps
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """
    Decorator for views that checks whether a user has a specific role.
    Redirects anonymous users to login.
    Raises PermissionDenied (403) for authenticated users without the required role.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if request.user.role not in roles:
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def admin_only(view_func):
    return role_required('admin')(view_func)


def staff_or_admin(view_func):
    return role_required('admin', 'staff')(view_func)


def any_logged_in_role(view_func):
    return role_required('admin', 'staff', 'customer')(view_func)

