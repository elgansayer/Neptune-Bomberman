#!/usr/bin/env python3
"""Static SH-2 call-site scanner: every call to a target address and the constant value of an
argument register at that call.

Calls found: `bsr`/`bra` whose displacement reaches the target, and `jsr @Rm`/`jmp @Rm` (tail
call) where Rm was last loaded by `mov.l @(disp,PC),Rm` from a literal holding the target. The
argument value is the last straight-line write to the register before the call, delay slot
first, never across an earlier call. It counts when that write is a constant (`mov #imm`,
`mov.w`/`mov.l @(disp,PC)`), a copy `mov Rk,Rn` of a callee-saved Rk (r8-r14) whose last write
is a constant, or a reload `mov.l @r15,Rn` of a constant spilled to the same stack slot with r15
unchanged in between. Anything else is reported as dynamic with the instruction word. The scan
is static: a branch target between the write and the call would make a reported constant
path-dependent.

  python3 tools/saturn_lab/sh2_call_args.py --binary code.bin --base 0x06004000 \\
      --target 0x06004100 [--target ...] [--reg 4] [--reg 5]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

WINDOW = 64  # instructions searched back from a call for the argument write


def writes(w: int, n: int) -> bool:
    """True when instruction word w writes general register n (the forms that matter here)."""
    top, rn, rm = w >> 12, (w >> 8) & 15, (w >> 4) & 15
    low = w & 0xF
    if rm == n and ((top == 0x6 and low in (4, 5, 6)) or (top in (0x0, 0x4) and low == 0xF)):
        return True  # post-increment source register
    if rn != n:
        return False
    if top in (0x3, 0x5, 0x6, 0x7, 0x9, 0xD, 0xE):
        return True
    if top == 0x2:
        return low in (4, 5, 6, 9, 0xA, 0xB, 0xD, 0xE, 0xF)
    if top == 0x0:
        return low in (2, 9, 0xA, 0xC, 0xD, 0xE)
    if top == 0x4:
        return (w & 0xFF) in (0x00, 0x01, 0x04, 0x05, 0x08, 0x09, 0x10, 0x11, 0x15, 0x18, 0x19, 0x20,
                              0x21, 0x24, 0x25, 0x28, 0x29, 0x02, 0x12, 0x22, 0x06, 0x16, 0x26, 0x0A,
                              0x1A, 0x2A, 0x03, 0x13, 0x23, 0x07, 0x17, 0x27, 0x0E, 0x1E, 0x2E)
    return False


def is_call(w: int) -> bool:
    return w >> 12 == 0xB or (w & 0xF0FF) in (0x400B, 0x0003)


def words_of(code: bytes) -> list[int]:
    return list(struct.unpack(f">{len(code) // 2}H", code[: len(code) // 2 * 2]))


def _literal32(code: bytes, base: int, pc: int, w: int) -> int | None:
    a = (pc & ~3) + 4 + (w & 0xFF) * 4
    return struct.unpack_from(">i", code, a - base)[0] if 0 <= a - base <= len(code) - 4 else None


def register_value(code: bytes, words: list[int], i: int, base: int, reg: int = 4,
                   delay: bool = True) -> dict[str, Any]:
    """Value of `reg` at the instruction at index i (a call: its delay slot counts first)."""
    r = f"r{reg}"
    order = ([i + 1] if delay and i + 1 < len(words) else []) + list(range(i - 1, max(i - WINDOW, -1), -1))
    for j in order:
        w = words[j]
        if j < i and is_call(w):
            return {"value": None, "how": f"{r} not written after the previous call", "at": base + 2 * j}
        if not writes(w, reg):
            continue
        pc = base + 2 * j
        if w >> 12 == 0xE:
            v = w & 0xFF
            return {"value": v - 256 if v & 0x80 else v, "how": f"mov #imm,{r}", "at": pc}
        if w >> 12 == 0x9:
            a = pc + 4 + (w & 0xFF) * 2
            if 0 <= a - base <= len(code) - 2:
                return {"value": struct.unpack_from(">h", code, a - base)[0], "how": f"mov.w @(disp,PC),{r}", "at": pc}
        if w >> 12 == 0xD:
            v = _literal32(code, base, pc, w)
            if v is not None:
                return {"value": v, "how": f"mov.l @(disp,PC),{r}", "at": pc}
        if w == 0x60F2 | reg << 8:  # mov.l @r15,Rn: a spilled value, r15 unchanged since the store
            for q in range(j - 1, max(j - 2 * WINDOW, -1), -1):
                wq = words[q]
                if wq & 0xFF0F == 0x2F02:  # mov.l Rx,@r15
                    v = register_value(code, words, q, base, (wq >> 4) & 15, delay=False)
                    if isinstance(v.get("value"), int):
                        return {**v, "how": f"mov.l @r15,{r} (spilled {v['how']})"}
                    break
                if writes(wq, 15):
                    break
        if w & 0xF00F == 0x6003 and (w >> 8) & 15 == reg and 8 <= (w >> 4) & 15 <= 14:
            m = (w >> 4) & 15  # mov Rk,Rn with a callee-saved Rk: its write may precede earlier calls
            for q in range(j - 1, max(j - 2 * WINDOW, -1), -1):
                wq = words[q]
                if not writes(wq, m):
                    continue
                qpc = base + 2 * q
                if wq >> 12 == 0xD:
                    v = _literal32(code, base, qpc, wq)
                    if v is not None:
                        return {"value": v, "how": f"mov r{m},{r}; r{m} = mov.l @(disp,PC)", "at": qpc}
                if wq >> 12 == 0xE:
                    v = wq & 0xFF
                    return {"value": v - 256 if v & 0x80 else v, "how": f"mov r{m},{r}; r{m} = mov #imm", "at": qpc}
                break
        return {"value": None, "how": f"dynamic (word 0x{w:04x})", "at": pc}
    return {"value": None, "how": f"no {r} write within {WINDOW} instructions"}


def call_sites(code: bytes, base: int, target: int, regs: tuple[int, ...] = (4,)) -> list[dict[str, Any]]:
    words = words_of(code)
    sites = []
    for i, w in enumerate(words):
        pc = base + 2 * i
        kind = None
        if w >> 12 in (0xA, 0xB):
            d = w & 0xFFF
            d = d - 0x1000 if d & 0x800 else d
            if pc + 4 + 2 * d == target:
                kind = "bsr" if w >> 12 == 0xB else "bra (tail call)"
        elif (w & 0xF0FF) in (0x400B, 0x402B):
            m = (w >> 8) & 15
            for j in range(i - 1, max(i - 64, -1), -1):
                wj = words[j]
                if wj >> 12 == 0xD and (wj >> 8) & 15 == m:
                    v = _literal32(code, base, base + 2 * j, wj)
                    if v is not None and v & 0xFFFFFFFF == target:
                        kind = "jsr" if (w & 0xF0FF) == 0x400B else "jmp (tail call)"
                    break
                if writes(wj, m):
                    break
        if kind:
            sites.append({"site": pc, "kind": kind,
                          "args": {f"r{n}": register_value(code, words, i, base, n) for n in regs}})
    return sites


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--base", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--target", type=lambda s: int(s, 0), action="append", required=True)
    ap.add_argument("--reg", type=int, action="append", choices=range(4, 8))
    a = ap.parse_args(argv)
    code = a.binary.read_bytes()
    regs = tuple(a.reg or [4])
    out = {f"0x{t:08x}": [{**s, "site": f"0x{s['site']:08x}",
                           "args": {k: {**v, "at": f"0x{v['at']:08x}" if "at" in v else None} for k, v in s["args"].items()}}
                          for s in call_sites(code, a.base, t, regs)] for t in a.target}
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
