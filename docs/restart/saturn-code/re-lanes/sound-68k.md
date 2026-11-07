LANE-STATUS: ACTIVE

# Lane ledger: sound-68k (68000 sound drivers and SCSP/DSP)

## Charter

Recover every original 68000 sound-CPU program and the SCSP DSP programs it
loads, plus the SH-2 command protocol that drives them:

- SND: `BOMSS/PROGRAM.BIN[0x44:0x6418]`, the main game driver;
- NLSND: `NETLINK/SNDDRV.BIN`;
- XBSND: `XBAND/XBAND.DAT[0x11868:0x17C3C]`.

Issues: #488 (parent), #665, #703, #707, #489.

Priorities:
1. Measured SND function inventory with a denominator.
2. Command dispatcher, handlers and mailbox protocol.
3. Sequence format/interpreter, then sample-timed playback comparison.
4. NLSND/XBSND: recover only what differs from SND.

**Denominator:** all 68000 functions in the three drivers, plus observed DSP
programs. Ownership: do not edit Codex's Japan kernel chain, Gemini's #464
scope, the Factory, or other lanes' ledgers. Earlier NLSND work (#600–#703
probes, `probe_netlink_*`) stays accepted and is reused, not repeated.

## Status (run 20261107T1351Z, private head 1fbdfdb1)

This run added two asset categories that earlier counts missed; the driver
counts below are unchanged.

- **XBAND sound banks.** XBAND mode keeps its own audio as 24 items of the
  XBAND client database, stored after the XBSND driver copy in
  `XBAND/XBAND.DAT`. Each item's data starts 2 bytes before its listed offset
  (five independent header witnesses, and the corrected items tile the file
  with 10 leftover bytes). In id order the items form six driver records,
  named by their own area map: 2 tone banks (27 voices, 28 samples), 2
  sequence banks (19 songs, 1,988 events, one MIDI file each), 1 DSP program
  (24/128 non-zero steps, a different program from the game's) and a DSP work
  area. All 19 songs agree with the original `0x537E` fetch routine in the
  isolated 68000 probe (16,631 calls, 6/6 negative controls rejected, two runs
  byte-identical). Finding: the map reserves 321,538 bytes for the first tone
  bank, but the bank as stored is 352,586 bytes and one voice's sample runs
  31,046 bytes past the reservation. NetLink and the XBAND/field executables
  hold no further sound-bank records. XBAND's own loader (`0x060A2AC4` in
  `XBAND.BIN`) was read later in the run. It initialises the driver from two
  database items, then walks the area map in order and asks an XBAND OS
  service to copy a fixed run of items to each entry's address. It requests
  all 15 tone-bank items, so the next two banks, loaded after it, overwrite
  the tail of that voice's sample. That one-shot is played whole by one of
  the 18 one-note songs, so in XBAND mode about the last 0.7 s of it would
  come from other data, unless the OS service (not on the disc) truncates
  the copy.
- **Sound-ID table (SH-2 side).** KRNL contains Sega's host-side SND library
  for this driver; its sequence-start routine (`0x0609E78C`, command 0x01:
  slot, bank, song, priority) has exactly one caller, the game's play-sound
  routine `0x0600996A`. That routine reads a 4-byte record per sound ID from
  resource kind 10 of PROGRAM.BIN banks 1/2 and skips an ID already started
  in the same sound-task pass. The table has 322 records (identical in both
  banks); a second table lists 20 streamed voice-clip AIFF names, one of which
  (`M_087.AIF`) is not on the USA disc but is on the Japan disc. A static scan
  finds 384 call sites (57 of them tail calls): 377 pass a constant ID (247
  distinct, with the item-pickup table), 7 are computed or user-selected. A
  forward dataflow re-check resolves every site the backward scan called
  dynamic. The scan agrees with every play-sound call in usa-code's verified
  C (8 sites). Each record is
  resolved to a song file in every sound context where it exists (all 322
  resolve somewhere).
