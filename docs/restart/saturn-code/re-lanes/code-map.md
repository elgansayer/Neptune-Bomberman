LANE-STATUS: ACTIVE

# Lane ledger: code-map (module map, splitter, byte-identical build)

Scope: the decomp project's infrastructure and the whole-program denominator in
the private `elgansayer/saturn-bomberman-decomp` repository:

- the module map (every code-bearing file/range with load address, CPU, lifetime
  and compression);
- a config-driven splitter and a `make` build that rebuilds every module and
  verifies SHA-256 (`make check`);
- library identification (SBL/SGL/BIOS/CD-block);
- progress tooling (`docs/PROGRESS.md`).

Issues: #480, #497, #515, #496 (all `factory-skip`). usa-code and sound-68k
build on the splitter and build.

Denominator: every byte of every code-bearing file classified and covered by the
byte-identical build, and every module in the build.

## Status (run 20261107T0822Z)

Private repo commit: `235efea` (clean C rebuild + XBAND/XS re-split + `make check` 19/19 under the heavy lock).

**4,702 MATCHING** by the private progress generator (1,292 at the start of this run). Per module: BOOT 760,
XS 232, XBAND 3,664, H2H 46. Run 20261106T1722Z's last figure, 1,245, was a running count that left out H2H.

**XBAND's own code is compiled C, and 3,406 of its functions now match.**
- XBAND.BIN `0x06006000`-`0x060A0000` is the XBAND client itself (Catapult), not the shared NetLink layer.
- **How it was built:** without `-O`. The SH port forces optimization on anyway, so the code is optimized and
  keeps its frame pointer, with no scheduling after reload. But only variables declared `register` get
  registers; anything else lives in a stack slot. The compiler is a GCC 2.7 without SH `PROMOTE_MODE`
  (FSF added it on 4 May 1995), so short/char variables are widened where they are used. The build's
  variant is `xb2`.
- Most of the matches are dispatcher stubs. Each passes a selector and its parameters to one dispatcher,
  which looks the routine up in RAM tables. A `void` stub keeps its `register` parameters live to the end of
  its scope, so they land in callee-saved registers. A value-returning stub looks ordinary; both are now
  reproduced. Generators write C for the stubs and for common small shapes (constants, getters/setters,
  call wrappers, field reads, min/max, byte-order helpers, class dispatch).
- Trap: without `-O`, only the first function of a source file is expanded that way. Candidates must be
  tested one function per file, as the build compiles them.
- 13 stubs that push a 4th argument need GCC 2.6.3's delay-slot memory rule as well (`xb6` = `xb2` + that
  rule; the full regression leaves all 3,120 other entries unchanged).
- Rejected this run: no SH `PUSH_ROUNDING` (argument order), stupid register allocation kept, FSF GCC 2.6.3
  as a whole (it fails an ordinary switch function), and a deferred-parameter-copy variant (`xb3`, which
  the `register` model made unnecessary except for 2 pass-through stubs).

Next:
- About 2,846 XBAND functions remain asm-only, mostly unique. Write C by hand: `register` on every variable the
  original keeps in a register, `xb2 -m2`, one function per file.
- Move XBAND to `xb6`: the full regression is clean (3,120/3,120). Then retry XBAND's soft-float and newlib
  routines (`xb6` with `-O2 -fno-force-mem` finds 3 more libgcc units).
- BOOT's main body (1,000 asm-only) as before.

## Status (run 20261106T1722Z)

Private repo commit: `8fb8764` (last build check 19/19 byte-identical at `ce79712`; one documentation commit after it).

**1,186 MATCHING** (1,149 at the start of the run; +37 so far). BOOT: 701 of 1,760 entries MATCHING.

**The NetLink layer's compiler now lets halfword stores take a constant source (`nocopy17w`).**
- `nocopy17w` is `nocopy17` with one change to the halfword move pattern: like the word pattern, it accepts a
  constant source when the destination is memory. Combine then folds the constant into the store and reload
  picks its register. In BOOT `0x06062000`-`0x06067000` the original stores such constants from `r3`/`r7`.
- It leaves all 700 recorded `nocopy17` functions (BOOT, XS, XBAND and H2H) byte-identical and matches 4 more.
- Rejected: relaxing the byte move pattern as well (`nocopy17h`): 126 of 655 layer functions change, because
  the original stores byte constants from `r1`.
- The regression check (`cregress.py`) now covers H2H too.

What the 33 main-body functions are (cc1 `la4`): hook wrappers and hook tables, record scans and resets, a list
unlink, a tag skipper, an `alloca` string copy, the backup-library status call and its error-code map.

Source idiom found this run: a chain of equality tests on one character matches only as one `if` per test. GCC 2.7.2
folds an `||` chain of adjacent constants into range tests, and the original has none.

Compiler leads recorded in the private `docs/TOOLCHAIN.md`:
- the prologue push placed in a branch delay slot past a load from a structure (`060608E4`, `06060710`);
- an indexed store for `a[i]` (experiment `la5b`: identical on all 377 `la4` functions, but no near miss matched yet).

## Status (run 20261106T1222Z)

Private repo commit: `0f83d82` (last build check at that commit, 19/19; clean rebuild 19/19 at `dd0068b`, 13:34Z).

**1,149 MATCHING** (794 at the start of run 20261106T0917Z, 885 at the start of this run; +264 this run). C
functions: BOOT 591, XS 219, XBAND 219; library routines unchanged (120). BOOT: 664 of 1,760 entries MATCHING.

**BOOT's main body is GCC output with its own compiler configuration.**
- The main body (`0x06010000`-`0x06067000`, below the NetLink layer) was compiled with
  `-m2 -O2 -fomit-frame-pointer`. A few regions keep the frame pointer (`-m2 -O2`).
- Its compiler, `la3`, is `jan96` (FSF 2.7.2 with the SH changes of 9 Dec 1995 and 2 Jan 1996) plus an SH
  `LEGITIMIZE_ADDRESS`. For a 4-byte access whose displacement does not fit `add #imm8`, the displacement goes
  into a register and the access is indexed (`@(r0,Rn)`). FSF 2.7.2's macro is empty, so it adds the
  constant to the base first. Displacements 64..127 still use `add`, as in the original.
- Over the first 91 main-body functions: `la3` matches 91, `jan96` 87, plain 2.7.2.3 86, and the NetLink
  layer's `nocopy17` 78. `la3` leaves the 25 `jan96` library units identical. So the layer and the main body
  were built separately.
