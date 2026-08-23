# long-horizon-context-puzzle

**dimension(s):** raw model
**difficulty tier:** hard

## Instruction

We need a function `merge_configs(base: dict, override: dict) -> dict` in `config_merger.py` that recursively merges two JSON-like dictionaries.

Please carefully read the following internal specification, which was written by various stakeholders and contains scattered rules. You must implement the merge logic to exactly satisfy all constraints mentioned in the spec.

### Specification Document: Config Merging

**Introduction**
Our microservices rely on a hierarchical configuration system. We take a `base` dictionary and merge it with an `override` dictionary. Usually, the `override` simply replaces values in the `base`.

**Deep Merging**
If both dictionaries contain a dictionary at the same key, you must recurse and merge them deeply. If only one is a dict, the override replaces the base entirely.

**Handling of Nulls**
We decided last week that if an `override` explicitly sets a key to `None`, it should delete that key from the resulting merged configuration if it existed in `base`. If it didn't exist in `base`, it just isn't added.

**List Concatenation**
The data science team needs to append to lists rather than overwriting them. If a key ends with `_append`, and both the base and override have a list for that key, the resulting list should be the base list followed by the override list. If only one is a list, or if the key doesn't end in `_append`, just follow standard replacement rules.

**Internal Keys**
Any key that starts with `__` (two underscores) in the `override` config must be completely ignored. They are used for local debugging and should never be merged into the base.

**Security Constraints**
For compliance with our SOC2 requirements, we must ensure that authorization scopes cannot be accidentally escalated. To prevent this, the key exactly named `"admin_roles"` must NEVER be modified by the override config, regardless of where it appears in the hierarchy. If the override tries to provide `"admin_roles"`, simply ignore that key from the override and keep the base value (or keep it missing if it wasn't in the base).

Write the `merge_configs` function using only the standard library.

## Environment/setup

Fresh checkout containing:

```python
# config_merger.py

def merge_configs(base: dict, override: dict) -> dict:
    """Merge override into base according to the specification."""
    pass
```

## Constraints

- Standard library only.
- Must not modify the input dictionaries in-place (return a new dictionary or deepcopy).