- **Tone banks verified against the driver.** SND's voice start routine
  (`0x3552`, up to the instruction after its pan write) was run in the
  isolated probe for every layer of all 124 unique tone banks (USA, Japan,
  XBAND): 400 layers, 648 runs covering mono and both stereo pan paths. The
  slot registers it writes (start address relative to the bank, loop
  start/end, loop mode, 8-bit flag, envelope, LFO, input and pan fields)
  equal the extracted metadata in every run. 4/4 negative controls are
  rejected, and two runs are byte-identical.
- **DSP listing is lossless.** An encoder that inverts the decoder rebuilds
  all 128 steps of both DSP programs byte-identical from the listed fields.
- **Game DSP program checked against the original core.** The extracted
  program, coefficients, addresses and ring-buffer settings equal what the
  original driver left in the reference core's DSP after the natural
  7,200-frame run (the hashes already published in the 2026-11-05 evidence),
  under the SCSP register mapping. This checks the loaded state, not
  execution of the microcode.
- **Banks found in the reference core's sound RAM.** Every extracted tone,
  sequence and DSP payload was searched for in the sound RAM of saved
  reference-core states: 12 picked states (menu, navigation, opening, normal
  stages, battle, Master, five bosses), then every 4th of the assets lane's
  1,175 captures (1,088 distinct sound-RAM images). 51 of the 101 unique
  payloads, from 24 banks including 13 voice banks, are present byte for
  byte, nearly always at the address their own area map gives. The only
  off-map cases are tone data reused under another id and a tone-container
  member, which has no map id. Every one-byte-flipped control is absent.
- **Debug sound test and library versions.** The kernel holds a hidden test
  menu (movie player, clip player, sound-effect test, ending). Its
  sound-effect test plays the chosen number straight through the play-sound
  routine, so its numbers are the table IDs. Its sound blocks are the same
  eight contexts as the scene loader. How the menu is reached is open. The
  kernel names its Sega file-system and stream libraries as version 2.10
  (1996-02-01) and its PCM library as 1.15 (1995-02-21). The sound command
  routines carry no version string.
- **Japan sound IDs.** The recipe now derives every routine and table
  address from the code, so it runs unchanged on the Japan kernel (base
  `0x0600A000`). Japan has the same 322 records and clip names. One
  item-pickup entry differs between the releases. After the scan learned to
  follow callee-saved register copies and constants spilled to the stack:
  USA has 384 sites (377 constant) and Japan 375 (368). No ID is used by
  only one release. The 7 sites left per release are six computed lookups
  (per-player offsets, a 4-entry table, the item table) and the debug SE
  test, whose ID is user input. The two former "argument wrappers" pass the
  constant 4; their r5/r6 arguments go to another routine.
- **Which banks load when.** The scene loader picks the sound bank by game
  mode and world: normal worlds 1-5 each have their own bank, and battle and
  Master one each. Voice banks come from constants or from two per-player
  tables. None of these paths reaches the three headerless voice-bank slots,
  which agrees with their being leftover sectors.
- **Voice clips.** The clip-name table's only reader is dead code, and it
  would step 16 bytes per entry over 15-byte names. The game instead streams
  clips by name through one routine, found from the data: every clip-name
  load leads to it. 11 clips are named by constants and 7 through a small
  name table. Two listed clips (`M_037`, `M_087`) are named nowhere in the
  kernel code of either release.
- **Gap (cross-lane): the SH-2 library source.** The kernel's host-side SND
  library (39 inventory functions at `0x0609E28C-0x0609FB00`) and its PCM
  stream routines are mostly generated assembly, with 3 NONMATCHING-verified
  by usa-code. Their differential harness stops when fuzzed pointers reach
  sound RAM, so they need a sound-RAM memory mode first. usa-code was working
  on the kernel at the same time, so this lane added no kernel C. The bounded
  fix (recorded privately) is a flat, checkpoint-seeded sound-RAM region in
  the harness memory, compared after each run like Work RAM.

