# Case 53

## The issue

glossary duplicate term with a different case
**Describe the bug**
```
Warning, treated as error:
doc/glossary.rst:243:duplicate term description of mysql, other instance in glossary
```

**To Reproduce**
Steps to reproduce the behavior:
[.travis.yml#L168](https://github.com/phpmyadmin/phpmyadmin/blob/f7cc383674b7099190771b1db510c62bfbbf89a7/.travis.yml#L168)
```
$ git clone --depth 1 https://github.com/phpmyadmin/phpmyadmin.git
$ cd doc
$ pip install 'Sphinx'
$ make html
```

**Expected behavior**
MySQL != mysql term right ?

**Your project**
https://github.com/phpmyadmin/phpmyadmin/blame/master/doc/glossary.rst#L234


**Environment info**
- OS: Unix
- Python version: 3.6
- Sphinx version: 3.0.0

**Additional context**
Did occur some hours ago, maybe you just released the version

- https://travis-ci.org/github/williamdes/phpmyadmintest/jobs/671352365#L328

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/sphinx/domains/std.py b/sphinx/domains/std.py
index d820cfe5c..c02b2d907 100755
--- a/sphinx/domains/std.py
+++ b/sphinx/domains/std.py
@@ -305,7 +305,7 @@ def make_glossary_term(env: "BuildEnvironment", textnodes: Iterable[Node], index
         term['ids'].append(node_id)
 
     std = cast(StandardDomain, env.get_domain('std'))
-    std.note_object('term', termtext.lower(), node_id, location=term)
+    std.note_object('term', termtext, node_id, location=term)
 
     # add an index entry too
     indexnode = addnodes.index()
@@ -646,6 +646,20 @@ class StandardDomain(Domain):
     def objects(self) -> Dict[Tuple[str, str], Tuple[str, str]]:
         return self.data.setdefault('objects', {})  # (objtype, name) -> docname, labelid
 
+    def _find_object(self, objtype: str, name: str) -> Optional[Tuple[str, str]]:
+        """Return ``(docname, labelid)`` for an object, or None if not found.
+
+        Glossary terms are matched case-insensitively, after trying an exact match.
+        """
+        if (objtype, name) in self.objects:
+            return self.objects[objtype, name]
+        if objtype == 'term':
+            lname = name.lower()
+            for (otype, oname), info in self.objects.items():
+                if otype == 'term' and oname.lower() == lname:
+                    return info
+        return None
+
     def note_object(self, objtype: str, name: str, labelid: str, location: Any = None
                     ) -> None:
         """Note a generic object for cross reference.
@@ -928,8 +942,9 @@ class StandardDomain(Domain):
                           node: pending_xref, contnode: Element) -> Element:
         objtypes = self.objtypes_for_role(typ) or []
         for objtype in objtypes:
-            if (objtype, target) in self.objects:
-                docname, labelid = self.objects[objtype, target]
+            info = self._find_object(objtype, target)
+            if info:
+                docname, labelid = info
                 break
         else:
             docname, labelid = '', ''
@@ -951,11 +966,9 @@ class StandardDomain(Domain):
                 results.append(('std:' + role, res))
         # all others
         for objtype in self.object_types:
-            key = (objtype, target)
-            if objtype == 'term':
-                key = (objtype, ltarget)
-            if key in self.objects:
-                docname, labelid = self.objects[key]
+            info = self._find_object(objtype, target)
+            if info:
+                docname, labelid = info
                 results.append(('std:' + self.role_for_objtype(objtype),
                                 make_refnode(builder, fromdocname, docname,
                                              labelid, contnode)))
@@ -972,6 +985,10 @@ class StandardDomain(Domain):
             else:
                 yield (option, option, 'cmdoption', info[0], info[1], 1)
         for (type, name), info in self.objects.items():
+            if type == 'term':
+                # glossary terms are matched case-insensitively; keep the
+                # lowercased name in the inventory as before
+                name = name.lower()
             yield (name, name, type, info[0], info[1],
                    self.object_types[type].attrs['searchprio'])
         for name, (docname, labelid, sectionname) in self.labels.items():
```

## The official fix

```diff
diff --git a/sphinx/domains/std.py b/sphinx/domains/std.py
--- a/sphinx/domains/std.py
+++ b/sphinx/domains/std.py
@@ -305,7 +305,7 @@ def make_glossary_term(env: "BuildEnvironment", textnodes: Iterable[Node], index
         term['ids'].append(node_id)
 
     std = cast(StandardDomain, env.get_domain('std'))
-    std.note_object('term', termtext.lower(), node_id, location=term)
+    std.note_object('term', termtext, node_id, location=term)
 
     # add an index entry too
     indexnode = addnodes.index()
@@ -565,7 +565,7 @@ class StandardDomain(Domain):
         # links to tokens in grammar productions
         'token':   TokenXRefRole(),
         # links to terms in glossary
-        'term':    XRefRole(lowercase=True, innernodeclass=nodes.inline,
+        'term':    XRefRole(innernodeclass=nodes.inline,
                             warn_dangling=True),
         # links to headings or arbitrary labels
         'ref':     XRefRole(lowercase=True, innernodeclass=nodes.inline,
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/test_domain_std.py b/tests/test_domain_std.py
--- a/tests/test_domain_std.py
+++ b/tests/test_domain_std.py
@@ -99,7 +99,7 @@ def test_glossary(app):
     text = (".. glossary::\n"
             "\n"
             "   term1\n"
-            "   term2\n"
+            "   TERM2\n"
             "       description\n"
             "\n"
             "   term3 : classifier\n"
@@ -114,7 +114,7 @@ def test_glossary(app):
     assert_node(doctree, (
         [glossary, definition_list, ([definition_list_item, ([term, ("term1",
                                                                      index)],
-                                                             [term, ("term2",
+                                                             [term, ("TERM2",
                                                                      index)],
                                                              definition)],
                                      [definition_list_item, ([term, ("term3",
@@ -127,7 +127,7 @@ def test_glossary(app):
     assert_node(doctree[0][0][0][0][1],
                 entries=[("single", "term1", "term-term1", "main", None)])
     assert_node(doctree[0][0][0][1][1],
-                entries=[("single", "term2", "term-term2", "main", None)])
+                entries=[("single", "TERM2", "term-TERM2", "main", None)])
     assert_node(doctree[0][0][0][2],
                 [definition, nodes.paragraph, "description"])
     assert_node(doctree[0][0][1][0][1],
@@ -143,7 +143,7 @@ def test_glossary(app):
     # index
     objects = list(app.env.get_domain("std").get_objects())
     assert ("term1", "term1", "term", "index", "term-term1", -1) in objects
-    assert ("term2", "term2", "term", "index", "term-term2", -1) in objects
+    assert ("TERM2", "TERM2", "term", "index", "term-TERM2", -1) in objects
     assert ("term3", "term3", "term", "index", "term-term3", -1) in objects
     assert ("term4", "term4", "term", "index", "term-term4", -1) in objects
```

## Hidden tests the cheap fix failed

- `tests/test_domain_std.py::test_glossary`

## Test output for those tests (excerpt)

```
________________________________ test_glossary _________________________________

app = <SphinxTestApp buildername='html'>

    def test_glossary(app):
        text = (".. glossary::\n"
                "\n"
                "   term1\n"
                "   TERM2\n"
                "       description\n"
                "\n"
                "   term3 : classifier\n"
                "       description\n"
                "       description\n"
                "\n"
                "   term4 : class1 : class2\n"
                "       description\n")
    
        # doctree
        doctree = restructuredtext.parse(app, text)
        assert_node(doctree, (
            [glossary, definition_list, ([definition_list_item, ([term, ("term1",
                                                                         index)],
                                                                 [term, ("TERM2",
                                                                         index)],
                                                                 definition)],
                                         [definition_list_item, ([term, ("term3",
                                                                         index)],
                                                                 definition)],
                                         [definition_list_item, ([term, ("term4",
                                                                         index)],
                                                                 definition)])],
        ))
        assert_node(doctree[0][0][0][0][1],
                    entries=[("single", "term1", "term-term1", "main", None)])
        assert_node(doctree[0][0][0][1][1],
                    entries=[("single", "TERM2", "term-TERM2", "main", None)])
        assert_node(doctree[0][0][0][2],
                    [definition, nodes.paragraph, "description"])
        assert_node(doctree[0][0][1][0][1],
FAILED tests/test_domain_std.py::test_glossary - AssertionError: assert ('TER...
```
