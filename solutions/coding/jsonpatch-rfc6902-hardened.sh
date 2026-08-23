#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > jsonpatch.py
import copy


class PatchFailed(Exception):
    pass


def _tokens(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchFailed(f"bad pointer: {pointer!r}")
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer.split("/")[1:]]


def _walk(doc, tokens):
    cur = doc
    for t in tokens:
        if isinstance(cur, dict):
            if t not in cur:
                raise PatchFailed(f"missing member {t!r}")
            cur = cur[t]
        elif isinstance(cur, list):
            try:
                idx = int(t)
            except ValueError:
                raise PatchFailed(f"bad array token {t!r}")
            if idx < 0 or idx >= len(cur):
                raise PatchFailed("index out of range")
            cur = cur[idx]
        else:
            raise PatchFailed("cannot descend into scalar")
    return cur


def _parent_and_key(doc, tokens):
    if not tokens:
        raise PatchFailed("need a parent for this op")
    return _walk(doc, tokens[:-1]), tokens[-1]


def _array_index(key, length, append_ok):
    if key == "-":
        if not append_ok:
            raise PatchFailed("'-' only valid for add/copy/move targets")
        return length
    try:
        idx = int(key)
    except ValueError:
        raise PatchFailed(f"bad array index {key!r}")
    upper = length if append_ok else length - 1
    if idx < 0 or idx > upper:
        raise PatchFailed("index out of range")
    return idx


def _insert(parent, key, value, append_ok):
    if isinstance(parent, dict):
        parent[key] = value
    elif isinstance(parent, list):
        parent.insert(_array_index(key, len(parent), append_ok), value)
    else:
        raise PatchFailed("target not a container")


def _delete(parent, key):
    if isinstance(parent, dict):
        if key not in parent:
            raise PatchFailed(f"missing member {key!r}")
        del parent[key]
    elif isinstance(parent, list):
        parent.pop(_array_index(key, len(parent), append_ok=False))
    else:
        raise PatchFailed("target not a container")


def _json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def apply_patch(document, patch):
    work = copy.deepcopy(document)
    for op in patch:
        kind = op.get("op")
        path = op.get("path", "")
        tokens = _tokens(path)
        if not tokens and kind in ("add", "replace"):
            # root-level add/replace swaps the entire document
            work = copy.deepcopy(op["value"])
            continue
        if kind == "add":
            parent, key = _parent_and_key(work, tokens)
            _insert(parent, key, copy.deepcopy(op["value"]), append_ok=True)
        elif kind == "replace":
            parent, key = _parent_and_key(work, _tokens(path))
            _delete(parent, key)  # must exist; raises otherwise
            _insert(parent, key, copy.deepcopy(op["value"]), append_ok=True)
        elif kind == "remove":
            parent, key = _parent_and_key(work, _tokens(path))
            _delete(parent, key)
        elif kind == "copy":
            value = copy.deepcopy(_walk(work, _tokens(op["from"])))
            parent, key = _parent_and_key(work, _tokens(path))
            _insert(parent, key, value, append_ok=True)
        elif kind == "move":
            src_tokens = _tokens(op["from"])
            value = copy.deepcopy(_walk(work, src_tokens))
            p, k = _parent_and_key(work, src_tokens)
            _delete(p, k)  # removal FIRST ...
            parent, key = _parent_and_key(work, _tokens(path))  # ... then resolve dst
            _insert(parent, key, value, append_ok=True)
        elif kind == "test":
            got = _walk(work, _tokens(path))
            if not _json_equal(got, op["value"]):
                raise PatchFailed("test failed")
        else:
            raise PatchFailed(f"unknown op {kind!r}")
    return work
PYEOF
chmod +x solutions/coding/jsonpatch-rfc6902-hardened.sh
