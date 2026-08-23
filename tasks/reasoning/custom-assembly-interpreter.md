# custom-assembly-interpreter

**dimension(s):** raw model
**difficulty tier:** hard

## Instruction

Write a Python function `run_program(code: str) -> int` that simulates a simple custom 8-bit CPU. 
The CPU has 4 registers (`R0`, `R1`, `R2`, `R3`), initially all 0.
The instructions are:
- `MOV Rx, V`: Move integer V (0-255) into register Rx.
- `ADD Rx, Ry`: Add Ry to Rx, store in Rx (modulo 256).
- `SUB Rx, Ry`: Subtract Ry from Rx, store in Rx (modulo 256).
- `JMP L`: Jump to instruction index L (0-indexed).
- `JZ Rx, L`: Jump to L if Rx is 0.
- `HALT`: Stop execution and return the value in R0.

The `code` is a newline-separated string of these instructions. Empty lines should be ignored, but they do NOT count towards the instruction index for JMP/JZ. (The first valid instruction is index 0, the second is 1, etc.)
Infinite loops should raise a `RuntimeError` after 10,000 executed instructions.

## Environment/setup

```python
# interpreter.py

def run_program(code: str) -> int:
    pass
```

## Constraints
- Standard library only.
- Registers must correctly wrap at 256 (0-255). Negative numbers from SUB wrap around (e.g. 0 - 1 = 255).
