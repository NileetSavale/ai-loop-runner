# Case 23

## The issue

add filter is unable to concatenate strings with lazy string
Description
	
If you try to concatenate a string with a lazy string with the add template filter, the result is always the empty string because the add filter generates an exception (TypeError: can only concatenate str (not "__proxy__") to str).

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/template/defaultfilters.py b/django/template/defaultfilters.py
index 1c844580c6..39d35882d2 100755
--- a/django/template/defaultfilters.py
+++ b/django/template/defaultfilters.py
@@ -15,6 +15,7 @@ from django.utils.html import (
     avoid_wrapping, conditional_escape, escape, escapejs,
     json_script as _json_script, linebreaks, strip_tags, urlize as _urlize,
 )
+from django.utils.functional import Promise
 from django.utils.safestring import SafeData, mark_safe
 from django.utils.text import (
     Truncator, normalize_newlines, phone2numeric, slugify as _slugify, wrap,
@@ -678,6 +679,12 @@ def add(value, arg):
         return int(value) + int(arg)
     except (ValueError, TypeError):
         try:
+            if isinstance(value, Promise) or isinstance(arg, Promise):
+                # Lazy strings can't be concatenated directly with str.
+                if isinstance(value, Promise):
+                    value = str(value)
+                if isinstance(arg, Promise):
+                    arg = str(arg)
             return value + arg
         except Exception:
             return ''
```

## The official fix

```diff
diff --git a/django/utils/functional.py b/django/utils/functional.py
--- a/django/utils/functional.py
+++ b/django/utils/functional.py
@@ -176,6 +176,12 @@ def __mod__(self, rhs):
                 return str(self) % rhs
             return self.__cast() % rhs
 
+        def __add__(self, other):
+            return self.__cast() + other
+
+        def __radd__(self, other):
+            return other + self.__cast()
+
         def __deepcopy__(self, memo):
             # Instances of this class are effectively immutable. It's just a
             # collection of functions. So we don't need to do anything
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/template_tests/filter_tests/test_add.py b/tests/template_tests/filter_tests/test_add.py
--- a/tests/template_tests/filter_tests/test_add.py
+++ b/tests/template_tests/filter_tests/test_add.py
@@ -2,6 +2,7 @@
 
 from django.template.defaultfilters import add
 from django.test import SimpleTestCase
+from django.utils.translation import gettext_lazy
 
 from ..utils import setup
 
@@ -46,6 +47,22 @@ def test_add07(self):
         output = self.engine.render_to_string('add07', {'d': date(2000, 1, 1), 't': timedelta(10)})
         self.assertEqual(output, 'Jan. 11, 2000')
 
+    @setup({'add08': '{{ s1|add:lazy_s2 }}'})
+    def test_add08(self):
+        output = self.engine.render_to_string(
+            'add08',
+            {'s1': 'string', 'lazy_s2': gettext_lazy('lazy')},
+        )
+        self.assertEqual(output, 'stringlazy')
+
+    @setup({'add09': '{{ lazy_s1|add:lazy_s2 }}'})
+    def test_add09(self):
+        output = self.engine.render_to_string(
+            'add09',
+            {'lazy_s1': gettext_lazy('string'), 'lazy_s2': gettext_lazy('lazy')},
+        )
+        self.assertEqual(output, 'stringlazy')
+
 
 class FunctionTests(SimpleTestCase):
 
diff --git a/tests/utils_tests/test_functional.py b/tests/utils_tests/test_functional.py
--- a/tests/utils_tests/test_functional.py
+++ b/tests/utils_tests/test_functional.py
@@ -184,6 +184,11 @@ class Foo:
         with self.assertRaisesMessage(TypeError, msg):
             Foo().cp
 
+    def test_lazy_add(self):
+        lazy_4 = lazy(lambda: 4, int)
+        lazy_5 = lazy(lambda: 5, int)
+        self.assertEqual(lazy_4() + lazy_5(), 9)
+
     def test_lazy_equality(self):
         """
         == and != work correctly for Promises.
```

## Hidden tests the cheap fix failed

- `test_lazy_add (utils_tests.test_functional.FunctionalTests)`

## Test output for those tests (excerpt)

```
test_lazy_add (utils_tests.test_functional.FunctionalTests) ... ERROR
ERROR: test_lazy_add (utils_tests.test_functional.FunctionalTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/utils_tests/test_functional.py", line 190, in test_lazy_add
    self.assertEqual(lazy_4() + lazy_5(), 9)
TypeError: unsupported operand type(s) for +: '__proxy__' and '__proxy__'

----------------------------------------------------------------------
Ran 27 tests in 0.009s

FAILED (errors=1)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
>>>>> Test Exit Code: 1
+ git checkout fe886eee36be8022f34cfe59aa61ff1c21fe01d9 tests/template_tests/filter_tests/test_add.py tests/utils_tests/test_functional.py
Updated 2 paths from 64ee9d3cf6
```
