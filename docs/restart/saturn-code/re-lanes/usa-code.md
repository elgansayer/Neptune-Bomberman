LANE-STATUS: ACTIVE

# Lane ledger: usa-code (USA main SH-2 program)

Scope: the USA MK-81070 V1.003 release's original SH-2 game code. That covers
BOOT (`0` at `0x06010000`), `BOMSS/0KRNL.BIN` (KRNL at `0x06006000`) and every
gameplay/menu overlay they load, on both master and slave SH-2. Japan kernel
execution is Codex's lane; compare with it without extending its probes.
Code-map owns the whole-disc census and `module-candidates.json`, and consumes
the USA ranges recorded here. Sound-68k owns the 68000 drivers.

Issues: #480, #481, #482, #483, #492, #493, #495, #497. All carry `factory-skip`
while this lane works them.

Goal: a reproducible static project for the USA program with validated symbols.
For each function: boundaries, ABI, state read/written, callers/callees,
behaviour and gameplay role. Validate against original bytes in an isolated
CPU interpreter and against natural emulator execution, with negative controls.

## Denominator

All USA SH-2 executable functions, including overlays and dynamic targets,
reconciled with runtime discovery. Measured so far (run 20261105T0632Z):

| Module | Static entries A/B/C | Code / literal / table / unclassified halfwords | Unresolved indirect | Runtime evidence |
| --- | --- | --- | --- | --- |
| KRNL `0x06006000` | 4,868 = 37 / 4,663 / 168 | 284,948 / 54,016 / 83 / 54,169 | 485 | resident at f10200/f10800; 0 code/literal halfwords mutated |
| BOOT `0x06010000` | 1,751 = 959 / 767 / 25 | 150,786 / 21,349 / 945 / 44,568 | 704 | fully resident at f600, replaced by f1200 |

Upstream comparison on identical bytes: KRNL 4,867 shared of 5,098 upstream;
BOOT 1,744 shared of 2,146. There are no code/data contradictions in either
module.

Not yet counted:

- Overlays loaded after KRNL (none mapped yet).
- The BOOT `0x0604B4B0` blob's possible `0x00200000` lifetime.
- XBAND/H2H/FLD/XS (outside this lane unless they run in the USA game path).
- Slave-SH-2 entry points.
- Code behind the unresolved indirect sites and the unclassified bytes.

The function denominator is therefore a measured static lower bound, not a total.

Semantic recovery (boundaries plus ABI plus state plus negative control) remains
limited to the earlier isolated results:

- `0600A4B0`, `0600B934`, `0600A0EC`/`0600A08C`, `06009FA8`.
- Library entries `060958EC`, `06095904`, `06095992`, `06095A84`, `06095AB4`,
  `06095ACE`, `06095E5A`, `060A681A`.
- Natural returns of `060089C8`/`06095B04`.

All 4 natural roots and 12 of 13 probe entries reconcile as inventory entries.

## Decompilation counts

Source of truth: the private `saturn-bomberman-decomp` repo,
`docs/progress/usa-code.md` and `config/usa/krnl.status.txt`.

KRNL was compiled by Hitachi SHC (code-map lane, private `docs/TOOLCHAIN.md`).
SHC is not available, so no KRNL C can be MATCHING yet. KRNL C counts as
NONMATCHING-verified only through the private differential test
(`tools/difftest/difftest.py`). It runs the original bytes and the C (built by
GCC 2.7.2.3 `-m2 -O2 -mhitachi`) in the pinned SH-2 interpreter
(saturn-recomp `f20de94` `sh2emu.py`, loaded by SHA-256). Every run starts from
in-game Work RAM (three Beetle checkpoints: Normal 1-1, battle, Master) with
fuzzed arguments and memory. The test requires identical registers, RAM, MMIO
order and stub calls on every vector, and at least one detected source mutant
(negative control).

| Module | Static entries | MATCHING | NONMATCHING-verified | Asm-only |
| --- | ---: | ---: | ---: | ---: |
| USA KRNL | 4,879 | 0 | 1,754 | 3,125 |
| USA BOOT | 1,760 | 760 (code-map lane) | 0 | 1,000 |

Counts at run 20261107T1350Z, private head `6e37bd54`. KRNL still rebuilds
byte-identically after every rename (`split.py --only krnl` + `make` +
`check.py`: `usa/krnl` SHA-256 `20109f50…c798a7`, 14/14 USA modules).
BOOT's MATCHING count is the code-map lane's (`config/usa/boot.status.txt`).
KRNL has 11 static entries more than the inventory (4,868 + 11). They are
functions reached only by a tail branch (`bra`/`jmp`) or only through a pointer
literal, found while writing C.