- Rejected: indexing every access size and every displacement (`la1`) and every 4-byte displacement (`la2`).
- **`la4` replaces `la3` (this run):** the same indexed form for byte and halfword accesses too, with the same
  displacement limit. It changes none of the 310 recorded `la3` functions or the 25 `jan96` library units, and it
  matches a function whose byte stores at large offsets are indexed. The same address change on the NetLink
  layer's compiler loses 30 of its 649 functions, so the layer was not built with it.

**New build feature: C units that start with constants (`lead=N`).**
- GCC 2.7.2 writes a function's string literals into `.text` just before the function. So do constants it
  forces into memory, such as the multiplier of a division by a constant. The originals have them in the same
  place.
- A C function entry can now say that its compiled unit starts N bytes before the function address. The
  splitter cuts there and places the function symbol inside the unit. The C comparison tool measures N from
  the object.
- Negative control: changing one character of a literal fails `make check` at that byte.
- Literals that GCC merged within one original source file stay external references.

What the 264 functions are:
- PPP/LCP/IPCP trace wrappers, modem command senders, and the modem state-machine event handlers (switch tables);
- SMPC and SCU register access, an interrupt handler, BIOS calls (including the backup-library table);
- the `sprintf` wrapper (varargs), memory-region lookups, ring-buffer and byte readers;
- list walks and frees, record initialisers, and accessors of large records;
- the launcher of the TRAMP copy routine. This resolves an open module-map item: TRAMP runs at `0x00200000`, or
  at `0x00300000` minus its 0x8C bytes, and the launcher jumps there without returning.

**The NetLink layer starts lower than thought.** BOOT's code at `0x06062000`-`0x06067000` keeps the frame
pointer, and it is built with the layer's compiler (`nocopy17 -m2 -O2 -fno-force-mem`): one function there matches
only with a nocopy cc1, and three more give the same bytes with it. Its halfword stores of constants use `r3`/`r7`
in the original and `r1` with every cc1, which is the next experiment.

A twin scan groups BOOT functions by their instruction bytes (literal pools excluded), so one C source covers every
member of a group. It found a group of six object-step handlers and three pairs.

Verification:
- every function was compared byte for byte by the private `ctry.py` before it was recorded;
- each batch of 2-25 was then checked by a BOOT re-split and `make check` (19/19 byte-identical) before its
  commit, 34 times this run (the last 33 functions after the clean rebuild);
- clean rebuilds with every C object recompiled passed 19/19 at 12:24Z and at the end (13:34Z, 561 C sources);
- negative control after the final check: one changed constant in a main-body source fails `make check` at that
  byte; restored, 19/19.

Compiler leads from the near misses are listed in the private `docs/TOOLCHAIN.md`:
- loop-counter elimination in favour of the reduced induction variable;
- `x == 0 || x == 1` kept as two tests;
- an unfilled `bra` delay slot;
- the register of a stored constant in frame-pointer code.

## Status (run 20261106T0722Z)

Private repo commit: `450d254` (this run's commits: `99268e1` to `450d254`; the last verified build state is `dded95e`,
followed by one documentation commit).

**794 MATCHING** (712 at the start of the run; +82). The previous run's last 27 were verified and committed
first. C functions: BOOT 236, XS 219, XBAND 219; library routines unchanged (120).

Verification under the heavy lock:
- clean rebuilds (`rm -rf build/csrc`, re-split of BOOT/XS/XBAND, `make check`) passed 19/19 byte-identical at
  721 (07:50Z, `nocopy10a`) and at 757 (08:31Z, `nocopy13`, 216 C sources);
- the final 790 state passed 19/19 at 08:57Z (`nocopy17`, 235 C sources, 12 of them built without `-O`);
  negative control after it: one changed constant in a shared source fails `make check` in BOOT, XS and XBAND,
  each inside that function; restored, 19/19;
- the last functions were checked by more clean rebuilds and `make check`: 791 at 09:05Z and 794 at 09:08Z, 19/19
  (239 C sources);
- every function was compared byte for byte with BOOT, XS and XBAND (`ctry.py`) before it was recorded;
- every compiler change was decided by a regression check over all recorded C functions (0 regressions).

**Four compiler findings this run. The layer's compiler is now `nocopy17` (`-m2 -O2 -fno-force-mem`):**

1. **`nocopy10a`: the FSF move expander with a permissive `movsi_i`.**
   - Constants and memory values are copied into pseudos at expand time again, as in FSF GCC.
   - Only the condition of the SH `movsi_i` pattern stays permissive: a constant or memory source may go
     straight to a memory destination.
   - CSE then folds stored zeros back into the stores (a zero costs less than a register), and combine
     folds single-use constants, which reload loads. A constant stored twice keeps its register.
2. **`nocopy13`: reload synthesises the constants it loads.**
   - 128..255 become `mov #v-256; extu.b`.
   - `b << s` (first `s` of 1, 2, 8, 16) becomes `mov #b; shll<s>`.
   - Constants that the expander forces into pseudos still come from the literal pool, which is why the
     originals load a field offset like 0xB4 from the pool but synthesise a stored 0x800.
3. **`nocopy15`: GCC 2.6.3's `reorg.c` memory model.**
   - A literal-pool load counts as a memory reference, so a store is never moved past it into a delay slot.
   - GCC 2.7 tracks unchanging memory separately.
   - Four near misses matched at once. One of them was the oldest open scheduling lead, "argument moves
     around the last stores before a call".
4. **`nocopy17`: the rest of the FSF SH change of 2 Jan 1996.**
   - The earlier `jan96` cc1 had only one part of that change. The rest stops the SH backend forcing
     optimisation and delayed branches when no `-O` is given.
   - Some BOOT code was built without `-O` (every delay slot a `nop`). All 16 BOOT functions that look like
     that now match, most on the first try (XBAND, XS and H2H have none). Code built with `-O2` is unchanged.

So the vendor compiler is FSF 2.7.2 with the late-1995/January-1996 SH changes and at least three GCC 2.6.3-era
parts: cbranch delay slots, the merge-point search and the reorg memory model. GCC 2.6.3's whole `reorg.c`
loses the four `nocopy15` matches, so its reorg is a mix.

- Rejected (evidence only):
  - zero-only constant stores (`nocopy9`);
  - a forced constant as operand 1 (`nocopy11`);
  - tying the constant operand first in local allocation (`nocopy12`);
  - immediate loads typed as pool loads for the scheduler (`nocopy14`, breaks 350);
  - 2.6.3's whole `reorg.c` (`nocopy16`).
- Source idioms that mattered (no code):
  - a struct copy where the original copies bytes through one incremented pointer;
  - one block-local pointer per group of stores to a global record;
  - if/else instead of a ternary for the branch layout;
  - chained assignments (`a = b = 0`) for the store order;
  - comparison operands in the original order;
  - one result variable shared by several calls;
  - an interrupt-mask helper that computes the new status word as the `ldc` operand.
