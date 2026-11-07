"""Synthetic SH-2 listings only: no original game code or binary fixtures are used."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sh2_xmap


def listing(base: int, lit_a: int, lit_b: int, extra_nops: int = 0) -> str:
    """One function that loads two literals (mov.l @(disp,PC)) and branches; the
    displacements differ with the base address, the masked opcode run does not."""
    a = base
    rows = ["\t.global func_%08X" % a, "func_%08X:" % a]
    body = [
        ("2FE6", "mov.l r14,@-r15"),
        ("4F22", "sts.l pr,@-r15"),
        ("D%03X" % (0x100 + extra_nops), "mov.l .L%08X,r1" % (base + 0x40)),
        ("D%03X" % (0x201 + extra_nops), "mov.l .L%08X,r2" % (base + 0x44)),
        ("6122", "mov.l @r2,r1"),
        ("8B%02X" % (2 + extra_nops), "bf .L%08X" % (base + 0x20)),
        ("E354", "mov #84,r3"),
        ("223E", "mulu.w r3,r2"),
        ("031A", "sts macl,r3"),
        ("4F26", "lds.l @r15+,pr"),
        ("000B", "rts"),
        ("6EF6", "mov.l @r15+,r14"),
    ]
    for op, text in body:
        rows.append("/* %08X %s */\t%s" % (a, op, text))
        a += 2
    rows += [".L%08X:" % (base + 0x40), "/* %08X */\t.4byte 0x%08X" % (base + 0x40, lit_a),
             ".L%08X:" % (base + 0x44), "/* %08X */\t.4byte 0x%08X" % (base + 0x44, lit_b)]
    return "\n".join(rows) + "\n"


class Sh2XmapTests(unittest.TestCase):
    def test_literals_pair_through_a_matched_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp, "old"), Path(tmp, "new")
            old.mkdir(); new.mkdir()
            (old / "seg_06010000.s").write_text(listing(0x06010000, 0x060C1000, 0x00254000))
            # Same code at another address with other displacements and moved data.
            (new / "seg_06012000.s").write_text(listing(0x06012000, 0x060C2D50, 0x00254000, extra_nops=3))
            out = Path(tmp, "map.json")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sh2_xmap.main([str(old), str(new), str(out)]), 0)
            doc = json.loads(out.read_text())
            self.assertEqual(doc["functions"], {"0x06010000": "0x06012000"})
            self.assertEqual(doc["addresses"]["0x060C1000"], "0x060C2D50")
            self.assertEqual(doc["addresses"]["0x00254000"], "0x00254000")
            self.assertEqual(doc["summary"]["conflicts"], 0)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                sh2_xmap.main([str(old), str(new), str(out), "--lookup", "0x060C1000", "0x060C1004"])
            self.assertIn("0x060C1000 -> 0x060C2D50 (exact)", buf.getvalue())
            self.assertIn("d=0x1D50", buf.getvalue())

    def test_changed_code_and_duplicates_do_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp, "old"), Path(tmp, "new")
            old.mkdir(); new.mkdir()
            (old / "seg_06010000.s").write_text(listing(0x06010000, 0x060C1000, 0x060C2000))
            changed = listing(0x06012000, 0x060C3000, 0x060C4000).replace("E354 */\tmov #84,r3", "E355 */\tmov #85,r3")
            (new / "seg_06012000.s").write_text(changed)
            # Negative control 2: the same function twice in the new build is ambiguous.
            (old / "seg_06020000.s").write_text(listing(0x06020000, 0x060C5000, 0x060C6000).replace("6122", "6123"))
            (new / "seg_06022000.s").write_text(listing(0x06022000, 0x060C7000, 0x060C8000).replace("6122", "6123"))
            (new / "seg_06024000.s").write_text(listing(0x06024000, 0x060C9000, 0x060CA000).replace("6122", "6123"))
            out = Path(tmp, "map.json")
            with contextlib.redirect_stdout(io.StringIO()):
                sh2_xmap.main([str(old), str(new), str(out)])
            doc = json.loads(out.read_text())
            self.assertEqual(doc["functions"], {})
            self.assertEqual(doc["addresses"], {})


if __name__ == "__main__":
    unittest.main()
