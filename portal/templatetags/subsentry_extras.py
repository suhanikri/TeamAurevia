from decimal import Decimal, InvalidOperation
from django import template
from urllib.parse import urlencode

register = template.Library()


@register.filter(name='inr')
def inr(value):
    """
    Formats a Decimal or numeric value as Indian Rupee currency (e.g., ₹1,234.50).
    Safely handles None, empty strings, floats, ints, and Decimals.
    """
    if value is None or value == '':
        return '₹0.00'
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return '₹0.00'

    is_negative = d < Decimal('0.00')
    abs_d = abs(d)
    formatted = f"{abs_d:,.2f}"
    if is_negative:
        return f"-₹{formatted}"
    return f"₹{formatted}"


@register.filter(name='abs')
def abs_val(value):
    """Returns the absolute value of a number/Decimal."""
    try:
        return abs(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return value


@register.filter(name='status_class')
def status_class(status):
    """
    Maps a status code to a Bootstrap/SubSentry badge CSS class.
    draft -> secondary (grey)
    quotation -> info (blue)
    confirmed -> badge-indigo (indigo)
    active -> success (green)
    paused -> warning (amber)
    closed -> dark (dark)
    paid -> success (green)
    cancelled -> danger (red)
    overdue -> danger (red)
    """
    if not status:
        return 'secondary'
    key = str(status).strip().lower()
    mapping = {
        'draft': 'secondary',
        'quotation': 'info text-dark',
        'confirmed': 'badge-indigo',
        'active': 'success',
        'paused': 'warning text-dark',
        'closed': 'dark',
        'paid': 'success',
        'cancelled': 'danger',
        'overdue': 'danger',
    }
    return mapping.get(key, 'secondary')


@register.filter(name='add_class')
def add_class(field, css_class):
    """
    Appends a CSS class to a BoundField's widget.
    Example: {{ form.email|add_class:"form-control" }}
    """
    if hasattr(field, 'as_widget'):
        existing = field.field.widget.attrs.get('class', '')
        combined = f"{existing} {css_class}".strip()
        return field.as_widget(attrs={'class': combined})
    return field


@register.filter(name='is_checkbox')
def is_checkbox(field):
    """Checks if a field's widget is a CheckboxInput."""
    if hasattr(field, 'field') and hasattr(field.field, 'widget'):
        return field.field.widget.__class__.__name__ == 'CheckboxInput'
    return False


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """
    Preserves current GET query parameters while updating or overriding specified keys.
    Useful for pagination and filter links.
    Example: ?{% query_transform page=page_obj.next_page_number %}
    """
    request = context.get('request')
    if not request or not hasattr(request, 'GET'):
        return urlencode({k: v for k, v in kwargs.items() if v is not None})
    updated = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None:
            updated[k] = v
        elif k in updated:
            del updated[k]
    return updated.urlencode()