- New functions include the request-queue walk and three request state machines (up to 508 bytes), the
  file open, seek, read and window functions, the SH-2 DMA copy, the file-layer init, and BOOT's unoptimised
  display-list, table and command-area helpers.
- Remaining in the layer: 34 shared bodies and 35 BOOT-only functions. Open compiler leads are callee-saved
  register priority and a few scheduling/allocation choices, each listed with its near miss in the private
  `docs/TOOLCHAIN.md`.

## Status (run 20261106T0222Z)

Private repo commit: `0f9dd61` (this run's commits: `a45c101` to `0f9dd61`).

Verified at `d4e7f79`/`0f9dd61` under the heavy lock: a re-split of BOOT/XS/XBAND and `make check` passed
19/19 byte-identical; then every C object was recompiled with the unified flags (192 sources) and
`make check` passed 19/19 again. Negative control: one changed constant in a shared C source makes
`make check` fail in BOOT, XS and XBAND, each at that instruction.

**685 MATCHING** (442 at the start of the run): 81 more functions of the NetLink application layer that
BOOT, XS and XBAND share are compiled from C, one source per function built into all three modules
(+243). C functions: BOOT 189, XS 188, XBAND 188; library routines unchanged (120).

**The whole layer now builds with one compiler configuration: `nocopy6`, `-m2 -O2 -fno-force-mem`.**

- `nocopy6` = `nocopy3` plus GCC 2.6.3's merge-point search in `reorg.c`
  (`fill_simple_delay_slots`): after a forward conditional branch, the search for a delay-slot insn
  continues past the branch's own target label once all uses of the label have been seen. GCC 2.7 deleted
  that code ("redundant with fill_eager_delay_slots"). The originals show it as the epilogue's frame-pointer
  restore placed in a conditional branch's delay slot. All 322 C targets matched before stay identical.
- `-fno-force-mem` turns 5 near misses into matches (a large constant is loaded before the memory operand
  it is added to) and changes none of the 159 earlier C functions of the layer.
- Together with the two findings of run 20261105T2122Z (stores of constants left to reload; GCC 2.6.3
  branch delay slots), the layer's compiler looks like FSF GCC 2.7.2 with the late-1995 SH backend changes
  and several GCC 2.6.3-era parts: a vendor branch, not an FSF release.
- With these, the two oldest near misses (run 20261105T1122Z, "register choice only") also match.
- Rejected this run (evidence only): GCC 2.6.3's SH function units on top of `nocopy6` (breaks 11
  matches, fixes none), and the register allocators compiled for strict IEEE double instead of x87
  (no change).
- Open compiler leads, in order of the near misses they block: the order of callee-saved `r8`/`r9`;
  reload's spill-register choice for stored constants; QImode/HImode displacement addresses formed by
  reload rather than at expand time (GCC 2.6.3 had `-mtry-r0`); constant synthesis (`mov #64; shll2` for
  256, `mov #imm8; extu.b`).
- Source idioms that mattered (no code): clearing an 8-byte message through its address so it takes the
  first stack slot; a mask constant kept in a variable; a `MIN` macro that evaluates its argument twice; a
  switch case that only leaves the switch; `void` prototypes deciding the call register.
- Remaining in the layer: 65 shared bodies (mostly 160-516 bytes) and 35 BOOT-only functions.

### Compiler findings of run 20261105T2122Z

Private repo commit then: `119f126`.

**442 MATCHING** (145 at the start of the run): the NetLink application layer that BOOT,
XS and XBAND share is now being compiled from C. 97 shared functions are built from one
C source each into all three modules (+291), and 3 XS/XBAND-only loader functions into
both (+6). Among them are the SBL CD block command executor and the transfer service
routine. Every batch was verified by a re-split and `make check` (19/19 identical).
The 418 state was verified as below. The final 442 state was verified by a re-split of
boot/xs/xband and `make check` (19/19) at 22:42Z.
At the end of the run, under the heavy lock:

- a clean `make clean && make split && make check && make audit` passed (19/19 identical,
  audit OK);
- negative control: changing one constant in a shared C source makes `make check` fail in
  BOOT, XS and XBAND, each at that function.

New tooling (private): `tools/toolchain/ctry.py` compiles a candidate C file with a chosen
`cc1`, compares each function with the original bytes in every module holding the same
body (relocated literal words masked), prints a side-by-side diff, and records a match in
per-module lists (`config/usa/<module>.{c_functions,c_globals,status}.txt`) that the
splitter merges into the build. Callee and data addresses per module come from the
original literal words.

**Compiler finding: this layer's compiler left word stores of constants and memory values
to reload.**

- FSF GCC 2.6.3, 2.7.2.3 and the Feb 1996 trunk copy a non-register source into a pseudo
  at expand time when the destination is memory (`prepare_move_operands` in the SH
  backend). Local allocation then gives it `r1`.
- The originals hold such values in the register reload would choose: the first register
  in allocation order (`r1 r2 r3 r7 r6 r5 r4 r0 r8`) that no pseudo uses. Examples: a 0
  stored through `r3` (r1, r2 taken), through `r7` (r1-r3 taken), a -1 through `r5`, and
  one function saves `r8` in its prologue only to store a constant. A cache-purge loop
  re-loads its 0 inside the loop, as a reload does.
- `jan96` plus that two-line change (`nocopy2`: no copy for SImode constant and memory
  sources with a memory destination; `movsi_i` accepts them until reload) reproduces 7
  earlier "register choice" near misses and 50 further functions. It changes no C function
  matched before.
- The prebuilt libraries were not built with it: 14 matched libgcc/newlib units change
  under `nocopy2`. So the application code and the vendor libraries come from different
  compilers.
- **Second finding: branch delay slots as in GCC 2.6.3.** GCC 2.7.x declares annul-true
  slots for SH conditional branches, so `reorg` puts a fall-through insn after a plain
  `bt`/`bf`. The originals instead steal the next test from the branch target into a
  `bt/s` slot, as GCC 2.6.3's definition (no annul-true slot) allows. `nocopy3` (`nocopy2`
  plus the 2.6.3 `define_delay`) matches 5 more functions and keeps all 104 earlier C
  matches. The team's compiler thus mixes Dec 1995/Jan 1996 FSF SH changes with an older
  backend part: a vendor branch rather than an FSF release.
- Next compiler leads in this layer:
  - `clear_by_pieces` (FSF trunk, 24 Dec 1995; small structs are cleared with two word
    stores);
  - `mov #imm8; extu.b` synthesis of constants 128-255;
  - large address displacements whose constant is loaded late (base in `r1`, constant in
    `r2`), the same "left to reload" pattern;
  - the order of callee-saved registers.

