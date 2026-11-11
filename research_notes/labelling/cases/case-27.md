# Case 27

## The issue

Changing user's email could invalidate password reset tokens
Description
	
Sequence:
Have account with email address foo@…
Password reset request for that email (unused)
foo@… account changes their email address
Password reset email is used
The password reset email's token should be rejected at that point, but in fact it is allowed.
The fix is to add the user's email address into ​PasswordResetTokenGenerator._make_hash_value()
Nothing forces a user to even have an email as per AbstractBaseUser. Perhaps the token generation method could be factored out onto the model, ala get_session_auth_hash().

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/contrib/auth/tokens.py b/django/contrib/auth/tokens.py
index 93e2d71af2..116db3a7b4 100755
--- a/django/contrib/auth/tokens.py
+++ b/django/contrib/auth/tokens.py
@@ -94,7 +94,8 @@ class PasswordResetTokenGenerator:
         # Truncate microseconds so that tokens are consistent even if the
         # database doesn't support microseconds.
         login_timestamp = '' if user.last_login is None else user.last_login.replace(microsecond=0, tzinfo=None)
-        return str(user.pk) + user.password + str(login_timestamp) + str(timestamp)
+        email = getattr(user, 'email', '') or ''
+        return str(user.pk) + user.password + str(login_timestamp) + str(timestamp) + str(email)
 
     def _num_seconds(self, dt):
         return int((dt - datetime(2001, 1, 1)).total_seconds())
diff --git a/tests/auth_tests/test_tokens.py b/tests/auth_tests/test_tokens.py
index bba435be84..db32ec57ce 100755
--- a/tests/auth_tests/test_tokens.py
+++ b/tests/auth_tests/test_tokens.py
@@ -110,3 +110,13 @@ class TokenGeneratorTest(TestCase):
         legacy_token = p_old_generator.make_token(user)
         self.assertIs(p_old_generator.check_token(user, legacy_token), True)
         self.assertIs(p_new_generator.check_token(user, legacy_token), True)
