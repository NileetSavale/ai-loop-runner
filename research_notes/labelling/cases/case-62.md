# Case 62

## The issue

`runserver 0`'s "Starting development server at <address>" doesn't work
Description
	
According to ​tutorial running 
python manage.py runserver 0:8000
is the same as 
python manage.py runserver 0.0.0.0:8000
but it's output 
$ python manage.py runserver 0:8000									 Watching for file changes with StatReloader						 
...
Starting development server at http://0:8000/ 
...
So that you can't use link "​http://0:8000/" in your browser. Output should be "Starting development server at ​http://0.0.0.0:8000/" when providing "0:8000" in command line in order to stay consistent with docs.

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/core/management/commands/runserver.py b/django/core/management/commands/runserver.py
index 3c39f57e4d..d9d1001e2a 100755
--- a/django/core/management/commands/runserver.py
+++ b/django/core/management/commands/runserver.py
@@ -105,6 +105,9 @@ class Command(BaseCommand):
                     self._raw_ipv6 = True
                 elif self.use_ipv6 and not _fqdn:
                     raise CommandError('"%s" is not a valid IPv6 address.' % self.addr)
+                elif self.addr == "0":
+                    # "0" is shorthand for all interfaces, shown as 0.0.0.0.
+                    self.addr = "0.0.0.0"
         if not self.addr:
             self.addr = self.default_addr_ipv6 if self.use_ipv6 else self.default_addr
             self._raw_ipv6 = self.use_ipv6
```

## The official fix

```diff
diff --git a/django/core/management/commands/runserver.py b/django/core/management/commands/runserver.py
--- a/django/core/management/commands/runserver.py
+++ b/django/core/management/commands/runserver.py
@@ -129,6 +129,13 @@ def inner_run(self, *args, **options):
         shutdown_message = options.get("shutdown_message", "")
         quit_command = "CTRL-BREAK" if sys.platform == "win32" else "CONTROL-C"
 
+        if self._raw_ipv6:
+            addr = f"[{self.addr}]"
+        elif self.addr == "0":
+            addr = "0.0.0.0"
+        else:
+            addr = self.addr
+
         if not options["skip_checks"]:
             self.stdout.write("Performing system checks...\n\n")
             self.check(display_num_errors=True)
@@ -147,7 +154,7 @@ def inner_run(self, *args, **options):
                 "version": self.get_version(),
                 "settings": settings.SETTINGS_MODULE,
                 "protocol": self.protocol,
-                "addr": "[%s]" % self.addr if self._raw_ipv6 else self.addr,
+                "addr": addr,
                 "port": self.port,
                 "quit_command": quit_command,
             }
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/admin_scripts/tests.py b/tests/admin_scripts/tests.py
--- a/tests/admin_scripts/tests.py
+++ b/tests/admin_scripts/tests.py
@@ -1587,6 +1587,21 @@ def test_runserver_addrport(self):
         call_command(self.cmd, addrport="7000")
         self.assertServerSettings("127.0.0.1", "7000")
 
+    @mock.patch("django.core.management.commands.runserver.run")
+    @mock.patch("django.core.management.base.BaseCommand.check_migrations")
+    def test_zero_ip_addr(self, *mocked_objects):
+        call_command(
+            "runserver",
+            addrport="0:8000",
+            use_reloader=False,
+            skip_checks=True,
+            stdout=self.output,
+        )
+        self.assertIn(
+            "Starting development server at http://0.0.0.0:8000/",
+            self.output.getvalue(),
+        )
+
     @unittest.skipUnless(socket.has_ipv6, "platform doesn't support IPv6")
     def test_runner_addrport_ipv6(self):
         call_command(self.cmd, addrport="", use_ipv6=True)
```

## Hidden tests the cheap fix failed

- `test_honor_umask (admin_scripts.tests.StartProject)`

## Test output for those tests (excerpt)

```
FAIL: test_honor_umask (admin_scripts.tests.StartProject) [settings.py]
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/admin_scripts/tests.py", line 2812, in test_honor_umask
    self.assertEqual(
AssertionError: 448 != 384

----------------------------------------------------------------------
Ran 209 tests in 51.441s

FAILED (failures=1)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
+ git checkout 93d4c9ea1de24eb391cb2b3561b6703fd46374df tests/admin_scripts/tests.py
>>>>> Test Exit Code: 1
Updated 1 path from 237608f168
```
