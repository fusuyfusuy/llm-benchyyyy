# wal-torn-write-recovery

**dimension(s):** raw model, coding harness, tool-use/agentic (multi-file reasoning
about a binary format + failure modes)
**difficulty tier:** hard

## Instruction

`kvstore.py` implements a persistent key-value store backed by a write-ahead log.
Users report two catastrophic failure modes after crashes:

1. After a crash mid-write, the store refuses to start at all ("corrupt log" error),
   losing every acknowledged write — even the ones fully flushed before the crash.
2. After recovering from one crash, a subsequent crash loses writes that were
   acknowledged *after* the recovery.

Fix `KVStore` so that recovery is crash-consistent:

- A torn or truncated **tail** record must be discarded; every complete record before
  it must still be applied, in order.
- A record whose checksum does not match its payload must be treated as the end of the
  log (everything after it is suspect), not skipped-over.
- Recovery must be idempotent: recovering twice yields the same state.
- After recovery, newly appended records must continue the sequence numbering from
  what survived, and re-opening the store repeatedly must never lose or replay-duplicate
  acknowledged writes.

The on-disk format is documented in `kvstore.py`'s module docstring and MUST NOT change
— external tools read these files byte-for-byte. Public API (`KVStore(path)`, `.get`,
`.set`, `.delete`, `.close`, `recover(path)`) must not change.

## Environment/setup

Fresh checkout containing:

```python
# kvstore.py
"""Persistent KV store over a write-ahead log.

On-disk WAL format (little-endian):
    record := length(4) | payload(length) | crc32(4)
    - length: uint32 LE, byte length of payload
    - payload: UTF-8 JSON object {"seq": int, "op": "set"|"del", "key": str, "value": any}
      ("value" absent for "del")
    - crc32: uint32 LE of the raw payload bytes (zlib.crc32)

A record is "complete" iff length and payload are fully present and crc32 matches.
"""
import json
import os
import struct
import zlib


def _encode_record(seq, op, key, value=None):
    obj = {"seq": seq, "op": op, "key": key}
    if op == "set":
        obj["value"] = value
    payload = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return struct.pack("<I", len(payload)) + payload + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)


class KVStore:
    def __init__(self, path):
        self.path = path
        self._mem = {}
        self._seq = 0
        self._f = open(path, "a+b")
        self._recover_locked()

    def _iter_records(self, buf):
        """Yield (offset, payload_dict) for each complete record; raise on damage."""
        off = 0
        n = len(buf)
        while off < n:
            if off + 4 > n:
                raise IOError("corrupt log: truncated header")
            (length,) = struct.unpack_from("<I", buf, off)
            if off + 4 + length + 4 > n:
                raise IOError("corrupt log: truncated record")
            payload = bytes(buf[off + 4 : off + 4 + length])
            (crc,) = struct.unpack_from("<I", buf, off + 4 + length)
            if zlib.crc32(payload) & 0xFFFFFFFF != crc:
                raise IOError("corrupt log: checksum mismatch")
            yield off, json.loads(payload.decode("utf-8"))
            off += 4 + length + 4

    def _recover_locked(self):
        self._f.seek(0)
        buf = self._f.read()
        # BUG(1): any damage anywhere makes startup raise, losing the whole log,
        # instead of keeping the intact prefix.
        for _off, rec in self._iter_records(buf):
            self._apply(rec)
        # BUG(2): sequence counter restarts from the highest seq seen in THIS scan
        # of the raw file, but acknowledged-but-torn records were already handed to
        # the caller before the crash, so seq must also survive via the data itself;
        # worse, this resets to 0 on an empty-but-existing log after compaction.

    def _apply(self, rec):
        if rec["op"] == "set":
            self._mem[rec["key"]] = rec["value"]
        else:
            self._mem.pop(rec["key"], None)
        self._seq = max(self._seq, rec["seq"])

    def set(self, key, value):
        self._seq += 1
        self._f.write(_encode_record(self._seq, "set", key, value))
        self._f.flush()
        os.fsync(self._f.fileno())
        self._mem[key] = value

    def delete(self, key):
        self._seq += 1
        self._f.write(_encode_record(self._seq, "del", key))
        self._f.flush()
        os.fsync(self._f.fileno())
        self._mem.pop(key, None)

    def get(self, key, default=None):
        return self._mem.get(key, default)

    def close(self):
        self._f.close()


def recover(path):
    """Open, recover, and return the store's contents as a dict."""
    s = KVStore(path)
    try:
        return dict(s._mem)
    finally:
        s.close()
```

Tests are ground truth. Where this docstring and old comments disagree with the
required behavior, the required behavior wins.

## Constraints

- On-disk format must not change (held-out tests hand-craft record bytes).
- Public API signatures must not change.
- Standard library only.
- Recovery may truncate an invalid tail, but must never alter any byte belonging
  to a complete record (held-out tests snapshot those bytes).
