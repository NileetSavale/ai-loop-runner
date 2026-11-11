# Case 52

## The issue

AuthenticationForm's username field doesn't set maxlength HTML attribute.
Description
	
AuthenticationForm's username field doesn't render with maxlength HTML attribute anymore.
Regression introduced in #27515 and 5ceaf14686ce626404afb6a5fbd3d8286410bf13.
​https://groups.google.com/forum/?utm_source=digest&utm_medium=email#!topic/django-developers/qnfSqro0DlA
​https://forum.djangoproject.com/t/possible-authenticationform-max-length-regression-in-django-2-1/241

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/contrib/auth/forms.py b/django/contrib/auth/forms.py
index a0cfed0995..b62f2893aa 100755
--- a/django/contrib/auth/forms.py
+++ b/django/contrib/auth/forms.py
@@ -191,7 +191,9 @@ class AuthenticationForm(forms.Form):
 
         # Set the max length and label for the "username" field.
         self.username_field = UserModel._meta.get_field(UserModel.USERNAME_FIELD)
-        self.fields['username'].max_length = self.username_field.max_length or 254
+        max_length = self.username_field.max_length or 254
+        self.fields['username'].max_length = max_length
+        self.fields['username'].widget.attrs['maxlength'] = str(max_length)
         if self.fields['username'].label is None:
             self.fields['username'].label = capfirst(self.username_field.verbose_name)
 
diff --git a/tests/auth_tests/test_forms.py b/tests/auth_tests/test_forms.py
index 7085dcfa11..6263fe9805 100755
--- a/tests/auth_tests/test_forms.py
+++ b/tests/auth_tests/test_forms.py
@@ -423,6 +423,7 @@ class AuthenticationFormTest(TestDataMixin, TestCase):
         CustomEmailField.objects.create_user(**data)
         form = AuthenticationForm(None, data)
         self.assertEqual(form.fields['username'].max_length, 255)
+        self.assertEqual(form['username'].field.widget.attrs['maxlength'], '255')
         self.assertEqual(form.errors, {})
 
     @override_settings(AUTH_USER_MODEL='auth_tests.IntegerUsernameUser')
@@ -435,6 +436,7 @@ class AuthenticationFormTest(TestDataMixin, TestCase):
         IntegerUsernameUser.objects.create_user(**data)
         form = AuthenticationForm(None, data)
         self.assertEqual(form.fields['username'].max_length, 254)
+        self.assertEqual(form['username'].field.widget.attrs['maxlength'], '254')
         self.assertEqual(form.errors, {})
 
     def test_username_field_label(self):
```

## The official fix

```diff
diff --git a/django/contrib/auth/forms.py b/django/contrib/auth/forms.py
--- a/django/contrib/auth/forms.py
+++ b/django/contrib/auth/forms.py
@@ -191,7 +191,9 @@ def __init__(self, request=None, *args, **kwargs):
 
         # Set the max length and label for the "username" field.
         self.username_field = UserModel._meta.get_field(UserModel.USERNAME_FIELD)
-        self.fields['username'].max_length = self.username_field.max_length or 254
+        username_max_length = self.username_field.max_length or 254
+        self.fields['username'].max_length = username_max_length
+        self.fields['username'].widget.attrs['maxlength'] = username_max_length
         if self.fields['username'].label is None:
             self.fields['username'].label = capfirst(self.username_field.verbose_name)
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/auth_tests/test_forms.py b/tests/auth_tests/test_forms.py
--- a/tests/auth_tests/test_forms.py
+++ b/tests/auth_tests/test_forms.py
@@ -423,6 +423,7 @@ def test_username_field_max_length_matches_user_model(self):
         CustomEmailField.objects.create_user(**data)
         form = AuthenticationForm(None, data)
         self.assertEqual(form.fields['username'].max_length, 255)
+        self.assertEqual(form.fields['username'].widget.attrs.get('maxlength'), 255)
         self.assertEqual(form.errors, {})
 
     @override_settings(AUTH_USER_MODEL='auth_tests.IntegerUsernameUser')
@@ -435,6 +436,7 @@ def test_username_field_max_length_defaults_to_254(self):
         IntegerUsernameUser.objects.create_user(**data)
         form = AuthenticationForm(None, data)
         self.assertEqual(form.fields['username'].max_length, 254)
+        self.assertEqual(form.fields['username'].widget.attrs.get('maxlength'), 254)
         self.assertEqual(form.errors, {})
 
     def test_username_field_label(self):
```

## Hidden tests the cheap fix failed

- `test_username_field_max_length_defaults_to_254 (auth_tests.test_forms.AuthenticationFormTest)`
- `test_username_field_max_length_matches_user_model (auth_tests.test_forms.AuthenticationFormTest)`

## Test output for those tests (excerpt)

```
test_username_field_max_length_defaults_to_254 (auth_tests.test_forms.AuthenticationFormTest) ... FAIL
test_username_field_max_length_matches_user_model (auth_tests.test_forms.AuthenticationFormTest) ... FAIL
FAIL: test_username_field_max_length_defaults_to_254 (auth_tests.test_forms.AuthenticationFormTest)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/django/test/utils.py", line 370, in inner
    return func(*args, **kwargs)
  File "/testbed/tests/auth_tests/test_forms.py", line 439, in test_username_field_max_length_defaults_to_254
    self.assertEqual(form.fields['username'].widget.attrs.get('maxlength'), 254)
AssertionError: '254' != 254

======================================================================
FAIL: test_username_field_max_length_matches_user_model (auth_tests.test_forms.AuthenticationFormTest)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/django/test/utils.py", line 370, in inner
    return func(*args, **kwargs)
  File "/testbed/tests/auth_tests/test_forms.py", line 426, in test_username_field_max_length_matches_user_model
    self.assertEqual(form.fields['username'].widget.attrs.get('maxlength'), 255)
AssertionError: '255' != 255

----------------------------------------------------------------------
Ran 79 tests in 0.224s

FAILED (failures=2)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
+ git checkout b1d6b35e146aea83b171c1b921178bbaae2795ed tests/auth_tests/test_forms.py
>>>>> Test Exit Code: 1
Updated 1 path from 616cc5cf3c
```
