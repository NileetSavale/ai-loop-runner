# Case 24

## The issue

Allow autoreloading of `python -m pkg_other_than_django runserver`
Description
	 
		(last modified by William Schwartz)
	 
​django.utils.autoreload.get_child_arguments detects if Python was launched as python -m django. Currently it detects only when ​-m was passed specifically django (and only in Python environments in which __file__ is set on modules, which is ​not true of all Python environments). Like #32177, this ticket aims to remove one impediment to creating Django-based command-line utilities that have their own ​__main__ sub-module while overriding Django's built-in management commands—in this case, runserver.
The fix, which I have submitted in the ​attached PR, is to use Python's ​documented way of determining if -m was used in get_child_arguments:
The top-level __main__ module is always the entry point of a ​complete Python program.
 __main__.__spec__ is not None ​if and only if Python was launched with -m or the name of a "directory, zipfile or other sys.path entry." In the latter cases, the ​documentation says
If the script name refers to a directory or zipfile, the script name is added to the start of sys.path and the __main__.py file in that location is executed as the __main__ module.
Hence __main__.__spec__.parent (which is ​usually but not always __main__.__package__) exists and is the empty string when Python is started with the name of a directory or zip file.
Therefore Python was started with -m pkg if and only if __main__.__spec__.parent == "pkg".
Following this algorithm is guaranteed to work as long as Python obeys its own documentation, and has the side benefit of avoiding use of __file__.

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/utils/autoreload.py b/django/utils/autoreload.py
index b8efb9f881..053e92a0cd 100755
--- a/django/utils/autoreload.py
+++ b/django/utils/autoreload.py
@@ -216,14 +216,17 @@ def get_child_arguments():
     executable is reported to not have the .exe extension which can cause bugs
     on reloading.
     """
-    import django.__main__
-    django_main_path = Path(django.__main__.__file__)
+    import __main__
     py_script = Path(sys.argv[0])
 
     args = [sys.executable] + ['-W%s' % o for o in sys.warnoptions]
-    if py_script == django_main_path:
-        # The server was started with `python -m django runserver`.
-        args += ['-m', 'django']
+    # __spec__ is set when the server was started with the `-m` option, see
+    # https://docs.python.org/3/reference/import.html#main-spec
+    # __spec__ may not exist, e.g. when running in a Conda env.
+    main_spec = getattr(__main__, '__spec__', None)
+    if main_spec is not None and main_spec.parent:
+        # The server was started with `python -m pkg runserver`.
+        args += ['-m', main_spec.parent]
         args += sys.argv[1:]
     elif not py_script.exists():
         # sys.argv[0] may not exist for several reasons on Windows.
diff --git a/tests/utils_tests/test_autoreload.py b/tests/utils_tests/test_autoreload.py
index b9f2db7276..5c5823c041 100755
--- a/tests/utils_tests/test_autoreload.py
+++ b/tests/utils_tests/test_autoreload.py
@@ -159,12 +159,22 @@ class TestIterModulesAndFiles(SimpleTestCase):
 class TestChildArguments(SimpleTestCase):
     @mock.patch('sys.argv', [django.__main__.__file__, 'runserver'])
     @mock.patch('sys.warnoptions', [])
+    @mock.patch('__main__.__spec__', types.SimpleNamespace(parent='django'))
     def test_run_as_module(self):
         self.assertEqual(
             autoreload.get_child_arguments(),
             [sys.executable, '-m', 'django', 'runserver']
         )
 
+    @mock.patch('sys.argv', ['/path/to/pkg/__main__.py', 'runserver'])
+    @mock.patch('sys.warnoptions', [])
+    @mock.patch('__main__.__spec__', types.SimpleNamespace(parent='pkg_other_than_django'))
+    def test_run_as_module_other_package(self):
+        self.assertEqual(
+            autoreload.get_child_arguments(),
+            [sys.executable, '-m', 'pkg_other_than_django', 'runserver']
+        )
+
     @mock.patch('sys.argv', [__file__, 'runserver'])
     @mock.patch('sys.warnoptions', ['error'])
     def test_warnoptions(self):
@@ -446,7 +456,7 @@ class RestartWithReloaderTests(SimpleTestCase):
         main = '/usr/lib/pythonX.Y/site-packages/django/__main__.py'
         argv = [main, 'runserver']
         mock_call = self.patch_autoreload(argv)
-        with mock.patch('django.__main__.__file__', main):
+        with mock.patch('__main__.__spec__', types.SimpleNamespace(parent='django')):
             autoreload.restart_with_reloader()
             self.assertEqual(mock_call.call_count, 1)
             self.assertEqual(mock_call.call_args[0][0], [self.executable, '-Wall', '-m', 'django'] + argv[1:])
```

## The official fix

```diff
diff --git a/django/utils/autoreload.py b/django/utils/autoreload.py
--- a/django/utils/autoreload.py
+++ b/django/utils/autoreload.py
@@ -216,14 +216,14 @@ def get_child_arguments():
     executable is reported to not have the .exe extension which can cause bugs
     on reloading.
     """