## Status (run 20261107T1311Z, private head fb272a2c)

Counts are reported separately and are not rounded up. SND is hand-written
68000 assembly, so its source is annotated symbolic assembly. A function is
MATCHING when its whole inventory range lies in annotated, reviewed units:
named labels and fields, tables as label expressions, no raw splitter words,
and the whole file rebuilds byte-identical with the pinned binutils. Eight
mutated-source controls are rejected.

| Driver | Functions | MATCHING (annotated asm, byte-identical) | NONMATCHING-verified | generated asm only |
| --- | --- | --- | --- | --- |
| SND | 146 | 146 (56 of them 4-byte dispatch/table entries) | 0 | 0 |
| XBSND (same bytes as SND, same source) | 146 | 146 | 0 | 0 |
| NLSND | 132 | 132 | 0 | 0 |

Both 68000 sources are now complete annotated assembly and rebuild
byte-identical: SND `c8842cc9…bd04` (146/146, `0x2534` closed in the previous
run) and NLSND `f3728939…2296` (132/132 this run, including the
`0x40C8-0x4BE0` stream engine, the `0x18F2-0x1EEE` command handlers, the
`0x2072-0x3504` voice layer and the `0x0000-0x17C4` boot/vector/reset unit).
XBSND is the same bytes as SND and uses the same source. Identical tables
found across drivers are reused verbatim (SineTable, PitchOctTable,
PitchFnsTable). The stream dispatcher masks its sub-command with 7 but each
branch table has five entries, and `VoiceRegTable` has 31 records, so those
out-of-range indexes read neighbouring data; kept as written and documented in
the source. No raw splitter lines remain in either file.

The one EXB DSP program is now decoded as raw microcode: 84 non-zero steps out
of 128, identical in both releases (`730cff6f…f194`). Private
`tools/sound/scsp_dsp.py` parses the record (0x40 header, 0x100 COEF/MADRS,
128 x 8-byte steps) and prints every field, with synthetic tests in
`test_scsp_dsp.py`; the listing and field map are in `docs/sound/EXB_DSP.md`.
This is a decode, not a high-level algorithm reconstruction.

Regional target check: the USA and Japan `PROGRAM.BIN` containers differ
(`f5154d4a…` vs `928b959f…`) but both hold the same SND driver at `+0x44`
(`c8842cc9…bd04`). The Japan disc contains no `NETLINK/SNDDRV.BIN` and no
`XBAND.DAT`, so NLSND and XBSND are USA-only; SND's source applies to both
releases. Read directly from both cue sheets with `tools/saturn_disc`
(USA `785e6f9f…`, Japan `ac6c34bb…`). The private regression test now builds
both sources byte-identically and rejects three mutations for each (SND and
NLSND, via `SND_DRIVER`/`NLSND_DRIVER`). The DSP test pins the committed EXB:
asset hash, USA/Japan equality, and 84 non-zero steps. Final private commits also
replaced the stale "not yet annotated" section in `docs/sound/SND_DRIVER.md`.

Timing facts read from the source (tick-rate frontier closed):

- The driver's time base is the SCSP Timer B interrupt. It is reloaded every
  88 samples, so it runs at 44100/88 = 501.14 Hz. The three natural snapshots
  give 88.00–88.05 samples per interrupt at Beetle's NTSC 59.826 fps.
- The tempo code assumes 500 calls per second: ticks per call
  = 2000 × resolution / µs-per-beat, counted in 1/256 ticks. Sequenced music
  therefore runs 0.23% fast, plus integer-division rounding. Event times are
  exact running sums of the steps, because each overshoot carries over.
- Timer A (178 samples) is polled by the main loop. It drives fades, pitch
  updates (8 voices per tick, so each voice every 4th tick) and the effect
  load. The Timer B handler clears Timer A's pending bit too, so polled
  Timer A events are lost. That explains the earlier natural rate of
  ~240 samples per tick.

Driver behaviour found "as written" (kept byte-exact, documented privately):