### Measures (current)

| Measure | Value |
| --- | --- |
| Modules in the build | 14 (USA 11, Japan 3) |
| Modules rebuilt byte-identically by `make check` | **14/14** (2,971,194 bytes) |
| Whole code-bearing files rebuilt and verified | **all 14 census code-bearing sources** (USA 11, Japan 3). The 5 containers (USA/Japan system area, USA/Japan PROGRAM.BIN, XBAND.DAT) take their code from the disassembled modules via `.incbin`; their other bytes are data owned by the asset lanes |
| Modules disassembled | **14/14**; 1,988,942 code bytes emitted as instructions, the rest as data |
| Functions MATCHING / NONMATCHING-verified / asm-only | **794** / see usa-code / 18,229 static entries (19,023 known; USA 14,027 incl. the duplicate XBSND; Japan 4,996). 674 are C functions compiled by GCC 2.7.2.3 variants (BOOT 236, XS 219, XBAND 219): the NetLink application layer, built from one source per function into every module that holds it, and 16 BOOT helpers built without `-O`. 120 are library routines compiled from their original free-software sources: GCC's libgcc (BOOT 55, XBAND 22, XS 3, H2H 1) and Cygnus newlib 1.6.1 (BOOT 18, XBAND 17, XS 4). 20 more inventory entries are extra entry points inside those routines and are not counted as functions |
| SH-2 instructions as mnemonics | USA: KRNL 283,487, BOOT 150,786, XBAND 225,221, XS 13,224, H2H 3,009, FLD 1,652, IP 703, SAMPLEIP 719. Japan: KRNL 285,623, IP 719 |
| Cross-file `bsr` kept as raw words | KRNL 1,461; Japan KRNL 1,468; IP/SAMPLEIP 12 each |
| 68000 instructions as verified mnemonics | SND/XBSND/Japan SND 4,050 of 4,051; NLSND 3,746 of 3,747 |
| Assembly files | USA KRNL 1,166, BOOT 1,746, XBAND 6,509, XS 307, H2H 71, FLD 11, IP 11; Japan KRNL 1,203 |

The function counts are static entries from `sh2_discover.py` (SH-2) and the
pinned Musashi descent (68000). They are a measured lower bound, not
source-level totals. Bytes that no inventory classifies are built as data.
No C exists yet because the original compiler is not identified.

USA code-bearing modules (load address, CPU, evidence):

| Module | Load | CPU | Evidence |
| --- | --- | --- | --- |
| KRNL | `0x06006000` | SH-2 | base check passed |
| BOOT | `0x06010000` | SH-2 | |
| IP | `0x06002000` (IP size `0x1000`) | SH-2 | code from `0x06002100` |
| SND | `PROGRAM.BIN[0x44:0x6418]` → sound RAM `0` | 68000 | |
| XBSND | `XBAND.DAT[0x11868:+25,556]` (same bytes as SND) | 68000 | |
| NLSND | `NETLINK/SNDDRV.BIN` | 68000 | |
| XS | `0x00280000` (lead) | SH-2 | first literal `0x00280078` lands in-module |
| FLD | `0x00200000` | SH-2 | base check passed, 0.122 vs 0.0 |
| SAMPLEIP | template | SH-2 | |
| H2H | `0x06002F00` (lead) | SH-2 | leading table of 54 in-module entry pointers |
| XBAND | `0x06006000` | SH-2 | base check passed, 0.197 vs 0.005 |

BOOT `+0x3B4B0` is TRAMP, a 0x8C-byte SH-2 copy routine. Its `mova` targets
`+0x8C`, which is the start of the byte-identical NLSND copy (`+0x3B53C`). The
build now includes that copy from the rebuilt NLSND module.

Japan: KRNL `0x0600A000` (IP first read; 4,835 static entries), IP (`0x1800`
bytes, 15 entries), SND (byte-identical to USA SND).

Runtime residency comes from captured Beetle states on sound-68k's cold-boot
route. It counts matched non-zero bytes at the load address (runs of at least
16 bytes).

| Module | f900 | f1200 | f1800 | f7200 (stage 1-1) |
| --- | ---: | ---: | ---: | ---: |
| BOOT | 399,184/399,184 | 0 | 0 | 0 |
| KRNL | 0 | 580,550 (loading) | 688,475/693,936 | 688,483 |
| **H2H `0x06002F00`** | 0 | 7,240/7,334 | 7,239 | 7,239 |
| **XS `0x00280000`** | 0 | 34,409/34,409 | 0 | 0 |
| **FLD `0x00200000`** | 0 | 4,378/4,378 | 0 | 0 |
| XBAND | 0 | 0 | 0 | 0 |

So XS, FLD and H2H run on the normal USA path, and H2H stays resident in game.

Uncovered WorkRAM bytes were screened for SH-2 code and chunk-matched
against every disc file and the BIOS images. No unknown disc-derived code
overlay was found in these frames.

The one code region that is not from a disc file is WorkRAM-L
`0x002F0000`-`0x002F33FF`:

- **What the address is.** KRNL `0x0600B494` builds an SBL Cinepak (CPK)
  player parameter block:
  - work area `0x002F0000`, size `0x3190`;
  - ring buffer `0x060C341C`, size `0x2D000`;
  - PCM buffer in sound RAM `0x25A20000`, size `0x10000`;
  - decoding goes to VDP1 VRAM `0x25C08000`.

  So the region is the player's work area. KRNL also passes `0x002F31A0` as a
  code or callback address (`0x0600B730`).
- **Its SH-2 code has an open origin.** It is not raw on the disc or in the
  BIOS. BIOS images match it 10x more often than they match game code, so it
  may be Sega library code that is unpacked or generated at runtime.
- **Rejected: "BIOS backup-RAM library".** KRNL's `BUP_Init` call installs BUP
  in WorkRAM-H at `0x060EC8B0` or `0x060770A4`.

The other code-signal regions were raw PROGRAM.BIN banks staged in WorkRAM-L
(data), and BOOT/XS bytes in transit.

Toolchain (static idiom evidence; no matching build yet):

- **KRNL (USA and Japan) is Hitachi SHC output**:
  - no GCC libgcc helpers and no frame pointer;
  - SHC-style register-preserving division helpers (dividend r1, divisor r0,
    r2-r4 saved);
  - 3,519 direct `bsr` near calls.
- **BOOT/XBAND/XS/H2H are GNU GCC (SH) output**:
  - libgcc `___sdivsi3`/`___udivsi3`/`___movstrSI`;
  - frame-pointer prologues and epilogues.

