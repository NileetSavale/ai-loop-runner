import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, capacity, ttl, clock=time.monotonic):
        if capacity < 1 or ttl <= 0:
            raise ValueError("capacity must be at least 1 and ttl above 0")
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self._entries = OrderedDict()

    def _drop_expired(self):
        now = self.clock()
        for key in [k for k, (_, written) in self._entries.items() if now - written >= self.ttl]:
            del self._entries[key]

    def get(self, key, default=None):
        self._drop_expired()
        if key not in self._entries:
            return default
        self._entries.move_to_end(key)
        return self._entries[key][0]

    def put(self, key, value):
        self._drop_expired()
        if key not in self._entries and len(self._entries) >= self.capacity:
            self._entries.popitem(last=False)
        self._entries[key] = (value, self.clock())
        self._entries.move_to_end(key)

    def __len__(self):
        self._drop_expired()
        return len(self._entries)