- The high-command table's last entries are 6-byte jumps in a 4-byte-stride
  table, so commands 0x8C, 0x8D and 0x8F enter mid-instruction.
- Controllers 120/123 branch two bytes short of their all-notes-off routine,
  so they do nothing.
- The voice layer ignores channels 16–31. No song in either release uses
  them.
- A queued note off stores its port shifted.
- One routine saves SR after masking interrupts.
- Pitch-bend range 14 enters mid-block.

Driver-verified asset model (this is not a source reconstruction and is not
counted above): the private Python model of SND's sequence fetch routine
`0x537E` (event fetch, sequence start, tempo start, tempo next) agrees with
the original 68000 routine on every compared call in the isolated Musashi
probe (ABI1). USA: 36,343 calls; Japan: 36,350. Each covers 240/240 songs
(17 unique banks, two loop passes where a song loops), all 256 first bytes
four times, and 600 seeded random streams. Six negative controls are rejected:
three model mutations, two driver byte patches and a wrong record number. Two
runs of each report are byte-identical. Format findings, in our own words:
`step` is the delay before an event and `gate` the note length; the tempo
map loops (all 240 songs carry a tempo loop offset; 226 have one tempo);
extension bytes add fixed step/gate amounts; a reference plays n events
elsewhere and returns. Runs that need more than the probe's 256-instruction
cap resume exactly from the reported registers and memory (15 calls in total).

Audio assets (private repo, `assets/<release>/sound/`, every output hashed in a
manifest; offline check: 1,649 outputs, 0 problems):

| Category | USA | Japan |
| --- | --- | --- |
| Tone banks (WAV with loop/envelope metadata) | 115 banks (83 unique), 220 samples | 93 banks (59 unique), 195 samples |
| Sequence banks | 33 (17 unique), 240 songs, events + one MIDI file per song | 33 (17 unique), 240 songs |
| DSP programs | 10 (1 unique), raw + decoded microcode listing (lossless), equal to the reference core's loaded DSP state | 10 (1 unique) |
| ISO audio files | 131 | 20 |
| CD-DA tracks | 29/29 FLAC, decode-verified to the source PCM | 29/29 |
| XBAND sound banks (run 1351Z) | 2 tone banks (28 samples), 2 sequence banks (19 songs, MIDI), 1 DSP program, 1 area map | none on the disc |
| Sound-ID table (run 1611Z) | 322 records, 20 clip names, 28-entry item table, 384 call sites (377 constant), 17 clip-stream sites | same 322 records; 375 call sites (368 constant), 16 clip-stream sites |
| Sequencer render (run 1611Z) | 11 songs through the original driver (maps 0/2): 330 events, 70 note-offs, 0 mismatches; control rejected | not run |

FLAC files (247 MB per release) stay in `$RE_ASSETS_OUT` with committed
manifests (FLAC and PCM hashes).

## Measured denominator (2026-11-05, updated run 20261105T0750Z)

