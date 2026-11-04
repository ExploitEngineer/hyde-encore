"""A least-recently-used cache bounded by bytes, not entries.

Word textures range from a few kilobytes to megabytes (big column words at
4K), so a count limit either wastes memory or thrashes; a byte budget holds
what fits.
"""

from __future__ import annotations

from collections import OrderedDict


class ByteLRU:
    def __init__(self, budget: int):
        self.budget = budget
        self.bytes = 0
        self._items: OrderedDict = OrderedDict()

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key):
        hit = self._items.get(key)
        if hit is None:
            return None
        self._items.move_to_end(key)
        return hit[0]

    def put(self, key, value, size: int) -> None:
        old = self._items.pop(key, None)
        if old is not None:
            self.bytes -= old[1]
        self._items[key] = (value, size)
        self.bytes += size
        # evict oldest first; an entry bigger than the budget stays on its own
        while self.bytes > self.budget and len(self._items) > 1:
            _key, (_value, gone) = self._items.popitem(last=False)
            self.bytes -= gone

    def clear(self) -> None:
        self._items.clear()
        self.bytes = 0
