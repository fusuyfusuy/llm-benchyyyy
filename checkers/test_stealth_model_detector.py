#!/usr/bin/env python3
"""Self-check for stealth_models_check.py's non-trivial logic (stealth
detection + filter + offline snapshot fallback). Run directly:
python3 test_stealth_models_check.py
"""
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stealth_model_detector as smc  # type: ignore[import-not-found]  # noqa: E402


def test_is_stealth_model():
    assert smc.is_stealth_model({"id": "stealth/ox-alpha"}) is True
    assert smc.is_stealth_model({"id": "stealth/"}) is True  # degenerate but prefix matches
    assert smc.is_stealth_model({"id": "openai/gpt-5"}) is False
    assert smc.is_stealth_model({"id": "xstealth/foo"}) is False  # must be prefix, not substring
    assert smc.is_stealth_model({"id": ""}) is False
    assert smc.is_stealth_model({}) is False


def test_filter_synthetic_catalog():
    catalog = {
        "data": [
            {"id": "openai/gpt-5", "name": "GPT-5", "pricing": {"prompt": "1.0", "completion": "2.0"}},
            {"id": "stealth/ox-alpha", "name": "Ox Alpha", "created": 1787256295,
             "context_length": 1048576, "pricing": {"prompt": "0", "completion": "0"},
             "architecture": {"modality": "text->text"}},
            {"id": "meta-llama/llama-4", "name": "Llama 4", "pricing": {"prompt": "0", "completion": "0"}},
        ]
    }
    or_map = {m.get("id"): m for m in catalog["data"] if m.get("id")}
    stealth = [r for r in or_map.values() if smc.is_stealth_model(r)]
    assert len(stealth) == 1, f"expected 1 stealth, got {len(stealth)}"
    assert stealth[0]["id"] == "stealth/ox-alpha"


def test_created_date_and_pricing():
    rec = {"id": "stealth/x", "created": 1787256295, "pricing": {"prompt": "0", "completion": "0"}}
    d = smc.created_date(rec)
    assert d == "2026-08-20", f"unexpected date {d}"
    assert smc.created_date({"id": "stealth/x"}) == "\u2014"  # missing created → em dash, no crash


def test_offline_snapshot_fallback(tmp=None):
    with tempfile.TemporaryDirectory() as td:
        raw = pathlib.Path(td) / "raw"
        raw.mkdir(parents=True)
        old = raw / "openrouter_models_20260801.json"
        new = raw / "openrouter_models_20260810.json"
        old.write_text(json.dumps({"data": []}))
        new.write_text(json.dumps({"data": [{"id": "stealth/ox-alpha"}]}))
        # pick_latest_raw must resolve against the dir we point RAW at
        smc.RAW = raw
        snap = smc.pick_latest_raw("openrouter_models")
        assert snap is not None and snap.name == new.name, f"expected newest snapshot, got {snap}"
        j = json.loads(snap.read_text())
        ids = [m["id"] for m in j["data"]]
        assert ids == ["stealth/ox-alpha"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"all {len(tests)} tests passed")