| Driver | Identity | Function entries | Executed naturally | Status |
| --- | --- | --- | --- | --- |
| SND | `c8842cc9…bd04`, 25,556 B, embedded "Ver2.04 96/01/25" (Sega Saturn sound driver) | 146 union (141 resident + 5 patched-out disc-only); 3 interior | 58 in accepted 7,200-frame window (60 with single-run pause window) | 20 with complete isolated contracts; 2 partial; 124 open |
| XBSND | same bytes as SND | same 146 static entries | not run (XBAND lifetime) | byte-identical; natural lifetime and patching open |
| NLSND | `f3728939…2296`, 23,920 B, embedded "Ver1.31 95/06/20" | not yet inventoried with this tool | not run | earlier isolated handler probes exist (#600–#703) |
| DSP programs | SCSP `DSP.MPROG` hashes | — | SND lifetime: 1 (`b8c82dd4…`, 84 steps); pre-SND program: 1 (`13700781…`, 100 steps) | microcode not decoded |

Other open counts for SND:
- Unclassified resident bytes: 10,826, including the 3,072-byte work area at
  `0x400–0xFFF`. Of these, `0x53E0–0x54DF` is now identified as a zero-filled
  runtime record table (static `lea` witness at `0x5380`, natural writes).
- Unreferenced code-like candidates (unproven): `0x2E8A`, `0x3D0E`, `0x5356`,
  `0x1A46`.
- Runtime code patches: **resolved**. SND's boot routine `0x1768` writes the
  seven NOP sites itself, gated by host byte `0x4E1` (`0x00` in the image).
  `0x141E` is a self-modifying 4-phase counter. The previous "759 work-area
  bytes" at frame 7200 are 684 bytes in `0x416–0xD9F` plus 75 bytes in the
  record table.
- The pre-SND epoch-0 program (frames 52–1280) is a different resident
  program; its loader and identity are open and it is outside the SND count.

Recovered-semantics count (boundaries, ABI, state, callers and behaviour, with a
negative control): **20 of 146 SND entries**. They are `0x1768` (self-patch),
`0x1A60` (executor) and 18 dispatch-table stubs whose whole body is a return or
ignore path (`0x1B6E`, `0x1BAA`, `0x1BBE`–`0x1BEA`, `0x1AEA`, `0x1B06`,
`0x1B0E`, `0x1B12`). There are also 2 partial entries (`0x1B0A`, `0x1B16`),
which reach a device-write guard. The 28 handler-bearing table entries have
verified dispatch but open bodies. See
[the mailbox note](../../research/2026-11-05-snd-command-mailbox.md).

## Tool pins

- Isolated CPU: ABI1 `libneptune_m68k.so` `cc059d3a7f443cf2869496c245f9acae357b1f773e054e2ac009e5632df2c83c`
  (prepared with `m68k_probe.py`, gcc 14.2.0-19, about 20 s), at
  `$RE_TOOLS_DIR/m68k-probe-abi1-001`.
- Pinned decoder: saturn-recomp `f20de940` (`/home/dev/neptune-tools/saturn-recomp-f20de94`),
  source hashes in `analyze_sound_driver.TOOL_HASHES`; decoder cache is private.
- Reference core: Beetle `01bc063f`, tree `2522acca`, `.so` `c862380e…`;
  USA lock file `eb0d91e0…`.
- Coverage core ABI1: binary `fa0f92ec051dea0df13ea0de435eb4cf9203363f6ca4892b27a0763fbb24787a`.
  Built twice from `tools/saturn_lab/m68k_coverage_core.py` with
  gcc 14.2.0-19; only `m68k.c` is recompiled (~32 s).
- Tool hashes at evidence time are recorded in
  `docs/restart/evidence/2026-11-05-snd-natural-function-inventory.json`.

## Run log

| Run | Result | Notes |
| --- | --- | --- |
| 20261105T0635Z | PR [#840](https://github.com/elgansayer/Neptune-Bomberman/pull/840) | Added the coverage observer, runner and inventory join, with 14 owned tests. Natural cold-boot windows: reference + 2 enabled, 7,200 frames, identical. SND inventory 146 entries; dispatcher map; 8 runtime patches; DSP identities. The first core preparation failed its own smoke (re-armable `begin()`), was fixed before evidence and retained privately as `failed-prepare-001-rearmable-begin`. |
| 20261105T0750Z | PR [#863](https://github.com/elgansayer/Neptune-Bomberman/pull/863) | Added `probe_snd_mailbox.py` with 18 owned tests and no new emulator run. Self-patch `0x1768`: 512 isolated cases, 4 controls; the resident image is derived exactly from disc + isolated writes (`0x4E1 = 0`). Executor `0x1A60`: 9,216 cases over all 256 command bytes, 7 controls, and a natural replay of 89 records. The natural command stream (89 records) matches coverage dispatch counts and the 49,526 vector-26 interrupts exactly; 5 natural-data controls are rejected. Two fresh reports are byte-identical (`2376d1f7…af0`). The first executor contract draft was wrong (offset masked after the add) and was rejected by execution, then corrected from the listing. |
| 20261106T0931Z–20261106T1826Z | none | Usage-limit stops. The 0931Z result line cited assets-lane PRs by mistake. The private sound tools were committed (`8631c44`); the sequence model was left uncommitted. |
| 20261107T0451Z | this PR | Committed and verified the sequence model: `verify_seq_fetch.py` runs the original `0x537E` in the isolated probe on all songs in both releases plus synthetic streams, with 6 controls (above). Added the tempo-map loop, which the earlier draft ignored. Committed all audio assets for both releases, including per-song events and MIDI. Japan PROGRAM.BIN now extracts. Harness lessons: data regions may not overlap executable ranges, so the routine runs with per-request range sets (request 1 runs as 2 exact segments). Range ends must include the last instruction's extension words (the first try stopped at `0x5770`). |
| 20261107T0451Z (cont.) | this PR | Wrote the SND source as annotated 68000 assembly: 145/146 functions, byte-identical (above). The source check (private `snd_source.py check` plus tests) counts a function only when its whole range is annotated, and rejects duplicate labels. Lessons: GNU as cannot resolve a short branch to a global symbol (it becomes an 8-bit relocation), so short-branch targets stay local. Hand-written branches must keep the original `.s`/`.w` sizes. Two label names collided, and 9-character names starting with "M" collided with the splitter's marker parsing, so the check now assembles by itself. |
| 20261107T1311Z | PR #930 | Closed the remaining NLSND units: `0x40C8-0x4BE0` stream engine (five command tables, indirect dispatcher, the `0x4442-0x4764` handler block the splitter had emitted as words, StreamTick/VoiceTick/SCSP pollers), `0x18F2-0x1EEE` sequence command handlers, `0x2072-0x3504` voice layer (SeqTrackStep jump tables, SeqEventDrain, the `0x27BE` release routine reclaimed as code, SineTable), `0x35DE` VoiceInit with PitchOctTable/PitchFnsTable, and `0x0000-0x17C4` boot/vectors/reset (256-entry vector table with symbolic targets, version string, main loop). SND `0x2534` had been closed before this run. Both sources: 100% annotated, byte-identical, 0 raw lines. Also decoded the one EXB DSP program (`src/usa/snd/snd.s` EffectTick loads 0x500 bytes to 0x100700; 0x100 COEF/MADRS + 128 x 8-byte steps): 84/128 non-zero, identical USA/Japan, synthetic-tested decoder and full listing in the private repo. Harness lesson: GNU ld pads a `.text` at an odd 4-byte boundary, so generate dead-code fragments at origin 0 and shift labels rather than linking at the real address. |
| 20261107T1351Z | PR #934 | Found two uncovered asset categories. XBAND: the 24 database items in `XBAND.DAT` start 2 bytes before their listed offsets; regrouped by their own area map into 2 tone, 2 sequence, 1 DSP program records (new `xband` recipe subcommand, 60 outputs), 19/19 songs verified against the original fetch routine with 6 controls. Sound IDs: KRNL's SND library command map, the single play-sound entry, the 322-record table in PROGRAM.BIN banks 1/2, voice-clip names (one missing on the USA disc), item-pickup table, 384 static call sites cross-checked with usa-code's C (new `sound_ids.py`, 7 synthetic tests). The recipe refactor reproduces both releases' program-bin outputs byte for byte. Harness lesson: tail calls (`jmp @Rm`) carried 57 of the call sites; a `jsr`-only scan missed the explosion sound. |
| 20261107T1351Z (cont.) | PR #936 | Tone-bank decode verified through the original voice start for all 124 unique banks (648 runs, 4 controls). DSP listing proven lossless by re-encoding. The sound-ID recipe derives addresses from code and covers Japan, and follows callee-saved copies (16 computed sites left per release). Voice-clip streaming map, with two listed clips named nowhere in kernel code. Implementation issue #935 (sound triggers by ID) filed for the factory. Harness lesson: the isolated probe maps sound RAM only (regions must lie below `0x80000`), so slot writes need an a5-relative stand-in slot. |
| 20261107T1351Z (cont. 2) | PR #937 | Read XBAND's SH-2 sound loader: area-map order, fixed item runs through an OS copy service, so the first tone bank overruns its area and one voice's tail is overwritten. The sound-ID scan now follows constants spilled to the stack slot (11 computed sites per release), and the computed ones are described. Added a Counts section to the private progress page (it had none), with the SH-2 library listed as 39 functions, 3 NONMATCHING-verified by usa-code, plus the bounded harness fix. |
| 20261107T1351Z (cont. 3) | PR #938 | Generic public tool `tools/saturn_lab/sh2_call_args.py` (call sites of an address and constant argument registers, by the same rules as the private sound-ID scan), with 11 owned synthetic tests; run locally on the USA kernel it reproduces the private counts (384 sites, 375 constant). Private follow-ups: NetLink WAV names are built in the boot program from 14 event names and a numbered `%d.WAV` variant (all 112 reachable); resource kind 10 entry 3 is a 1-bit glyph font, not sound. |
| 20261107T1351Z (cont. 4) | PR #939 | Scene → sound-bank and voice-bank selection read from the kernel with the new scanner (private `docs/sound/SOUND_IDS.md`); the headerless voice-bank slots are unreachable. Context rule added to issue #935. Private head `8fdd3131`. |
| 20261107T1351Z (cont. 5) | PR #940 | The game DSP program was matched to the reference core state already recorded in the 2026-11-05 evidence (pinned private test). The XBAND driver item was found in the client database: its list starts one entry before the recorded offset, a note for the assets lane. Residency check: extracted banks are byte-exact in reference-core sound RAM (sweep of 1,175 states: 51 of 101 unique payloads). Private head `d4ced488`. |
| 20261107T1351Z (cont. 6) | PR #942 | Debug sound-effect test and host library versions found in the kernel. A further 384 battle/item states added no resident payloads (51 of 101 stays). Private head `1fbdfdb1`. |
| 20261107T1611Z | this PR | Shared build: `tools/split/split.py` takes a module-level `source =` and emits a segment that includes the hand-written annotated driver source; `config/usa.toml` uses it for snd/xbsnd/nlsnd and `config/japan.toml` for snd. `make check` is 19/19 byte-identical (snd/xbsnd/nlsnd/japan snd included, and BOOT's embedded NLSND copy follows). Negative control: a one-byte source mutation fails `tools/check.py` at offset 0x1; restoring gives the original hash. Private `9d99455c`. |
| 20261107T1611Z (cont. 2) | PR #947 | Driver-render attempt in the isolated probe. Booting Reset needs the SCSP window relocated below 0x80000 and, because data regions may not overlap executable ranges and only 4 ranges are allowed, more disjoint ranges than Reset/MainLoop + BootPatch/BootCheck + ScspInit + VoiceInit need with their literal pools and the `ScspInitRegs` table at 0x3C42. Reset does reach ScspInit with `0x4E1 = 0x7F`; the 0x3C42 table read is the first fault. Recorded as the blocker for frontier item 4; a render should use the full coverage core. Private `97a3cee6`. |
| 20261107T1611Z (cont. 3) | this PR | Sequencer render. Built a wide variant of the pinned isolated probe (MAX_RANGES/REGIONS 4096, events 65536, data regions to 0x200000; same backend and Musashi pins) and booted the original driver (host config 0x4E1 = 0xFF avoids self-patches). Loaded the PROGRAM.BIN area-map list at 0xA000 with runtime loaded flags and the scene's tone/sequence banks at the map addresses; command 0x08 selects the map, 0x01 starts a song, TimerTick (0x4A00) is called per 88-sample tick. The event ring at (0x450)+0x1A00 is compared with `sound_formats.seq_play`: status type, channel/port, data1/2 and tick (floor(T*256/SLOT_INC), SLOT_INC = 512000/(us_per_beat/resolution)); note-offs are driver-generated and excluded. Eleven songs over maps 0 and 2: 330 events and 70 note-offs, 0 mismatches; negative control (SeqPostEvent type mask #7 -> #6) fails with 8. This is a sequencer render, not an SCSP sample render. Private `1874bd6e`. |
| 20261107T1611Z (cont.) | this PR | PlaySound scan: a forward dataflow pass re-checks every dynamic call site over its function (constants merged on joins, caller-saved registers undefined after a call). Four sites move to the constant 4 (USA `func_060482FC`/`func_06058492`, Japan `func_0603DD82`/`func_0605DC80`); their r5/r6 arguments are pointers for another routine, so the earlier argument-wrapper reading was wrong. Counts: USA 377/384 constant, Japan 368/375; 7 dynamic per release (six computed lookups + debug SE test). Three synthetic tests. Private `8c0baab9`. |

## Frontier (ranked)

0. **SH-2 library source and open IDs.** Verify the kernel's SND/PCM library
   with usa-code, after adding a flat sound-RAM region to their differential
   harness. The remaining 7 sound-ID sites per release are the six computed
   lookups and the debug SE test (user input); the third kind-10 table is a
   glyph font. (Japan IDs and XBAND's loader were done in run 20261107T1351Z.)
1. ~~**Shared build.**~~ Done in run 20261107T1611Z: `make check` assembles
   `src/usa/snd/snd.s` and `src/usa/nlsnd/nlsnd.s` (19/19 byte-identical).
2. **DSP behaviour.** The one EXB program is decoded (84/128 steps); next is a
   behavioural test against the original core, then the sound-ID producer map (#707).
4. **Render through the original driver.** Sequencer render done in run
   20261107T1611Z: a wide variant of the pinned isolated probe (limits raised,
   original driver bytes, host config 0x4E1 = 0xFF) boots Reset, loads an area
   map and scene banks, runs command 0x01 and ticks TimerTick, then compares
   the voice-layer event ring with the decoded model. Eleven songs over maps 0
   and 2: 330 sequence events and 70 driver note-offs, 0 mismatches; the
   negative control (SeqPostEvent type mask #7 -> #6) fails with 8. A
   sample-accurate SCSP render still needs the full coverage core; tone key-on
   and resident payloads are verified separately.
5. **Sound IDs.** USA producer map done (run 20261107T1351Z, above); the
   remaining items are in 0.

## Private evidence (never commit)

`$RE_EVIDENCE_DIR` = `/var/lib/repo-factory/saturn-re-lanes/evidence/sound-68k`:
- `sources/`: the three containers, `SND.driver` and `extraction.json`, all
  hash-checked;
- `static/SND.static.lst`: linear listing of the static descent;
- `mailbox/final-{1,2}.json`: the two identical mailbox reports;
  `try-001.json` (rejected executor draft: offset masked after the add) and
  `try-002.json` (resident derivation rejected before the record table was
  declared) are retained failures; `try-003.json` passed before the timing
  field was added; `check.log` is the full tooling-test output;
- `runs/final-{reference-1,enabled-1,enabled-2}`, `runs/final-comparison.json`
  and the exploratory `runs/explore-*` windows;
- `inventory/final-v2-enabled-{1,2}.json`;
- `inputs/route-gameplay-v1.json`;
- `scripts/`.

Tools live in `$RE_TOOLS_DIR/beetle-m68kcov-abi1-00{1,2}` (coverage cores) and
`$RE_TOOLS_DIR/m68k-probe-abi1-001` (isolated Musashi ABI1).

Host notes: `cp`/`rm` are interactive aliases, so use `command cp -f` and
`command rm -f`. `/` had about 6.6 GiB free and all heavy work used the large
volume. Emulation runs at about 70–100 fps here, so a 7,200-frame window takes
100–130 s.