Cross-module function matching (`tools/split/function_match.py`, private):
functions of at least 12 instructions are hashed with PC-relative
displacements masked and literal pools ignored.

| Module pair | Shared bodies | Reading |
| --- | ---: | --- |
| USA KRNL + Japan KRNL | **3,844** of about 4,200 | one C source per function can serve both releases |
| XBAND + XS | 229 | GCC-built NetLink/XBAND modules share a library layer |
| BOOT + XBAND | 216 | same |
| BOOT + XS | 210 | same |
| KRNL + BOOT | 3 | SBL was shipped as source, so each studio compiled it with its own compiler |
| FLD + KRNL | 29 | FLD_KNL.BIN came from the KRNL team and toolchain |
| USA IP + Japan IP + SAMPLEIP | 14 (all) | Sega's security/area code |

CPU roles:

- KRNL kicks the slave SH-2 via SINIT from `06067608`, and 8+ functions signal
  the master via MINIT. Japan KRNL is the same.
- In all 12 captured states (f900-f7200 and the f10800 menu), **the slave
  SH-2's PC is 0**: it is not running on this route.
- The master executes:
  - BOOT at f900;
  - **FLD in WorkRAM-L at f1200** (`0x002007C6`), so the field loader runs;
  - the Cinepak player path at f2400-f3600;
  - KRNL's main loop in game.

Libraries (version strings):

- SBL `GFS 2.10` (1996-02-01) in both KRNLs, BOOT, XS and XBAND.
- SBL `STM 2.10` and `PCM 1.15`, plus a Cinepak player, in both KRNLs.
- `SYS 2.21` (1996-10-01) in USA KRNL only.
- `FLD 1.21` in FLD/XS/XBAND.
- The PlanetWeb browser in BOOT.
- Sega's 1994 security code in the IPs.
- No SGL.
- USA KRNL's CD-block code clusters in `060958EA`-`06095ACE`.

Census basis (run 20261105T0801Z, private evidence): 457 sources and 138
PROGRAM.BIN entries screened for SH-2/68000 signals. Only bank 0 (`s_init`,
the SND driver) of PROGRAM.BIN carries code; no code signal was found in any
decoded bank stream.

## Tools and identities

- Toolchain: GNU binutils 2.44 (Debian `binutils-sh4-linux-gnu`/`binutils-m68k-linux-gnu`
  2.44-3), unpacked without root into `$RE_TOOLS_DIR/cross-binutils-2.44-3`. Deb SHA-256:
  sh4 `9ae1397e431be6b07e63287799d07e791454820bd03406f88fc6f3adee1fbd8c`,
  m68k `195f98f2c4fa751481d6c10eab3b1d8995a67d6452ab5de99fc15686550dc552`.
  The assembler runs as `as -big --isa=sh2` / `as -m68000`, the linker as `ld -EB --no-relax`.
