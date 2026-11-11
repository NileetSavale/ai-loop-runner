# Case 44

## The issue

After #26052 runserver returns response body for HTTP HEAD requests
Description
	
For compliance with RFC 2616, section 4.3, response bodies must not be returned for HEAD requests.
In #26052, the stripping of the response bodies was removed from Django in favour of letting the server perform the body removal, since the common servers (gunicorn, mod_wsgi etc) already do so.
However it appears that runserver does not strip the body, contrary to:
https://code.djangoproject.com/timeline?from=2016-04-23T20%3A26%3A34-05%3A00&precision=second
As such, starting in Django 1.10 the responses from runserver for HEAD requests are no longer compliant with the spec. (In certain configurations this also results in "Broken pipe" error messages in runserver output, since compliant user agents expect to be able to terminate the connection after the headers are sent.)
STR:
1) mkvirtualenv django-test
2) pip install 'Django>1.10,<1.11'
3) django-admin startproject django-test
4) cd django-test
5) ./manage.py runserver
6) In another terminal, run curl -iX HEAD http://127.0.0.1:8000/
7) Observe response from curl
Expected:
HTTP/1.0 200 OK
Date: Fri, 07 Apr 2017 14:56:39 GMT
Server: WSGIServer/0.2 CPython/3.4.5
Content-Type: text/html
X-Frame-Options: SAMEORIGIN
Actual:
HTTP/1.0 200 OK
Date: Fri, 07 Apr 2017 14:56:39 GMT
Server: WSGIServer/0.2 CPython/3.4.5
Content-Type: text/html
X-Frame-Options: SAMEORIGIN
<!DOCTYPE html>
<html lang="en"><head>
 <meta http-equiv="content-type" content="text/html; charset=utf-8">
 <meta name="robots" content="NONE,NOARCHIVE"><title>Welcome to Django</title>
...
Tested with Python 2.7.13 and 3.4.5.
Doesn't reproduce under Django 1.9.13.

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/core/servers/basehttp.py b/django/core/servers/basehttp.py
index fef5532e58..6be24f8a93 100755
--- a/django/core/servers/basehttp.py
+++ b/django/core/servers/basehttp.py
@@ -143,6 +143,13 @@ class ServerHandler(simple_server.ServerHandler):
         if self.headers.get("Connection") == "close":
             self.request_handler.close_connection = True
 
+    def write(self, data):
+        # RFC 2616, section 4.3: the response to a HEAD request must not
+        # include a message body. Headers are still sent by the parent class.
+        if self.environ.get("REQUEST_METHOD") == "HEAD":
+            data = b""
+        super().write(data)
+
     def close(self):
         self.get_stdin().read()
         super().close()
```

## The official fix

```diff
diff --git a/django/core/servers/basehttp.py b/django/core/servers/basehttp.py
--- a/django/core/servers/basehttp.py
+++ b/django/core/servers/basehttp.py
@@ -11,6 +11,7 @@
 import socket
 import socketserver
 import sys
+from collections import deque
 from wsgiref import simple_server
 
 from django.core.exceptions import ImproperlyConfigured
@@ -130,10 +131,18 @@ def __init__(self, stdin, stdout, stderr, environ, **kwargs):
 
     def cleanup_headers(self):
         super().cleanup_headers()
+        if (
+            self.environ["REQUEST_METHOD"] == "HEAD"
+            and "Content-Length" in self.headers
+        ):
+            del self.headers["Content-Length"]
         # HTTP/1.1 requires support for persistent connections. Send 'close' if
         # the content length is unknown to prevent clients from reusing the
         # connection.
-        if "Content-Length" not in self.headers:
+        if (
+            self.environ["REQUEST_METHOD"] != "HEAD"
+            and "Content-Length" not in self.headers
+        ):
             self.headers["Connection"] = "close"
         # Persistent connections require threading server.
         elif not isinstance(self.request_handler.server, socketserver.ThreadingMixIn):
@@ -147,6 +156,22 @@ def close(self):
         self.get_stdin().read()
         super().close()
 
+    def finish_response(self):
+        if self.environ["REQUEST_METHOD"] == "HEAD":
+            try:
+                deque(self.result, maxlen=0)  # Consume iterator.
+                # Don't call self.finish_content() as, if the headers have not
+                # been sent and Content-Length isn't set, it'll default to "0"
+                # which will prevent omission of the Content-Length header with
+                # HEAD requests as permitted by RFC 9110 Section 9.3.2.
+                # Instead, send the headers, if not sent yet.
+                if not self.headers_sent:
+                    self.send_headers()
+            finally:
+                self.close()
+        else:
+            super().finish_response()
+
 
 class WSGIRequestHandler(simple_server.WSGIRequestHandler):
     protocol_version = "HTTP/1.1"
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/servers/test_basehttp.py b/tests/servers/test_basehttp.py
--- a/tests/servers/test_basehttp.py
+++ b/tests/servers/test_basehttp.py
@@ -1,4 +1,5 @@
 from io import BytesIO