+
+    def test_email_change_invalidates_token(self):
+        user = User.objects.create_user('tokentestuser', 'test2@example.com', 'testpw')
+        generator = PasswordResetTokenGenerator()
+        token = generator.make_token(user)
+        self.assertIs(generator.check_token(user, token), True)
+
+        user.email = 'new@example.com'
+        user.save()
+        self.assertIs(generator.check_token(user, token), False)
```

## The official fix

```diff
diff --git a/django/contrib/auth/tokens.py b/django/contrib/auth/tokens.py
--- a/django/contrib/auth/tokens.py
+++ b/django/contrib/auth/tokens.py
@@ -78,9 +78,9 @@ def _make_token_with_timestamp(self, user, timestamp, legacy=False):
 
     def _make_hash_value(self, user, timestamp):
         """
-        Hash the user's primary key and some user state that's sure to change
-        after a password reset to produce a token that invalidated when it's
-        used:
+        Hash the user's primary key, email (if available), and some user state
+        that's sure to change after a password reset to produce a token that is
+        invalidated when it's used:
         1. The password field will change upon a password reset (even if the
            same password is chosen, due to password salting).
         2. The last_login field will usually be updated very shortly after
@@ -94,7 +94,9 @@ def _make_hash_value(self, user, timestamp):
         # Truncate microseconds so that tokens are consistent even if the
         # database doesn't support microseconds.
         login_timestamp = '' if user.last_login is None else user.last_login.replace(microsecond=0, tzinfo=None)
-        return str(user.pk) + user.password + str(login_timestamp) + str(timestamp)
+        email_field = user.get_email_field_name()
+        email = getattr(user, email_field, '') or ''
+        return f'{user.pk}{user.password}{login_timestamp}{timestamp}{email}'
 
     def _num_seconds(self, dt):
         return int((dt - datetime(2001, 1, 1)).total_seconds())
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/auth_tests/models/__init__.py b/tests/auth_tests/models/__init__.py
--- a/tests/auth_tests/models/__init__.py
+++ b/tests/auth_tests/models/__init__.py
@@ -8,6 +8,7 @@
 from .no_password import NoPasswordUser
 from .proxy import Proxy, UserProxy
 from .uuid_pk import UUIDUser
+from .with_custom_email_field import CustomEmailField
 from .with_foreign_key import CustomUserWithFK, Email
 from .with_integer_username import IntegerUsernameUser
 from .with_last_login_attr import UserWithDisabledLastLoginField
@@ -16,10 +17,10 @@
 )
 
 __all__ = (
-    'CustomPermissionsUser', 'CustomUser', 'CustomUserNonUniqueUsername',
-    'CustomUserWithFK', 'CustomUserWithM2M', 'CustomUserWithM2MThrough',
-    'CustomUserWithoutIsActiveField', 'Email', 'ExtensionUser',
-    'IntegerUsernameUser', 'IsActiveTestUser1', 'MinimalUser',
+    'CustomEmailField', 'CustomPermissionsUser', 'CustomUser',
+    'CustomUserNonUniqueUsername', 'CustomUserWithFK', 'CustomUserWithM2M',
+    'CustomUserWithM2MThrough', 'CustomUserWithoutIsActiveField', 'Email',
+    'ExtensionUser', 'IntegerUsernameUser', 'IsActiveTestUser1', 'MinimalUser',
     'NoPasswordUser', 'Organization', 'Proxy', 'UUIDUser', 'UserProxy',
     'UserWithDisabledLastLoginField',
 )
diff --git a/tests/auth_tests/models/with_custom_email_field.py b/tests/auth_tests/models/with_custom_email_field.py
--- a/tests/auth_tests/models/with_custom_email_field.py
+++ b/tests/auth_tests/models/with_custom_email_field.py
@@ -15,7 +15,7 @@ def create_user(self, username, password, email):
 class CustomEmailField(AbstractBaseUser):
     username = models.CharField(max_length=255)
     password = models.CharField(max_length=255)
-    email_address = models.EmailField()
+    email_address = models.EmailField(null=True)
     is_active = models.BooleanField(default=True)
 
     EMAIL_FIELD = 'email_address'
diff --git a/tests/auth_tests/test_models.py b/tests/auth_tests/test_models.py
--- a/tests/auth_tests/test_models.py
+++ b/tests/auth_tests/test_models.py
@@ -17,8 +17,7 @@
     SimpleTestCase, TestCase, TransactionTestCase, override_settings,
 )
 
-from .models import IntegerUsernameUser
-from .models.with_custom_email_field import CustomEmailField
+from .models import CustomEmailField, IntegerUsernameUser
 
 
 class NaturalKeysTestCase(TestCase):
diff --git a/tests/auth_tests/test_tokens.py b/tests/auth_tests/test_tokens.py
--- a/tests/auth_tests/test_tokens.py
+++ b/tests/auth_tests/test_tokens.py
@@ -7,6 +7,8 @@
 from django.test.utils import ignore_warnings
 from django.utils.deprecation import RemovedInDjango40Warning
 
+from .models import CustomEmailField
+
 
 class MockedPasswordResetTokenGenerator(PasswordResetTokenGenerator):
     def __init__(self, now):
@@ -37,6 +39,27 @@ def test_10265(self):
         tk2 = p0.make_token(user_reload)
         self.assertEqual(tk1, tk2)
 
+    def test_token_with_different_email(self):
+        """Updating the user email address invalidates the token."""
+        tests = [
+            (CustomEmailField, None),
+            (CustomEmailField, 'test4@example.com'),
+            (User, 'test4@example.com'),
+        ]
+        for model, email in tests:
+            with self.subTest(model=model.__qualname__, email=email):
+                user = model.objects.create_user(
+                    'changeemailuser',
+                    email=email,
+                    password='testpw',
+                )
+                p0 = PasswordResetTokenGenerator()
+                tk1 = p0.make_token(user)
+                self.assertIs(p0.check_token(user, tk1), True)
+                setattr(user, user.get_email_field_name(), 'test4new@example.com')
+                user.save()
+                self.assertIs(p0.check_token(user, tk1), False)
+
     def test_timeout(self):
         """The token is valid after n seconds, but no greater."""
         # Uses a mocked version of PasswordResetTokenGenerator so we can change
```

## Hidden tests the cheap fix failed

- `Updating the user email address invalidates the token.`
- `test_token_with_different_secret (auth_tests.test_tokens.TokenGeneratorTest)`

## Test output for those tests (excerpt)

```

======================================================================
FAIL: test_token_with_different_email (auth_tests.test_tokens.TokenGeneratorTest) (email=None, model='CustomEmailField')
Updating the user email address invalidates the token.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/auth_tests/test_tokens.py", line 61, in test_token_with_different_email
    self.assertIs(p0.check_token(user, tk1), False)
AssertionError: True is not False

======================================================================
FAIL: test_token_with_different_email (auth_tests.test_tokens.TokenGeneratorTest) (email='test4@example.com', model='CustomEmailField')
Updating the user email address invalidates the token.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/auth_tests/test_tokens.py", line 61, in test_token_with_different_email
    self.assertIs(p0.check_token(user, tk1), False)
AssertionError: True is not False

----------------------------------------------------------------------
Ran 58 tests in 1.029s

FAILED (failures=2)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Destroying test database for alias 'other' ('file:memorydb_other?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
```
