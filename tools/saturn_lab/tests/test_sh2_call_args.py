"""Owned synthetic SH-2 programs only: no original game code, BIOS or upstream source."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sh2_call_args as ca

BASE = 0x06004000
TARGET = 0x06004800


def blob(words, pool):
    """Instruction words at BASE, then 32-bit literals at the given byte offsets."""
    size = max([2 * len(words)] + [o + 4 for o in pool])
    b = bytearray(size)
    struct.pack_into(">%dH" % len(words), b, 0, *words)
    for o, v in pool.items():
        struct.pack_into(">I", b, o, v)
    return bytes(b)


def movl_pc(n, at, lit):
    """mov.l @(disp,PC),Rn at byte offset `at` loading the literal at byte offset `lit`."""
    disp = (lit - (((BASE + at) & ~3) + 4 - BASE)) // 4
    assert 0 <= disp < 256
    return 0xD000 | n << 8 | disp


def r4(site):
    return site["args"]["r4"]


class CallSites(unittest.TestCase):
    def test_jsr_with_literal_argument(self):
        # mov.l arg,r4 ; mov.l fn,r3 ; jsr @r3 ; nop
        w = [movl_pc(4, 0, 0x14), movl_pc(3, 2, 0x10), 0x430B, 0x0009]
        sites = ca.call_sites(blob(w, {0x10: TARGET, 0x14: 15}), BASE, TARGET)
        self.assertEqual([(s["kind"], r4(s)["value"]) for s in sites], [("jsr", 15)])

    def test_tail_jmp_with_delay_slot_argument(self):
        # mov.l fn,r1 ; jmp @r1 ; mov #-3,r4
        w = [movl_pc(1, 0, 0x10), 0x412B, 0xE4FD, 0x0009]
        sites = ca.call_sites(blob(w, {0x10: TARGET}), BASE, TARGET)
        self.assertEqual([(s["kind"], r4(s)["value"]) for s in sites], [("jmp (tail call)", -3)])

    def test_bsr_and_mov_w(self):
        start = TARGET - 0x20 - BASE
        words = [0x0009] * (start // 2)
        i = len(words)
        lit = 2 * i + 8
        words += [0x9400 | ((lit - (2 * i + 4)) // 2), 0xB000 | ((TARGET - (BASE + 2 * (i + 1)) - 4) // 2 & 0xFFF),
                  0x0009, 0x0009, 0x0123]
        code = struct.pack(">%dH" % len(words), *words)
        sites = ca.call_sites(code, BASE, TARGET)
        self.assertEqual([(s["kind"], r4(s)["value"]) for s in sites], [("bsr", 0x123)])

    def test_not_across_an_earlier_call(self):
        # mov #7,r4 ; jsr @r2 (other) ; nop ; mov.l fn,r3 ; jsr @r3 ; nop
        w = [0xE407, 0x420B, 0x0009, movl_pc(3, 6, 0x10), 0x430B, 0x0009]
        sites = ca.call_sites(blob(w, {0x10: TARGET}), BASE, TARGET)
        self.assertIsNone(r4(sites[0])["value"])
        self.assertIn("previous call", r4(sites[0])["how"])

    def test_callee_saved_copy_across_a_call(self):
        # mov.l arg,r10 ; jsr @r2 ; nop ; mov.l fn,r3 ; jsr @r3 ; mov r10,r4
        w = [movl_pc(10, 0, 0x14), 0x420B, 0x0009, movl_pc(3, 6, 0x10), 0x430B, 0x64A3]
        sites = ca.call_sites(blob(w, {0x10: TARGET, 0x14: 77}), BASE, TARGET)
        self.assertEqual(r4(sites[0])["value"], 77)

    def test_spilled_constant_reloaded(self):
        # mov.l arg,r4 ; mov.l r4,@r15 ; jsr @r2 ; nop ; mov.l @r15,r4 ; mov.l fn,r3 ; jsr @r3 ; nop
        w = [movl_pc(4, 0, 0x18), 0x2F42, 0x420B, 0x0009, 0x64F2, movl_pc(3, 10, 0x14), 0x430B, 0x0009]
        sites = ca.call_sites(blob(w, {0x14: TARGET, 0x18: 50}), BASE, TARGET)
        self.assertEqual(r4(sites[0])["value"], 50)
        self.assertTrue(r4(sites[0])["how"].startswith("mov.l @r15,r4 (spilled"))

    def test_spill_not_followed_across_a_stack_change(self):
        # ... mov.l r4,@r15 ; add #-4,r15 ; mov.l @r15,r4 ...: different slot
        w = [movl_pc(4, 0, 0x18), 0x2F42, 0x7FFC, 0x64F2, movl_pc(3, 8, 0x14), 0x430B, 0x0009]
        sites = ca.call_sites(blob(w, {0x14: TARGET, 0x18: 50}), BASE, TARGET)
        self.assertIsNone(r4(sites[0])["value"])

    def test_register_copy_is_dynamic(self):
        w = [0x64A3, movl_pc(3, 2, 0x10), 0x430B, 0x0009]  # mov r10,r4 with r10 unknown
        sites = ca.call_sites(blob(w, {0x10: TARGET}), BASE, TARGET)
        self.assertIsNone(r4(sites[0])["value"])

    def test_other_target_and_overwritten_register_ignored(self):
        w = [movl_pc(4, 0, 0x14), movl_pc(3, 2, 0x10), 0x430B, 0x0009]
        self.assertEqual(ca.call_sites(blob(w, {0x10: TARGET + 2, 0x14: 15}), BASE, TARGET), [])
        w = [movl_pc(3, 0, 0x10), 0x6353, 0x430B, 0x0009]  # mov.l fn,r3 ; mov r5,r3 ; jsr @r3
        self.assertEqual(ca.call_sites(blob(w, {0x10: TARGET}), BASE, TARGET), [])

    def test_second_argument_register(self):
        # mov #9,r5 ; mov.l fn,r3 ; jsr @r3 ; mov #1,r4
        w = [0xE509, movl_pc(3, 2, 0x10), 0x430B, 0xE401]
        sites = ca.call_sites(blob(w, {0x10: TARGET}), BASE, TARGET, regs=(4, 5))
        self.assertEqual((sites[0]["args"]["r4"]["value"], sites[0]["args"]["r5"]["value"]), (1, 9))

    def test_cli_json(self):
        w = [movl_pc(4, 0, 0x14), movl_pc(3, 2, 0x10), 0x430B, 0x0009]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "code.bin"
            p.write_bytes(blob(w, {0x10: TARGET, 0x14: 15}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(ca.main(["--binary", str(p), "--base", hex(BASE), "--target", hex(TARGET)]), 0)
        doc = json.loads(out.getvalue())
        self.assertEqual(doc["0x%08x" % TARGET][0]["args"]["r4"]["value"], 15)
        self.assertEqual(doc["0x%08x" % TARGET][0]["site"], "0x%08x" % (BASE + 4))


if __name__ == "__main__":
    unittest.main()