The 220 KRNL functions, by private source file (`src/usa/krnl/`):

| File | Functions | System |
| --- | ---: | --- |
| `rng.c` | 7 | random numbers (Knuth subtractive, 55 entries, modulus 0x8000, seed 1234) |
| `pad.c` | 1 | pad direction decoder |
| `field.c` | 3 | cell index, soft-block layout, hidden-item placement |
| `stage.c` | 33 | descriptor lookups, the four map layers (grid decode, metatile drawing), gameplay-map attributes, field wrap |
| `stage_setup.c` | 9 | Normal, battle and Master stage set-up, battle start-position shuffle |
| `view.c` | 23 | pixel/cell conversion, free-direction masks, field rectangle and scroll limits, actor placement |
| `scroll.c`, `view_scroll.c` | 11 | scroll register image, plane scroll steps, per-layer fixed-point scroll |
| `items.c` | 25 | item slots, hiding and revealing items, item spawn, per-frame item animation states, burning soft blocks |
| `item_pickup.c` | 1 | the effect of each of the 28 item kinds on the bomber who picks it up |
| `effects.c` | 2 | effect-list reset |
| `bomb.c` | 20 | bomb records (a doubly linked list): lookups by cell and owner, setting bombs off, cell marks, animation frame |
| `bomb_move.c` | 12 | moving bombs: stopping on a cell, probing the cell ahead, reversing, one-pixel steps, the second actor, following the owner |
| `pdec.c` | 73 | a predictive stream decoder: byte, halfword and word streams, history-ring predictors, 1/2/3/4-bit field readers, mode tables |


## Tools and identities

- `tools/saturn_lab/sh2_discover.py`: inventory, base-check, reconcile and
  residency. SHA-256 `8795160857be036c2a633d3f777c6d830b515c1fc4648ad9f68a20859093e516`
  at this run.
- `tools/saturn_lab/compare_discovery.py`: SHA-256
  `7129a0da9c2eabe76308ae5a50ae67e4f43f318c668ef74878c3184784a66d75`. It loads
  `saturn-recomp@f20de940` `sh2.py`/`hw.py`/`recomp/discover.py` by hash.
- `tools/saturn_lab/compare_resident_module.py`: reused unchanged.
- Upstream leads: `pc-saturnbomberman@c73bc117` (`game.toml` blob `0ec8d923`,
  `seeds.json` `d1486948`, `coverage-classes.tsv` `30ccb2d4`).
- Reference address sets:
  [usa-krnl-reference-addresses.json](usa-krnl-reference-addresses.json).
- Private inputs:
  - `/home/dev/neptune-research-private/483/0KRNL.BIN`.
  - `$RE_EVIDENCE_DIR/inputs/BOOT-0.bin` (EDC-checked extraction receipt beside it).
  - Checkpoints: f600 `a40ddab1…`, f1200 `5caef9e1…`, f3000 `a6f7f4ad…`,
    f10200 `7049c389…`, f10800 `e5bd5164…`.
  - The f3000 → f10200 → f10800 chain is one verified restore lineage:
    `continuation-release` → `navigation-release-late` → `menu-release` under
    `/home/dev/neptune-research-private/27/`.
- `tools/saturn_lab/sample_workram.py` (passive lineage sampler): SHA-256
  `79ff1ccc14b2772c443797eefd856a9fee11aa9b3b343fb11fd386ce3c7de10c` at this run.
  The private recipe is `$RE_EVIDENCE_DIR/scripts/vblank-runs.sh`: three
  `--checkpoint` directories in lineage order, `--value
  frame_counter=06006038:4` and five more values, six `--witness` ranges, and
  `--expect-rate frame_counter=1/1`.
- No Ghidra/JDK was installed. The stdlib tool plus the pinned upstream
  implementation is the current "equivalent" project. Ghidra 12.2/JDK 25 has a
  factory recipe (`tools/factory/provision_ghidra.py`) that is not installed on
  this VPS.

## Run log

### 20261105T0632Z, slice 1 (PR #838, merged 07:20:28Z by native auto-merge)

Moved:

- First measured USA KRNL and BOOT function inventories.
- Independent decoder and descent, tested on 16 synthetic cases.
- Cross-implementation comparison, deterministic repeats, and a base/byte-order
  negative control (KRNL passes; BOOT not applicable, recorded).
