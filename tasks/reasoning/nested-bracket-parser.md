# nested-bracket-parser

**dimension(s):** raw model
**difficulty tier:** hard

## Instruction

Write a Python function `parse_lisp_expr(s: str) -> list` that parses a simplified LISP-like string into a nested Python list.
- An expression is enclosed in parentheses `()`.
- Parentheses act as structural delimiters. Elements may be separated by spaces or delimited directly by adjacent parentheses (e.g. `(a b)` or `((a)b(c))`).
- Elements can be atomic strings (e.g. `foo`, `123`) or nested expressions.
- Empty expressions `()` evaluate to empty lists `[]`.
- The input string will always represent a valid expression at the root.

Example:
`"(a (b c) d)"` -> `['a', ['b', 'c'], 'd']`
`"(first (second third (fourth)))"` -> `['first', ['second', 'third', ['fourth']]]`
`"((a)b(c))"` -> `[['a'], 'b', ['c']]`

## Environment/setup

```python
# parser.py
def parse_lisp_expr(s: str) -> list:
    pass
```

## Constraints
- Standard library only.
- You must correctly handle arbitrary levels of nesting.
