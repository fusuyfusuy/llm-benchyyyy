#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > kvstore.py
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
PYEOF
chmod +x solutions/coding/wal-torn-write-recovery.sh
