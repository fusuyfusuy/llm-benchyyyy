# jsonpatch-rfc6902-hardened

**dimension(s):** raw model, coding harness, tool-use/agentic (spec-driven
implementation against hostile edge cases)
**difficulty tier:** hard

## Instruction

`jsonpatch.py` is our in-house JSON Patch (RFC 6902) applier. It was written quickly
and customers keep hitting corruption bugs. Make it correct.

Required semantics (RFC 6902 unless stated):

- `apply_patch(document, patch)` applies the list of operations **atomically** and
  returns a **new** document; the input `document` must be left completely untouched,
  including all nested containers (no shared mutable substructure between input and
  output).
- Operations: `add`, `replace`, `remove`, `move`, `copy`, `test`.
- JSON Pointer paths must honor `~1` (decodes to `/`) and `~0` (decodes to `~`)
  escapes in every token. The empty string path refers to the whole document. The
  path `"/"` addresses the member whose key is the empty string.
- Array rules: `add` may use index `len(array)` or the `-` character (append);
  `remove`/`replace` require an existing index; any other out-of-range index is an
  error. `move`/`copy` into arrays follow the same rule, and when source and target
  are the same array, the removal of the source element happens FIRST — destination
  indices are interpreted against the post-removal array.
- `test` compares by JSON value equality, but JSON distinguishes `true` from `1`:
  a test of value `1` against document value `true` must FAIL even though Python's
  `==` says otherwise. (Numeric equality across int/float, e.g. `1` vs `1.0`, IS a
  match.)
- Any failure — unknown op, missing object member, bad index, failed `test`,
  malformed pointer — raises the module's `PatchFailed` exception (not KeyError /
  IndexError / TypeError leaking through). On failure nothing is applied and nothing
  partially-modified escapes the call.

## Environment/setup

Fresh checkout containing:

```python
# jsonpatch.py
"""JSON Patch (RFC 6902) applier. See task spec for required semantics."""

import copy


class PatchFailed(Exception):
    pass


def _tokens(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchFailed(f"bad pointer: {pointer!r}")
    return pointer.split("/")[1:]  # TODO: unescape ~1/~0


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
    parent = _walk(doc, tokens[:-1])
    return parent, tokens[-1]


def _insert(parent, key, value, append_ok):
    if isinstance(parent, dict):
        parent[key] = value
    elif isinstance(parent, list):
        if key == "-":
            parent.append(value)
            return
        try:
            idx = int(key)
        except ValueError:
            raise PatchFailed(f"bad array index {key!r}")
        if idx < 0 or (append_ok is False and idx >= len(parent)) or idx > len(parent):
            raise PatchFailed("index out of range")
        parent.insert(idx, value)
    else:
        raise PatchFailed("target not a container")


def _delete(parent, key):
    if isinstance(parent, dict):
        if key not in parent:
            raise PatchFailed(f"missing member {key!r}")
        del parent[key]
    elif isinstance(parent, list):
        try:
            idx = int(key)
        except ValueError:
            raise PatchFailed(f"bad array index {key!r}")
        if idx < 0 or idx >= len(parent):
            raise PatchFailed("index out of range")
        parent.pop(idx)
    else:
        raise PatchFailed("target not a container")


def apply_patch(document, patch):
    work = copy.deepcopy(document)
    for op in patch:
        kind = op.get("op")
        path = op.get("path", "")
        if kind == "add":
            parent, key = _parent_and_key(work, _tokens(path))
            _insert(parent, key, copy.deepcopy(op["value"]), append_ok=True)
        elif kind == "replace":
            parent, key = _parent_and_key(work, _tokens(path))
            # BUG: replace on a missing member inserts instead of failing
            _delete(parent, key)
            _insert(parent, key, copy.deepcopy(op["value"]), append_ok=True)
        elif kind == "remove":
            parent, key = _parent_and_key(work, _tokens(path))
            _delete(parent, key)
        elif kind == "copy":
            src = _walk(work, _tokens(op["from"]))
            parent, key = _parent_and_key(work, _tokens(path))
            # BUG: shallow aliasing -- nested objects shared with source
            _insert(parent, key, src, append_ok=True)
        elif kind == "move":
            src_tokens = _tokens(op["from"])
            value = _walk(work, src_tokens)
            p, k = _parent_and_key(work, src_tokens)
            _delete(p, k)
            parent, key = _parent_and_key(work, _tokens(path))
            # BUG: destination index resolved BEFORE the delete above shifted
            # same-array indices; also value may alias its old position
            _insert(parent, key, value, append_ok=True)
        elif kind == "test":
            got = _walk(work, _tokens(path))
            # BUG: Python == treats True == 1 -- JSON does not
            if got != op["value"]:
                raise PatchFailed("test failed")
        else:
            raise PatchFailed(f"unknown op {kind!r}")
    return work
```

Tests are ground truth; where inline comments and behavior disagree, behavior wins.

## Constraints

- Public API is exactly `PatchFailed` and `apply_patch`. Do not change signatures.
- Standard library only.
- The input document's nested containers must be structurally independent of the
  output.