- `tools/saturn_lab/sh2_gas.py` (this PR) is the SH-2 → GNU as formatter used by the
  private splitter (`tools/split/sh2_gas.py`, identical bytes). Synthetic tests:
  - accept/reject agreement with `sh2_discover.decode` on all 65,536 words;
  - PC-relative target agreement;
  - known encodings;
  - an optional exhaustive GNU as round trip (53,752/53,752 accepted words
    reassemble identically, and the accept set equals objdump `-m sh2`'s decode).
- Code maps: `sh2_discover.py inventory` reports (tool SHA-256 `87951608…e516`).
  - USA KRNL and BOOT entry lists reproduce usa-code's receipt
    (`9bc8348f…`, `76ee15fe…`).
  - Japan KRNL (seed `0600A000`) has entry list `f36a46f7f00d61be86d209ef1493da4ff106b0a32c3ad5a5dd5de690a6aed61d`.
- Private inputs: EDC-checked extraction under `$RE_EVIDENCE_DIR/inputs/<release>/`
  (receipt `extraction.json`). It is never committed.

Hard constraint found: GNU as cannot relocate SH fixed-width PC-relative forms
(`bra`/`bsr`/`bt`/`bf` and `mov.l`/`mov.w`/`mova` literals) to symbols in another
file. Errors seen: "displacement to undefined symbol overflows", "pcrel too far".
So the splitter:

- cuts files only where no branch or literal load crosses;
- emits cross-file `bsr` as a raw word;
- starts files on 4-byte boundaries, because `mov.l`/`mova` alignment is
  resolved against the section start.

## Run log

### 20261105T0801Z, 0847Z, 0922Z, 1027Z, 1327Z (no result)

- 0801Z built the whole-disc census (`disc_code_census.py` in its worktree;
  2 private census reports kept in evidence).
- 0801Z then hit the account usage limit before committing. The worktree, and
  with it the census tool, was cleaned up.
- 0847Z, 0922Z, 1027Z and 1327Z exited immediately on the same limit.
- The census JSON survives in private evidence and is used by this run's
  module map.

### 20261105T1122Z

Moved:

- Splitter, build, checker and progress generator in the private repo.
- 14/14 modules byte-identical and disassembled.
- 68000 path: objdump text rewritten for GNU as, then each instruction
  verified by assemble+link+compare, with fallback to raw words.
- New inventories and base checks for IP/SAMPLEIP/XS/FLD/H2H/XBAND/Japan IP.
- TRAMP length resolved.
- USA/Japan module map (`docs/MODULE_MAP.md`, private).
- Public formatter and tests (this PR).

Facts learned about GNU as (they bound the C path):

- It sign-extends negative byte immediates into the 68000 extension word,
  where the original has `00xx`.
- It shortens `(0,An)` to `(An)` unless written `(0:w)`.
- It leaves branches to global symbols as relocations, on both CPUs.

**MATCHING count at the end of the run: 25.**

- 11 BOOT functions are compiled from `src/usa/boot/*.c` by GCC 2.7.2.3.
- 7 of them are shared library functions that also sit byte-identical in XS
  and XBAND, so the same sources build them there: 7 + 7. Among them:
  - the SBL CD-block command-register write (CR1-CR4);
  - three accessors of a global record.
- A clean `make clean && make split && make check && make audit` under the
  heavy lock passed (19/19, audit OK) at the 16-function state. The last 9
  functions were verified by rebuilding BOOT, XS and XBAND.
- All 8 BOOT fingerprint targets match at `-m2 -O2`, with or without
  `-fomit-frame-pointer` per source file, once the C is phrased like the
  original (statement order and temporaries matter).
- New build features:
  - Globals referenced from C are mapped to their original per-module
    addresses (`c_globals` → linker script).
  - cc1's `.align` is zero-filled, because the original assembler padded
    with `0000` and GNU as 2.44 pads code with `nop`.
- Every addition was verified by a rebuild of the affected modules with
  identical SHA-256.

**First MATCHING functions (end of run 20261105T1122Z):**

- GCC 2.7.2.3 for SH was built here without root:
  - 32-bit i386 host from Debian multilib debs;
  - `--host=i386-linux --target=sh-hms`;
  - an `obstack.h` cast-lvalue patch for modern host compilers;
  - `cc1` SHA-256 `63fb80a61c9517e23bcbe833c08fd307db4bf591baab084261a5a5ccb8264bd4`.
- It reproduces three small BOOT functions byte for byte:
  - `06041DAC` with `-m2 -O2 -fomit-frame-pointer`;
  - `0606E2C8` and `0606E2E0` with `-m2 -O2`, frame pointer kept.
- They are now compiled from C into the build (`[[module.c_function]]`:
  `.include` of the cc1 output), and `make check` stays 19/19 identical.
- Negative control: changing one constant in a C source makes `make check`
  fail at `0x0606E2ED`.
- So NetLink's BOOT is GCC 2.7-era code with per-file flags. KRNL (Hitachi SHC)
  remains blocked on a licensed compiler.
- The whole-disc census tool is restored (this PR). Regenerating the census
  reproduces the 0801Z census byte for byte (SHA-256 `65d9aba7…d5e2`).

Later in the run:

- `tools/check.py` now locates the first differing byte. Negative control: a
  flipped FLD byte is reported at `0x00200064`.
- Toolchain preparation for the GCC-built modules:
  - Debian i386 multilib debs unpacked without root (`$RE_TOOLS_DIR/i386-multilib`,
    with a `cc32` wrapper; a 32-bit test program links and runs).
  - GCC 2.7.2.3 source downloaded (SHA-256
    `16166e0f0f2064bb3114716650569065ef3855ae2331d7a29b85d4b9aa73773c`).
  - A bounded `cc1` build for `sh-hms`
    (`$RE_TOOLS_DIR/build-gcc-2.7.2.3-sh/build.sh`) succeeded on the third
    attempt. The first failed on `obstack.h`; the second on read-only tarball
    files.
  - Hitachi SHC for KRNL is proprietary and was not fetched. The owner needs
    to supply a licensed copy.
- Incident: replaying the 0801Z run's edit commands to recover the census tool
  also ran one recorded cleanup command. That command deleted the superseded
  private `census-run1.json` from this lane's evidence directory.
  `census-run2.json`, the one in use, is intact. The reconstructed tool is
  validated: regenerating the census gives byte-identical output.

Also moved later in the run:

- Container files are in the build.
- Library and toolchain identification.
- Runtime residency and overlay screen from captured states.

Next frontier:

1. Compilers:
   - GCC 2.7.2.3 is live for the GCC-built modules (BOOT, XBAND, XS, H2H).
     Decompile them function by function; BOOT semantics belong to usa-code.
   - **Blocked on the owner:** a licensed period Hitachi SHC (and its
     optimizing linker) for KRNL.
2. Trace the writer of the SH-2 code in the CPK work area
   (`0x002F0000`-`0x002F33FF`) with a write-watch (heavy). Extend the
   residency screen to battle mode, stage changes and the NetLink/XBAND paths.
3. Classify the remaining unclassified bytes (switch tables, unreached code)
   and re-import updated usa-code inventories.
4. Separate SBL library functions from game code (anchors above) in the
   symbol files.
5. The census tool is restored (`tools/saturn_lab/disc_code_census.py`). Use
   its `verify` on future census updates.

### 20261105T1622Z

Moved: **GCC's runtime library (libgcc) is now compiled from its original
sources inside the byte-identical build: 70 routines MATCHING** (95 MATCHING in
total). Private commit `6a37a0f`.

- Method: compile every libgcc unit for SH (`lib1funcs.asm` members; every
  function of `fp-bit.c`/`dp-bit.c`) for both multilibs (`-m2`, default `sh1`).
  Search each module for the bytes, with the literal-pool words that hold
  external addresses masked. The original words in those slots then give the
  addresses of the callees and data. Identical wrappers (for example
  `___eqsf2`/`___nesf2`/`___ltsf2`) are placed by their references and by object
  order.
- Found:
  - BOOT links the `-m2` libgcc: 6 `lib1funcs.asm` routines and 38 of the 42
    soft-float functions of `fp-bit.c`/`dp-bit.c`.
  - XBAND links the default (`sh1`) multilib (21 units).
  - XS has 3 `lib1funcs.asm` routines and H2H has 1.
- Source revision: the soft-float functions match **GCC 2.7.0's**
  `config/fp-bit.c`, which packs IEEE fields with bitfields; 2.7.1 and later use
  shifts.
  - GCC 2.7.0 is not on the GNU mirrors as a tarball. It was rebuilt from
    `gcc-2.6.3` plus the official `gcc-2.6.3-2.7.0` diff.
  - Check: applying the `2.7.0-2.7.1` diff gives GCC 2.7.2's file.
- Compiler: a GCC 2.7.0 `cc1` was rebuilt the same way (bison 3 needed two
  grammar fixes). Its soft-float output matches nothing, while 2.7.1 and
  2.7.2.3 both give the 38 matches. So the original `cc1` is 2.7.1-like.
- The 4 BOOT misses (`_pack_d`/float, `___fixsfsi`, `__fpmul_parts`/double,
  `___fixdfsi`) differ in how `constant - register` is compiled:
  - the original emits `neg` + `add #imm`;
  - FSF 2.7.x's `subsi3` has no constant-operand expansion.

  This points to a later (Cygnus-era) SH backend: the next compiler lead.
- Build: new `[[module.lib_function]]` entries, plus `tools/split/libfunc.py`
  (compile one library source, extract one unit, make its labels unique, resolve
  its references per module).
  - `make check` stays 19/19 identical.
  - Negative control: mutating one statement of `fp-bit.c` breaks `usa/boot`
    and `usa/xband`.
- Counting rule: 20 inventory entries are extra entry points inside one
  `lib1funcs.asm` routine (`___ashiftrt_r4_N`). They are recorded as `covered`
  and no longer counted as functions, so the MATCHING count is not inflated.

Later in the run (private `5a1180f`, `8f1b0de`, `978a858`): **136 MATCHING**.

- `libgcc2.c` of GCC 2.7.0 adds BOOT's `___divdi3`/`___moddi3`/`___udivdi3`/
  `___umoddi3` and XBAND's `___lshrdi3`.
- **Compiler variant found.** The 4 soft-float misses need Jim Wilson's FSF
  trunk SH change of **9 Dec 1995** (`subsi3` expander, `ADDRESS_COST`; GCC
  2.8.0 ChangeLog.10).
  - GCC 2.7.2.3 with only that change (`cc1 = "dec95"`) matches all four, plus
    BOOT's `___lshrdi3`, and keeps every other BOOT/XS/H2H unit and C function
    identical.
  - XBAND's libgcc does not have the change, so XBAND was built with a
    different toolchain.
  - BOOT's toolchain therefore had a 1996 backend with mid-1995 library
    sources: a Cygnus-style release branch.
- **C library identified: Cygnus newlib.** newlib 1.6.1's sources compile to
  BOOT's string functions and `mktime` (16), XBAND's string and stdio pieces
  (14) and XS's (3). BOOT's `vfprintf` tables are the BSD 4.4 ones that newlib
  carries.
- Matching discipline:
  - A one-call wrapper under 64 bytes counts only if one of its references
    points at another accepted unit. This rejected look-alike
    `___builtin_vec_new`/`___builtin_vec_delete` hits.
  - Data tables are not units.
  - The matcher reads the original files, never build outputs.
- Public: `tools/saturn_lab/lib_unit.py` (this PR) is the generic,
  content-free core, with synthetic tests.
- Two older GCCs were rebuilt for the comparison:
  - FSF 2.7.0 from gcc-2.6.3 plus the official diff; its parser was
    regenerated with Debian bison 3.8.2 after two grammar fixes;
  - 2.7.1 from 2.7.0 plus the 2.7.0-2.7.1 diff.

Final part of the run (private `fe239a6`-`3ab68a3`): **138 MATCHING**.

- A second backend change is confirmed: Jim Wilson's **2 Jan 1996**
  `gen_shifty_op` change (a `nop` for a shift by 0).
  - Added to the Dec-1995 cc1, it gives `jan96`. That matches BOOT's
    double-precision `__fpmul_parts` (876 bytes) and loses nothing.
  - BOOT's compiler therefore has the FSF trunk SH work through at least
    2 Jan 1996.
- `___udivmoddi4` matched once `longlong.h` was vendored; the matcher had been
  skipping it as a compile failure. BOOT's whole libgcc is now compiled from
  source.
- Shared lead: XBAND's unmatched soft-float core and BOOT's corrected near miss
  `0606F4E4` differ from our output **only in register choice**.
  - `REG_ALLOC_ORDER` is the same, and FSF 2.7.0/2.7.1 do not help.
  - Suspect a generic register-allocation change from late 1995 or 1996.

Rejected at the end of the run: a cc1 built from the FSF trunk of 14 Feb 1996
(GCC git mirror, overlaid on 2.7.2.3; two build fixes).
- It gives fewer BOOT matches than `jan96` (libgcc 41 vs 55, newlib 14 vs 16)
  and leaves the near misses unchanged.
- So BOOT's compiler is a 2.7.2 branch with selected SH backports, not the
  trunk.
- The GCC git mirror does serve 1996 commits (`gh api
  repos/gcc-mirror/gcc/commits?path=...`), so single commits can be tested on
  top of `jan96`.

Last change of the run (private `d7c5b11`, public `lib_unit.py` in this PR):
**145 MATCHING**.

- The resolver resolves larger units first and allows one name per address.
  - It rejected a `_localeconv` look-alike whose callee address belongs to
    XBAND's `_rand_r`.
  - It added BOOT's `index`/`bcmp`, which wrap the placed `strchr`/`memcmp`.
- XBAND/XS library units match best with `-O2 -fno-force-mem` (+5, one unit
  keeps plain `-O2`), a proxy for their compiler variant.

Next frontier (from this run):

1. Register allocation: find the generic 1995-96 change behind the
   register-choice differences:
   - XBAND's `sh1` soft-float core;
   - BOOT's near misses;
   - probably many more GCC-module functions.
2. XBAND's toolchain:
   - `-O2 -fno-schedule-insns2` also matches its `___negdf2`;
   - most of its newlib (`_malloc_r`, `__swbuf`, `fflush`, `vfprintf`) does not
     match yet.
3. BOOT's remaining C library (`vfprintf`, `sprintf`, `strtol`, ...). These now
   compile but do not match.
4. Decompile BOOT/XBAND/XS/H2H game and NetLink code with
   `[[module.c_function]]`. BOOT should use the `jan96` cc1.
5. Still open from the previous run: the CPK work-area writer, classification
   of unclassified bytes, SBL symbol names, census verification. Owner decision:
   Hitachi SHC for KRNL.

### 20261105T1852Z (no result)

Exited at once on the account usage limit.

### 20261105T2122Z

Moved: **442 MATCHING** (from 145). See the status section for the two compiler findings.

- Target: the code BOOT, XS and XBAND share (function-match report: about 210 bodies), the
  NetLink application layer above the libraries. One C source per function goes into all
  three modules, so each function adds three MATCHING.
- Batches of 3-14 functions; each batch was rebuilt (re-split of boot/xs/xband, then
  `make check` 19/19 identical) and committed.
- Rules that turned near misses into matches (recorded in the private progress file):
  - callee return types decide the call register (`r0` for value-returning callees);
  - struct member access instead of `char *` arithmetic;
  - `return f(x)` per switch case keeps the original's separate calls;
  - branch order of `if (...) return A(); return B();`.
- An `r1`/`r2` register swap in many functions was traced to the compiler, not the source
  (status section). Two experimental `cc1` builds (constants only; constants and memory
  sources) took about 3 s each, because only `sh.o` is rebuilt.
- About 25 near misses remain, listed in the private `docs/TOOLCHAIN.md` with their cause
  where known.
- Rejected experiment: leaving every large `add` constant to reload (`nocopy4`) improves
  some near misses and breaks others, so it was not adopted.

Next frontier:

1. Continue the shared layer (about 120 larger bodies left), then BOOT-only and
   XBAND-only code of the same layer.
2. Build the next compiler variants one change at a time (`clear_by_pieces`, constant
   synthesis, delay slots, callee-saved order) and keep only changes that lose nothing.
3. Still open from earlier runs: XBAND's soft-float core and newlib, BOOT's remaining C
   library, the CPK work-area code origin, unclassified bytes, SBL symbol names.
   Owner decision: a licensed Hitachi SHC for KRNL.

### 20261105T2357Z (no result)

Exited without a result (rc=1); no commits.

### 20261106T0222Z

Moved: **685 MATCHING** (from 442). See the status section for the compiler findings.

- Re-tested the previous run's near misses and scratch C with the newer compiler variants first; then
  wrote C for the remaining shared bodies, smallest first, 1-3 attempts each.
- Found 35 small shared functions that the cross-module function matcher skips (under 12 instructions);
  their XS/XBAND copies were located from the layer's address offsets and checked byte for byte.
- Two experimental cc1 builds were rejected (status section). Each takes about 3-10 CPU-seconds,
  because only the changed objects are rebuilt.
- Verification:
  - every function was compared with the original bytes by the private `ctry.py` (relocated literal
    words masked) before it was recorded;
  - `make check` (re-split of BOOT/XS/XBAND under the heavy lock) passed 19/19 byte-identical at the
    607-MATCHING state (private `62c16b1`, 03:09Z);
  - at the 685-MATCHING state (private `d4e7f79`, 03:35Z) the re-split and `make check` passed 19/19;
    a rebuild with every C object recompiled under the unified flags passed 19/19 (03:36Z);
  - negative control: `return 6` -> `return 5` in the state machine's C source fails `make check` in
    BOOT, XS and XBAND at that instruction; restored, 19/19.
- Near misses with their causes are in the private `docs/TOOLCHAIN.md` (run 20261106T0222Z section).

Next frontier:

1. The open compiler leads in the status section, starting with the callee-saved register order and
   reload's spill-register choice; build each as one small change on `nocopy6` and keep it only if it
   loses no match.
2. The 65 remaining shared bodies and 35 BOOT-only functions of the layer; then BOOT-only and XBAND-only
   code outside it.
3. Still open: XBAND's soft-float core and newlib, BOOT's remaining C library, the CPK work-area code
   origin, unclassified bytes, SBL symbol names. Owner decision: a licensed Hitachi SHC for KRNL.

### 20261106T0722Z

Moved: **794 MATCHING** (from 712). See the status section for the four compiler findings.

- Verified and committed the previous run's uncommitted last batch first.
- Wrote a regression check for compiler variants over all recorded C functions (private `cregress.py`).
  Tested nine variants against it: four adopted (`nocopy10a`, `nocopy13`, `nocopy15`, `nocopy17`), five rejected.
- Wrote C for 22 more shared functions (+66), smallest-first among the bodies not tried before, plus former
  near misses that the new compilers made reachable; and 16 BOOT functions built without `-O` (+16).
- Verification: see the status section. Another lane held the heavy lock for long stretches, so batches
  were verified by `ctry.py` first and by a clean `make check` whenever the lock was free.

Next frontier:

1. The 34 shared bodies left (among them `0606E740`, 888 bytes, and `0606FC70`, which fills delay slots with
   `or r0,r0`) and the BOOT-only functions of the layer, with `nocopy17`. (BOOT code built without `-O` is
   done: all 16 such entries match.)
2. Compiler leads:
   - GCC 2.6.3's long-branch filler `or r0,r0` (`0606FC70`; the -O0 BOOT helpers use `nop`, so possibly two
     compiler builds);
   - global-alloc priority between equal-looking pseudos (`0606E384`, `0606DCEC`, `0606E408`);
   - scheduling of a constant load next to an independent copy (`06070CBC`, 4 bytes);
   - the base/constant order for large offsets used twice (`0606C028`);
   - the stack-pop order after a call with a pushed argument (`0606B0A4`).
