#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > config_merger.py
import copy

def merge_configs(base: dict, override: dict) -> dict:
    """Merge override into base according to the specification."""
    result = copy.deepcopy(base)
    
    for key, val in override.items():
        # Internal Keys: Any key starting with __ in override config must be ignored
        if isinstance(key, str) and key.startswith("__"):
            continue
        
        # Security Constraints: admin_roles must NEVER be modified by override config
        if key == "admin_roles":
            continue
        
        # Handling of Nulls: if override sets a key to None, delete from merged
        if val is None:
            if key in result:
                del result[key]
            continue
        
        # Deep Merging: if both are dicts, recurse; if override is dict and base isn't, recurse with empty dict
        if isinstance(val, dict):
            if key in result and isinstance(result[key], dict):
                result[key] = merge_configs(result[key], val)
            else:
                result[key] = merge_configs({}, val)
        # List Concatenation: key ends with _append, and both are lists
        elif (
            isinstance(key, str)
            and key.endswith("_append")
            and key in result
            and isinstance(result[key], list)
            and isinstance(val, list)
        ):
            result[key] = copy.deepcopy(result[key]) + copy.deepcopy(val)
        else:
            # Standard replacement
            result[key] = copy.deepcopy(val)
            
    return result
PYEOF
