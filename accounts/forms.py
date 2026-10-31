from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class SignupForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'autocomplete': 'email',
            'required': True,
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a strong password',
            'autocomplete': 'new-password',
            'required': True,
        }),
        help_text="Must be more than 8 characters, with an uppercase letter, a lowercase letter, and a special character."
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
            'required': True,
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    for error in e.error_list:
                        self.add_error('password', error)
        return cleaned_data

    def save(self):
        email = self.cleaned_data['email']
        password = self.cleaned_data['password']
        # Public signup ALWAYS creates role=customer
        return User.objects.create_user(email=email, password=password, role=User.ROLE_CUSTOMER)


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'autocomplete': 'email',
            'required': True,
        })
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
            'required': True,
        })
    )


class StaffCreationForm(forms.Form):
    email = forms.EmailField(
        label="Staff Email address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'staff@subsentry.test',
            'required': True,
        })
    )
    first_name = forms.CharField(
        label="First Name",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jane'})
    )
    last_name = forms.CharField(
        label="Last Name",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Doe'})
    )
    password = forms.CharField(
        label="Temporary Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create temporary password',
            'required': True,
        }),
        help_text="Must be more than 8 characters, with an uppercase letter, a lowercase letter, and a special character."
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm temporary password',
            'required': True,
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    for error in e.error_list:
                        self.add_error('password', error)
        return cleaned_data

    def save(self):
        email = self.cleaned_data['email']
        password = self.cleaned_data['password']
        first_name = self.cleaned_data.get('first_name', '')
        last_name = self.cleaned_data.get('last_name', '')
        # Only admin creates staff users with role=staff
        return User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=User.ROLE_STAFF,
        )