-    import django.__main__
-    django_main_path = Path(django.__main__.__file__)
+    import __main__
     py_script = Path(sys.argv[0])
 
     args = [sys.executable] + ['-W%s' % o for o in sys.warnoptions]
-    if py_script == django_main_path:
-        # The server was started with `python -m django runserver`.
-        args += ['-m', 'django']
+    # __spec__ is set when the server was started with the `-m` option,
+    # see https://docs.python.org/3/reference/import.html#main-spec
+    if __main__.__spec__ is not None and __main__.__spec__.parent:
+        args += ['-m', __main__.__spec__.parent]
         args += sys.argv[1:]
     elif not py_script.exists():
         # sys.argv[0] may not exist for several reasons on Windows.
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/utils_tests/test_autoreload.py b/tests/utils_tests/test_autoreload.py
--- a/tests/utils_tests/test_autoreload.py
+++ b/tests/utils_tests/test_autoreload.py
@@ -23,6 +23,7 @@
 from django.utils import autoreload
 from django.utils.autoreload import WatchmanUnavailable
 
+from .test_module import __main__ as test_main
 from .utils import on_macos_with_hfs
 
 
@@ -157,6 +158,7 @@ def test_path_with_embedded_null_bytes(self):
 
 
 class TestChildArguments(SimpleTestCase):
+    @mock.patch.dict(sys.modules, {'__main__': django.__main__})
     @mock.patch('sys.argv', [django.__main__.__file__, 'runserver'])
     @mock.patch('sys.warnoptions', [])
     def test_run_as_module(self):
@@ -165,6 +167,15 @@ def test_run_as_module(self):
             [sys.executable, '-m', 'django', 'runserver']
         )
 
+    @mock.patch.dict(sys.modules, {'__main__': test_main})
+    @mock.patch('sys.argv', [test_main.__file__, 'runserver'])
+    @mock.patch('sys.warnoptions', [])
+    def test_run_as_non_django_module(self):
+        self.assertEqual(
+            autoreload.get_child_arguments(),
+            [sys.executable, '-m', 'utils_tests.test_module', 'runserver'],
+        )
+
     @mock.patch('sys.argv', [__file__, 'runserver'])
     @mock.patch('sys.warnoptions', ['error'])
     def test_warnoptions(self):
@@ -447,7 +458,8 @@ def test_python_m_django(self):
         argv = [main, 'runserver']
         mock_call = self.patch_autoreload(argv)
         with mock.patch('django.__main__.__file__', main):
-            autoreload.restart_with_reloader()
+            with mock.patch.dict(sys.modules, {'__main__': django.__main__}):
+                autoreload.restart_with_reloader()
             self.assertEqual(mock_call.call_count, 1)
             self.assertEqual(mock_call.call_args[0][0], [self.executable, '-Wall', '-m', 'django'] + argv[1:])
 
diff --git a/tests/utils_tests/test_module/__main__.py b/tests/utils_tests/test_module/__main__.py
new file mode 100644
```

## Hidden tests the cheap fix failed

- `test_run_as_non_django_module (utils_tests.test_autoreload.TestChildArguments)`

## Test output for those tests (excerpt)

```

======================================================================
ERROR: __main__ (unittest.loader._FailedTest)
----------------------------------------------------------------------
ImportError: Failed to import test module: __main__
Traceback (most recent call last):
  File "/opt/miniconda3/envs/testbed/lib/python3.6/unittest/loader.py", line 153, in loadTestsFromName
    module = __import__(module_name)
ModuleNotFoundError: No module named 'utils_tests.test_module.__main__'


----------------------------------------------------------------------
Ran 79 tests in 0.516s

FAILED (errors=1, skipped=20)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
```