3. Still open: XBAND's soft-float core and newlib, BOOT's remaining C library, the CPK work-area code
   origin, unclassified bytes, SBL symbol names. Owner decision: a licensed Hitachi SHC for KRNL.

### 20261106T0917Z (cut by the usage limit after 21 minutes; no result line)

- Found that BOOT's main body is GCC output built with `-fomit-frame-pointer`, and built the `la3` cc1
  (status section). Wrote C for 91 small main-body functions.
- Committed 46 at private `a504f2f` after `make check` 19/19 (840 MATCHING). The other 45 were checked with
  `ctry.py` but not committed, and there is no ledger entry for the run.

### 20261106T1222Z

- Verified the previous run's 45 uncommitted functions with a clean rebuild (19/19), then committed them
  (private `e252f5e`, 885 MATCHING).
- Added the `lead=N` build feature and 231 more main-body functions in 18 verified batches. Adopted the `la4`
  compiler (0 regressions). Final state: 1,149 MATCHING at private `0f83d82`.
- Another lane held the heavy lock for most of the run. Incremental BOOT checks were measured at about 14
  CPU-seconds and ran niced without the lock.
- Deviation: the final clean rebuild of all three modules also ran without the lock and cost 82 CPU-seconds, over
  the 1-minute guideline. Future clean rebuilds go under the lock.
