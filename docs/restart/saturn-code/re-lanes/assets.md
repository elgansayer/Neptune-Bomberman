LANE-STATUS: ACTIVE

# Lane ledger: assets (graphics, animation, stage data, text, movies)

Scope: every non-audio asset of Saturn Bomberman, USA MK-81070 V1.003
first, with Japan T-14302G V1.000 where it differs. That covers VDP1 sprites
and palettes, sprite animation tables, VDP2 cells, maps and backgrounds, stage
data, fonts and text, UI layouts and the FILM movies. Audio banks and files
are classified here but owned by `sound-68k`; executables are classified here
but owned by `usa-code` and `code-map`. Issues: #485, #486, #487, #489, #494,
#28 and the REF inventories #395–#399. Gemini's #464 is read-only.

Outputs live only in the private `elgansayer/saturn-bomberman-decomp`
repository (`assets/usa/…`, `assets/japan/…`, recipes in `tools/assets/`,
progress in `docs/progress/assets.md`). This ledger records counts, formats
in our own words and private commits, with no game bytes.

## Denominator

Every file and byte range on the disc must be classified, and every asset
inside it extracted by a deterministic recipe with a manifest (source
file/offset/hash → output hash).

### Disc files

| Release | ISO files | Unknown | Notes |
| --- | ---: | ---: | --- |
| USA | 430 | 0 | 1 archive, 3 movies, 174 images, 66 font files, 42 text, 5 data (XBAND/NetLink, run 20261106T1723Z: the client database split into its items; the XBAND file map and the game-info record decoded field by field from the XBAND code that reads them; the XBAND data file mapped end to end, 6 bytes open; the NetLink data file identified as a byte-exact copy of the boot program's initialised data), 8 code, 131 audio |
| Japan | 25 | 0 | `BOMSS1.CPK`, `BOMSS3.CPK` and 9 AIFs are byte-identical to USA |

### `PROGRAM.BIN` banks

| Bank class | USA | Japan | Status |
| --- | ---: | ---: | --- |
| Graphics | 12 | 11 (no `xband1`) | decoded |
| Sound `s_*` | 11 | 10 | classified; owner sound-68k |
| Voice `s_vo*` | 45 | 45 | classified; owner sound-68k |
| Headerless voice container (USA id 23) | 1 | 0 | classified audio; owner sound-68k |
| Headerless voice-slot sectors (USA ids 41–43) | 3 | 0 | unidentified (likely audio); handed to sound-68k |
| Bytes after the last directory entry | 2,169,666 | 2,931,522 | build-container residue |

Japan graphics banks `base1`, `base2`, `openning`, `normal5`, `battle1`,
`master1` and `staff` decode to different outputs from USA. `normal1`
differs only in bank bytes, and `normal2`–`normal4` are identical.

### Extracted (USA; Japan where it differs)

| Category | Extracted / known |
| --- | ---: |
| CRAM palettes | 414 / 414 |
| VDP1 sprite frames | 11,695 / 11,695 (34,681 parts) |
| VDP1 unique pixel blocks | 10,659 / 10,659 |
| Sprite animation sequences | 4,915 / 4,915 |
| **Sprite palettes bound from captures** (7,215 states, was 6,365; 364,636 of 364,767 sprite draws match a decoded block, the rest are RGB movie frames and off-screen draws with no graphics assigned) | **4,932 blocks drawn directly, 3,285 sequences** (was 4,614 / 3,086); **7,484 of 10,659 blocks** have their exact colours once the frames of bound sequences are included (was 7,064; the kernel's draw rule, checked on 204,620 of 204,648 drawn actors); 19 more sequences (39 blocks) only from per-frame actor samples, counted apart; staff bank 185 / 185, all 50 sequences. Run 20261106T1223Z: battles with computer players and with battle characters 8-11 (never picked by the earlier walks), the first captures with the XBAND bank resident, and boss stages played with every button. Run 20261106T1723Z's closing pass (finished after that run ended; integrated by run 20261107T0823Z) added its XBAND-bank battles, Master Game rank states and backup-memory boots |
| VDP2 cell blocks | 84 / 84 |
| Stage grids and background planes | 115 / 115 (exact pattern-name planes + renders) |
| Metatile sets and per-metatile attributes | 39 / 39 sets; 115 attribute maps; attribute bits named from the kernel's readers (run 20261107T0823Z: solid, soft, no-soft-block, fire-and-bomb stop, bomb stop, overhang sprite priority, and a 4-bit cell code kept in a second map; four rare bits and one counter open) |
| Colour-cycle scripts | 124 / 124 |
| VDP2 cell animations | 36 records, 232 frames (stage banks); placement closed (run 20261107T0823Z): the stage descriptor gives the destination, and the record's first word, never read by the kernel, is not it |
| FONTX2 Shift-JIS fonts (16×16) | 2 / 2 (316 glyphs each) |
| VDP2 menu/UI maps | 65 / 65 decoded and rendered; **47 confirmed by capture on every cell** (was 45; run 20261107T0823Z: the BOMBER CATCHER background and its byte-identical XBAND-bank copy, whose palette field the screen's set-up code rewrites over a 63 x 63 cell rectangle right after loading it; with that call applied, the map equals VRAM on a displayed page in 75 captures; earlier: was 41; run 20261106T1723Z: the Battle Series AWARDS frame and a Series wallpaper under one palette offset each, found by an offset search of the newer battle, Series and Master states, and two Master Game result backgrounds reached by setting the rank inputs), rendered in capture colours. Every map is searched anywhere in the captured VDP2 VRAM: 29 lie exactly on a displayed page in run 0223Z's 1,535 states, 3 more under one palette offset (the title's logo wallpaper and the battle scoreboard's crosshair), 4 Master Game hub flame maps in a natural idle run. Run 20261106T0723Z added 5 from its 476 new screens: the battle set winner's VICTORY on the stadium screen (battle1 15), the Battle Series VICTORY parade (battle1 11) and its AWARDS screen's trophy wallpaper (battle1 5), and the xband1 copies of 5 and 15 |
| Normal Game stage descriptors | 50 / 50 |
| Normal Game enemy placement lists (kernel table) | 50 / 50 |
| Master Game enemy placement lists | 20 / 20 |
| Battle stage descriptors (with item lists) | 36 / 36 |
| Master Game stages and item placement | 20 / 20 |
| Gameplay maps (64×64 cell attributes) | 106 / 106 |
| Base1 slot-4 records | 13 / 13 classified (stage descriptors, 10 attract-demo pad recordings, and two older copies of the kernel's enemy tables that no code reads) |
| Slot-9 records outside the base banks | 24 / 24 (battle1 and xband1 list the same battle table twice; master1 20 item lists) |
| **XBAND client database** (`XBAND/DRAMDB.BIN`, new this run) | 110 type rows, 948 entries: 917 items in the file (all of its data area but 367 alignment bytes); the 24 items of one type chain through `XBAND/XBAND.DAT` right after its sound driver, to the file's end (audio-like, handed to sound-68k); 7 open (6 references, 1 bad entry); 4,695 strings with their item and offset; item formats open |
| FILM movies | USA 3 / 3 (10,421 frames, 320×160, 30 fps, stereo 22,050 Hz); Japan `BOMSS2` 1 / 1 |
| NetLink/XBAND images | 174 / 174 |
| NetLink font strips and width tables | 58 / 58 and 8 / 8 |
| HTML/TXT text | 42 / 42 |
| **Sprite text frames** (story, save-system messages, Master Game intro and results, staff credits, animated words) | **97 frames, all machine-checked against the bank data, 0 conflicts** (was 96; run 20261106T1723Z read a tenth save message, the in-game "not enough free memory" box, which no earlier list had). The 55 glyph-built frames: 30 glyph by glyph, 21 word by word (10 save messages, 11 animated-word frames), 4 mixed glyph and word blocks (3 staff cards, "Fin"). Plus 42 Master Game result frames (score labels, 19 ranks from Baby to Master, rank letters). **Japan: 75 frames transcribed** (was 74; the same tenth save message): 8 story screens, 9 save messages, the Master Game intro (vertical text), 25 staff cards, and (run 20261106T1223Z) the animated HURRY!/MONO/STEREO frames, the 16 Master Game gong-sign frames and 4 result-label frames; **71 machine-checked** (was 1): 1 glyph by glyph, 31 word by word, 1 mixed, and 38 story, save-message and staff frames on the 16-pixel character pitch (each multi-character block must read the same in every frame and agree with its word-block reading); 4 still visual. The animated words are part-for-part pixel-identical to the USA frames, so their readings carry over by block hash. Each gong sign is one brush kanji (start, end, next, celebrate, complete, stop, hurry, special); the USA release draws the same kanji blocks with an English word block beside each. The Japan release has no Master Game rank frames: its result screen is a score table |
| **Sprite word blocks** (menu labels, arena, character, world and boss names, banners, Master Game labels, battle taunts) | **446 blocks read, 630 entries** (was 438 / 622; run 20261106T1223Z read the 8 brush-kanji blocks of the Master Game gong signs) (every text-bearing banner-shaped block of all 12 banks, the whole save-message font; entries include pixel-identical base2/xband1 copies; run 20261106T0223Z added staff initials, animated-word letters and the Master Game result labels, ranks and rank letters; other narrow blocks partial). **Japan: 290 entries** (was 261; run 20261106T1223Z added the animated-word letters, the 8 gong kanji and one result-label block) over openning, base1, base2, battle1, master1, normal5 and staff (menus, control set-up, world, boss and arena names, the guest characters' name plates, award titles, save messages in katakana, credit headings); Japan normal5's only differing block is the localised version of a one-word USA banner |
| **Menu, screen and play capture states** (scripted pad input, no memory writes) | **381 new** (incl. 8 battle arena previews and a match with Devil, Mad Bomber and Bonus Game on); run 20261106T1223Z added 2,197 sampler states: 1,248 from stage-select play with every button, 494 from battles with characters 8-11, 392 from computer-player battles and 63 from the XBAND bank (memory writes at the select or title screen, labelled `patched-`) |
| **Ending, staff roll and boss capture states** (the game's own end-of-game path, entered by a memory write; Normal and Master boss stages continued from stage select) | **382 new** (907 states in all) |

### Formats confirmed (own words)

- **Stage descriptors.** Normal Game keeps one 152-byte
  record per stage (5 worlds × 10 slots) in the first base bank's slot 4.
  The kernel finds it as world × 10 + stage. In order, the record names:
  - the stage's cell block and palette;
  - the metatile and attribute set;
  - the gameplay-layer grid and up to two more background-layer grids;
  - up to ten colour-cycle scripts;
  - up to five tile animations, each with its VDP2 target address;
  - the field's bounding box;
  - the soft-block count;
  - the start views;
  - the single bomber's entry cell and the two-bomber start cells;
  - the time limit in minutes;
  - a zero-terminated list of the item kinds hidden in the stage.

  Battle mode keeps 36 shorter records (9 arenas × 4 variants) in the
  battle bank, each with its own soft-block count and item list. Master Game stages are set up
  by code: field grid n, background grid n + 20. Each also has a list of
  fixed item cells.
- **Enemy placement.** The game reads it from two
  tables inside the kernel executable, not from the base bank:
  - The Normal Game table has one 64-byte row per (world, stage), with up to
    16 (kind, x, y) entries ending at kind 0.
  - The Master Game table has one row per Master stage.
  - A short (world, stage) list names the seven boss stages that spawn
    nothing from the table. Their objects come from stage code.

  The spawner creates each entry at its cell and stores the kind in the
  object. Some kinds bring extra objects with them that code spawns, such as
  a companion on the same cell or a three-part body. The base bank holds two
  older copies that nothing reads:
  - The Normal copy differs on 27 of 60 rows. Every World 5 row in it lists
    only the exit mechanism; earlier outputs used it.
  - The Master copy has 25 rows in five groups of four stages and a boss,
    against the shipped five groups of three stages and a boss.

  Japan's kernel holds the same table bytes.
- **Gameplay map.** The kernel builds the 64×64 cell map by looking
  each field-grid metatile up in its set's attribute table. The upper bits
  go into the cell map (solid and floor-class flags), and the low nibble
  goes into a parallel map. Soft blocks, bombs, items and fire are run-time
  bits on top. The lookup is unbounded: indices past the attribute table
  read the bytes that follow it, which explains battle arena 17's outer
  columns.
- **Soft blocks and hidden items.** Placement is generated by code,
  from the descriptor's count and the field rectangle:
  - **Random generator:** subtractive, 55 entries, modulus 32768, seed
    1234. Demos re-seed it at stage set-up, so their layouts repeat. Real
    play does not re-seed, so layouts vary from play to play.
  - **Soft blocks:** row sweeps with a rising threshold. Reserved cells
    are the bomber's 3×3 area and the enemy cells.
  - **Hidden items:** each item goes into the first free soft block to the
    right of a random cell.
  - **Stage set-up draws:** enemy set-up draws a stage-dependent number of
    random values first: 0 for 1-1, 34 for 2-1 (the same in a demo and in
    real play).
- **Sprites.** A frame is a list of 20-byte part records; a sequence is a
  list of (frame, duration) pairs. All 34,681 parts are VDP1 4-bit
  colour-bank sprites. Over 470 capture states, 22,001 of 22,008 draws
  match a decoded pixel block byte-exactly. The rest are three captures of
  the RGB movie frame and 4 draws in stage 2-2. Each match binds the
  object's runtime colour base.
- **Battle characters (new this run).** The battle base bank holds one group
  of about 34 animation sequences per character (12 groups). Every captured
  sequence of group k uses the runtime colour base 0x60 + 0x10·k; some also
  use a second base, 0x200 + 0x10·k. Ten groups are bound from captures.
- **Stage backgrounds.** A 64×64 grid of metatile indices expands through a
  metatile set (four 2-word VDP2 pattern names per 16×16 block) into the
  game's NBG plane. Nine live planes equal the disc-derived planes on all
  16,384 cells. Renders are now paired from the stage tables:
  - USA: 111 of 115 planes, including XBAND's 18 grids through its own
    battle table.
  - 2 more planes come from capture pairings, and 2 still use the old
    heuristic.
  - The earlier index-based renders were wrong for 38 of 93 planes.
  - All five capture-confirmed pairings agree with the tables.
- **Menu and title maps.** The kernel loader gives rows × columns of 2-word
  pattern names; the title maps equal live NBG0 on every cell. The battle
  menus use one-page planes (each of the four planes is a single 64×64-cell
  page). The capture checker now reads that layout, which confirmed four
  battle maps.
- **Scenes, modes and the ending (new this run).** The kernel runs one
  scene at a time. Each scene stores the next scene's entry point and a mode
  number, and the mode picks the banks loaded for the next scene: title,
  Normal Game (bank by world), Battle (or the XBAND bank), Master Game, and
  the ending (staff bank). A Normal Game stage ends when its 16-bit flag word
  gets the stage-over bit. A cleared stage runs the stage's clear hook; a
  game over sets another bit. With that bit set and the world number one
  past the last world, the game starts the ending scene: the ending movie,
  then the staff roll. Setting those two values in a running stage reaches
  the staff roll and then the title screen.
- **Sprite text (new this run).** The English story screens, save-system
  messages, the Master Game intro and the staff credits are each one sprite
  frame. Its parts are glyph blocks shared across frames, one character per
  block. The fonts draw the apostrophe with the comma glyph, placed higher.
  The checker splits a frame's parts into the transcribed lines and aligns
  them with the characters: 30 frames align, and no glyph block reads as two
  characters. The save-system font packs several characters into a block,
  so those frames are visual transcriptions only. Menu labels, arena names
  and character names are single "word blocks".
- **Sprite actors and the draw rule (new this run).** The kernel draws
  every sprite object through an actor record (400 records of 84 bytes).
  Each record holds:
  - the current frame;
  - a bank class (base bank or overlay);
  - a 16-bit colour word;
  - the sequence id;
  - pointers to the sequence and the current step.

  The part drawers add each part's colour field to the actor's colour word
  to get the VDP1 colour (CMDCOLR). So one capture of an actor playing a
  sequence gives the colour base of every frame of that sequence. Over all
  1,535 states, 36,768 of the 36,769 drawn actors obey the rule. The one
  exception differs by one colour step between building the draw list and
  the capture. The actor records alone bind 5 more sequences, whose frames
  were not on screen. A static pairing of constant sequence
  ids with constant colour stores in the same kernel function matched only
  40 of 69 checkable cases, so it is not used for bindings.
- **XBAND client database (new this run).** A typed item store:
  - a header;
  - 110 type rows (type, item count, list offset);
  - per type, 12-byte item entries (id, size, data offset).

  Most items are packed on 4-byte boundaries after the tables. The items of
  one type live in the separate XBAND data file instead. They start right
  after its sound driver and run to its end, which explains that file's
  layout. Strings include the XBAND service's UI text, help text and modem
  strings.
- **Palette and tile animation, fonts, movies.** As in the previous update:
  (CRAM index, count, (delay, colours) frames) cycles; tile animations as
  4-bit cell frames; a FONTX2 Shift-JIS font in the base banks; Japan
  `BOMSS2.CPK` is a separate dub.

- **XBAND and NetLink files (new, run 20261106T1723Z).** Read from the code
  that loads them:
  - The NetLink data file is a byte-exact copy of the last 19,168 bytes of
    the boot program, its initialised data; the boot program reads it back
    by name over that range.
  - The XBAND file map holds a word, the game directory, the XBAND
    directory, the game-info file name and a flag byte; the XBAND module
    changes into the XBAND directory and loads the game-info record into a
    fixed buffer.
  - The game-info record holds a game identifier (sent to the other player
    when connecting), a second word, the title, a credit line, the
    initial-program file and two head-to-head library files. One accessor
    function reads each field.
  - The XBAND data file starts with two blank 320 x 224 4-bit screens (one
    colour index everywhere), then 8 zero bytes, the sound driver copy, 6
    open bytes and the database's audio items.
- **Master Game result (new, run 20261106T1723Z).** The rank comes from a
  table indexed by the score band and the technique-points band, with two
  top ranks reserved for full clears. The result screen's background
  follows the rank: the dragon door below rank 9, a cave door from 9 to 17
  and the summit at 18. Every earlier capture showed the dragon door.

### Live checks of the stage data

| Check | Result |
| --- | --- |
| Solid bit, table-derived map vs live cell map | 4,092–4,096 / 4,096 for normal 1-1, 2-1, 3-1, 4-1, battle 10-0, master 9 and 13 (the rest are standing enemies) |
| 1-1 at stage start: enemies, player starts, soft-block count | 7/7 cells, 2/2 cells, 56 = 56 |
| Kernel enemy tables vs all stage-select captures (this run) | Normal Game: every listed (kind, cell) present at build on 50/50 stages (405/405 entries); Master Game: live kinds equal the row and every (kind, cell) present on 20/20 (166/166) |
| Hidden item kinds vs live item slots | equal for 1-1, 2-1, 3-1, 4-1 and battle 17-0 (75/75, two runs); battle 10-0 32/33 (one slot already used) |
| Master item cells | 5/5 and 12/12 in demos |
| All 36 battle arenas, selected through world/variant in the battle demo's pre-build state | solid bit 4,090–4,096/4,096 on 36; item lists 36/36; soft-block count exact on 35/36 (one arena runs out of free cells); descriptor grids equal the live planes on 32/36 (arena 17's large field is on a plane layout the checker doesn't read), cell block and palette confirmed on 36/36 |
| All 20 Master Game stages, selected through the stage byte in a demo's pre-build state | solid bit 4,092–4,096/4,096 on 20; field grid s+1 and background grid s+21 equal the live planes on every cell on 20; item kinds 19/20 and item cells 98/100 (stage 14 skips one item and shifts the rest) |
| Battle arena 17 | 4,096/4,096 solid bits in two captures (once the lookup reads past the table) |
| Japan | same tables and maps byte for byte |
| All 50 Normal Game stages, selected through the game's stage variables in a cold-boot menu state | 47 build (1-8–1-10 are identical placeholder records); timer = descriptor minutes × 3,600 frames 47/47; hidden item kinds 47/47; soft-block count exact 43/47; solid bit ≥ 4,083/4,096; the single bomber on its entry cell (31) or player-1 cell (16); enemies: see the kernel-table row above (the old base-bank source matched 17 stages) |
| Backgrounds of all 47 built stages (display-on stage-select captures) | every descriptor grid equals a live plane on all 16,384 cells on 44 stages; descriptor cell block in VRAM on 47 (byte-exact on 20, ≥ 98% where tiles animate); descriptor palette the best CRAM match on 47 |
| Soft-block generator from the captured generator state | with a per-stage set-up offset: exact on 24 of the 39 built stages with soft blocks when the bomber area and the kernel table's enemy cells are reserved, 28 of 39 when the objects code spawns are reserved too (the other 11 within 1–5 blocks); 1-1 exact in two demo captures including hidden items |

## Private repository state (runs 20261105T1623Z, 1833Z, 2123Z, 20261106T0223Z, 0723Z, 1223Z, 1723Z, 20261107T0823Z and 1543Z)

Run 20261107T1543Z: `d0241525` run 0823Z's closing pass integrated (7,215 states).

Run 20261107T0823Z (in progress at this PR): `6a0ff05` (head) mount growth rule, loader census, state lists · earlier state list, recipe README · `a5c0eec` frontier details · `aa21d70` cell-animation word closed · `ebdf9c3` attribute bits · `a9a6fd5` VDP2 map 9 with the code's palette rectangle, maps 47/65 · `538fb67` run 1723Z's closing pass integrated.

Run 20261106T1723Z: `2c804cc` (head) XBAND image items · `a099ca4` master1 4 and 11 confirmed via the rank inputs, maps 45/65 · `a8d269f`, `178d918` battle1 16 and 17 under palette offsets (offset search over 2,175 states) · `7929435`, `a5d6313` the tenth save message, USA and Japan · `e60b164` map search bank filter · `452b702` XBAND/NetLink layouts from code · `1a6e88d` run 1223Z's closing pass integrated.

Run 20261106T1223Z: `e3d107b` (head) player-slot colours, computer players, XBAND word, unbound inventory · `1651bf9` docs, sampler KNOWN filter · `1c5ca72` Japan pitch check (70 of 74 frames) · `c571a48` all-button generator · `f2e726d` Japan animated words and gong signs.

Run 20261106T0723Z: `864abd6` (head) Japan staff word blocks · `4ca664a` all-button egg battle (4 more base2 sequences sampled, verified at the next capture pass) · `c2890eb` progress and sprite document · `60f5477` closing pass over 3,681 states · `e4a1109`, `348fc8b`, `9eaa2ce`, `54dccec`, `6dc822d`, `8fd1c26` Japan word blocks · `8f44a0f`, `2733124` walk actions, scripts and recipes · `42b435e`, `80e5698` draw-checked actor colour words, merge rules · `862ee62` item patch tool · `834c1af` per-frame actor sampler, BOMBER CATCHER input · `eb63f21` capture pass over 1,935 states.

Run 20261106T0223Z after PR #900: `c466f69` (head) Master hub flame maps (master1 12-15) confirmed, maps 36/65 · `8c99cc3` draw rule on 36,768 of 36,769 drawn actors · `750c873`, `123bee5` state list adds the Series walk, the second Normal Game play pass and the hub idle run · `054005f`, `5923972` Series-screen word blocks (622 entries) · `d54fd5e` hub flame lead.

Run 20261106T0223Z: `b005bde` (head) closing pass over 1,535 states · `17ebcac`, `a8969aa` Master Game result text · `de638e6`, `3d9e0fd`, `859b593` Japan staff credits, Master intro and save messages · `62d75c3`, `35173fa` all text frames machine-checked · `05967b4` map search under a name offset · `dc68656` XBAND database across files · `cc23b45` sprite runtime document and walk recipes · `ccc03d5` state list shared by the capture pass · `002325a` XBAND client database split, static colour-pairing tool · `2a3dcb4` map search at any position, actor-record colour reader.

Run 2123Z: `57ea324` (head) word blocks of all 12 banks · `fae4c79` special-rules battle, 907-state pass · `d5ca419` word-level check of the save messages, Japan story text, stage 2-2 draws explained · `6b795ae` word blocks of four banks · `ba74aa2` battle arena previews (864-state pass) · `5f69132` Master boss floors, 852-state capture pass, 241 word
blocks · `35176ac` 200 word blocks · `1f46dfd` ending, staff roll and boss
captures (722-state capture pass) · `080174c` ending trigger and capture-pass update · `47e1792`
capture pass over 470 states (sprite bindings, map
checks, one-page planes, deduplicated draw PNGs, Counts section) ·
`6265cec` 133 word blocks · `d400937` sprite text recipe and output, menu and
play walk recipe, multi-checkpoint emulator wrapper, draw lister. Run 1833Z:
`d9862b4` enemy placement from the kernel tables (Normal, Master, boss skip
list) with stage-select checks · `e398b07` soft-block fit with the kernel
table, format document and progress. Run 1623Z: `38952ec` master1 pairing confirmed by capture and the second attract walk's
checks · `0f256a2` stage data recipe and outputs · `ef1b663` backgrounds
paired from the stage tables, starting-field generator · `2d55396` emulator
wrapper after the host kernel update · `7946a43` stage-select checks of all
50 stages · `8e22b08`, `7a71f0e` generator fit · `bce4e78` demo-input
records · `69902d2` capture checks and sprite bindings over 86 states ·
`be65314` progress · `1bbdf46` format document
(`docs/assets/STAGE_DATA.md`) · `54a85be`, `771f5a1` Master Game checks and
106-state capture run · `d04c8dd`, `3ad230c` battle arena checks and
142-state capture run · `7d07e38` menu maps from the cold-boot states. Earlier: `8c81955`, `6f02041`, `7925bb6`, `058e59d`, `43239a1`,
`0eb90a8`, `f6f075b`, `21e5e2e`, `df30aee`, `4d94bee`.

## Frontier

1. Sprite palettes: 7,484 of 10,659 blocks have exact colours from draws
   (4,932 drawn directly), and 3,285 of 4,915 sequences are bound (19 more
   only from per-frame samples). The
   private `sprite_unbound.json` lists every unbound sequence and block.
   - Computer-player battles (a type byte per player at character select)
     play whole rounds with Louies and items by themselves; next, Team
     mode, Wide stages with 10 players and the computer level.
   - A per-frame actor sampler and an item patch tool exist. The tool puts
     chosen items, eggs included, in a built field's own tables.
   - Still unbound:
     - riderless Louie poses, Louie abilities and their sound words; next,
       press the ability buttons while riding;
     - Master Game boss attacks and the ending portraits; next, longer boss
       fights;
     - Series screens not yet reached;
     - the rest of base2 characters 8-11 (the earlier walks only played 0-7).
   - xband1 is now resident in an XBAND-word battle (run 20261106T1223Z);
     most of its bindings still come from pixel-identical battle1 blocks. Japan normal1-normal5
     match the USA banks except one block.
2. VDP2 map colours: 47 of 65 confirmed. The 18 still open:
   - battle1 7, 8, 13, 14 and 18. Maps 6-8 are one battle-menu panel in
     three versions chosen through a 13-entry screen table in the kernel
     (screen id -> cell block, map): screen 4 shows map 6 (captured),
     screen 5 map 7 (taken instead of 4 when bit 2 of a battle flag word is
     set), screens 6-11 map 8 (a different menu handler). No capture ever has
     a screen id above 4 or that flag bit set. Map 7's earlier "86% of its
     cells" is only the frame it shares with map 6. Maps 13 and 14 are loaded
     together by one records function. No loader of map 18 is known (an
     earlier reading of this run took a task priority for its index; that
     function tiles map 1);
   - master1 6 (no fixed load in the kernel);
   - 12 xband1 maps: 1 and 8 (64 x 64, XBAND-only), 13 and 14 (copies of
     battle1's), 11 (2 x 2 cells) and eight one-cell records (4 bytes each,
     at the indices of battle1's menu panels 6-7 and screens 16-21; probably
     placeholders).

   The BOMBER CATCHER is solved: Saturn B starts the crane, and after the
   prize the game returns to the battle menu.
3. Text: Japan word blocks are read for the banner-shaped blocks of seven
   banks and the animated words (290 entries); Japan's animated words,
   gong signs and result labels are word-checked. Next:
   - the narrower word blocks;
   - machine checks for the other 42 Japan frames (story, save messages,
     staff cards): their blocks hold several characters each, so they need
     per-block readings;
   - XBAND item formats and the 7 open database entries (the XBAND and
     NetLink file layouts are closed, run 20261106T1723Z).
4. Soft-block layouts: make the per-stage set-up offset and the
   code-spawned objects derivable from code instead of fitted (usa-code
   scope). Also the open descriptor parameters, the two unpaired
   background grids. The slot-6 attribute bits are named (run
   20261107T0823Z); four rare bits and the counter fed by the cell code
   stay open. Neptune #923 asks for the cell attributes in the game.
5. Master Game result rank (new lead, run 20261106T1723Z): the rank is a
   16 x 17 table lookup of a score band (16 thresholds, 20,000 to 320,000)
   and a technique-points band (16 thresholds, 1,000 to 30,000), with two
   top ranks that also need every floor cleared and two per-floor
   counters in range; the result background follows the rank (below 9,
   9-17, 18). Name those two counters, then file the implementation issue.
6. Neptune implementation issues: #877 (soft blocks and items), #887
   (enemy placement) and #890 (battle arena set-up) are filed. The BOMBER
   CATCHER crane's inputs, states and prize rule are posted on #425
   (bonus-game framework).

## Run log

- 20261105T0828Z–1028Z: no work; the runs stopped at start on the account
  usage limit.
- 20261105T1123Z: first working run. Covered PROGRAM.BIN graphics, disc
  classification, movies, stage backgrounds, attributes, colour and tile
  animations, fonts, sprite palette bindings, attract-mode captures and
  Japan differences (PRs #866, #868). It stopped on the usage limit during
  its closing pass.
- 20261105T1328Z: no work (usage limit).
- 20261105T1623Z:
  - Finished the 1123Z closing pass.
  - Found the game's stage tables through the kernel code that reads them, and exported every stage's descriptor, enemy and item placement and gameplay map (PR #876).
  - Re-paired the backgrounds from those tables.
  - Re-implemented the soft-block and item placement.
  - Filed Neptune #877.
  - Blocker found and fixed: the host's kernel update made the pinned emulator frontend refuse to run, because its platform-string pin no longer matched. A wrapper maps only that string. Checked byte-identical against a pre-update checkpoint.
  - Then checked all 50 Normal Game stages in the running game: stage data, background pairing and sprite palettes (860 blocks).
- 20261105T1833Z:
  - Found the enemy spawner in the kernel. It reads two kernel tables (Normal Game and Master Game) and a boss-stage skip list. This closes World 5 and Master Game enemy placement.
  - Classified base1 records 17 and 18 as unread older copies; record 18 was the last open base-bank record.
  - Checked both tables against every stage-select capture: 405/405 and 166/166 entries.
  - Re-fitted the soft-block generator with the correct enemy cells.
- 20261105T2123Z:
  - Walked the menus and play with scripted pad input from the cold-boot
    states. No memory writes. The walks reached:
    - the title menus and Option Mode;
    - the whole Battle set-up chain;
    - an 8-player random match through HURRY, TIME UP, DRAW and the
      scoreboard;
    - Normal Game play to GAME OVER and continue;
    - the Master Game intro and floors.
  - Captured 326 new states. A new emulator wrapper saves many checkpoints
    in one pass; its states are byte-identical to the one-at-a-time chain.
  - The capture pass over all 470 states:
    - doubled the sprite palette bindings;
    - raised the maps confirmed on every cell from 6 to 18, after the checker
      learned the battle menus' one-page planes.
  - Found that the English text is glyph-built sprite frames. Transcribed all
    54, with 30 checked glyph by glyph (0 conflicts). Read 133 word blocks.
  - Filed Neptune #887 (enemy placement) and #890 (battle arena set-up).
  - Read the kernel's scene and mode logic. Started the ending through the
    game's own end-of-game path, which bound the staff bank: 152 of 185
    blocks and all 50 sequences.
  - Continued the seven Normal Game boss stages and the five Master Game
    boss floors from stage select.
  - Read 351 word blocks: every text-bearing banner-shaped block in all 12 banks, and the whole save-message font.
  - Checked the 9 save messages word by word: 39 of 54 text frames are
    machine-checked.
  - Transcribed the Japan story screens.
  - Explained the 4 unmatched draws in stage 2-2: they are off-screen
    objects with no graphics assigned.
  - Played a battle with the Devil, Mad Bomber and Bonus Game rules on.
  - Total: 2,285 blocks bound over 907 states, 19 maps confirmed.
- 20261106T0223Z:
  - Found the kernel's sprite actor records and the draw rule. The actor's
    colour word plus each part's colour field gives the VDP1 colour, so a
    captured actor binds the colours of its whole sequence.
  - Searched every VDP2 map in all captured VRAM at any position, and also
    under one constant name offset: 32 of 65 maps confirmed (was 19).
  - Split the XBAND client database into its 948 entries and extracted its
    strings. A later correction found that one type's 24 items live in the
    XBAND data file, after the sound driver. The final count is 4,695
    strings.
  - Started new captures:
    - the Master Game area-clear path (temple gate, dragon door, RESULT
      ranking), via a flag-word write that mirrors the game's own clear;
    - a Battle set continued to its winner and the Bonus Game (BOMBER
      CATCHER);
    - random play on all 47 built Normal Game stages.
  - Closing pass over 1,535 states (was 907):
    - 2,846 sprite blocks and 2,138 sequences bound (was 2,285 / 1,908);
    - 5,350 of 10,659 blocks have exact colours with the frames of bound
      sequences;
    - every on-screen draw matches a decoded block.
  - Text: all 54 glyph-built frames are machine-checked (mixed glyph and
    word-block readings). The Master Game result text (19 ranks from Baby
    to Master Bomber) adds 42 checked frames, 96 in all. Japan's save
    messages, Master Game intro and 25 staff cards are transcribed.
  - Open: the BOMBER CATCHER waits for an input the walks have not found.
    The Master RESULT waits for a button. A Battle Series walk was queued
    at the end of the run.
  - After PR #900: the Master Game hub flames (4 maps) were confirmed from a
    natural idle capture, which makes 36 of 65 maps. The Series walk (50
    states) found no new map.
- 20261106T0418Z: no work recorded (the run ended without output).
- 20261106T0723Z:
  - Recorded the end of run 0223Z in the ledger (PR #902).
  - Capture pass over 1,935 states. It now includes run 0223Z's Series
    walk, second Normal Game play pass and Master hub run.
  - Wrote a per-frame actor sampler. It reads the kernel's actor table
    after every emulated frame through the core's memory export.
    Self-check: the table read at frame 300 equals the saved state's bytes,
    and the replay's video and audio match the original walk on all 300
    frames.
  - Replaying old walks this way added little. New content added more:
    - The BOMBER CATCHER crane starts with Saturn B, read from the crane
      handler. The earlier walks pressed A, C and START but never B. Played
      to the end twice (two different prizes); findings posted on #425.
    - The Battle Series continued with every player's pad: stage preview,
      a match, VICTORY, the AWARDS screen and the stadium's records pages.
    - Items placed by patch: eggs and rare item kinds were put in the
      attract demos' and battle fields, in the kernel's own hidden-item
      tables. The game's bombers then revealed the items and hatched and
      rode Louies. Item kind 21 is the egg.
  - Closing pass over 3,681 states:
    - 6,295 of 10,659 blocks with exact colours (was 5,340);
    - 2,720 sequences (was 2,133);
    - the draw rule holds on 103,167 of 103,168 drawn actors;
    - 15 sequences bound only by samples;
    - VDP2 maps 41/65. The battle set winner's VICTORY, the Series VICTORY
      parade and the AWARDS trophy wallpaper are new, with their xband1
      copies.
  - Japan word blocks: 261 entries over 7 banks (menus, control set-up,
    world, boss and arena names, the guest characters' name plates, award
    titles, save messages, credit headings). Japan normal5's only differing block is the
    localised version of a one-word USA banner.
- 20261106T1223Z (first PR, run in progress):
  - Japan text: the animated HURRY!/MONO/STEREO frames (pixel-identical to
    USA), the Master Game gong signs (one brush kanji each) and the result
    labels; 31 frames word-checked, Japan 74 frames with 32 machine-checked.
  - Battle character select stores one byte per player with the chosen
    character. Writing the two characters that no select screen offers into
    it gives a normal battle with them (the game's own code loads and draws
    them): 15 new base2 sequences in the first run, verified at the closing
    pass. Character colours follow the player slot, not the character.
  - Random play that presses every button: item-patched 1-1 gave nothing
    new (the bomber dies to its own bombs within seconds); a second player
    in World 3 and the World 2 boss with every button gave 17 new
    sequences. A wider sweep is running.
- 20261106T1223Z (final; the closing pass finished at 14:12Z, but the run
  ended before committing it, and run 1428Z produced nothing; run 1723Z
  integrated it):
  - Japan text: 74 frames, 70 machine-checked, 0 conflicts (1 before the
    run). The animated words, gong signs and result labels pass the
    word-level check; the story, save-message and staff frames pass a new
    pitch check (their blocks hold several characters on a 16-pixel pitch;
    every block must read the same in all frames and agree with its
    word-block reading).
  - Battle player bytes found at character select: a type byte per player
    (2 = computer) and a character byte per player. The lane's walks had
    only ever played characters 0-7 (default cursors). Battles with
    characters 8-11 and with computer players (who ride Louies, use items
    and play whole rounds by themselves) are memory writes like stage
    select; the game's own code does the rest.
  - Colours follow the player slot (0x60 + 0x10·k), not the character; an
    earlier ledger line read the slots as characters, and the PR #908 run
    log's "two characters no select screen offers" is not established.
  - The XBAND word makes the kernel load xband1 for Battle: first captures
    with xband1 resident (a two-player XBAND match).
  - Random play with every button: nothing new in item-patched 1-1 (the
    bomber dies to its own bombs), but boss stages with every button and a
    second player bound boss sequences in every world.
  - The sampler can now save states only for sequences no capture has
    bound (deterministic replays of runs whose new sequences vanished
    before a state was saved).
  - Closing pass over 5,958 states: 6,882 of 10,659 blocks with exact
    colours (was 6,295), 3,053 of 4,915 sequences bound (was 2,720),
    4,432 blocks drawn directly (was 3,787); 16 sequences bound
    only by samples. Draw rule 172,440 of 172,462. VDP2 maps 41/65.
- 20261106T1723Z (second PR, run in progress):
  - Integrated run 1223Z's closing pass (private `1a6e88d`).
  - XBAND and NetLink data: the last open layouts closed from the code that
    reads them (see Formats); 6 bytes of the XBAND data file stay open.
  - VDP2 maps 45/65 (was 41): an offset search of the newer states found
    the Series AWARDS frame and one wallpaper under a palette offset; the
    Master Game result backgrounds for ranks 9-18 appeared once the rank
    inputs were set in the area-clear trigger state (ranks 9, 15, 18).
  - Text: a tenth save message (USA and Japan), 97 USA frames and 71 of 75
    Japan frames machine-checked.
  - Save-memory messages: a cold boot with the internal backup memory
    filled by one file shows the "not enough free memory" screen; a zeroed
    backup memory does not show the "not ready" one (the game goes on to
    its intro).
  - Negative result: computer-player battles with the XBAND bank resident
    add almost nothing (one sequence); the XBAND bank's common battle
    sequences were already bound through identical battle-bank blocks.
  - The 22 draw-rule exceptions are in 4 captures. In each, the actor's
    colour word is one palette step (0x10, once 0x20) above the drawn
    colour; 20 are the parts of the World 5 boss in two states, consistent
    with a flash that changed the word after the frame's draw list was
    built. Conflicting words are never draw-checked, so they bind nothing.
- 20261107T0823Z (run in progress):
  - Integrated run 20261106T1723Z's closing pass, which finished after that
    run ended: 6,365 states, 4,614 blocks drawn directly, 3,086 sequences,
    7,064 of 10,659 blocks with exact colours (was 6,882); the draw rule
    holds on 177,956 of 177,978 drawn actors.
  - VDP2 maps 47/65: the BOMBER CATCHER background (battle bank map 9 and its
    XBAND-bank copy). Its set-up code loads the map and then rewrites the
    palette field of a 63 x 63 cell rectangle; the palette-free search had
    matched the page's characters, and applying that call gives a byte-exact
    match on a displayed page. A new private checker applies such calls.
  - Battle menu panels: maps 6, 7 and 8 come from a 13-entry kernel screen
    table; map 7 needs a battle flag bit and map 8 another menu handler,
    and no capture has reached either.
  - Tests with memory-write set-ups (the game's own code does the rest):
    letting the match timer run out kills the bomber and restarts the stage
    (two new base-bank sequences in World 2); the stage-over flag word ends
    a Normal Game stage and shows the next stage's banner; the item-7 effect
    (a state bit and its timer) keeps the bomber alive through 9,000-frame
    boss fights, but random play does not damage the World 5 boss (the World
    1 boss gave two new sequences).
  - Open question: two 88-sequence groups (a creature and a bomber with 64
    poses) in the World 1 and World 3 banks were never drawn in any capture;
    they are not table enemies, the time-up path, the stage-clear path or the
    boss phases tried so far.
  - Second PR (static findings):
    - Field attributes: the bits of the per-metatile attribute words are
      named from the code that reads them (overhang cells change a
      character's sprite priority; two bits stop fire and/or moving bombs;
      a 4-bit cell code goes to a second map). Filed Neptune #923.
    - Cell animations: the record's first word was the open "target"; the
      kernel never reads it. The stage descriptor gives the destination
      (checked on 89 of 105 stage captures).
    - Boss fights with the bomber protected by the game's own item effect
      (a state bit and its timer, written into player 1's record) last the
      full 9,000 frames; seeded every-button play damages the bosses of
      Worlds 1-4 and the last boss of World 5 (the World 4 mid-boss alone
      showed 26 sequences never captured before). The World 5 machine was
      never damaged.
    - Eggs: the hatch picks the mount colour at random and, in Normal Game,
      a level 0-2 from a per-player table that riding raises; presetting
      the levels shows grown-mount poses.
    - The battle-mode menu leads to a match-type screen with Normal/Wide
      stages and Single/Team modes (the Team and Wide set-ups the frontier
      names); walks that pick them are queued.
    - Still unexplained: two pixel-identical 88-sequence groups (a creature
      and a bomber in every direction) in the World 1 and World 3 banks,
      in no other bank and never drawn. The opening bank's save-menu items
      need a real save; stage and boss clears do not write one.
  - Third PR (static findings, closing pass still running):
    - Mount growth, from the code: a hatched mount's colour is random; in
      the Normal Game it starts at the level the player has earned for that
      colour. Points scored while riding go into a per-player, per-colour
      counter; level 1 at 5,000 points, level 2 at 15,000. Each level has
      its own sprite set (levels 1 and 2 drew mount sequences level 0
      never draws). Posted on Neptune #296.
    - Loader census: only the kernel writes VDP2 maps, through two
      routines; no call passes the battle bank's map 18, and the Master
      bank's map 6 is reachable only through the battle menu's screen
      table, so both are most likely unused data (still counted as open).
    - Game over: with the lives counter and the timer set low, the Normal
      Game's GAME OVER menu appears (CONTINUE / SAVE GAME / QUIT); its SAVE
      GAME is the route to a real save and so to the opening bank's
      NEW GAME / LOAD GAME and save-slot items (walk queued).
    - The Master Game boss floors with the protected bomber gave nothing
      new; eggs (level 0) in two more stages and the World 2 level runs
      gave 10-19 new sequences each.
- 20261107T1543Z:
  - Integrated run 20261107T0823Z's closing pass, which finished as that
    run hit the usage limit (private `d0241525`): 7,215 states (was 6,365),
    4,932 blocks drawn directly (was 4,614), 3,285 of 4,915 sequences bound
    (was 3,086), 7,484 of 10,659 blocks with exact colours (was 7,064); 19
    sequences (39 blocks) only from per-frame samples. The draw rule holds
    on 204,620 of 204,648 drawn actors. The egg-level, boss and game-over
    runs of that run gave the gain.
