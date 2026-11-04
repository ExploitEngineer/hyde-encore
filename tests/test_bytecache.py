from encorelib.bytecache import ByteLRU


def test_evicts_least_recently_used_past_the_budget():
    cache = ByteLRU(budget=100)
    cache.put("a", "A", 40)
    cache.put("b", "B", 40)
    assert cache.get("a") == "A"  # a is now the most recent
    cache.put("c", "C", 40)  # 120 > 100: evict b
    assert cache.get("b") is None
    assert cache.get("a") == "A" and cache.get("c") == "C"
    assert cache.bytes == 80


def test_replacing_a_key_updates_the_size():
    cache = ByteLRU(budget=100)
    cache.put("a", "A", 60)
    cache.put("a", "A2", 10)
    assert cache.bytes == 10 and cache.get("a") == "A2"


def test_an_entry_larger_than_the_budget_is_kept_alone():
    cache = ByteLRU(budget=100)
    cache.put("a", "A", 30)
    cache.put("huge", "H", 500)
    assert cache.get("huge") == "H" and cache.get("a") is None
    assert len(cache) == 1


def test_clear_empties_and_resets_the_size():
    cache = ByteLRU(budget=100)
    cache.put("a", "A", 40)
    cache.clear()
    assert len(cache) == 0 and cache.bytes == 0 and cache.get("a") is None
