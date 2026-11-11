# Case 26

## The issue

Provide a way for model formsets to disallow new object creation
Description
	
Model formsets don't provide a way to create an "edit only" view of objects. We see users trying to use extra=0 to accomplish this, but that's not reliable as extra is merely meant for the extra number of forms to display. You can add more forms with Javascript (or just send additional post data).

## The cheap model's fix (passed the repository's own tests)

```diff
diff --git a/django/forms/models.py b/django/forms/models.py
index 7effb202e3..6f97b72503 100755
--- a/django/forms/models.py
+++ b/django/forms/models.py
@@ -568,6 +568,9 @@ class BaseModelFormSet(BaseFormSet):
     A ``FormSet`` for editing a queryset and/or adding new objects to it.
     """
     model = None
+    # When True, the formset only edits existing objects: no extra forms are
+    # built or saved, so no new objects can be created.
+    edit_only = False
 
     # Set of fields that must be unique among forms of this set.
     unique_fields = set()
@@ -584,6 +587,16 @@ class BaseModelFormSet(BaseFormSet):
             return len(self.get_queryset())
         return super().initial_form_count()
 
+    def total_form_count(self):
+        """Return the total number of forms in this FormSet."""
+        if self.edit_only:
+            # Ignore extra forms, including any posted in the data, so that
+            # no new objects can be created.
+            if self.is_bound:
+                return min(self.initial_form_count(), self.absolute_max)
+            return self.initial_form_count()
+        return super().total_form_count()
+
     def _existing_object(self, pk):
         if not hasattr(self, '_object_dict'):
             self._object_dict = {o.pk: o for o in self.get_queryset()}
@@ -813,6 +826,8 @@ class BaseModelFormSet(BaseFormSet):
 
     def save_new_objects(self, commit=True):
         self.new_objects = []
+        if self.edit_only:
+            return self.new_objects
         for form in self.extra_forms:
             if not form.has_changed():
                 continue
@@ -875,7 +890,8 @@ def modelformset_factory(model, form=ModelForm, formfield_callback=None,
                          widgets=None, validate_max=False, localized_fields=None,
                          labels=None, help_texts=None, error_messages=None,
                          min_num=None, validate_min=False, field_classes=None,
-                         absolute_max=None, can_delete_extra=True, renderer=None):
+                         absolute_max=None, can_delete_extra=True, renderer=None,
+                         edit_only=False):
     """Return a FormSet class for the given Django model class."""
     meta = getattr(form, 'Meta', None)
     if (getattr(meta, 'fields', fields) is None and
@@ -896,6 +912,7 @@ def modelformset_factory(model, form=ModelForm, formfield_callback=None,
                               absolute_max=absolute_max, can_delete_extra=can_delete_extra,
                               renderer=renderer)
     FormSet.model = model
+    FormSet.edit_only = edit_only
     return FormSet
```

## The official fix

```diff
diff --git a/django/forms/models.py b/django/forms/models.py
--- a/django/forms/models.py
+++ b/django/forms/models.py
@@ -676,7 +676,10 @@ def save_m2m():
                 for form in self.saved_forms:
                     form.save_m2m()
             self.save_m2m = save_m2m
-        return self.save_existing_objects(commit) + self.save_new_objects(commit)
+        if self.edit_only:
+            return self.save_existing_objects(commit)
+        else:
+            return self.save_existing_objects(commit) + self.save_new_objects(commit)
 
     save.alters_data = True
 
@@ -875,7 +878,8 @@ def modelformset_factory(model, form=ModelForm, formfield_callback=None,
                          widgets=None, validate_max=False, localized_fields=None,
                          labels=None, help_texts=None, error_messages=None,
                          min_num=None, validate_min=False, field_classes=None,
-                         absolute_max=None, can_delete_extra=True, renderer=None):
+                         absolute_max=None, can_delete_extra=True, renderer=None,
+                         edit_only=False):
     """Return a FormSet class for the given Django model class."""
     meta = getattr(form, 'Meta', None)
     if (getattr(meta, 'fields', fields) is None and
@@ -896,6 +900,7 @@ def modelformset_factory(model, form=ModelForm, formfield_callback=None,
                               absolute_max=absolute_max, can_delete_extra=can_delete_extra,
                               renderer=renderer)
     FormSet.model = model
+    FormSet.edit_only = edit_only
     return FormSet
 
 
@@ -1076,7 +1081,8 @@ def inlineformset_factory(parent_model, model, form=ModelForm,
                           widgets=None, validate_max=False, localized_fields=None,
                           labels=None, help_texts=None, error_messages=None,
                           min_num=None, validate_min=False, field_classes=None,
-                          absolute_max=None, can_delete_extra=True, renderer=None):
+                          absolute_max=None, can_delete_extra=True, renderer=None,
+                          edit_only=False):
     """
     Return an ``InlineFormSet`` for the given kwargs.
 
@@ -1109,6 +1115,7 @@ def inlineformset_factory(parent_model, model, form=ModelForm,
         'absolute_max': absolute_max,
         'can_delete_extra': can_delete_extra,
         'renderer': renderer,
+        'edit_only': edit_only,
     }
     FormSet = modelformset_factory(model, **kwargs)
     FormSet.fk = fk
```