- First runtime residency for BOOT (exact at f600).
- KRNL code/literal versus runtime-mutation cross-tabulation: 0 code changed.
- Reconciliation of all 199 upstream runtime-learned targets (all inside
  functions) and of prior Neptune entries.
- Five `SYS_SETUINT` interrupt-handler registrations identified statically.
- Note: [2026-11-05 USA function inventory](../../research/2026-11-05-usa-function-inventory.md).
- Receipt: [evidence JSON](../../evidence/2026-11-05-usa-function-inventory.json).

Retained failures and refinements:

- The first base metric (tier-A only) had no power. It was replaced by the
  whole-image `bsr`/literal agreement.
- A stub rule false positive at `060BD924` (a data table) was caught by residency
  and the rule was narrowed.
- The BOOT `bsr`/literal test fails because BOOT has no `bsr` call signal. The
  rule was not changed.

### 20261105T0632Z, slice 2 (#492 natural counter lineage)

Moved:

- Passive samples from one verified restore lineage (f3000 → f10200 → f10800).
  - The VBlank-OUT counter `0x06006038` (handler `06006368`) advances exactly
    once per emulated frame: +7,200 and +600.
  - Pad-port counters `0x06006100`+ advance +4,347 and +428 (60.4% and 71.3% of
    frames), a separate tick domain.
  - The VBlank-IN word `0x060B2D20` stays at 5.
- Code witnesses held throughout; four negative controls fail as required; the
  repeat report is byte-identical.
- Note: [VBlank counter lineage](../../research/2026-11-05-usa-vblank-counter-lineage.md).
- Receipt: [evidence JSON](../../evidence/2026-11-05-usa-vblank-counter-lineage.json).

Correction: the slice-1 note and #492 comment gave the handler registration order
backwards. `060064E0` (`0x40` → `06006652`, `0x41` → `0600665C`) runs first, then
startup re-registers `0x41` → `06006368`. The inventory note is corrected.

### 20261105T1310Z (stopped at the usage limit; work recovered in 20261105T1835Z)

- Built the private differential-test harness and decompiled the 8 functions
  above. All vectors were identical and the mutants were detected.
- Started the pinned Ghidra 12.2 / JDK 25 download (hash-checked).
- Nothing was committed before the limit hit.

### 20261105T1835Z

- Re-ran the recovered harness and committed it (private `6539e50`), with the
  progress file (`f97b25b`).
- `make split && make check`: 19/19 byte-identical with the renamed KRNL
  symbols.
- Unpacked Ghidra 12.2 and JDK 25 under `$RE_TOOLS_DIR/ghidra-12.2/`.
- Runs 0801Z to 1400Z ended at the usage limit. Run 1125Z was killed
  (rc 143). None of them added results beyond the above.

### 20261105T2255Z (start of run)

- The 1835Z run had also committed three playing-field functions in C
  (`f9a8578`), each passing the difftest with every original instruction
  covered and all effective mutants killed. The progress file and this
  ledger still said 8. Private `34b1ea8` corrects the counts to 11 and adds
  `tools/difftest/probe.py`, which lists the memory an original function
  reads and writes, to help draft difftest specs.
- The 1835Z run also produced Ghidra 12.2 headless decompiler drafts for all
  4,869 KRNL functions in 90 s under the heavy lock (private
  `tools/ghidra/drafts.sh`). The drafts stay in lane evidence and are not
  committed.

### 20261105T2255Z (main work)

- 104 more KRNL functions in C, each NONMATCHING-verified by the private
  difftest: every vector identical, at least one mutant killed. Six new files
  cover the stage system, view/scroll and items (table above). Private head
  `66f6f03`.
- `make split && make check` gives 19/19 byte-identical with the renamed
  symbols and the 6 new entries.
- Harness additions (private `tools/difftest/`):
  - per-stub argument counts;
  - a `bit` stub return;
  - libgcc1 helper symbols accepted.
- Compiler finding: GCC 2.7.2.3 with `-mhitachi` miscompiles multiplies when
  many values live across calls. The option makes MACH/MACL call-saved but
  leaves them fixed. The allocator then hands them to pseudos that cross
  calls, and the next `mul.l`/`mulu.w` overwrites MACL. The difftest caught
  this twice. `tools/difftest/build-cc1-macfix.sh` builds a cc1 that also
  excludes the fixed registers there (3 lines in `global.c`/`local-alloc.c`);
  new receipts use it.
