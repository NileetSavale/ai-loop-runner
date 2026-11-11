# Case 4

## The issue

sqf and sqf_list output is not consistant
The example below is wrong in the sense that we should have (x*_2 - 5_x + 6, 3) and not 2 factors of multiplicity 3.

```
>  sqf_list(  (x**2 + 1)  * (x - 1)**2 * (x - 2)**3 * (x - 3)**3  )

>  (1, [(x**2 + 1, 1), (x - 1, 2), (x - 3, 3), (x - 2, 3)])
```

whereas below is correct --- one factor of multiplicity 2

```
>  sqf_list( x**5 - 2*x**4 - 2*x**3 + 4*x**2 + x - 2 )

>  (1, [(x - 2, 1), (x**2 - 1, 2)])
```

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/sympy/polys/polytools.py b/sympy/polys/polytools.py
index c9e77a901f..2d0ffc1d11 100755
--- a/sympy/polys/polytools.py
+++ b/sympy/polys/polytools.py
@@ -5874,6 +5874,33 @@ def sqf_part(f, *gens, **args):
         return result
 
 
+def _merge_sqf_factors(factors):
+    """Merge square-free factors that share the same multiplicity.
+
+    Factors with multiplicity ``1`` are left untouched, so that e.g.
+    ``x*(x + y)`` still gives ``[(x, 1), (x + y, 1)]``. For other
+    multiplicities the bases are multiplied together, so that
+    ``(x - 2)**3*(x - 3)**3`` gives ``[(x**2 - 5*x + 6, 3)]``.
+    """
+    groups, merged = {}, []
+
+    for f, k in factors:
+        if k == 1:
+            merged.append((f, k))
+        else:
+            groups.setdefault(k, []).append(f)
+
+    for k, polys in groups.items():
+        poly = polys[0]
+
+        for other in polys[1:]:
+            poly = poly*other
+
+        merged.append((poly, k))
+
+    return merged
+
+
 def _sorted_factors(factors, method):
     """Sort a list of ``(expr, exp)`` pairs. """
     if method == 'sqf':
@@ -5995,6 +6022,10 @@ def _generic_factor_list(expr, gens, args, method):
                     f, _ = _poly_from_expr(f, _opt)
                     factors[i] = (f, k)
 
+        if method == 'sqf':
+            fp = _merge_sqf_factors(fp)
+            fq = _merge_sqf_factors(fq)
+
         fp = _sorted_factors(fp, method)
         fq = _sorted_factors(fq, method)
```

## The official fix

```diff
diff --git a/sympy/polys/polytools.py b/sympy/polys/polytools.py
--- a/sympy/polys/polytools.py
+++ b/sympy/polys/polytools.py
@@ -2,7 +2,8 @@
 
 from __future__ import print_function, division
 
-from functools import wraps
+from functools import wraps, reduce
+from operator import mul
 
 from sympy.core import (
     S, Basic, Expr, I, Integer, Add, Mul, Dummy, Tuple
@@ -5905,10 +5906,7 @@ def _symbolic_factor_list(expr, opt, method):
         if arg.is_Number:
             coeff *= arg
             continue
-        if arg.is_Mul:
-            args.extend(arg.args)
-            continue
-        if arg.is_Pow:
+        elif arg.is_Pow:
             base, exp = arg.args
             if base.is_Number and exp.is_Number:
                 coeff *= arg
@@ -5949,6 +5947,9 @@ def _symbolic_factor_list(expr, opt, method):
                         other.append((f, k))
 
                 factors.append((_factors_product(other), exp))
+    if method == 'sqf':
+        factors = [(reduce(mul, (f for f, _ in factors if _ == k)), k)
+                   for k in set(i for _, i in factors)]
 
     return coeff, factors
```

## The official tests added or changed for this issue

```diff
diff --git a/sympy/polys/tests/test_polytools.py b/sympy/polys/tests/test_polytools.py
--- a/sympy/polys/tests/test_polytools.py
+++ b/sympy/polys/tests/test_polytools.py
@@ -3273,7 +3273,7 @@ def test_to_rational_coeffs():
 def test_factor_terms():
     # issue 7067
     assert factor_list(x*(x + y)) == (1, [(x, 1), (x + y, 1)])
-    assert sqf_list(x*(x + y)) == (1, [(x, 1), (x + y, 1)])
+    assert sqf_list(x*(x + y)) == (1, [(x**2 + x*y, 1)])
 
 
 def test_as_list():
@@ -3333,3 +3333,8 @@ def test_issue_17988():
 def test_issue_18205():
     assert cancel((2 + I)*(3 - I)) == 7 + I
     assert cancel((2 + I)*(2 - I)) == 5
+
+def test_issue_8695():
+    p = (x**2 + 1) * (x - 1)**2 * (x - 2)**3 * (x - 3)**3
+    result = (1, [(x**2 + 1, 1), (x - 1, 2), (x**2 - 5*x + 6, 3)])
+    assert sqf_list(p) == result
```

## Hidden tests the cheap fix failed

- `test_factor_terms`

## Test output for those tests (excerpt)

```
____________ sympy/polys/tests/test_polytools.py:test_factor_terms _____________
Traceback (most recent call last):
  File "/testbed/sympy/polys/tests/test_polytools.py", line 3276, in test_factor_terms
    assert sqf_list(x*(x + y)) == (1, [(x**2 + x*y, 1)])
AssertionError

== tests finished: 148 passed, 1 failed, 1 expected to fail, in 23.64 seconds ==
DO *NOT* COMMIT!
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
+ git checkout 3dff1b98a78f28c953ae2140b69356b8391e399c sympy/polys/tests/test_polytools.py
>>>>> Test Exit Code: 1
Updated 1 path from 98178a19ee
```
