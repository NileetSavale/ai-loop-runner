import pytest
from pagination import paginate


def test_later_and_partial_pages():
    assert paginate([1, 2, 3, 4, 5], 2, 2) == [3, 4]
    assert paginate([1, 2, 3, 4, 5], 3, 2) == [5]


def test_past_the_end_is_empty():
    assert paginate([1, 2], 5, 2) == []


@pytest.mark.parametrize("page", [0, -1])
def test_page_below_one_raises(page):
    with pytest.raises(ValueError):
        paginate([1, 2], page, 2)