- Next:
  - the main body's remaining 1,096 BOOT entries (the 61-200 byte buckets first);
  - `nocopy17h` (constant sources allowed for halfword/byte memory destinations) for the layer's frame-pointer
    code at `0x06062000`-`0x06067000` (the build waited for the heavy lock all through this run's last hour and
    was withdrawn unbuilt);
  - the compiler leads in the private `docs/TOOLCHAIN.md`: loop-counter elimination, `x == 0 || x == 1` kept as
    two tests, an unfilled `bra` delay slot, and the stored-constant register in frame-pointer code.

### 20261106T1722Z, 20261106T1842Z, 20261107T0612Z

- 1722Z: BOOT main-body batches and the layer compiler `nocopy17w`. Its last private commit (`a5632d7`) is
  in this run's baseline; the status section above has its findings.
- 1842Z and 0612Z exited without a result and left no evidence or commits.

### 20261107T0822Z (this run)

- Baseline at private `c0851bc`: full split + `make check` 19/19 under the heavy lock (98 CPU-s).
- Found that XBAND's own code is GCC output and that most of its small entries are dispatcher stubs.
  First model: `-O1` with a deferred-parameter-copy compiler (`xb3`); 1,461 stubs at private `bb30158`, `make check`
  19/19, with a negative control.
- Then found the real model: built without `-O`, with `register` parameters, by a GCC 2.7 without SH `PROMOTE_MODE`
  (`xb2`). It also explains the stubs that keep parameters in callee-saved registers. Converted the 1,461 stubs,
  added 1,945 more XBAND functions (stubs, templates for small shapes, some written by hand) and 4 XS loader
  functions.
- Final state: private `235efea`, 4,702 MATCHING; clean C rebuild + XBAND/XS re-split + `make check` 19/19
  under the heavy lock. A full `xb6` regression (3,120/3,120) ran under the lock as well.
- Built and tested 8 compiler variants (`xb1`-`xb6`, FSF 2.6.3, reconstructed 2.7.0/2.7.1); kept `xb2`, `xb6` and,
  for 2 entries, `xb3`.
- The heavy lock was busy with other lanes' emulator batches for most of the run. My queued checks were
  withdrawn only while still waiting (no child process), to add more work, and then re-queued.
- Left for the next run: 13 functions matched and staged in private evidence (`next-run/`), not applied.