- Rules found while writing the C:
  - SHC passes 16-bit values sign-extended through a stack round trip, so C
    parameters are `int` with explicit casts.
  - Orchestrators go in their own files, so their callees run as original
    code and can be stubbed.

### 20261106T0010Z to 20261106T1825Z

- Five runs stopped at the usage limit within seconds of starting. No results.
- Run 20261105T2255Z had also left `bomb.c` (20 functions) with passing
  receipts uncommitted when it hit the limit. Run 20261107T0450Z registered and
  committed it.

### 20261107T0450Z

- Committed the leftover bomb work (private `aa87ad9`): 20 functions over the
  bomb list. They find the bomb on a cell or of an owner, set off every lit
  bomb on a cell or of a player, mark and unmark cells, and pick the animation
  frame.
- `bomb_move.c` (private `1d9b04b`), 12 functions on moving bombs:
  - stop a bomb on its cell (fuse at most 1, motion bits off, cell re-marked);
  - stop every lit bomb;
  - probe the cell one step ahead (pixel offsets per direction, then field wrap);
  - test whether that cell blocks the bomb (field bits `0x42B0` or auxiliary
    bits `0x7000`);
  - reverse direction (1↔3, 2↔4);
  - one-pixel step in the bomb's direction;
  - keep the bomb's second actor in step;
  - carry the bomb on its owner and move it one pixel toward the owner.

  It also found one more tail-branch entry, `0601F5AC`.
- `pdec.c` (private `79ddb79`), 73 functions: a predictive stream decoder in
  KRNL (`0x06033DF0`-`0x0603443C`).
  - The state record holds input and output pointers, a history ring with
    index mask and write index, and bit buffers.
  - The helpers read and write 8/16/32-bit big-endian samples and append to the
    ring.
  - The predictors are "previous sample ± 1..32" and "the sample 2..64 entries
    back".
  - The bit-field readers take 1, 2 or 4 bits, low bits first, or 3 bits, one
    from each of three bit planes.
  - A mode byte selects the sample width (1, 2 or 4 bytes) and the predictor
    tables.
  - The driver `0603443C` is still asm.
- Tools added to the private `tools/difftest/`:
  - `progress_md.py` regenerates the lane progress file from the status file
    and receipts;
  - `mkspec.py` writes difftest specs from a compact table.

### 20261107T1225Z

- Finished the interrupted run's two batches: `small15.c` (22) and
  `small16.c` (32) KRNL functions NONMATCHING-verified (private `d6514326`).
- Decompiled and verified the core bomb/fire chain:
  - `fire_spread` (`0601EA10`, private `9643d9b7`): recursive four-side walk;
    joins bombs, burns items and soft blocks, stops at hard blocks and
    recurses around corners.
  - `fire_cell.c` (private `9398c83b`): `0601E300` makes the effect layer
    current, draws the cell metatile and marks the hidden bomb; `0601E336`
    picks the fire record fields, sets the cell bits and draws.
  - `fire_mark_cell` (`0601ED54`, private `910c7527`): battle hidden-map mark
    and the hand-off to the effect update.
  - `bomb_update_all` (`0601EDD2`, private `b6e44f7d`): per-frame bomb list
    walk, held/ticking fuse, explosion start, fire-pass hand-off.
  - `effect_update_all` (`0601E3F0`, private `fea07d4e`): per-frame fire
    effect records, cell draw/clear, exploding-bomb follow, phase transfer.
  - `bomb_try_hold` (`0601FA22`, private `937a1ca5`): start carrying the lit
    bomb on a cell (held flag, direction, mode 4).
  - `bomb_throw` (`0601FB04`, private `944b858c`): throw/carry step off the
    cell in front; the same commit fixed the hold/throw predecessor-next
    return, and the hold spec now covers 99/99 PCs.
  - `fire_record_alloc` (`0601E13C`, private `0c82771a`): fire-effect record
    allocator (free-slot search, chain insert, phase/owner fields).
  - `bomb_scene.c` (private `4ac435fd`, `6ea66919`): seven bomb/scene task
    helpers (`0601D7A8`, `0601D7E4`, `0601D812`, `0601D84A`, `0601D9F0`,
    `0601D734`, `0601D962`): place-animation finish, task end, timer
    subtract, script start.
  - `bomb_table_reset` (`0601DB4C`, private `d486d720`): clear the 50 bomb
    and 2000 fire-effect records, re-link the heads and reset the serials;
    the two hardware init callees are stubs in the difftest.
  - `bomb_record_insert` (`0601DE4E`, private `6831c764`): link a placed bomb
    between the record-1 predecessor and the head, copy fuse/owner/cell and
    mark the cell.
