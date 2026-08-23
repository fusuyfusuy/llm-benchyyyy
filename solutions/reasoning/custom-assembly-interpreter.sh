#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > interpreter.py
def run_program(code: str) -> int:
    registers = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}

    lines = [line.strip() for line in code.splitlines() if line.strip()]
    instructions = []
    for line in lines:
        parts = line.replace(",", " ").split()
        if not parts:
            continue
        instructions.append(parts)

    pc = 0
    executed_count = 0
    max_instructions = 10000

    while pc < len(instructions):
        executed_count += 1
        if executed_count > max_instructions:
            raise RuntimeError("Infinite loop detected: exceeded 10,000 instructions")

        parts = instructions[pc]
        op = parts[0]

        if op == "MOV":
            rx = parts[1]
            val = int(parts[2]) % 256
            registers[rx] = val
            pc += 1
        elif op == "ADD":
            rx = parts[1]
            ry = parts[2]
            registers[rx] = (registers[rx] + registers[ry]) % 256
            pc += 1
        elif op == "SUB":
            rx = parts[1]
            ry = parts[2]
            registers[rx] = (registers[rx] - registers[ry]) % 256
            pc += 1
        elif op == "JMP":
            target = int(parts[1])
            pc = target
        elif op == "JZ":
            rx = parts[1]
            target = int(parts[2])
            if registers[rx] == 0:
                pc = target
            else:
                pc += 1
        elif op == "HALT":
            return registers["R0"]
        else:
            raise ValueError(f"Unknown instruction: {op}")

    return registers["R0"]
PYEOF
