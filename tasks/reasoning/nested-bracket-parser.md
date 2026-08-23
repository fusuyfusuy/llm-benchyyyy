# nested-bracket-parser

**dimension(s):** raw model
**difficulty tier:** hard

## Instruction

Write a Python function `parse_lisp_expr(s: str) -> list` that parses a simplified LISP-like string into a nested Python list.
- An expression is surrounded by parentheses `()`.
- Elements are separated by spaces.
- Elements can be atomic strings (e.g. `foo`, `123`) or nested expressions.
- The input string will always represent a single valid expression at the root.

Example:
`"(a (b c) d)"` -> `['a', ['b', 'c'], 'd']`
`"(first (second third (fourth)))"` -> `['first', ['second', 'third', ['fourth']]]`

## Environment/setup

```python
# parser.py
def parse_lisp_expr(s: str) -> list:
    pass
```

## Constraints
- Standard library only.
- You must correctly handle arbitrary levels of nesting.
