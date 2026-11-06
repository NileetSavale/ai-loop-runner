from ttl_cache import TTLCache


def test_stores_and_returns_values():
    cache = TTLCache(2, 10)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing", "fallback") == "fallback"
