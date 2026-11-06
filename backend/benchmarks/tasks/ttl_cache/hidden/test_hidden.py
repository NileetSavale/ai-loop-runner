import pytest
from ttl_cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.mark.parametrize("capacity,ttl", [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_invalid_settings(capacity, ttl):
    with pytest.raises(ValueError):
        TTLCache(capacity, ttl)


def test_expires_exactly_at_ttl(clock):
    cache = TTLCache(2, 10, clock)
    cache.put("a", 1)
    clock.now = 9.999
    assert cache.get("a") == 1
    clock.now = 10
    assert cache.get("a") is None


def test_get_does_not_extend_expiry(clock):
    cache = TTLCache(2, 10, clock)
    cache.put("a", 1)
    clock.now = 9
    cache.get("a")
    clock.now = 10
    assert cache.get("a") is None


def test_put_restarts_expiry(clock):
    cache = TTLCache(2, 10, clock)
    cache.put("a", 1)
    clock.now = 9
    cache.put("a", 2)
    clock.now = 18
    assert cache.get("a") == 2


def test_get_changes_which_entry_is_evicted(clock):
    cache = TTLCache(2, 100, clock)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (1, None, 3)


def test_replacing_a_key_in_a_full_cache_evicts_nothing(clock):
    cache = TTLCache(2, 100, clock)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 3)
    assert (cache.get("a"), cache.get("b")) == (3, 2)


def test_expired_entries_go_before_any_live_entry(clock):
    cache = TTLCache(2, 10, clock)
    cache.put("old", 1)
    clock.now = 5
    cache.put("recent", 2)
    cache.get("old")  # old is now most recently used, but it expires first
    clock.now = 10
    cache.put("new", 3)
    assert (cache.get("recent"), cache.get("new")) == (2, 3)


def test_all_expired_entries_are_dropped_and_len_is_live_only(clock):
    cache = TTLCache(3, 10, clock)
    cache.put("a", 1)
    cache.put("b", 2)
    assert len(cache) == 2
    clock.now = 10
    assert len(cache) == 0
    cache.put("c", 3)
    assert len(cache) == 1
