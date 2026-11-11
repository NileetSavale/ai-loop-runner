# Case 39

## The issue

Nitpick flags Literal annotation values as missing py:class
### Describe the bug

When a value is present in a type annotation as `Literal`, sphinx will treat the value as a `py:class`. With nitpick enabled, values like `Literal[True]` end up failing, because `True` is not a class.

This is a problem for builds which want to use `-n -W` to catch doc errors.

### How to Reproduce

Setup a simple function which uses Literal, then attempt to autodoc it. e.g.
```python
import typing
@typing.overload
def foo(x: "typing.Literal[True]") -> int: ...
@typing.overload
def foo(x: "typing.Literal[False]") -> str: ...
def foo(x: bool):
    """a func"""
    return 1 if x else "foo"
```

I've pushed an example [failing project](https://github.com/sirosen/repro/tree/master/sphinxdoc/literal) to [my repro repo](https://github.com/sirosen/repro). Just run `./doc.sh` with `sphinx-build` available to see the failing build.

### Expected behavior

`Literal[True]` (or whatever literal value) should be present in the type annotation but should not trigger the nitpick warning.

### Your project

https://github.com/sirosen/repro/tree/master/sphinxdoc/literal

### Screenshots

_No response_

### OS

Linux

### Python version

3.8, 3.9

### Sphinx version

4.1.2

### Sphinx extensions

autodoc

### Extra tools

_No response_

### Additional context

_No response_

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/sphinx/domains/python.py b/sphinx/domains/python.py
index 9875a9f4b..f9a4dbd81 100755
--- a/sphinx/domains/python.py
+++ b/sphinx/domains/python.py
@@ -147,7 +147,14 @@ def _parse_annotation(annotation: str, env: BuildEnvironment = None) -> List[Nod
         elif isinstance(node, ast.Subscript):
             result = unparse(node.value)
             result.append(addnodes.desc_sig_punctuation('', '['))
-            result.extend(unparse(node.slice))
+            args = unparse(node.slice)
+            # Literal values (ex. ``True``, ``'foo'``) are not classes; render them as
+            # literals instead of cross-references so that they are not resolved as py:class.
+            if result and isinstance(result[0], nodes.Text) and \
+                    result[0].astext() in ('Literal', 'typing.Literal'):
+                args = [nodes.literal('', '', n) if isinstance(n, nodes.Text) else n
+                        for n in args]
+            result.extend(args)
             result.append(addnodes.desc_sig_punctuation('', ']'))
             return result
         elif isinstance(node, ast.Tuple):
```

## The official fix

```diff
diff --git a/sphinx/domains/python.py b/sphinx/domains/python.py
--- a/sphinx/domains/python.py
+++ b/sphinx/domains/python.py
@@ -123,7 +123,7 @@ def unparse(node: ast.AST) -> List[Node]:
             if node.value is Ellipsis:
                 return [addnodes.desc_sig_punctuation('', "...")]
             else:
-                return [nodes.Text(node.value)]
+                return [nodes.Text(repr(node.value))]
         elif isinstance(node, ast.Expr):
             return unparse(node.value)
         elif isinstance(node, ast.Index):
@@ -149,6 +149,12 @@ def unparse(node: ast.AST) -> List[Node]:
             result.append(addnodes.desc_sig_punctuation('', '['))
             result.extend(unparse(node.slice))
             result.append(addnodes.desc_sig_punctuation('', ']'))
+
+            # Wrap the Text nodes inside brackets by literal node if the subscript is a Literal
+            if result[0] in ('Literal', 'typing.Literal'):
+                for i, subnode in enumerate(result[1:], start=1):
+                    if isinstance(subnode, nodes.Text):
+                        result[i] = nodes.literal('', '', subnode)
             return result
         elif isinstance(node, ast.Tuple):
             if node.elts:
@@ -179,7 +185,9 @@ def unparse(node: ast.AST) -> List[Node]:
         tree = ast_parse(annotation)
         result = unparse(tree)
         for i, node in enumerate(result):
-            if isinstance(node, nodes.Text) and node.strip():
+            if isinstance(node, nodes.literal):
+                result[i] = node[0]
+            elif isinstance(node, nodes.Text) and node.strip():
                 result[i] = type_to_xref(str(node), env)
         return result
     except SyntaxError:
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/test_domain_py.py b/tests/test_domain_py.py
--- a/tests/test_domain_py.py
+++ b/tests/test_domain_py.py
@@ -342,6 +342,27 @@ def test_parse_annotation(app):
     assert_node(doctree[0], pending_xref, refdomain="py", reftype="obj", reftarget="None")
 
 
+@pytest.mark.skipif(sys.version_info < (3, 8), reason='python 3.8+ is required.')
+def test_parse_annotation_Literal(app):
+    doctree = _parse_annotation("Literal[True, False]", app.env)
+    assert_node(doctree, ([pending_xref, "Literal"],
+                          [desc_sig_punctuation, "["],
+                          "True",
+                          [desc_sig_punctuation, ", "],
+                          "False",
+                          [desc_sig_punctuation, "]"]))
+
+    doctree = _parse_annotation("typing.Literal[0, 1, 'abc']", app.env)
+    assert_node(doctree, ([pending_xref, "typing.Literal"],
+                          [desc_sig_punctuation, "["],
+                          "0",
+                          [desc_sig_punctuation, ", "],
+                          "1",
+                          [desc_sig_punctuation, ", "],
+                          "'abc'",
+                          [desc_sig_punctuation, "]"]))
+
+
 def test_pyfunction_signature(app):
     text = ".. py:function:: hello(name: str) -> str"
     doctree = restructuredtext.parse(app, text)
```

## Hidden tests the cheap fix failed

- `tests/test_domain_py.py::test_parse_annotation_Literal`

## Test output for those tests (excerpt)

```
[31mFAILED[0m tests/test_domain_py.py::[1mtest_parse_annotation_Literal[0m - AssertionError: The node '[2]' is not 'True': <literal: <#text: 'True'>>
```
