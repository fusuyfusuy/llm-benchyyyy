# jsonpatch-rfc6902-hardened — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_jsonpatch.py
import pytest
from jsonpatch import apply_patch, PatchFailed

def test_pointer_unescaping():
    doc = {"a/b": 1, "c~d": 2}
    out = apply_patch(doc, [
        {"op": "replace", "path": "/a~1b", "value": 10},
        {"op": "replace", "path": "/c~0d", "value": 20},
    ])
    assert out == {"a/b": 10, "c~d": 20}
    assert doc == {"a/b": 1, "c~d": 2}

def test_empty_string_pointer_replaces_whole_doc():
    doc = {"x": 1}
    out = apply_patch(doc, [{"op": "add", "path": "", "value": [1, 2]}])
    assert out == [1, 2]

def test_slash_path_is_empty_key():
    doc = {"": "v"}
    out = apply_patch(doc, [{"op": "test", "path": "/", "value": "v"}])
    assert out == {"": "v"}
    with pytest.raises(PatchFailed):
        apply_patch(doc, [{"op": "test", "path": "/", "value": "other"}])

def test_array_add_append_and_index_eq_len():
    doc = {"arr": [1, 2]}
    out = apply_patch(doc, [
        {"op": "add", "path": "/arr/-", "value": 3},
        {"op": "add", "path": "/arr/3", "value": 4},
    ])
    assert out == {"arr": [1, 2, 3, 4]}

def test_add_out_of_bounds_fails_but_len_ok():
    with pytest.raises(PatchFailed):
        apply_patch({"arr": [1]}, [{"op": "add", "path": "/arr/2", "value": 9}])

def test_remove_replace_need_existing():
    for op in ("remove", "replace"):
        with pytest.raises(PatchFailed):
            apply_patch({"arr": [1, 2]}, [{"op": op, "path": "/arr/5"}])
        with pytest.raises(PatchFailed):
            apply_patch({"m": {}}, [{"op": op, "path": "/m/nope", "value": 1}])

def test_replace_missing_member_must_fail_not_insert():
    with pytest.raises(PatchFailed):
        apply_patch({}, [{"op": "replace", "path": "/ghost", "value": 1}])

def test_move_within_array_downward():
    # remove-first semantics: moving /1 to /3 in [0,1,2,3]
    out = apply_patch({"a": [0, 1, 2, 3]},
                      [{"op": "move", "from": "/a/1", "path": "/a/3"}])
    assert out == {"a": [0, 2, 3, 1]}

def test_move_within_array_upward():
    out = apply_patch({"a": [0, 1, 2, 3]},
                      [{"op": "move", "from": "/a/3", "path": "/a/0"}])
    assert out == {"a": [3, 0, 1, 2]}

def test_move_across_containers():
    out = apply_patch({"s": {"k": [1, 2]}, "t": {}},
                      [{"op": "move", "from": "/s/k/0", "path": "/t/first"}])
    assert out == {"s": {"k": [2]}, "t": {"first": 1}}

def test_copy_is_deep_not_aliased():
    src = {"inner": {"list": [1]}}
    out = apply_patch(src, [{"op": "copy", "from": "/inner", "path": "/dup"}])
    assert out["dup"] == {"list": [1]}
    assert out["dup"] is not src["inner"]
    assert out["dup"]["list"] is not src["inner"]["list"]
    # and the returned doc's two subtrees are independent of each other too
    out2 = apply_patch(src, [{"op": "copy", "from": "/inner", "path": "/dup"}])
    out2["dup"]["list"].append(99)
    assert out2["inner"] == {"list": [1]}

def test_input_document_never_mutated_or_shared():
    doc = {"a": {"b": [1, 2]}, "keep": True}
    snapshot = repr(doc)
    out = apply_patch(doc, [
        {"op": "add", "path": "/a/b/-", "value": 3},
        {"op": "copy", "from": "/a", "path": "/copy_of_a"},
    ])
    assert repr(doc) == snapshot
    assert out["a"]["b"] is not doc["a"]["b"]
    assert out["copy_of_a"]["b"] is not doc["a"]["b"]

def test_test_op_bool_vs_int():
    with pytest.raises(PatchFailed):
        apply_patch({"x": True}, [{"op": "test", "path": "/x", "value": 1}])
    with pytest.raises(PatchFailed):
        apply_patch({"x": 1}, [{"op": "test", "path": "/x", "value": True}])
    # numeric equality across int/float IS a match
    out = apply_patch({"x": 1}, [{"op": "test", "path": "/x", "value": 1.0}])
    assert out == {"x": 1}

def test_atomicity_no_partial_application():
    doc = {"a": 1, "b": 2}
    snapshot = repr(doc)
    patch = [
        {"op": "replace", "path": "/a", "value": 100},
        {"op": "remove", "path": "/does_not_exist"},
        {"op": "replace", "path": "/b", "value": 200},
    ]
    with pytest.raises(PatchFailed):
        apply_patch(doc, patch)
    assert repr(doc) == snapshot

def test_unknown_op_and_bad_pointers_raise_patchfailed():
    with pytest.raises(PatchFailed):
        apply_patch({}, [{"op": "frobnicate", "path": "/x"}])
    with pytest.raises(PatchFailed):
        apply_patch({}, [{"op": "add", "path": "no-slash", "value": 1}])
    with pytest.raises(PatchFailed):
        apply_patch({"x": 5}, [{"op": "add", "path": "/x/too/deep", "value": 1}])

def test_rfc6902_appendix_examples():
    doc = {"foo": "bar", "child": {"grandchild": {}}}
    out = apply_patch(doc, [
        {"op": "add", "path": "/baz", "value": "qux"},
        {"op": "remove", "path": "/child/grandchild"},
        {"op": "move", "from": "/foo", "path": "/bar"},
        {"op": "copy", "from": "/bar", "path": "/qux-copy"},
        {"op": "test", "path": "/bar", "value": "bar"},
    ])
    assert out == {"baz": "qux", "bar": "bar", "qux-copy": "bar", "child": {}}
```

## Pass criteria

All sixteen tests pass. Binary pass/fail.

## Check

```bash
pytest -q test_jsonpatch.py
```

## Oracle solution

```python
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
```

Key details the oracle gets right and the seed gets wrong: `~`-unescaping;
deep-copying `copy`/`move` values; resolving the move destination AFTER deleting the
source (same-array index shift); `_json_equal`'s bool strictness; `replace`
requiring an existing member.

## Notes for scoring

- The bool/int trap catches solutions that just use `==`: Python's `True == 1`.
  Solutions normalizing via `type(a) is bool` checks are fine.
- Move-in-same-array is the most commonly botched op — both direction tests matter.
- Atomicity here falls out of deepcopy-then-mutate; solutions mutating the input in
  place fail `test_input_document_never_mutated_or_shared` immediately.

## Grader Notes

Moved from `tasks/` (contamination hygiene 2026-08-30).

- The structural-independence constraint is graded by held-out tests that check object
  identity of nested substructures between input and output, not just `==`.
