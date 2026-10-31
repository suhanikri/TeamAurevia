from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from .validators import StrongPasswordValidator

User = get_user_model()


class StrongPasswordValidatorTests(TestCase):

    def setUp(self):
        self.validator = StrongPasswordValidator()

    def test_accepts_good_password(self):
        # > 8 characters, uppercase, lowercase, special character
        try:
            self.validator.validate("GoodPass123!")
        except ValidationError:
            self.fail("Validator unexpectedly raised ValidationError for a valid password.")

    def test_rejects_password_too_short(self):
        # 8 characters exactly (rule says MORE than 8 characters, so <= 8 must fail)
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate("Short1!a")
        self.assertTrue(any('more than 8 characters' in str(msg).lower() for msg in ctx.exception.messages))

    def test_rejects_missing_uppercase(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate("lowercase123!")
        self.assertTrue(any('uppercase' in str(msg).lower() for msg in ctx.exception.messages))

    def test_rejects_missing_lowercase(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate("UPPERCASE123!")
        self.assertTrue(any('lowercase' in str(msg).lower() for msg in ctx.exception.messages))

    def test_rejects_missing_special_character(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate("NoSpecialCharacter123")
        self.assertTrue(any('special character' in str(msg).lower() for msg in ctx.exception.messages))

    def test_returns_all_failing_messages(self):
        # 'abc' fails length, uppercase, and special character
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate("abc")
        messages = ctx.exception.messages
        self.assertGreaterEqual(len(messages), 3)


@override_settings(ALLOWED_HOSTS=['*'])
class UserSignupTests(TestCase):

    def test_signup_creates_customer_and_logs_in(self):
        client = Client(SERVER_NAME='localhost')
        response = client.post(reverse('accounts:signup'), {
            'email': 'newcustomer@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
        }, follow=True)

        user = User.objects.filter(email='newcustomer@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, User.ROLE_CUSTOMER)
        self.assertTrue(user.is_customer_role)
        # Should redirect customer to /portal/
        self.assertRedirects(response, '/portal/')

    def test_duplicate_email_rejected_case_insensitive(self):
        User.objects.create_user(email='existing@example.com', password='ValidPassword123!')

        client = Client(SERVER_NAME='localhost')
        response = client.post(reverse('accounts:signup'), {
            'email': 'EXISTING@EXAMPLE.COM',
            'password': 'ValidPassword123!',
            'confirm_password': 'ValidPassword123!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'email',
            'An account with this email address already exists.'
        )


@override_settings(ALLOWED_HOSTS=['*'])
class StaffManagementPermissionTests(TestCase):

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.admin_user = User.objects.create_superuser('admin@subsentry.test', 'AdminPass123!')
        self.staff_user = User.objects.create_user('staff@subsentry.test', 'StaffPass123!', role=User.ROLE_STAFF)
        self.customer_user = User.objects.create_user('customer@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)

    def test_anonymous_redirected_to_login(self):
        url = reverse('accounts:staff_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].startswith('/accounts/login/'))

    def test_customer_gets_403(self):
        self.client.force_login(self.customer_user)
        response = self.client.get(reverse('accounts:staff_create'))
        self.assertEqual(response.status_code, 403)

    def test_staff_gets_403(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('accounts:staff_create'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_and_create_staff(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('accounts:staff_create'))
        self.assertEqual(response.status_code, 200)

        post_response = self.client.post(reverse('accounts:staff_create'), {
            'email': 'newstaff@subsentry.test',
            'first_name': 'Alex',
            'last_name': 'Smith',
            'password': 'StaffMember123!',
            'confirm_password': 'StaffMember123!',
        }, follow=True)

        self.assertRedirects(post_response, reverse('accounts:staff_list'))
        created_staff = User.objects.filter(email='newstaff@subsentry.test').first()
        self.assertIsNotNone(created_staff)
        self.assertEqual(created_staff.role, User.ROLE_STAFF)
        self.assertEqual(created_staff.first_name, 'Alex')


@override_settings(ALLOWED_HOSTS=['*'])
class LoginRoleRedirectTests(TestCase):

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.admin = User.objects.create_superuser('admin2@subsentry.test', 'AdminPass123!')
        self.staff = User.objects.create_user('staff2@subsentry.test', 'StaffPass123!', role=User.ROLE_STAFF)
        self.customer = User.objects.create_user('cust2@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)

    def test_customer_login_redirects_to_portal(self):
        response = self.client.post(reverse('accounts:login'), {
            'email': 'cust2@subsentry.test',
            'password': 'CustPass123!',
        })
        self.assertRedirects(response, '/portal/', fetch_redirect_response=False)

    def test_staff_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('accounts:login'), {
            'email': 'staff2@subsentry.test',
            'password': 'StaffPass123!',
        })
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)

    def test_admin_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('accounts:login'), {
            'email': 'admin2@subsentry.test',
            'password': 'AdminPass123!',
        })
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
