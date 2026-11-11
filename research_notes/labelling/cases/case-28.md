# Case 28

## The issue

evalf does not call _imp_ recursively
Example from https://stackoverflow.com/questions/41818842/why-cant-i-evaluate-a-composition-of-implemented-functions-in-sympy-at-a-point:

```
>>> from sympy.utilities.lambdify import implemented_function
>>> f = implemented_function('f', lambda x: x ** 2)
>>> g = implemented_function('g', lambda x: 2 * x)
>>> print(f(  2 ).evalf())
4.00000000000000
>>> print(  g(2) .evalf())
4.00000000000000
>>> print(f(g(2)).evalf())
f(g(2))
```

The code for this is in `Function._eval_evalf`. It isn't calling evalf recursively on the return of `_imp_`.

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/sympy/core/function.py b/sympy/core/function.py
index 1b8005e1d..bcf334f20 100755
--- a/sympy/core/function.py
+++ b/sympy/core/function.py
@@ -507,7 +507,8 @@ def _eval_evalf(self, prec):
             func = getattr(mpmath, fname)
         except (AttributeError, KeyError):
             try:
-                return Float(self._imp_(*self.args), prec)
+                res = self._imp_(*self.args)
+                return res.evalf(prec=prec)
             except (AttributeError, TypeError, ValueError):
                 return
 
diff --git a/sympy/core/tests/test_evalf.py b/sympy/core/tests/test_evalf.py
index 1d63f9ea9..5d80f55f6 100755
--- a/sympy/core/tests/test_evalf.py
+++ b/sympy/core/tests/test_evalf.py
@@ -325,7 +325,10 @@ def test_implemented_function_evalf():
     assert str(f(2)) == "f(2)"
     assert f(2).evalf() == 3
     assert f(x).evalf() == f(x)
+    g = implemented_function('g', lambda x: 2 * x)
+    assert f(g(2)).evalf() == 5.0
     del f._imp_     # XXX: due to caching _imp_ would influence all other tests
+    del g._imp_
 
 
 def test_evaluate_false():
```

## The official fix

```diff
diff --git a/sympy/core/function.py b/sympy/core/function.py
--- a/sympy/core/function.py
+++ b/sympy/core/function.py
@@ -507,7 +507,7 @@ def _eval_evalf(self, prec):
             func = getattr(mpmath, fname)
         except (AttributeError, KeyError):
             try:
-                return Float(self._imp_(*self.args), prec)
+                return Float(self._imp_(*[i.evalf(prec) for i in self.args]), prec)
             except (AttributeError, TypeError, ValueError):
                 return
```

## The official tests added or changed for this issue

```diff
diff --git a/sympy/utilities/tests/test_lambdify.py b/sympy/utilities/tests/test_lambdify.py
--- a/sympy/utilities/tests/test_lambdify.py
+++ b/sympy/utilities/tests/test_lambdify.py
@@ -751,6 +751,9 @@ def test_issue_2790():
     assert lambdify((x, (y, (w, z))), w + x + y + z)(1, (2, (3, 4))) == 10
     assert lambdify(x, x + 1, dummify=False)(1) == 2
 
+def test_issue_12092():
+    f = implemented_function('f', lambda x: x**2)
+    assert f(f(2)).evalf() == Float(16)
 
 def test_ITE():
     assert lambdify((x, y, z), ITE(x, y, z))(True, 5, 3) == 5
```

## Hidden tests the cheap fix failed

- `test_issue_12092`

## Test output for those tests (excerpt)

```
___________ sympy/utilities/tests/test_lambdify.py:test_issue_12092 ____________
  File "/testbed/sympy/utilities/tests/test_lambdify.py", line 756, in test_issue_12092
    assert f(f(2)).evalf() == Float(16)
AssertionError

 tests finished: 43 passed, 1 failed, 26 skipped, 1 exceptions, in 1.21 seconds 
DO *NOT* COMMIT!
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
>>>>> Test Exit Code: 1
+ git checkout d7c3045115693e887bcd03599b7ca4650ac5f2cb sympy/utilities/tests/test_lambdify.py
Updated 1 path from 728c7469e
```
