import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class StrongPasswordValidator:
    def validate(self, password, user=None):
        errors = []
        if len(password) <= 8:
            errors.append(ValidationError(
                _("Password must be more than 8 characters."),
                code='password_too_short',
            ))
        if not re.search(r'[A-Z]', password):
            errors.append(ValidationError(
                _("Password must contain at least one uppercase letter."),
                code='password_no_upper',
            ))
        if not re.search(r'[a-z]', password):
            errors.append(ValidationError(
                _("Password must contain at least one lowercase letter."),
                code='password_no_lower',
            ))
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append(ValidationError(
                _("Password must contain at least one special character."),
                code='password_no_special',
            ))
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must be more than 8 characters, with an uppercase letter, "
            "a lowercase letter, and a special character."
        )

