import logging

from sanadamaru import Castle, Store

SECRET = "test-secret-0123456789abcdef"
PROBER = "5.6.7.8"


class MemoryStore:
    """A store shared by several Castles, like Redis would be shared by several processes."""

    def __init__(self):
        self.events = []
        self.bans = {}

    def save_event(self, event):
        self.events.append(event)

    def ban(self, ip, until):
        self.bans[ip] = until

    def ban_until(self, ip):
        return self.bans.get(ip)


class BrokenStore:
    def save_event(self, event):
        raise RuntimeError("down")

    def ban(self, ip, until):
        raise RuntimeError("down")

    def ban_until(self, ip):
        raise RuntimeError("down")


def ask(c, path, peer=PROBER, now=1000.0, headers=None):
    return c.check(path=path, headers=headers or {"user-agent": "scanner/1.0"}, peer=peer, now=now)


def test_memory_store_satisfies_the_protocol():
    s: Store = MemoryStore()
    assert s.ban_until("x") is None


def test_every_record_is_saved_with_the_full_address():
    store = MemoryStore()
    c = Castle(secret=SECRET, store=store)
    ask(c, "/.env")
    assert len(store.events) == 1
    assert store.events[0]["ip"] == PROBER and store.events[0]["marker"] == "env"
    assert store.bans == {}   # blocking is off by default


def test_a_block_is_shared_between_processes():
    store = MemoryStore()
    a = Castle(secret=SECRET, store=store, ban=True)
    b = Castle(secret=SECRET, store=store, ban=True)
    ask(a, "/.env")
    assert store.bans[PROBER] == 1000.0 + a.ban_seconds
    assert ask(b, "/", now=1001.0).status == 403   # b never saw the probe, but the store did


def test_shared_blocks_expire():
    store = MemoryStore()
    a = Castle(secret=SECRET, store=store, ban=True, ban_seconds=10)
    b = Castle(secret=SECRET, store=store, ban=True, ban_seconds=10)
    ask(a, "/.env")
    assert ask(b, "/", now=1011.0) is None


def test_store_cannot_block_without_ban_turned_on():
    store = MemoryStore()
    store.bans[PROBER] = 10**12
    c = Castle(secret=SECRET, store=store)
    assert ask(c, "/") is None


def test_store_cannot_block_cloudflare_or_private_addresses():
    store = MemoryStore()
    c = Castle(secret=SECRET, store=store, ban=True)
    for ip in ("10.0.0.5", "104.16.0.1", "127.0.0.1"):
        store.bans[ip] = 10**12
        assert ask(c, "/", peer=ip) is None


def test_store_cannot_block_for_longer_than_ban_seconds():
    store = MemoryStore()
    store.bans[PROBER] = 10**12
    c = Castle(secret=SECRET, store=store, ban=True, ban_seconds=60)
    assert ask(c, "/").status == 403
    store.bans.clear()
    assert ask(c, "/", now=1061.0) is None


def test_store_cannot_block_never_block_paths():
    store = MemoryStore()
    store.bans[PROBER] = 10**12
    c = Castle(secret=SECRET, store=store, ban=True)
    assert ask(c, "/health") is None


def test_odd_values_from_the_store_do_not_block():
    store = MemoryStore()
    c = Castle(secret=SECRET, store=store, ban=True)
    for value in ("9999999999", True, None, [1]):
        store.bans[PROBER] = value
        assert ask(c, "/") is None


def test_a_broken_store_never_stops_the_defense_and_never_blocks(caplog):
    c = Castle(secret=SECRET, store=BrokenStore(), ban=True)
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        assert ask(c, "/", peer="9.9.9.9") is None
        assert ask(c, "/.env").status == 200
        assert ask(c, "/", now=1001.0).status == 403   # the block still works from memory
    assert c.report()["total"]["door"] == 1
    assert caplog.text.count("the store failed") == 1   # at most one warning a minute
