#!/usr/bin/env python3
"""Map SH-2 data addresses between two builds of one program by matching functions.

Input: two directories of generated SH-2 disassembly (`seg_*.s`, one instruction per line
as `/* ADDRESS OPCODE */<TAB>mnemonic operands`, literal pools as
`/* ADDRESS */<TAB>.4byte VALUE` under `.Lxxxx:` labels, functions as `func_XXXXXXXX:`).

Each function is reduced to its opcode words with the PC-relative parts masked
(mov.w/mov.l @(disp,PC), mova, bra/bsr, bt/bf[/s] displacements). A function whose masked
opcode run (at least 8 instructions) occurs exactly once in each build is a match; the
literal-pool words its mov.l instructions load are then paired in instruction order
(old value -> new value). Only values inside the address windows (WorkRAM-H
0x06000000-0x060FFFFF, WorkRAM-L 0x00200000-0x002FFFFF) are kept. An address that pairs
with two different values is reported as a conflict and left out.

Usage: sh2_xmap.py OLD_ASM_DIR NEW_ASM_DIR OUT.json [--lookup 0xADDR ...]
--lookup prints the exact mapping, or the nearest mapped addresses with their deltas.
No game data is embedded; tests use synthetic listings.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import glob
import json
import re
from pathlib import Path

INS = re.compile(r"^/\* ([0-9A-F]{8}) ([0-9A-F]{4}) \*/\t(\S+)\s*(.*)$")
POOL = re.compile(r"^/\* ([0-9A-F]{8}) \*/\t\.(4byte|2byte)\s+(\S+)")
LABEL = re.compile(r"^(\.L[0-9A-F]+|func_[0-9A-F]+):")
FUNC = re.compile(r"^func_([0-9A-F]{8}):")


def mask(op: int) -> int:
    hi = op >> 12
    if hi in (0x9, 0xD):            # mov.w/mov.l @(disp,PC),Rn
        return op & 0xFF00
    if hi in (0xA, 0xB):            # bra/bsr
        return op & 0xF000
    if op >> 8 in (0x89, 0x8B, 0x8D, 0x8F, 0xC7):  # bt/bf/bt.s/bf.s, mova
        return op & 0xFF00
    return op


def parse(asm_dir: Path) -> dict:
    funcs = {}
    for f in sorted(glob.glob(str(asm_dir / "seg_*.s"))):
        lines = Path(f).read_text().splitlines()
        labels, cur = {}, None
        # pass 1: label -> pool value
        pending = []
        for ln in lines:
            m = LABEL.match(ln)
            if m:
                pending.append(m.group(1))
                continue
            p = POOL.match(ln)
            if p and pending:
                for lab in pending:
                    labels[lab] = p.group(3)
            pending = []
        for ln in lines:
            m = FUNC.match(ln)
            if m:
                cur = funcs.setdefault(int(m.group(1), 16), {"ops": [], "lits": []})
                continue
            if cur is None:
                continue
            i = INS.match(ln)
            if not i:
                continue
            op = int(i.group(2), 16)
            cur["ops"].append(mask(op))
            if op >> 12 in (0x9, 0xD):
                ref = re.search(r"(\.L[0-9A-F]+|func_[0-9A-F]+)", i.group(4))
                v = labels.get(ref.group(1)) if ref else None
                cur["lits"].append((op >> 12 == 0xD, v))
    return funcs


def val(s: str | None) -> int | None:
    if s is None:
        return None
    if s.startswith("func_"):
        return int(s[5:], 16)
    try:
        return int(s, 0)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("old_dir", type=Path)
    ap.add_argument("new_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lookup", nargs="*", default=[])
    args = ap.parse_args(argv)
    if args.out.exists() and args.lookup:
        doc = json.loads(args.out.read_text())
    else:
        a, b = parse(args.old_dir), parse(args.new_dir)
        ka = collections.defaultdict(list)
        kb = collections.defaultdict(list)
        for addr, fn in a.items():
            ka[tuple(fn["ops"])].append(addr)
        for addr, fn in b.items():
            kb[tuple(fn["ops"])].append(addr)
        matched = {}
        for key, la in ka.items():
            lb = kb.get(key)
            if len(la) == 1 and lb and len(lb) == 1 and len(key) >= 8:
                matched[la[0]] = lb[0]
        pairs = collections.defaultdict(collections.Counter)
        for fa, fb in matched.items():
            pairs[fa][fb] += 1
            for (wa, va), (wb, vb) in zip(a[fa]["lits"], b[fb]["lits"]):
                x, y = val(va), val(vb)
                if not (wa and wb) or x is None or y is None:
                    continue
                if not (0x06000000 <= x < 0x06100000 or 0x00200000 <= x < 0x00300000):
                    continue
                pairs[x][y] += 1
        amap, conflicts = {}, {}
        for x, c in pairs.items():
            if len(c) == 1:
                amap[x] = next(iter(c))
            else:
                conflicts[x] = dict(c)
        doc = {"schema": "neptune.sh2-xmap.v1", "tool": "tools/saturn_lab/sh2_xmap.py",
               "functions": {f"0x{k:08X}": f"0x{v:08X}" for k, v in sorted(matched.items())},
               "addresses": {f"0x{k:08X}": f"0x{v:08X}" for k, v in sorted(amap.items())},
               "conflicts": {f"0x{k:08X}": {f"0x{v:08X}": n for v, n in c.items()} for k, c in sorted(conflicts.items())},
               "summary": {"functions_from": len(a), "functions_to": len(b), "functions_matched": len(matched),
                           "addresses": len(amap), "conflicts": len(conflicts)}}
        args.out.write_text(json.dumps(doc, indent=1) + "\n")
        print(json.dumps(doc["summary"]))
    amap = {int(k, 16): int(v, 16) for k, v in doc["addresses"].items()}
    keys = sorted(amap)
    for s in args.lookup:
        x = int(s, 16)
        if x in amap:
            print(f"0x{x:08X} -> 0x{amap[x]:08X} (exact)")
            continue
        i = bisect.bisect_left(keys, x)
        near = [keys[j] for j in (i - 2, i - 1, i, i + 1) if 0 <= j < len(keys)]
        print(f"0x{x:08X} nearest:", ", ".join(f"0x{k:08X}->0x{amap[k]:08X} (d=0x{amap[k]-k:X})" for k in near))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