## The official tests added or changed for this issue

```diff
diff --git a/tests/model_formsets/tests.py b/tests/model_formsets/tests.py
--- a/tests/model_formsets/tests.py
+++ b/tests/model_formsets/tests.py
@@ -1771,6 +1771,73 @@ def test_initial_form_count_empty_data(self):
         formset = AuthorFormSet({})
         self.assertEqual(formset.initial_form_count(), 0)
 
+    def test_edit_only(self):
+        charles = Author.objects.create(name='Charles Baudelaire')
+        AuthorFormSet = modelformset_factory(Author, fields='__all__', edit_only=True)
+        data = {
+            'form-TOTAL_FORMS': '2',
+            'form-INITIAL_FORMS': '0',
+            'form-MAX_NUM_FORMS': '0',
+            'form-0-name': 'Arthur Rimbaud',
+            'form-1-name': 'Walt Whitman',
+        }
+        formset = AuthorFormSet(data)
+        self.assertIs(formset.is_valid(), True)
+        formset.save()
+        self.assertSequenceEqual(Author.objects.all(), [charles])
+        data = {
+            'form-TOTAL_FORMS': '2',
+            'form-INITIAL_FORMS': '1',
+            'form-MAX_NUM_FORMS': '0',
+            'form-0-id': charles.pk,
+            'form-0-name': 'Arthur Rimbaud',
+            'form-1-name': 'Walt Whitman',
+        }
+        formset = AuthorFormSet(data)
+        self.assertIs(formset.is_valid(), True)
+        formset.save()
+        charles.refresh_from_db()
+        self.assertEqual(charles.name, 'Arthur Rimbaud')
+        self.assertSequenceEqual(Author.objects.all(), [charles])
+
+    def test_edit_only_inlineformset_factory(self):
+        charles = Author.objects.create(name='Charles Baudelaire')
+        book = Book.objects.create(author=charles, title='Les Paradis Artificiels')
+        AuthorFormSet = inlineformset_factory(
+            Author, Book, can_delete=False, fields='__all__', edit_only=True,
+        )
+        data = {
+            'book_set-TOTAL_FORMS': '4',
+            'book_set-INITIAL_FORMS': '1',
+            'book_set-MAX_NUM_FORMS': '0',
+            'book_set-0-id': book.pk,
+            'book_set-0-title': 'Les Fleurs du Mal',
+            'book_set-0-author': charles.pk,
+            'book_set-1-title': 'Flowers of Evil',
+            'book_set-1-author': charles.pk,
+        }
+        formset = AuthorFormSet(data, instance=charles)
+        self.assertIs(formset.is_valid(), True)
+        formset.save()
+        book.refresh_from_db()
+        self.assertEqual(book.title, 'Les Fleurs du Mal')
+        self.assertSequenceEqual(Book.objects.all(), [book])
+
+    def test_edit_only_object_outside_of_queryset(self):
+        charles = Author.objects.create(name='Charles Baudelaire')
+        walt = Author.objects.create(name='Walt Whitman')
+        data = {
+            'form-TOTAL_FORMS': '1',
+            'form-INITIAL_FORMS': '1',
+            'form-0-id': walt.pk,
+            'form-0-name': 'Parth Patil',
+        }
+        AuthorFormSet = modelformset_factory(Author, fields='__all__', edit_only=True)
+        formset = AuthorFormSet(data, queryset=Author.objects.filter(pk=charles.pk))
+        self.assertIs(formset.is_valid(), True)
+        formset.save()
+        self.assertCountEqual(Author.objects.all(), [charles, walt])
+
 
 class TestModelFormsetOverridesTroughFormMeta(TestCase):
     def test_modelformset_factory_widgets(self):
```

## Hidden tests the cheap fix failed

- `test_edit_only_inlineformset_factory (model_formsets.tests.ModelFormsetTest)`

## Test output for those tests (excerpt)

```
test_edit_only_inlineformset_factory (model_formsets.tests.ModelFormsetTest) ... ERROR
ERROR: test_edit_only_inlineformset_factory (model_formsets.tests.ModelFormsetTest)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/model_formsets/tests.py", line 1806, in test_edit_only_inlineformset_factory
    AuthorFormSet = inlineformset_factory(
TypeError: inlineformset_factory() got an unexpected keyword argument 'edit_only'

----------------------------------------------------------------------
Ran 67 tests in 0.903s

FAILED (errors=1)
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
+ SWEBENCH_TEST_EXIT_CODE=1
+ : '>>>>> End Test Output'
+ echo '>>>>> Test Exit Code: 1'
>>>>> Test Exit Code: 1
+ git checkout 0af9a5fc7d765aa05ea784e2c3237675f3bb4b49 tests/model_formsets/tests.py
Updated 1 path from c4c9cffec5
```
