# wal-torn-write-recovery — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_wal.py
import json, os, struct, zlib
import pytest
from kvstore import KVStore, recover

def rec(seq, op, key, value=None):
    obj = {"seq": seq, "op": op, "key": key}
    if op == "set":
        obj["value"] = value
    payload = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    return struct.pack("<I", len(payload)) + payload + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)

def build(*records):
    return b"".join(records)

def write_raw(path, buf):
    with open(path, "wb") as f:
        f.write(buf)

R1 = rec(1, "set", "a", {"n": 1})
R2 = rec(2, "set", "b", [1, 2, 3])
R3 = rec(3, "del", "a")
R4 = rec(4, "set", "c", "three")
LOG4 = build(R1, R2, R3, R4)
STATE4 = {"b": [1, 2, 3], "c": "three"}

def test_clean_roundtrip(tmp_path):
    p = str(tmp_path / "wal")
    s = KVStore(p)
    s.set("x", 42); s.set("y", "z"); s.delete("x")
    assert s.get("x") is None and s.get("y") == "z"
    s.close()
    assert recover(p) == {"y": "z"}

def test_torn_tail_sweep_every_cut(tmp_path):
    # Truncate a valid 4-record log at EVERY byte position; the recovered state
    # must always equal the state given by the complete records that survive.
    prefix_states = []
    complete_bounds = []
    off = 0
    for r in (R1, R2, R3, R4):
        off += len(r)
        complete_bounds.append(off)
        d = {}
        for rr in (R1, R2, R3, R4)[:complete_bounds.index(off) + 1]:
            o = json.loads(rr[4:-4])
            if o["op"] == "set": d[o["key"]] = o["value"]
            else: d.pop(o["key"], None)
        prefix_states.append(d)
    p = str(tmp_path / "wal")
    for cut in range(len(LOG4)):
        write_raw(p, LOG4[:cut])
        got = recover(p)
        expected = {}
        for i, bound in enumerate(complete_bounds):
            if cut >= bound:
                expected = prefix_states[i]
        assert got == expected, f"cut={cut}: {got} != {expected}"

def test_middle_checksum_corruption_drops_suffix(tmp_path):
    # Flip one byte inside record 3's payload: records 3 AND 4 are suspect;
    # records 1-2 must survive.
    bad = bytearray(LOG4)
    bad[len(R1) + len(R2) + 10] ^= 0xFF
    p = str(tmp_path / "wal")
    write_raw(p, bytes(bad))
    # record 3 (the del of "a") is corrupt -> dropped, so "a" SURVIVES from
    # record 1; record 4 is behind the corruption -> also gone.
    assert recover(p) == {"a": {"n": 1}, "b": [1, 2, 3]}

def test_recovery_idempotent(tmp_path):
    p = str(tmp_path / "wal")
    write_raw(p, LOG4 + R4[:5])  # torn 5th record
    first = recover(p)
    second = recover(p)
    assert first == second == STATE4

def test_append_after_torn_recovery_survives_reopen(tmp_path):
    # After recovering from a torn tail, new writes must be durable across
    # reopen -- impossible unless the invalid tail was dealt with.
    p = str(tmp_path / "wal")
    write_raw(p, LOG4 + R4[:7])  # torn tail after 4 good records
    s = KVStore(p)
    assert s.get("c") == "three"
    s.set("post", {"ok": True})
    s.close()
    s2 = KVStore(p)
    try:
        assert s2.get("post") == {"ok": True}
        assert s2.get("c") == "three" and s2.get("b") == [1, 2, 3]
    finally:
        s2.close()

def test_seq_continues_above_survivors(tmp_path):
    # The next appended record's seq must exceed every surviving seq.
    p = str(tmp_path / "wal")
    write_raw(p, LOG4 + R4[:7])
    s = KVStore(p)
    s.set("k", 1)
    s.close()
    buf = open(p, "rb").read()
    # decode the LAST record's seq from raw bytes
    off = 0
    last_seq = None
    while off + 4 <= len(buf):
        (length,) = struct.unpack_from("<I", buf, off)
        if off + 4 + length + 4 > len(buf):
            break
        payload = buf[off + 4 : off + 4 + length]
        (crc,) = struct.unpack_from("<I", buf, off + 4 + length)
        if zlib.crc32(payload) & 0xFFFFFFFF != crc:
            break
        last_seq = json.loads(payload)["seq"]
        off += 4 + length + 4
    assert last_seq is not None and last_seq > 4

def test_complete_record_bytes_untouched(tmp_path):
    p = str(tmp_path / "wal")
    write_raw(p, LOG4 + R4[:9])
    before = open(p, "rb").read()[:len(LOG4)]
    recover(p)
    after = open(p, "rb").read()[:len(LOG4)]
    assert before == after

def test_empty_and_header_only(tmp_path):
    p = str(tmp_path / "wal")
    write_raw(p, b"")
    assert recover(p) == {}
    write_raw(p, struct.pack("<I", 50))  # header claims 50 bytes, none follow
    assert recover(p) == {}

def test_format_unchanged(tmp_path):
    src = open("kvstore.py").read()
    assert "<I" in src  # little-endian uint32 packing still present
```

## Pass criteria

All nine tests pass. Binary pass/fail.

## Check

```bash
pytest -q test_wal.py
```

## Oracle solution

Replace `_recover_locked` body (and keep everything else):

```python
    def _recover_locked(self):
        self._f.seek(0)
        buf = self._f.read()
        off = 0
        n = len(buf)
        end = 0  # end of the intact prefix
        while off < n:
            if off + 4 > n:
                break
            (length,) = struct.unpack_from("<I", buf, off)
            if off + 4 + length + 4 > n:
                break
            payload = bytes(buf[off + 4 : off + 4 + length])
            (crc,) = struct.unpack_from("<I", buf, off + 4 + length)
            if zlib.crc32(payload) & 0xFFFFFFFF != crc:
                break
            self._apply(json.loads(payload.decode("utf-8")))
            off += 4 + length + 4
            end = off
        # Drop any invalid tail so future appends start at a clean boundary.
        if end != n:
            self._f.truncate(end)
        self._f.seek(0, os.SEEK_END)
```

Note `self._f.truncate()` on an `"a+b"` handle requires seeking to `end` first on
some platforms; `truncate(size)` with an explicit size argument is portable. The
final seek-to-END matters: after reading, the append position must be re-anchored.

## Notes for scoring

- The seeded BUG(2) comment about sequence numbering is a deliberate red herring:
  `_apply`'s `max()` tracking is already correct once prefix recovery works. Models
  that "fix" seq handling by rewriting record numbering break
  `test_seq_continues_above_survivors` or the format-stability expectations.
- Watch for fixes that skip bad records instead of stopping at them —
  `test_middle_checksum_corruption_drops_suffix` catches exactly that.
- A fix that truncates but forgets to re-anchor the append position can pass every
  test except `test_append_after_torn_recovery_survives_reopen` on some platforms;
  run it at least twice if it looks borderline.
