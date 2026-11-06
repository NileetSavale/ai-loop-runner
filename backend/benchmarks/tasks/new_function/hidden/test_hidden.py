import pytest
from text_utils import slugify


@pytest.mark.parametrize("text,expected", [
    ("  Spaces   everywhere  ", "spaces-everywhere"),
    ("C'est déjà l'été", "c-est-deja-l-ete"),
    ("a--b__c!!d", "a-b-c-d"),
    ("Version 2.0", "version-2-0"),
    ("!!!", ""),
    ("", ""),
])
def test_slugify(text, expected):
    assert slugify(text) == expected
