#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > parser.py
def parse_lisp_expr(s: str) -> list:
    tokens = s.replace("(", " ( ").replace(")", " ) ").split()
    if not tokens:
        return []

    stack = []
    current = None

    for token in tokens:
        if token == "(":
            new_list = []
            if stack:
                stack[-1].append(new_list)
            stack.append(new_list)
        elif token == ")":
            if stack:
                current = stack.pop()
        else:
            if stack:
                stack[-1].append(token)

    return current if current is not None else []
PYEOF