+from socketserver import ThreadingMixIn
 
 from django.core.handlers.wsgi import WSGIRequest
 from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer
@@ -7,7 +8,7 @@
 from django.test.utils import captured_stderr
 
 
-class Stub:
+class Stub(ThreadingMixIn):
     def __init__(self, **kwargs):
         self.__dict__.update(kwargs)
 
@@ -15,6 +16,13 @@ def sendall(self, data):
         self.makefile("wb").write(data)
 
 
+class UnclosableBytesIO(BytesIO):
+    def close(self):
+        # WSGIRequestHandler closes the output file; we need to make this a
+        # no-op so we can still read its contents.
+        pass
+
+
 class WSGIRequestHandlerTestCase(SimpleTestCase):
     request_factory = RequestFactory()
 
@@ -79,12 +87,6 @@ def test_app(environ, start_response):
         rfile.write(b"Other_Header: bad\r\n")
         rfile.seek(0)
 
-        # WSGIRequestHandler closes the output file; we need to make this a
-        # no-op so we can still read its contents.
-        class UnclosableBytesIO(BytesIO):
-            def close(self):
-                pass
-
         wfile = UnclosableBytesIO()
 
         def makefile(mode, *a, **kw):
@@ -106,6 +108,59 @@ def makefile(mode, *a, **kw):
 
         self.assertEqual(body, b"HTTP_SOME_HEADER:good")
 
+    def test_no_body_returned_for_head_requests(self):
+        hello_world_body = b"<!DOCTYPE html><html><body>Hello World</body></html>"
+        content_length = len(hello_world_body)
+
+        def test_app(environ, start_response):
+            """A WSGI app that returns a hello world."""
+            start_response("200 OK", [])
+            return [hello_world_body]
+
+        rfile = BytesIO(b"GET / HTTP/1.0\r\n")
+        rfile.seek(0)
+
+        wfile = UnclosableBytesIO()
+
+        def makefile(mode, *a, **kw):
+            if mode == "rb":
+                return rfile
+            elif mode == "wb":
+                return wfile
+
+        request = Stub(makefile=makefile)
+        server = Stub(base_environ={}, get_app=lambda: test_app)
+
+        # Prevent logging from appearing in test output.
+        with self.assertLogs("django.server", "INFO"):
+            # Instantiating a handler runs the request as side effect.
+            WSGIRequestHandler(request, "192.168.0.2", server)
+
+        wfile.seek(0)
+        lines = list(wfile.readlines())
+        body = lines[-1]
+        # The body is returned in a GET response.
+        self.assertEqual(body, hello_world_body)
+        self.assertIn(f"Content-Length: {content_length}\r\n".encode(), lines)
+        self.assertNotIn(b"Connection: close\r\n", lines)
+
+        rfile = BytesIO(b"HEAD / HTTP/1.0\r\n")
+        rfile.seek(0)
+        wfile = UnclosableBytesIO()
+
+        with self.assertLogs("django.server", "INFO"):
+            WSGIRequestHandler(request, "192.168.0.2", server)
+
+        wfile.seek(0)
+        lines = list(wfile.readlines())
+        body = lines[-1]
+        # The body is not returned in a HEAD response.
+        self.assertEqual(body, b"\r\n")
+        self.assertIs(
+            any([line.startswith(b"Content-Length:") for line in lines]), False
+        )
+        self.assertNotIn(b"Connection: close\r\n", lines)
+
 
 class WSGIServerTestCase(SimpleTestCase):
     request_factory = RequestFactory()
```

## Hidden tests the cheap fix failed

- `test_no_body_returned_for_head_requests (servers.test_basehttp.WSGIRequestHandlerTestCase.test_no_body_returned_for_head_requests)`

## Test output for those tests (excerpt)

```
test_no_body_returned_for_head_requests (servers.test_basehttp.WSGIRequestHandlerTestCase.test_no_body_returned_for_head_requests) ... FAIL
FAIL: test_no_body_returned_for_head_requests (servers.test_basehttp.WSGIRequestHandlerTestCase.test_no_body_returned_for_head_requests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/servers/test_basehttp.py", line 159, in test_no_body_returned_for_head_requests
    self.assertIs(
AssertionError: True is not False

----------------------------------------------------------------------
Ran 5 tests in 0.010s

FAILED (failures=1)
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
>>>>> Test Exit Code: 1
+ git checkout 246eb4836a6fb967880f838aa0d22ecfdca8b6f1 tests/servers/test_basehttp.py
Updated 1 path from 3618293443
```