- Receipt audit: all receipts match their current source files
  (private `5fb9c5a7`); the new receipt is current too.
- KRNL: 4,876 entries, 1,077 NONMATCHING-verified, 0 MATCHING (SHC blocker);
  krnl split + `make check` byte-identical (19/19).

### 20261107T1350Z

- 130 more KRNL functions NONMATCHING-verified, all short wrappers that call
  one or more functions and often end in a tail call:
  - `small17.c` (45, private `5e8c808e`): task start-up, scene step chains,
    menu entry checks, map flag updates, 16-bit result clamps;
  - `small18.c` (85, private `854c827e`): menu entry checks (a test call
    followed by the menu step), menu value hand-offs, scene start-up chains,
    16-bit result retries, a clamped plane-colour set-up and record
    state-pointer setters.
- Difftest tool changes (private `tools/difftest/`):
  - new stub return kind `mem:ADDR`: the stub returns a fuzzed RAM word, so
    both sides of a branch on a callee's result run (a hash of constant
    arguments is constant and left one side untested);
  - pointer globals read through record macros are redirected to fuzzed
    scratch blocks by the batch generator;
  - `run_retry.sh`: six specs per heavy-lock process, re-running any spec
    whose process was ended by a signal. An unrelated agent on this host was
    running `pkill` during this run and ended several difftest processes
    with SIGTERM before they printed results.
- Later in the run (private `5e8c808e`..`90cb5f02`), 431 more:
  `small19.c`..`small32.c`. Most are object (enemy and boss) state handlers:
  each runs the shared state test, sets the next handler and ends the step,
  or arms a timer field of the current object record. The rest are scene
  start-up chains, menu entry checks, CD-block command entry checks, stream
  record counters, 16.16 sine/cosine quadrant folds, string helpers and
  record-table clears.
- Three entries the inventory missed (`060266E6` pointer entry, `06059A2A` and
  `0606AA06` after another function's `rts`); KRNL static entries are 4,879.
- Generator directives `@memstub` and `@range` (fuzzed callee results and
  bounded global values), and argument kinds for self-pointing records.
- End of run (private `6e37bd54`, `small33.c`..`small40.c` added after
  `90cb5f02`, `small38.c`/`small39.c` are bomber helpers): KRNL 4,879 entries, 1,754
  NONMATCHING-verified (677 this run),
  0 MATCHING (SHC blocker); krnl split + `check.py` byte-identical (14/14 USA
  modules), `make audit` clean. About 320 of the run's functions are object
  (enemy/boss) state handlers.

## Frontier (ranked)

1. **Bomber, bomb and explosion code.** Object records are at `0x060D5F30`
   (124 bytes; `0x060D7768` points at the current one). Bomb count is at +76
   and fire range at +78, as `item_pickup` shows. Bomb records and bomb
   movement are in C (`bomb.c`, `bomb_move.c`). The fire chain
   (`0601EA10`, `0601E300`, `0601E336`, `0601ED54`, `0601EDD2`, `0601E3F0`)
   and the hold/throw helpers (`0601FA22`, `0601FB04`) plus the record
   allocator (`0601E13C`) are now in C. Next: the throw/carry state machines
   `0601F830` and `06020560`, and the item special actor `0602277C` (uses SHC
   runtime helpers).
2. **Object (enemy/boss) state machines** (`0x0606C000`-`0x06094000`): the
   small handlers are mostly in C now; next are the larger per-object
   handlers and the shared state test `0606CF3E`.
3. Stage system leftovers: the per-stage hooks (`0x060B30C4`), the view task
   `0600D6B2`, the timer `0602ED18`/`0602ED56`.
4. **Scheduler and per-frame order (#492).** `060061C4`/`060061E6`/`06006D36`
   and the VBlank handler `06006368`. Ordering still open: pad read, game task
   and presentation within a frame.
5. Ghidra drafts of all 4,869 inventory functions exist in lane evidence
   (`tools/ghidra/drafts.sh`). They are a starting point for the C, not
   evidence.
6. **BOOT game-side functions.** BOOT is GCC output, so they can be MATCHING.
   Coordinate with code-map, which owns BOOT's library units.
7. **Blocker for KRNL MATCHING:** the owner must supply Hitachi SHC (the
   1995-96 SH C compiler).
8. Earlier measurement items stay open: dynamic interrupt handlers, overlay
   loader, unclassified KRNL halfwords and BOOT's `0x0604B4B0` lifetime.
