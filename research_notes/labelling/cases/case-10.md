# Case 10

## The issue

Mod function lambdify bug
Description:
When lambdifying any function of structure like `expr * Mod(a, b)` sympy moves the multiplier into the first argument of Mod, like `Mod(expr * a, b)`, WHEN we specify `modules=[]`

This is an example from Sympy online shell
```
>>> from sympy import Mod, lambdify, symbols
>>> x, y = symbols('x y')
>>> expr = -Mod(x, y)
>>> f = lambdify([x, y], expr)
>>> f(3, 7)
-3
>>> inspect.getsource(f)
def _lambdifygenerated(x, y):
    return (-mod(x, y))


>>> g = lambdify([x, y], expr, modules=[])
>>> g(3, 7)
4
>>> inspect.getsource(g)
def _lambdifygenerated(x, y):
    return (-x % y)
```

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/sympy/printing/pycode.py b/sympy/printing/pycode.py
index b669a2c783..2dec481751 100755
--- a/sympy/printing/pycode.py
+++ b/sympy/printing/pycode.py
@@ -6,7 +6,8 @@
 from collections import defaultdict
 from itertools import chain
 from sympy.core import S
-from .precedence import precedence
+from sympy.core.mod import Mod
+from .precedence import precedence, PRECEDENCE
 from .codeprinter import CodePrinter
 
 _kw_py2and3 = {
@@ -232,6 +233,14 @@ def _print_NegativeInfinity(self, expr):
     def _print_ComplexInfinity(self, expr):
         return self._print_NaN(expr)
 
+    def parenthesize(self, item, level, strict=False):
+        # In Python, ``%`` has the same precedence as ``*``, so a Mod must be
+        # bracketed whenever it appears in a multiplicative (or higher) context,
+        # e.g. ``-Mod(x, y)`` must not be printed as ``-x % y``.
+        if isinstance(item, Mod) and level >= PRECEDENCE["Mul"]:
+            return "(%s)" % self._print(item)
+        return super().parenthesize(item, level, strict=strict)
+
     def _print_Mod(self, expr):
         PREC = precedence(expr)
         return ('{} % {}'.format(*map(lambda x: self.parenthesize(x, PREC), expr.args)))
```

## The official fix

```diff
diff --git a/sympy/printing/codeprinter.py b/sympy/printing/codeprinter.py
--- a/sympy/printing/codeprinter.py
+++ b/sympy/printing/codeprinter.py
@@ -9,7 +9,7 @@
 from sympy.core.mul import _keep_coeff
 from sympy.core.symbol import Symbol
 from sympy.printing.str import StrPrinter
-from sympy.printing.precedence import precedence
+from sympy.printing.precedence import precedence, PRECEDENCE
 
 
 class requires:
@@ -487,7 +487,14 @@ def _print_Mul(self, expr):
 
         a = a or [S.One]
 
-        a_str = [self.parenthesize(x, prec) for x in a]
+        if len(a) == 1 and sign == "-":
+            # Unary minus does not have a SymPy class, and hence there's no
+            # precedence weight associated with it, Python's unary minus has
+            # an operator precedence between multiplication and exponentiation,
+            # so we use this to compute a weight.
+            a_str = [self.parenthesize(a[0], 0.5*(PRECEDENCE["Pow"]+PRECEDENCE["Mul"]))]
+        else:
+            a_str = [self.parenthesize(x, prec) for x in a]
         b_str = [self.parenthesize(x, prec) for x in b]
 
         # To parenthesize Pow with exp = -1 and having more than one Symbol
diff --git a/sympy/printing/precedence.py b/sympy/printing/precedence.py
--- a/sympy/printing/precedence.py
+++ b/sympy/printing/precedence.py
@@ -40,6 +40,7 @@
     "MatAdd": PRECEDENCE["Add"],
     "MatPow": PRECEDENCE["Pow"],
     "MatrixSolve": PRECEDENCE["Mul"],
+    "Mod": PRECEDENCE["Mul"],
     "TensAdd": PRECEDENCE["Add"],
     # As soon as `TensMul` is a subclass of `Mul`, remove this:
     "TensMul": PRECEDENCE["Mul"],
```

## The official tests added or changed for this issue

```diff
diff --git a/sympy/codegen/tests/test_rewriting.py b/sympy/codegen/tests/test_rewriting.py
--- a/sympy/codegen/tests/test_rewriting.py
+++ b/sympy/codegen/tests/test_rewriting.py
@@ -266,10 +266,10 @@ def test_create_expand_pow_optimization():
     # gh issue 15335
     assert cc(x**(-4)) == '1.0/(x*x*x*x)'
     assert cc(x**(-5)) == 'pow(x, -5)'
-    assert cc(-x**4) == '-x*x*x*x'
-    assert cc(x**4 - x**2) == '-x*x + x*x*x*x'
+    assert cc(-x**4) == '-(x*x*x*x)'
+    assert cc(x**4 - x**2) == '-(x*x) + x*x*x*x'
     i = Symbol('i', integer=True)
-    assert cc(x**i - x**2) == 'pow(x, i) - x*x'
+    assert cc(x**i - x**2) == 'pow(x, i) - (x*x)'
     # gh issue 20753
     cc2 = lambda x: ccode(optimize(x, [create_expand_pow_optimization(
         4, base_req=lambda b: b.is_Function)]))
diff --git a/sympy/printing/tests/test_pycode.py b/sympy/printing/tests/test_pycode.py
--- a/sympy/printing/tests/test_pycode.py
+++ b/sympy/printing/tests/test_pycode.py
@@ -30,6 +30,8 @@ def test_PythonCodePrinter():
 
     assert prntr.doprint(x**y) == 'x**y'
     assert prntr.doprint(Mod(x, 2)) == 'x % 2'
+    assert prntr.doprint(-Mod(x, y)) == '-(x % y)'
+    assert prntr.doprint(Mod(-x, y)) == '(-x) % y'
     assert prntr.doprint(And(x, y)) == 'x and y'
     assert prntr.doprint(Or(x, y)) == 'x or y'
     assert not prntr.module_imports
diff --git a/sympy/utilities/tests/test_lambdify.py b/sympy/utilities/tests/test_lambdify.py
--- a/sympy/utilities/tests/test_lambdify.py
+++ b/sympy/utilities/tests/test_lambdify.py
@@ -264,7 +264,15 @@ def test_issue_12984():
         warnings.simplefilter("ignore", RuntimeWarning)
         assert str(func_numexpr(-1, 24, 42)) == 'nan'
 
-#================== Test some functions ============================
+
+def test_empty_modules():
+    x, y = symbols('x y')
+    expr = -(x % y)
+
+    no_modules = lambdify([x, y], expr)
+    empty_modules = lambdify([x, y], expr, modules=[])
+    assert no_modules(3, 7) == empty_modules(3, 7)
+    assert no_modules(3, 7) == -3
 
 
 def test_exponentiation():
```

## Hidden tests the cheap fix failed

- `test_create_expand_pow_optimization`
- `test_PythonCodePrinter`
- `test_empty_modules`

## Test output for those tests (excerpt)

```
__________ sympy/printing/tests/test_pycode.py:test_PythonCodePrinter __________
Traceback (most recent call last):
  File "/testbed/sympy/printing/tests/test_pycode.py", line 33, in test_PythonCodePrinter
    assert prntr.doprint(-Mod(x, y)) == '-(x % y)'
AssertionError
________________________________________________________________________________
__________ sympy/utilities/tests/test_lambdify.py:test_empty_modules ___________
Traceback (most recent call last):
  File "/testbed/sympy/utilities/tests/test_lambdify.py", line 275, in test_empty_modules
    assert no_modules(3, 7) == -3
AssertionError

 tests finished: 94 passed, 3 failed, 53 skipped, 1 expected to fail, 
in 8.16 seconds 
DO *NOT* COMMIT!
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
>>>>> Test Exit Code: 1
+ git checkout 3f8c8c2377cb8e0daaf8073e8d03ac7d87580813 sympy/codegen/tests/test_rewriting.py sympy/printing/tests/test_pycode.py sympy/utilities/tests/test_lambdify.py
Updated 3 paths from ff3be61097
```
