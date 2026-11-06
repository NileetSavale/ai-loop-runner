from pagination import paginate


def test_first_page_starts_at_the_first_item():
    assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]
