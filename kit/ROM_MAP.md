# FE4 (Project Naga) ROM map

Built from: `Fire Emblem Genealogy of the Holy War - Copy.smc`
(8 MB + 512-byte copier header; headerless SHA-1 `2b6eb74646a527ba293b0e004db3e0134a28dc6c`).

- **Mapping:** ExHiROM (header map byte `0x35`). Internal name `FIREEMBLEM4`.
  The header exists at both `0x00FFC0` and `0x40FFC0`. Emulators read the
  second copy, which declares 8 KB SRAM.
- **Checksum:** 16-bit sum of all 8 MB. `fe4hack.py build` rewrites it in both headers.
- **Offsets:** all offsets below are headerless file offsets. Add `0x200` for the
  `.smc` file. Bank `$C3`/`$83` = file `0x03xxxx`.
- **Layout:** the original 4 MB game lives in `0x000000-0x3FFFFF`. Naga's
  English text, name tables and new code live in `0x500000+`, and script
  text starts around `0x600000`.
- **Free space the kit writes to:**
  - `$70:0000–$7D:EFFF`: edited dialogue (from `$70`) and maps (from `$78`)
  - `$7D:F000–$7D:FFFF`: code hooks (village gold)
  - the zero-filled tail of each chapter-info bank, after a 32-byte gap:
    `$86` 1,370 bytes, `$90` 2,528, `$B0` 324, `$B1` 618, `$B2` 298.
    Longer armory lists and new arena tables go here, since their pointers
    are 16-bit. Grown chapter scripts, scenes and AI programs go here too
    when they fit (scenes also use `$70–$7D`).
  - `$81` tail (4,664 bytes): grown deploy lists
  - `$83` tail (2,108 bytes): the enlarged unit pointer table and new units

Status key: **V** = verified by editing the ROM and checking the running game;
**C** = consistent across all records and the game's own data but not
edit-tested; **?** = unknown, kept as raw.

## Text encoding (Naga name tables)

| Byte | Meaning |
|---|---|
| `0x10–0x29` | `A–Z` |
| `0x2A–0x43` | `a–z` |
| `0xBF` | space |
| `0x48` | `'` |
| `0x01` | end of string |

Name slots are 16 bytes each:

- Characters: `0x500000`. The name starts at +8; the first 8 bytes are a VWF tile header.
- Classes: `0x506200`
- Items: `0x506700`
- Skills: `0x507A00`. 32-byte blocks with the name at the end.

### Pre-drawn names (V)

- **Slot table:** 16-byte slots at `0x500000`. Naga draws names from them
  with `$51:1321`, and the tiles are DMA'd or copied by `$51:0C63`.

| Slots | What | Layout |
|---|---|---|
| 0–575 | characters, by name ID | `[width][ptr24]`, text at +8 |
| 576–647 | classes | slot 586 (female Paladin) repeats 585 |
| 768–799 | terrain names | |
| 800–845 | castle names for the map terrain window | `[w][ptr24]` normal, `[8][ptr24]` centred in 64 px, `[w][ptr24]` right-aligned; 4 text bytes |
| 1024–1145 | items | second variant at +4, right-aligned in the same width |
| 1280–1325 | castles | second variant at +4: 8 tiles, right-aligned |

- **Graphic format:** 2bpp, top tile row then bottom row (16 px tall).
  Colour 2 = letter, 3 = outline, 0 = clear.
- **Font:** 1-px strokes with an outline. Neighbouring glyphs share their
  outline column, letter strokes are 1 px apart, and a space adds 3 px.
  - `fe4font.py` holds the glyphs, extracted from 425 names. It re-renders
    them pixel-for-pixel.
  - `I` and `l` are drawn identically.
- **Verified in-game:** renaming Sigurd, the Knight Lord class, the Steel
  sword and Chalphy shows the new names on the map, the status page, the
  castle view and the terrain window.

## Units: 569 records, IDs 1–569 (V)

Every unit in the game has one record: playable characters, children,
substitutes, bosses, NPCs and generic enemies.

- **ID lookup:** bank `$83` starts with a directory of word offsets.
  `$83:8002` (`0x038002`) gives the offset of the unit pointer table, which
  is `0x2DF5`, so the table is at file `0x03ADF5`.
- **Pointers:** ID *n* lives at `0x38000 + 0x2DF5 + word[n−1]`. Word 0 doubles
  as the table length (`0x472` = 569 × 2), because the records start right
  after the table. This is routine `$84:8481`.
- **Record type:** the first byte selects one of four formats. Spawning
  (`$84:8397`) dispatches through the jump table at `$84:83B0`.
- **Adding IDs (V):** `$84:8481` computes `CLC; ADC base; ADC #$8000`, keeping
  the carry of the first add. It also rejects IDs whose `(n−1)·2` is not below
  word 0.
  - `add_generic_units` rebuilds the table in bank `$83`'s free tail (2,108
    bytes from `$83:F7C4`) as `[table][copy of unit 1][new records]`, so
    word 0 is still the exact table size.
  - Pointers to records below the new table are stored minus 1, to cancel
    that carry.
  - **Pitfalls:** a table with a loose bound (word 0 larger than the table)
    crashes at chapter start, and so does ignoring the carry. Both were seen
    in testing.
  - **Verified:** new unit 570 (Paladin, level 15, Javelin) deployed in the
    Prologue shows correctly on its status page.
- **IDs 570–768 (V):** not units. The portrait table (`$8B:9A88`, read only by
  `$84:861C`) has 768 entries, and scripts use 570–768 for the portraits of
  people who only speak. A unit at 570 changes those portraits; in testing it
  hung the opening narration.
  - Since v12 the kit pads the pointer table to 768 (padding points at the
    copy of unit 1), so new units start at 769.
  - A JSL at `$84:8491`, in place of the bound check, still answers "no such
    unit" for 570–768.
- **Save format (V):** `$91:EFC4` lists the bit widths of each saved unit's
  header. The unit ID is 9 bits (max 511), so any unit past 511 loads as
  someone else. The kit makes it 10 bits when units are added.
  - Slots are 2 KB (`$30:6000` + slot × `$800`), and the checksum covers
    `$7BE` bytes.
  - At the start of chapter 6 a save uses about 1,890 bytes. Each extra
    child costs about 50.
- **Names by ID (V):** `$84:84F6` (battle screen, a child's parents) draws
  name slot ID − 1 through Naga's `$51:0C00`. For IDs past 569 the kit reads
  the record's `name_id` instead.

| Type | Size | Count | Who |
|---|---|---|---|
| 0 | 38 | 46 | Playable with fixed stats: all of gen 1, plus gen 2 substitutes (Shanan, Oifey, Hannibal, Julia…) |
| 1 | 12 | 17 | Playable children with inherited stats: Seliph, Leif, Altena, Ulster, Larcei, Lana… |
| 2 | 38 | 53 | Named NPCs and bosses with personal stats, growths and blood (Eldigan, …) |
| 3 | 13 | 453 | Class-based units: generic enemies and most bosses (Gerrard, DiMaggio, …) |

Unit objects in WRAM hold a long pointer into the record: +13 for types
0 and 2, +1 for type 3.

### Types 0 and 2: 38 bytes

| Off | Field | Notes |
|---|---|---|
| 0 | type | |
| 1 | HP | absolute (V) |
| 2–8 | Str Mag Skl Spd Def Res Lck | **added to class bases**; Lck is absolute because classes have no Lck (V) |
| 9 | class | (V) |
| 10 | level | (V) |
| 11 | authority | leadership stars (V: Sigurd 2★) |
| 12 | gold ÷1000 | (V) |
| 13–14 | char ID | equals the record's ID |
| 15–16 | name ID | index into the name table at `0x500000` |
| 17 | army slot | a child and the substitute who replaces them share a slot (Larcei 17 = Radney 17) |
| 18 | gender | 0 male, 1 female |
| 19 | ? | |
| 20–27 | growths HP Str Mag Skl Spd Def Res Lck | (V: a level-up with 100% Str/Skl/Def and 0 elsewhere raised exactly Str, Skl, Def) |
| 28–30 | skills | 24-bit field, see below (V) |
| 31–34 | holy blood | 13 × 2-bit slots, LSB first: 0 none, 1 minor, 2 major (C: matches canon for every character) |
| 35–37 | items | type 0: item **instance** IDs (V). Type 2: item **type** IDs (C). `255` = empty |

### Type 1: child, 12 bytes

| Off | Field |
|---|---|
| 0 | type |
| 1 | class |
| 2 | level |
| 3–4 | char ID |
| 5–6 | name ID |
| 7 | army slot |
| 8 | gender |
| 9–10 | item instances |
| 11 | heir: 1 = father (his blood in full, his items), 0 = mother |

Stats, growths and blood are inherited from the parents at runtime.

### Type 3: class-based, 13 bytes

| Off | Field |
|---|---|
| 0 | type |
| 1–2 | char ID |
| 3–4 | name ID |
| 5 | class |
| 6 | ? (0 bosses, 255 generics) |
| 7 | level |
| 8 | authority |
| 9 | ? (1 bosses, 255 generics) |
| 10–12 | item **type** IDs |

Stats come from class bases plus class growths × level. Verified: making unit
69 a Lv 15 Swordmaster with item 2 spawned a Silver-sword Swordmaster.

Item loading (`$84:F0E9`) dispatches on type: types 0/1 look up pre-created
instances, while types 2/3 create a fresh item of the given type.

**Holy blood slot order:** Baldur, Naga, Dain, Nova, Odo, Ullur, Neir, Fala,
Tordo, Forseti, Bragi, Hezul, Loptyr.

**Skill bits (V):** these were mapped by giving Sigurd one bit at a time and
reading the in-game Skills screen.

| Bit | Skill | Bit | Skill | Bit | Skill |
|---|---|---|---|---|---|
| 0 | Wrath | 8 | Critical | 13 | Sol |
| 1 | Pursuit | 9 | Vantage | 16 | Renewal |
| 2 | Adept | 10 | Accost | 17 | Paragon |
| 4 | Charm | 11 | Astra | 20 | Bargain |
| 6 | Nihil | 12 | Luna | | |
| 7 | Miracle | | | | |

Bits 3, 5, 14, 15, 18, 19 and 21–23 don't show up as skills. Bit 18 is set on
Quan, Ethlyn and Finn, so it's probably a story flag. Pavise, Steal and Dance
come from classes.

## Deployment lists: `0x01C000` (`$81:C000`), 58 lists (V)

The directory holds 58 word offsets from `0x1C000`. Each list is a run of
8-byte entries ending with char ID `0xFFFF`.

| Off | Field |
|---|---|
| 0–1 | char ID |
| 2 | X |
| 3 | Y |
| 4 | leader flag (1 = army leader; 254/255 = special, e.g. Gerrard stays in his castle) |
| 5 | AI orders: program number in the army's list (1-based, 0 = none) (V) |
| 6 | army slot (0 player; others filled per chapter by event `$4B`) (V) |
| 7 | slot/formation index |

- **How lists are used:** event command `$86:91A7` takes a one-byte list
  number and spawns that list through `$84:87BA`. List 0 is the Prologue's
  opening army.
- **Verified:** moving entry 0.0 by one tile changed exactly that unit's Y in
  RAM (`$7E:4507`), its pixel Y (`$7E:4627`) and the occupancy grid. Moving it
  to (60, 14) spawned it next to Sigurd.
- **List 57** has no terminator before unrelated data, so the tools stop it at `0x1EBBC`.
- **Inline lists:** a second event command (`$86:91CD`) deploys lists stored
  inline in event scripts. Those aren't extracted yet.

- **Growing a list (V):** `$86:91A7` sets `$24` = `$81:C000` + directory
  word, so a list can live anywhere in `$81:C000–$81:FFFF`. Grown lists move
  to the free tail (4,664 bytes from `$81:EDC8`). Verified: two extra Prologue
  entries, one of them new unit 570, spawn at their positions.

### Runtime RAM, for debugging

| Address | Contents |
|---|---|
| `$7E:4440+` | unit X array (words) |
| `$7E:44F0+` | unit Y array (words) |
| `$7E:4627` | pixel Y (one example address) |
| `$7E:169EE` | occupancy grid, 64 tiles wide |
| unit object + `0x22` | EXP |

## Classes: `0x038FC5`, 72 × 31 bytes (V)

| Off | Field |
|---|---|
| 0 | ? (20, or 1 for Pegasus Rider, Dracorider, Archer, Myrmidon) |
| 1 | base HP |
| 2–7 | base Str Mag Skl Spd Def Res (V) |
| 8–14 | class growths HP Str Mag Skl Spd Def Res (used by generic units) (C) |
| 15–24 | weapon ranks: sword, lance, axe, bow, staff, fire, thunder, wind, light, dark (`0`=A `1`=B `2`=C `3`=none) (V) |
| 25 | movement (V; the status screen shows only the last digit for values ≥ 10) |
| 26 | class group |
| 27 | flier flag |
| 28 | class skill bits (different layout from personal skills) |
| 29–30 | ? |

The class name table skips class 10 (female Paladin), so names for class IDs
≥ 11 come from slot ID−1. Arden's class 37 is Armored Sword.

## Items: `0x03EAE4`, 106 × 19 bytes, IDs 0–105 (V)

| Off | Field |
|---|---|
| 0 | id |
| 1 | category (0 weapon, 1 staff) |
| 2 | uses |
| 3–4 | price |
| 5 | holy-blood lock: 1–13 = bloodline in `fe4lib.BLOODS` order (Tyrfing 1 Baldur, Naga 2, Gungnir 3 Dain, … Mystletainn 12 Hezul, Loptyr 13); 14 Shield sword, 15 Barrier sword (their Def/Res bonus slots, guess) |
| 6 | staff effect |
| 7 | rank (0 A, 1 B, 2 C, 255 ★) |
| 8 | bonus flags |
| 9 | ? |
| 10 | weapon type |
| 11 | Mt (V) |
| 12 | Hit (V) |
| 13 | Wt |
| 14–15 | range min/max |
| 16 | effective-against flags (2 fliers, 8 armor) |
| 17–18 | special effect + argument: 1 magic sword casts item [arg] at range, 2 magic sword drains like [arg] (Earth sword → Nosferatu), 3 Nosferatu drain, 4 brave, 5 siege tome/ballista, 6 status edge (arg 4 silence, 5 sleep, 6 berserk), 7 Loptyr, 8 Naga (arg 84 Loptyr), 9 Hel, 10 Miracle sword — from the game's own items |

Each weapon type has three "broken" IDs (one per rank), but Naga's name table
has a single name for each set. `fe4lib.item_names()` handles the mismatch.

- **Rings:** `0x03F2C2`, 16 × 10 bytes, IDs 106–121. Fields: id, category, uses, price, stat bonus, ?, rank, 16-bit skill bits.
- **Item instances:** `0x03F488`, 141 bytes. FE4 tracks every physical item;
  this maps instance → item type. For example, instance 7 is Sigurd's Steel
  sword (type 1) and instance 45 is his Iron lance (type 28).

## Event system (V)

FE4 runs chapters through two bytecode interpreters plus the text renderer.
`fe4events.py` decodes all three: 2,643 event commands, 12,170 scene commands
and 785 messages, with every script decoded to its end.

### 1. Chapter event VM (`$86:83D8`)

- **Dispatch:** an opcode byte goes through a 121-entry table at `$86:83FA`.
  A script ends at word `$FFFF`.
- **Skip mode:** handlers entered with carry set just step over their
  arguments. The decoder runs each handler that way on a 65816 emulator to
  get exact lengths.
- **Handler bugs:** three handlers have skip-path bugs, so their lengths are
  set by rule:
  - `$34` is 2 bytes
  - `$67` is 3 bytes
  - `$5F` is 8 bytes, or 10 when byte 5 is `$0B`
- **Chapter headers:** 13 three-byte pointers at `$86:C739`. Each header is
  `[chapter word][opening-script ptr24][trigger-list ptr24]`.
  - The opening script runs once.
  - The trigger list is a run of `[condition][actions…]`.
  - Condition flag byte: `$FF` = none; `$00–$4F` = fire once, then set the
    flag (`$86:99D6` sets, `$86:9A50` tests); `$80|n` = needs flag n, then
    clears it. Each condition handler also checks the event mode in `$0EBC`
    (talk = `$0A`).
  - Ops `$20`/`$25`/`$2E`/`$21` start the list's structured tail; the editor
    adds new events before it.
  - Scenes 10 and up include 88 that are empty and unused; the editor
    writes new conversations there.
  - Per-chapter info pointers at `$86:C760` (12) and the army table at
    `$86:C784` (72) sit beside it.

| Op | Meaning | Evidence |
|---|---|---|
| `$02` | turn condition `[phase][word][turn word]` | Prologue turns 1 and 2 |
| `$0B` | unit in rectangle `[?][unit][x1 y1 x2 y2][?]` | |
| `$04` | talk: unit A talks to unit B `[flag][unit A word][unit B word][FFFF]` | V: Quan → Finn runs scene 426, Finn's talk boosts |
| `$16` | talk, same layout as `$04`; used from chapter 6 on (also enemy recruits) | V: Lana → Julia runs Lana's "Julia, right? Hello there!" |
| `$0C` | unit A next to unit B? `[flag][unit A][unit B][?][?]` | both orders listed, also between enemies |
| `$0D` | battle starts between units | boss quotes (Gerrard "Go to hell…") |
| `$1A` | unit dies | Midir's dying line |
| `$2B` | go-to (word address) | |
| `$30` | run scene `[once-bit][scene word]` via `$80:C1CB` | fails (carry set) while a scene runs (`$171A` ≠ 0): one scene per pass |
| `$31`/`$32` | show message `[speaker][ptr24][…]` | |
| `$4B` | set army slot `[slot][army ID]` | V: Prologue slot 1 = army 2 (Evans) |
| `$4D` | army relation? `[a][b][c]` | |
| `$4E` | deploy list `[n]` | V |
| `$4F` | deploy inline list | |
| `$20`/`$25`/`$2E` | 2-byte no-ops (`66 66`) | |
| `$57` | give item `[unit word, $FFFF = visiting unit][item instance]` | V: Prologue village 7 gives the Speed ring (#123) |
| `$70` | stat boost `[unit byte, $FF = visiting unit][stat 0–7][amount]`, capped by `$84:9FB1` | handler `$86:9852` → `$84:9F5A` |

### 2. Scene VM (`$91:A5FC`)

- **Where scenes live:** cutscenes and conversations are stored as 562
  three-byte pointers at `$8F:E8BF`. `RUN_SCENE` starts one.
- **Control bytes:**
  - word `$FFFF`: end of scene
  - word `$FEFE`: padding
  - `$FD`: yield one frame
  - anything else: one of 95 opcodes through `$91:A50A`
- **Control flow:**
  - `$01`: stop
  - `$02`: go to
  - `$03`/`$04`: if true / if false, go to (absolute)
  - `$05`/`$06`: relative jumps
  - `$07`: test a flag
- **Text:** `$0C [ptr24]` shows a message. `$14 [ptr24][3 bytes]` shows a message in a window.
- **Other special opcodes:**
  - `$4A`/`$4D` embed one event-VM command
  - `$45 [ptr24]` calls 65816 code
- **Measuring lengths:** the decoder runs handlers with calls outside bank
  `$91` stubbed. It follows every branch target.

### 3. Dialogue text (renderer `$91:8298`, control codes `$91:8A01`)

- **Characters:** text uses the name-table letters, plus digits `0x50–0x59`
  and `. , ? ! ' -` at `0x44–0x49`.
- **Control codes:** bytes below `0x10` are controls.
  - `$00 xx` is an extended code, with argument lengths measured from the game.
    For example, `{00 3F pp 00}` sets the portrait and `{00 1D xx}` takes one argument.
  - `{02}` is a new line.
  - `{08}` waits for a button press.
  - `{06}`/`{07}` select the left/right speaker.
  - `{01}` ends the message.
- **Letter widths (V):** `$91:9971`, one byte per text code − `$10` (Naga's VWF reads it at
  `$51:0083`): A 7, I 2, M 8, i 2, l 2, space 3… The widest line in the game's dialogue is
  223 px, so the box is taken as 224 px wide; pages are at most 3 lines.
- **More letters:** `{4A}` is `"`, `{89}` á, `{91}` é, `{9E}` ö (from the words they appear in);
  `{4C}` is probably `:` (2 px wide).
- **Portrait codes:** `{00 3F lo hi}` takes a character ID (570–768 are speakers with no unit).
  `{00 3D}` comes before it, `{00 40}{00 3E}` when a speaker leaves; `{04}` and `{00 29}` start a
  new box after `{08}` (guesses from the patterns).
- **Where text lives:** messages sit back to back in banks `$60–$68`.
- **Editing:** edited messages are written into the empty banks `$70–$7D`.
  All known pointers are then updated, and each message stays within one
  bank. Verified in-game: a longer Prologue line displayed correctly from
  `$70:0000`.

## Portraits (V)

- `$8B:9A88`: a word per character ID − 1 = portrait number (243 = none / picked at run time, e.g. by `$8A:B3E8`).
- `$8A:B4F9`: ptr24 per portrait number (248): compressed tiles, decoded through `$80:AA02`
  (not `$80:A9F2`: streams in the lower half of a HiROM bank need the `AA02` entry).
- `$8A:B7E1`: ptr24 per portrait number: 16 colours, raw; colour 0 is transparent.
- The 64 tiles form a 16-tile-wide block: the face is tiles 0–5 of rows 0–3 (top half) and tiles 6–11 of
  rows 0–3 (bottom half), 48×64 pixels.
- Tiles 12–15 of rows 0–3 are a 32×32 block holding two 32×16 talking frames (rows 0–1 and 2–3).
  Each matches the face's 32×16 block at (0, 32) in about 490 of 512 pixels across portraits:
  they are that block with the mouth open.
- Verified (kit v22): a 15-colour picture written as portrait 0 (tiles compressed with `fe4lz`,
  palette next to them, both pointers repointed) shows as Sigurd's face in a talk scene, with
  colour 0 transparent over the map.
- Most numbers from 185 on are class pictures for generic units. The status screen loads portraits at `$8A:B369`.

## Map sprites (V)

- **Small sprites** (on foot, ids 0–62): `$88:D526`, ptr24 each → three 16×16
  frames, `$80` bytes each (tiles TL TR BL BR, 4bpp, raw; data in `$D7`).
  The map plays frames 0 1 2 1 (`$88:DC20`).
- **Tall sprites** (mounted and flying, ids `$8000`–`$801E`): `$88:D5E3`,
  ptr24 each → three 16×24 frames, `$C0` bytes each (data in `$DA`). Tiles 0–1
  are the middle row, 2–3 the bottom row, 4–5 the top row (`$88:DC8B` sends
  `$40` bytes to VRAM `$6E00` and `$80` to `$6F00`).
- **Which sprite a unit uses:** `$84:A822` → `$84:A84A`. `$83:805E` has a word per
  class (72): offset + `$805E` in bank `$83` of 5-byte entries
  `[character word][gender][sprite word]`. Gender `$FF` ends the list and gives
  the default. An entry matches when its gender equals the unit's (ROM record
  +18: 0 male, 1 female) and its character is 0 or the unit's ID. For example,
  Knight Lord: Sigurd → `$800A`, Seliph → `$8008`, else `$8003`.
- The chosen ids are kept in RAM (`$7E:480B`, 8 slots) when the chapter loads;
  the frames are sent from ROM every animation step (queue at `$07ED`).
- **Palettes:** `$8C:9520`, 16 colours each: +`$00` player, +`$20` enemy, +`$40`
  ally, +`$60` other, +`$C0` grey (moved). Colour numbers mean the same in each.
- Longer lists (kit v25) move to the zero-filled end of bank `$83` (2 KB free from `$83:F7C4`;
  the class's word is the new address − `$805E`). Verified: a Cavalier row for Noish (char 2)
  → small sprite 12 shows Noish on foot while Alec and Arden stay mounted.
- Verified (kit v23): Sigurd's entry set to small sprite 3 shows him on foot
  on the Prologue map; a new drawing for small sprite 6 replaces the Verdane
  axe fighters (in enemy colours).

## Battle animations (v32)

Found by watching a Prologue battle (Gandolf vs Midir) in the emulator: DMA log, RAM writes, traces.

- **Lookup** `$95:A2C8`: each fighter's (class `$0D4E`/`$0D5C`, weapon kind `$0D5B`/`$0D69` high
  nibble, character `$0D50`/`$0D5E`, gender `$0D5A`/`$0D68`) is matched against **`$97:88C9`**,
  206 rows of 8 bytes: `class, kind, character (0 = any), gender, anim, body, upper, palette`. Class
  must match; then kind (9 = any), then character when the row's is non-zero, then gender. When the
  search fails part-way it takes the result of the row before (`$95:A378`); no class match uses row 0. Results go to `$7F:E1B6`-`E1B9` (and `E1BA`-`E1BD` for the other side). Weapon kinds:
  0 sword, 1 lance, 2 axe, 3 bow, 5 thrown lance, 6 thrown axe, 7 magic, 8 staff. Rows 184/185 are
  Julia's own (character 43).
- **Animation** (`$95:8AB7`): byte at `$97:874F + 1 + id` -> record `$97:87AF + 6k`: ptr24 script
  base, ptr24 tile-page table. 47 records, ids 0-94.
  - Script base: word ?, word `lt` (offset of the frame-layout table), then motion offsets from +4
    up to `lt`. Layout table: one offset per frame (count = first motion offset - `lt`) / 2.
  - Frame layout: `page` (`$FF` = keep), `count`, a byte, then `count` x 5 bytes:
    x low, x high (bit 0 = sign, bit 1 = 16x16), y (signed), tile, OAM attribute (palette in bits 1-3:
    0 body, 1 second body palette, 2 weapon, 3 shadow; bits 6/7 flips). The right-hand fighter is drawn
    as stored; the left one mirrored. Second fighter's palettes are +4.
  - Motion (interpreter `$95:BB4D`): 2-byte steps. Below `$E7`: `frame, ticks` (ticks scaled by the
    object's speed, `$95:BFC6`; 0 = no wait). Commands (low byte, argument high byte):
    `$FE` end (stops the interpreter), `$FD` hold, `$FC` start the motion over (`+$1F`), `$FB n` go back
    n steps, `$FA n` wait n ticks, `$F9 n` sound n (`$98:ACC0`, unused), `$F8` nothing, `$F7` set the
    signal `$0C42` (the hit lands; almost every motion ends `F7, FE`), `$F6`/`$F5` clear/set flag bit 2,
    `$F4` wait until `$0C42` is set, then clear it, `$F3 n` set flag bit 6 and go back n, `$F2` count
    (`$95:C077`), `$F1` finish (`$95:AAFF`), `$F0` `$95:AEA2`, `$EF n` effect (`$96:DC7C`, `$96:BCEC`;
    thrown weapons), `$EE n` weapon effect from the item (`$95:DBDE`), `$ED` `$96:F9BF`, `$EC n` layer
    bits, `$EB n` show/hide (0-3), `$EA`, `$E9`, `$E8` (`$95:C697`), `$E7` count hit. Motion 0 is the
    standing pose: shown but not run (its timers don't count down). Motion numbers per action come
    from the battle code (Gandolf's hand-axe attack is motion 4).
  - Tile pages (`$95:C2A9`): word offsets per page; page = count, then count x (word sheet offset,
    word bytes); row r goes to OBJ tile 16 r. Sent each time the frame's page changes
    (`$95:C46F` queues DMAs at `$0CC4`). Fighter objects: `$0B00 + $43 n` (+`$19` script ptr24,
    +`$1D` frame, +`$21` script position, +`$27` sheet ptr24 in `$7F`, +`$2A` page table ptr24,
    +`$2D` VRAM base `$4000`/`$5000`).
- **Body graphics** (`$95:84D7`, uses `E1B7`): byte `$97:8039 + 1 + id` -> record `$97:80A1 + 5k`:
  ptr24 compressed sheet (`$80:AA02` format) to `$7F:0000` / `$7F:6000`, word overlay (`$FFFF` none,
  else `& $7FF` indexes ptr24s at `$97:84B6`; overlay = word count, then count x (word offset, 32-byte
  tile) patched into the sheet, `$95:90C6`).
- **Upper body** (`$95:8400`, uses `E1B8`): byte `$97:828B + 1 + id` -> record `$97:82D3 + 7k`: OBJ
  tile, tile count (both `$80` = tiles `$80-$FF`), ptr24 compressed tiles, word overlay. Record 0 =
  none.
- **Palette** (`$95:858D`, uses `E1B9`): byte `$97:84B6 + 1 + id` -> `$97:8521 + 4k`: ptr24 colours,
  byte count (30 = one palette, 62 = two). Colours go from OBJ colour 1 (`$0200 + 2`, other side
  `+$82`). `$97:86AD` overrides it per character: word character, byte class, byte palette; `$FFFF` ends.
- **Weapon** (`$95:8697`, A = item id): word `$99:8725 + 2 item`: low byte = sheet (ptr24 at
  `$99:881F + 3k`, 32 tiles to OBJ tiles `$40-$5F`), high byte = palette (15 colours at
  `$E0:0F30 + 30 p`) to OBJ palette 2.
- **Cue table** `$97:C884` (`$95:E400`, read when a motion's `$FA` cue fires): byte per animation id
  -> record at `+$60 + 9k`: ptr24, ptr24 (cue list, read with Y), word (to object `+$2F`). A new
  animation id needs an entry here too.
- **Data bank**: the frame code (`$95:C51F` and others) sets DB to the script's bank and also reaches
  RAM buffers through it, so a script (and its page table) must sit in a bank whose `$0000-$1FFF` is
  RAM: `$80-$9F`/`$00-$3F` style banks. The kit puts new ones in the upper halves of `$70-$7D`, used
  through their `$30-$3D` mirrors.
- **Kit v34**: a look can also change motions and add frames (copies of existing ones). Script blocks
  are rebuilt: `4`, layout-table offset, motion offsets, layout offsets, motions, layouts (all
  relative). Verified: Gandolf's motion 4 with its first frame at 48 ticks makes the battle 60 frames
  longer (two attacks); motion 4 with every time tripled, about 120.
- **Kit v33 (redrawn looks)**: the animation, body and cue tables are copied to free space with 256
  id bytes each (records after `+$100`); the reads above are repointed (`$95:8ABF`/`8AD2`/`8AD9`/
  `8AE0`/`8AE7`, `ADC` at `$95:8ACD`; `$95:84E2`/`84F5`/`84FB`/`8527`/`8538`, `ADC` at `$95:84F0`;
  `$95:E41E`/`E432`/`E438`/`E43E`/`E444`/`E44A`/`E450`, `ADC` at `$95:E42D`). New animations get ids
  `$5F+`, new bodies `$67+`; a new animation is a copy of its base script with new layouts for the
  redrawn frames and a page table with one new page each (one chunk to OBJ tiles `$00-$3F`), and the
  new body is the base sheet plus the new tiles (at most `$6000` bytes decompressed).
- Verified: rendering frames from these tables matches the battle on screen; changing row 10 (Bow
  Knight, bow) to the Paladin row's four numbers made Midir fight as a Paladin; a redrawn Bow Knight
  look (frames 1-5 recoloured) plays frame for frame like the original with the new drawings.

## Spell effects (v35)

Found by running the Prologue battle with Gandolf frozen as a Fire Mage holding Fire (`lsrun --freeze`
on `$0D5C`, `$0D60`, `$0D69`).

- **Item -> spell** `$99:832D`: 3-byte rows `item, spell, spell at range`, ending `$FFFF` (46 rows:
  the magic swords, tomes and staves). `$96:DC7C` looks the attacker's item (`$0D52`/`$0D60`) up when
  a motion's `$EF` step runs (`$95:BE26` -> `$96:BCEC`); not found = spell 0. The second spell is used
  when `$7E:4EAB` >= 3 (Physic 69/28, Restore 34/70, Silence 71/36, Sleep 37/72, Berserk 38/73).
  Read at `$96:DC91`, `$96:DCB6`, `$96:DCBC` (long addressing; the kit moves a longer table to free space).
- **Spell scripts** `$97:8F7D`: word offset per spell (105), relative to the table. `$96:A4B2` starts
  one (A = spell; pointer `$7F:E4B9`/`E4BC`, bank `$97`). Script words: command = bits 9-13
  (`$96:A3F3`, under `$19`), the rest an argument; commands run effects, palette changes, waits.
  Other effects started the same way: `$2D` and `$4A` at battle start (`$96:883B`, `$96:888B`), `$31`,
  `$34` (`$96:F33C`, `$96:F326`).
- **Effect graphics** `$97:B081`: 10-byte records (compressed source ptr24, destination ptr24, ...),
  queued by `$96:B945` (Y = record) through the decompression queue at `$04:49` (`$80:A637`, run by
  `$80:A5F8`); a spell's background tiles are then copied to BG VRAM (`$2000+`, `$3800+`).
- Verified: Fire -> spell 4 plays Bolganone's red blast; the table moved to `$70:0000` with an extra row
  still drives the effect.

## Spell graphics (v36)

- **Script stepping** (`$96:A28B`, once a frame): `$FFFF` ends the script, `$FFFE` waits until the
  spawn counter `$7F:E4B8` is 0, `$FFFD`/`$FFFC`/`$FFFB`/`$FFFA`/`$FFF9`/`$FFF8` run helpers and go on in
  the same frame; any other word is one command (`$96:A3F3`: bits 9-13 index the 3-byte table at
  `$96:A42C`, 25 commands; bits 14-15 = `01` count a spawned effect). Commands advance the pointer by 2.
  Spells 0-76 are real scripts; table entries 77-104 point into other data.
- Commands that load pictures: `$01` (`$96:B945`, record = arg & `$1FF`) and `$14` (record or record+1,
  by side). `$02` writes a byte/word program (`$97:B67D` table) into direct page/registers; `$03` n >= 8
  palette programs; `$04` scene set-up.
- **Records** `$97:B081`, 10 bytes: src ptr24 (fe4lz, `$80:AA02` format), dst ptr24 (always `$7E:8B88`),
  VRAM word address, byte count. 136 records; the ones with dst 0 (27-31, 34-35, 115, 117-118) are
  placeholders the Thief/Charm scripts name but never draw. 128 real ones; 94/95/97/98/108 unused by
  spells 0-76. The byte count can differ from the decompressed length (the DMA copies the count).
- **Layers during a spell** (from `lsrun` with `REGLOG`): mode 1, BG1 tiles from VRAM `$0000`
  (4 bpp; spell tiles go to `$0000-$37FF`), BG1 map usually `$3800` (64x32) or `$3000` (32x64),
  BG2 map `$6000`, BG3 map `$7000` (or `$2000`/`$2C00`/`$3000`) with 2-bpp tiles at `$3000` or `$7000`;
  sprites `$4000-$5FFF` (status staves: records 129-133 at `$47B0`/`$57B0`).
- How the kit tells them apart (fe4spellfx.survey): a record whose words use at most 4 palette numbers
  is a tilemap (always at `$3800-$3FFF` and `$6000+`), unless another tilemap of the spell points at
  tiles inside it; tiles are 4 bpp when a tilemap points into them counting from `$0000`, else 2 bpp
  when one points in counting from `$3000`/`$7000`.
- **Colours** are not in the records: the battle cycles them (Fire: colours 9-15 of palette 1 rotate
  every 6 frames) and takes some from the terrain, and no frame's palette is stored as-is in the ROM.
  The editor shows colour numbers through a fixed ramp.
- Verified: Fire's record 36 redrawn (colours swapped, pillars blanked) shows in battle with the new
  colours; Bolganone's 2-bpp record 14 mirrored shows mirrored flame strands in the pit.

## Spell colours and new effects (v37)

- The script table at `$97:8F7D` has **77** entries (the first offset is 210 because spell 0's script
  isn't first; the smallest offset, 154, ends the table). Kits up to v36 counted 105.
- Palette buffer `$7E:0100-$02FF`, sent to CGRAM every frame (DMA from `$00:0100`).
- **Command `$0E`** (`$96:BB70`): record from the word-offset table `$97:AFE5` (23 records):
  `start colour, count, ptr24`; copies `count` little-endian colours (bank `$E0`, e.g. Elfire's
  `$E0:20A0`) to the buffer at `start`.
- **Command `$0B`** (`$96:DB58` -> `$96:DB94`): record from `$97:A9A8` (191 records):
  `slot, type, start, count` + data; sets up a 10-byte slot at `$7F:FD9A + 10*slot` run every frame by
  `$96:D695` (type table `$96:D6DD`). Types: 0 frames of `count` colours, 1 and 12 push one new colour in
  at the end (12 transformed by `$96:DACB`), 2 at the start (Fire's fireball: `$9B:D9F2`, colours 9-15
  of palette 1), 3-6 rotate (one delay byte), 7 fade towards `count` colours at ptr24 (after a delay byte;
  bank `$E0` or the RAM copies `$7F:F636`/`$7F:FE62`), 8/9 clear/fill, 10 copy `count` colours from
  ptr24, 11 stop. Data types 0/1/2/12 point at streams in bank `$9B`: `$FF` end, `$FE` start over,
  `$80+n` delay n frames for this step, otherwise a colour high byte first.
- Spell colours live only in banks `$9B` and `$E0`; the kit edits a colour set by copying it to free
  space and repointing the spell records that used it.
- **Table pointers** (all in bank `$96`; LDA #bank00 / LDA-ADC #address):
  scripts `$A4D4` / `$A4DD`, `$A4EC`; pictures `$B950` / `$B961`; colour effects (`$0B`) `$DB6D` /
  `$DB78`, `$DB83`; palette loads (`$0E`) `$BB72` / `$BB88`, `$BB7D`. All reads go through `[$24]` long,
  so the tables (and scripts) can sit in any bank: a project with new effects moves all four to
  `$70+` free space with the copies appended. Script words carry 9-bit record numbers (511 max).
- Verified: a copy of Fire with blue colours and a redrawn fireball plays for the Fire tome while
  Elfire keeps its colours; a copy of Bolganone given to Thunder plays Bolganone; battles finish.

## Spell steps (v38)

Script commands by handler (table `$96:A42C`, 3 bytes each); arg = word & `$1FF`:

| Cmd | Handler | What |
|---|---|---|
| `$00` | `$96:ABF6` | sprite effect, record from `$97:A411` |
| `$01` | `$96:B945` | load picture record (`$97:B081`) |
| `$02` | `$96:BCF1` | byte/word program from `$97:B67D` into direct page / registers (layer set-up) |
| `$03` | `$96:BD93` | n < 8: palette set n+5 (`$82:C0EF`); n >= 8: screen colour program from `$97:BD3E` |
| `$04` | `$96:CA1C` | scene set-up |
| `$06`/`$07` | `$96:B9B7`/`BB0C` | load data records (`$97:B5D1` 6 bytes / `$97:B60D` 7 bytes) |
| `$08` | `$96:C9D9` | screen routine pointer from `$97:BDD4` to `$7F:ECFF` |
| `$0A` | `$96:BBC2` | **pause** arg frames (`$7F:E4BE`, counted down before the next step) |
| `$0B` | `$96:DB58` | colour effect (above) |
| `$0D` | `$96:DEC0` | background motion, record from `$97:BEAC` (layer, type `$96:DF60`, data) |
| `$0E` | `$96:BB70` | set colours (above) |
| `$14` | `$96:B9A4` | load picture record or record + 1 by side |
| `$15` | `$96:BC4C` | **sound**: word from `$98:AD04` + arg*2 -> `$80:900D` (+`$2000` for one side) |
| `$16`/`$17` | `$96:BC72`/`BCAF` | sound panned at the attacker / target (`$9E:B4BB`) |
| `$18` | `$96:BBD2` | pause arg frames (`$7F:E4C0`, cleared when `$E4` = `$80`) |

Bit 14 (`01` in bits 14-15) counts a spawned part in `$7F:E4B8`; `$FFFE` waits for it to reach 0.
Control words: `$FFFD`/`$FFFC` signal the attacker's / the other fighter's animation (`$95:C057`/`C077`,
`$7F:E184`, the `F4` wait-for-signal in motions), `$FFF9` hit or dodge (`$96:F9BF`), `$FFFA` `$95:AEA2`,
`$FFFB`/`$FFF8` `$95:B006`/`B02B`.
- Colour stream speed: a delay byte (`$80` + n) holds a step for n + 1 frames and stays in force for the
  steps after it; the kit's "Changes every N frames" writes one delay at the start of the stream.
- Verified: Fire with a 60-frame pause after its first wait shows the fireball 60 frames later and the
  battle ends normally; Bolganone with one colour set at 8 frames per step plays to the end.

## Background motions (v39)

- Command `$0D` records: word-offset table `$97:BEAC` (78 records, packed so that records share bytes).
  The handler reads it at `$96:DECA` (LDA #$9700), `$96:DECF` (LDA `$97BEAC`,X, long) and `$96:DED4`
  (ADC #$BEAC); the kit moves it with the other tables and gives each record its own bytes.
- Record: `layer (& 3), type (& $1F)` + data; slot of `$15` bytes at `$7F:E475` (flags, position
  `$E476/$E477`, velocity `$E47C/$E47E` 8.8, count `$E480`). Types (`$96:DF60`): `$01` place at the
  attacker, `$05` at the target (from `$0AF9`/`$95:B5FD`), `$17` move: x, y (signed pixels per frame,
  negated for one side by `$0B24` bit 15), frames (word); `$1A` the same and also sets `$7F:E4B4`;
  `$1B` fly to the target at a speed (byte; `$96:E654` works out the velocity: Fire's fireball is
  `$0C`, `$30` reaches Midir about 12 frames sooner, `$04` crawls); `$18` the same aimed 16 px higher;
  `$16` follow a motion path (ptr24, bank `$97`).
- Verified: Fire's record 18 at speed 4 / 48 changes the fireball's flight and the battle finishes.

## Battle preview (PC port 0.9)

- The port takes `--turbo-until N` (no sound, as fast as possible until frame N), `--loop-at N` (then
  go back to frame N's state when reaching N), `--freeze ADDR VAL FROM` (from frame FROM, writes to RAM
  ADDR store VAL, through `snes_writeMap`), `--state-cache FILE` and `--title`.
- `dev/battle_preview.txt` is an input movie from power-on (new game, Prologue up to the enemy phase);
  the kit freezes `$0D5C=$35`, `$0D60=$3E`, `$0D69=$74` from frame 25200 (Gandolf becomes a Fire Mage
  with Fire), points Fire at the chosen effect in a copy of the ROM with only battle and spell changes,
  runs fast to frame 25300 (cached) and loops at 26250 plus the effect's pauses.

## Maps (V)

### Chapter map headers

Map headers are 12 records of 27 bytes. The pointer table is at `$88:9FC3` (file `0x089FC3`).

| Off | Field |
|---|---|
| +0 | ptr24, map layout, compressed |
| +3 | ptr24, chapter metatiles 0–255, compressed (2 KB) |
| +6 | ptr24, chapter BG tiles, compressed (4 KB, goes to VRAM `$5000`, tiles `$280–$2FF`) |
| +9 | ptr24, palettes 1–7, raw (224 bytes, goes to CGRAM byte 32) |
| +12 | width mode (`4` = 64 tiles wide) |
| +24 | ptr24, terrain type per metatile, compressed (1 KB) |

### Map layout

- **Format:** 64 × 64 cells (all 12 maps), stored as 16-bit words. `word & $3FF` is the metatile.
- **Area flags (V):** bits 10–15 of a cell are flags. Each value seen is a single bit (1, 2, 4, 8, 16),
  in blocks of cells (chapters 2–5 and 7–11 use them; the prologue and chapters 1 and 6 don't). What
  reads them isn't mapped yet; the editors keep them when painting.
- **In RAM:** the game keeps the map at `$7F:2400`.
- **Drawing:** the draw code is `$88:8EBB`. The row stride comes from `$075C` (4 → 64 tiles, 8 → 128 tiles).

### Metatiles

- **Layout:** each metatile is 4 tilemap words at `$7F:0000 + 8n`, ordered TL, BL, TR, BR.
- **Sources:** metatiles 0–255 are per chapter (the +3 pointer). Metatiles 256–1023 are shared, raw at `$D9:5000`.
- **Graphics:** shared BG tiles are raw at file `0x190000`.
- **Terrain:** terrain comes from the metatile, so painting water makes a cell impassable (V).
  The +24 header pointer is one terrain type byte per metatile (0–46 seen).
- **Terrain names:** a table of 13-byte records at file `0x503000` (`[tiles][0][word VRAM][word][0]` + text)
  has Naga's text for types 0–7: Peak, Thicket, Cliff, Plain, Woods, Sea, Stream, Mountain(s); later
  types have no text there. The editor names the others from how they look (8 desert, 9 castle,
  13 castle walls, 14 wasteland, 15 bridge, 18 houses, 22 village, 25 road…).

### Redrawing tiles (kit v24)

- Metatile words: tile (10 bits), palette row << 10, h-flip `$4000`, v-flip `$8000`; the priority
  bit is never set. Chapter metatiles use rows 1–5 (row 0 = `PAL0` rarely).
- Chapter 8×8 tiles 640–767: 106–125 are used by the chapter's metatiles (17 of them by shared
  metatiles), leaving 3–22 free per chapter.
- **Animated tiles:** `$88:CFC2` sends 32 tiles (`$400` bytes) from `$DC:xxxx` (frames `$400` apart,
  table `$88:D013`) to VRAM word `$0A00` = tiles 160–191; tiles up to 254 also changed during play.
- **BG1 and BG2 share char base 0** (`$7A` shadow of `$210B` = 0): BG2's windows use tiles 768–910,
  and dialogue fills tiles 928+, so those aren't free.
- **Shared pool (kit v26):** shared tiles 0–639 that no chapter's metatiles use, outside 128–255:
  25 tiles (264, 271, 280, …). Verified: the Prologue with 10 redrawn tiles (23 pool tiles in use)
  shows them right at the start and after enemy phase 1 with battles and scenes (VRAM matches the
  ROM data for every tile outside 128–255).
- Verified: Prologue tile 66 redrawn from a picture (4 new 8×8 tiles, grass reproduced by
  colour matching) shows on all 50 cells; its terrain set to Peak (0) takes those cells out of
  Sigurd's move range. The kit recompresses the chapter's +3, +6 and +24 data into free space.

### Compression

The decompressor is `$80:AA02`. `$80:A9F2` is a second entry that sets `$D2` = 1 and starts the
source index at 0; streams decoded through it go wrong after the source crosses `$xx:8000`
(chapter 5 and endgame maps, chapter 9 map tiles). Kits up to v15 used `A9F2`; v16 uses `AA02`
everywhere, which decodes all 12 maps to exactly 8192 bytes.

- Source pointer: `$C8–$CA`
- Destination: `$CB–$CD`

| Control byte | Meaning |
|---|---|
| `00–3F` | literal run of n+1 bytes |
| `40–7F` | packed and RLE variants |
| `80–BF xx` | back-reference: `((b>>2)&15)+2` bytes, `((b&3)<<8)|xx` bytes back |
| `C0–FD` | longer back-references and runs |
| `FE`/`FF` | end of stream |

- **Writing streams:** `fe4lz.py` writes streams using only literals, back-references and the end byte.
- **Verified:** all 12 maps round-trip byte-for-byte through the game's own decompressor (`AA02`), run on the emulator.
- **Edited maps:** these are written to banks `$78–$7D` (upper halves, never crossing a bank) and the header is repointed. Verified in-game.

## Map locations: castles, villages, sites (V)

- **Where:** per-chapter info pointers are at `$86:C760` (12 used). Each info
  block starts with five word pointers into its own bank:

| Off | Points to |
|---|---|
| +0 | location list `[count][word ptr × count]` |
| +2 | not decoded (7-byte records with x/y; possibly map changes) |
| +4 | arena table, or 0 (see below) |
| +6, +8 | not decoded |

- **Location record:**

| Off | Field |
|---|---|
| +0 | index in this chapter |
| +1 | castle name ID (names at `0x505000 + 16·id`, text at +8; e.g. `$0C` Chalphy, `$22` Evans) |
| +2 | kind: 0 castle, 2 village (the only kinds the game uses) |
| +3 | x |
| +4 | y |
| +5 | castles only: castle-town facilities (below); 0 on each chapter's final castle |
| +6–7 | castles only: armory stock pointer, or 0 |

- **Kind table:** `$87:F453` holds word offsets to 10-byte records, one per kind.
  - +0 word: starting village gold (`$1388` = 5,000 for kind 2)
  - +2..+5: footprint around (x, y): castle −1..+1 × −1..+2, village −1..+1 × −1..0
  - Lookup routine for map cells: `$87:EA09`.
- **Visiting:** event condition `$0A COND_VISIT` takes the location index. In
  the Prologue, villages 3–7 run scenes 20–24.

### Castle-town facilities (+5) (V)

The town menu (`$8A:9858`) blanks each button whose bit is clear:

| Bit | Button |
|---|---|
| `$80` | Armory |
| `$40` | Pawnbroker |
| `$20` | Blacksmith |
| `$10` | Supply |
| `$08` | Augury |
| `$04` | Arena |

Vanilla values: `$78` in the Prologue (no Armory or Arena), `$FC` in most
chapters, `$F8` in chapter 6 (no Arena). Verified: setting Chalphy to `$FC`
adds working Armory and Arena buttons to the Prologue.

### Armory stock (+6) (V)

- A word pointer (same bank) to item **instance** bytes, ending `$FF $FF`.
- At chapter start `$87:EBC8` walks the list. Each instance whose state is
  still 7 (unused) is set to state 4 (on sale) with this castle's location
  index as owner. Item states are kept in a list at `$7E:3D87` that
  `$82:E810` searches: state 7 = unused, 4 = on sale, 1 = carried by a unit.
- Vanilla: the first castle of chapters 1–4 and 6–10 has a list (4–23 items).
- Verified: pointing Chalphy at a five-item list in bank `$90`'s free tail
  shows those five items in a Prologue armory.

### Village gold (V)

- At chapter start `$87:EBEA` calls `$87:F391` (kind → gold) and stores the
  result at `$7E:4E55 + 2·index`. Visiting reads it back through `$87:EDEB`
  and adds it to the visitor with `$84:B23C`, capped at 50,000. Brigands
  reduce it through `$87:EDF8`.
- So every village starts with the same 5,000. `fe4locations.py` gives
  villages their own amounts with a hook: the call at `$87:EBEA` becomes
  `JSL $7D:F000`, which looks up `[record ptr16][bank][gold16]` entries
  (table at `$7D:F060`, ends `$FFFF`) and falls back to `$87:F391`.
- Verified: a village set to 12,345 pays exactly that; the others still pay 5,000.
- Item and stat rewards are ordinary scene commands: `$4A $57` (give item)
  and `$4A $70` (stat boost), listed in `events/scenes.evt`.

### Arena (+4) (V)

- `[melee list ptr][ranged list ptr]`, each a list of unit ID words ending `$FFFF`.
- `$87:A082` picks `list[rank]` (rank 0–6 from `$84:96A0`). The ranged list is
  used when the fighter's weapon reaches 2 or more. If that unit is already
  in play (`$84:84B4`), the next entry is used instead. That is how chapter 2's
  rank 7 is Holyn until he joins, then Chaimos.
- Opponents are ordinary units: their class, level and items are in
  `units_generic.csv` (IDs 480 onward).
- The Prologue and chapter 6 have no table (pointer 0).
- Verified: a new Prologue table put Tiburon at rank 1.

### Talk menu (+6) (V)

- Word pointer (same bank) to 8-byte entries ending `$FFFF`; 0 = none (chapter 4):
  `[flag-chapter word][flag][unit A word, $FFFF = anyone][unit B word][needs]`.
- `$87:9E42` (called from the map action menu, `$84:8A42` and others) walks the
  list. A = the moving unit (`$056F`), B = the unit beside it (`$0574`).
  - `$86:8294` skips the entry once the flag is set: `$86:821F` finds the
    flag-chapter's block in `$7E:52B7`, `$86:9A50` tests the flag.
  - needs 0 = always, 1 = the talker has 10,000 gold or more (`$84:9F0D`),
    e.g. chapter 2's "anyone → Beowulf".
- The talk itself is a trigger-list condition `$04`/`$16` with the same pair and
  flag. A `$04` condition without an entry here never fires from the menu.
- Verified: entries for Sigurd → Noish/Alec/Arden in the Prologue (new list at
  `$90:F7BE`) made "Talk" appear and the new talk scene play.
- Kit: `talks.csv`.

### Other verified edits

- Renaming Chalphy to castle ID 42 shows "Kapathogia" in the terrain window.
- Moving village 3 next to Sigurd gives him a Visit command there; the scene
  plays and pays the village's gold.

## Armies and enemy AI (V)

- **Army table:** `$86:C784`, 72 × ptr24 (army IDs 0–71). `$86:C55A` returns
  record n in Y with its bank in DB. Each chapter's opening script assigns
  armies to slots with `$4B [slot][army]`.
- **Army record (9 bytes):** the pointers are 16-bit, in the record's bank.

| Off | Field |
|---|---|
| +0 | name: castle name ID (`$35` reads "Sigurd's", `$FF` none) |
| +1, +2 | unknown (player armies 6/3; enemies mostly 7 or 4 / 13) |
| +3 | → member unit IDs (words, `$FFFF`), spawned or joined at setup (`$84:BC42`) |
| +5 | → location indices the army holds (words, `$FFFF`), claimed at setup (`$84:BC21`) |
| +7 | → AI programs (ptr24 each, `$FFFF`) |

- **Setup:** `$84:BBD2` runs per slot in `$4B` order, so a later slot's castle
  claim overrides an earlier one. Verified: moving Jungby from army 1 to army
  2 makes it Verdane-held at the start (`$7E:4E45+1` owner = slot 1).
- **Program choice:** `$87:D9B9` takes the unit's deploy `orders` byte n and
  loads entry n−1 of the army's +7 list into `$0E90`.
- **AI VM:** `$87:CD1E`, 36 opcodes through `$87:CD38`, `$FF` ends.
  - Each handler returns carry set when the unit has a job (decision made)
    or clear to fall through to the next command.
  - The program restarts from the top on every unit turn.
  - Argument lengths are taken from the handlers' fall-through paths, and
    every program in the ROM decodes cleanly with them (737 commands).

| Op | Args | Meaning |
|---|---|---|
| `$00` | – | stop |
| `$01` | addr16 | go to |
| `$06` | loc, mode | seize an enemy-held castle |
| `$07` | loc, mode | return to and hold an own castle |
| `$08` | loc | raid a village (kind 2, not yet destroyed) |
| `$09` | flag16, bit, x, y | move to (x, y) unless flag set; set it on arrival |
| `$0A` | – | attack whatever is in reach |
| `$0D` | unit16 | target a unit |
| `$0E` | unit16, n | follow a unit, staying within n |
| `$15`/`$16` | flag16, bit | set / clear an event flag (`$8699D6` / `$869A13`) |
| `$17` | – | raid any village |
| `$18` | – | attack anyone |
| `$1F` | turn, addr16 | go to once turn ≥ n (turn at `$0D8F`) |
| `$20`/`$21` | flag16, bit, addr16 | go to if the flag is set / clear (`$868294`) |
| `$22` | addr16 | go to if nothing can be attacked this turn (`$87:D411` fails) |
| `$03` | n | pace: n/256 of its move (0 = full) |
| `$04` | slot | never attack the player unit in that slot |
| `$0C` | shape, facing | march in formation |
| `$0F`/`$10` | – | go back to its castle (always / when no enemy is near) |
| `$11` | n | go home when under n/256 of its group is on the map |
| `$1E` | n, word | go home to heal when HP ≤ n/256 |
| `$23` | ptr24, addr16 | go to if the 65816 routine returns carry |

- **Handler details** (v30; decision in `$7E:201A` = action, `$7E:2002` = mode).
  Handlers return carry set when the unit has its job for the turn, clear to
  go on to the next command. Settings (`$02 $03 $04 $05 $0C`) always go on.
  - `$00` sets action 0 and stops: the unit does nothing this turn.
  - `$02 m` sets the mode `$2002`. Known: mode 1 turns into 2 once enemies are
    in reach (`$86:AF43`, table `$86:AF57`); modes 4 and 5 keep the group's
    centre where it is (`$86:B090`); 3, 6 and 7 skip a target check in `$86:B7E0`.
  - `$03 n` = **pace**: `$2008` = move (`$84:9D61`) × n / 256 + 1, or the full
    move when n = 0. `$86:B0B6` uses it to pick how far the group's centre
    advances (`$86:A6CD`, `$86:AD5E` → `$2010/$2012`).
  - `$04 n` = **spare a slot**: `$201E` = n; `$18`'s target loop skips a unit
    whose `$84:A358` (record +4 & `$7F`, the player army/love slot) equals it.
    Vanilla: `04 12` (Raquesis) in Eldigan's army, `04 08` Lewyn, `04 17` Aideen, `04 01` Sigurd.
  - `$05` sets bit 9 of `$7E:2000` (unused in the game; effect unknown).
  - `$06 loc mode` falls through once the castle check (`$84:C15F` ≠ 1) fails,
    i.e. after it is taken; otherwise action 1 toward the castle, mode = arg.
  - `$07 loc mode` only acts while the castle's owner is the unit's army
    (`$0E7E`); mode 5 runs `$0B` instead; if `$87:D411` finds a target it runs
    `$18`; otherwise action 6 and, when no formation is set, formation 13 facing 0.
  - `$0A`: if `$87:D411` finds something attackable this turn, `$18`; else
    action 4, mode 4 (stay). `$0B`: action 5, mode 5 when `$2000` bit 2 (targets
    listed) is set, else go on. `$22 addr` jumps when `$87:D411` finds nothing.
  - `$87:D411` walks the group's target list (`$7E:2022` count, 14-byte
    entries from `$2024`) through `$87:D45B`; carry set = a target can be hit
    (index in `$0E82`, sets `$2000` bit 6).
  - `$0C shape facing` = **formation**: `$2004` = shape, `$2006` = facing & 3.
    `$87:DA53` places each group member at the centre (`$2010/$2012`) plus an
    offset: shape table `$87:DCD8` (15 word pointers, then 18 signed x/y byte
    pairs per shape, indexed by the member's place `$84:C935`), turned by the
    facing (`$87:DAB0`: 0 = (x, y), 1 = (−y, x), 2 = (−x, −y), 3 = (y, −x)).
    With members behind the leader (negative y) facing 0 marches south.
    Not confirmed in game: in a Prologue test (DiMaggio's group, program
    replaced by `0C s 0` + seize or move-to), shapes 0, 5 and 7 left the
    group on the same tiles after enemy phase 1. It may only show when the
    leader is on the map or over several turns.
  - Tested from power-on (v30): the same group's program set to `00` keeps it
    at its start tiles; `09` move-to (22,16) moves it toward there.
  - `$0D unit` aims at the unit (action 3) unless it is off the map (status
    bit 9) or bit 13. `$0E unit n` follows it (action 8, distance `$201C` = n).
  - `$0F` = go back to its castle (action 9, mode 2, `$2000` bit 8). Actions
    9, 10 and 12 head for a castle the army holds (`$86:BD06`: `$84:BE3D` →
    kind 0) with command 3 (10: `$0D`). `$10` does it only while `$7E:5025` = 0
    (no enemy near). `$12` attacks via `$18` then action 11 (back toward the
    target tile).
  - `$11 n`: when the unit (`$2020`) is on the map and the share of its group
    still on the map (`$87:D3BD`: units with the same `$84:973F` as `$0E80`,
    minus those with status bit 9, ×256 / total) + 1 < n: action 10, home.
  - `$13`: action 7, mode 5 (hold). `$19`: `$18` with mode 7.
  - `$14 n`: on turns that are multiples of n (`$80:A17E` remainder), if the
    group is not all on the map, `$84:C54C` runs `$84:A9B6` on every member
    with status bit 9 (off the map) and `$87:D811` regroups: probably
    reinforcements.
  - `$1A`–`$1D` (one handler, `$87:D1FE`): for each enemy in `$7E:5030`
    (13-byte entries, count `$5025`), count its four neighbours that are free
    or held by the group; at 3 or more, follow it at distance 1 (close in).
  - `$1E n w`: when the unit's HP × 256 / max HP − 1 < n, or (status bit 15
    clear and HP share < word w, `$0100` = not full) → `$18` targets, then `$0F`.
    Vanilla `1E 4C 00 01`: home to heal at about 30%.
  - `$23 ptr24 addr` calls the routine and jumps when it returns carry clear.
- **Unit positions (RAM):** unit object +4 = index i, x = `$7E:441B + i`,
  y = `$7E:44AB + i` (words); +6 army slot, +7 deploy `orders`.
- **Verified in-game:**
  - Setting `orders` to 0 for four Prologue units kept them in place during
    enemy phase 1 while the rest moved as usual.
  - Changing army 2 orders 2 from "turn ≥ 3" to "turn ≥ 1" made exactly
    those four units (0.4–0.6, 0.17) march on turn 1.
  - Kit v21: army 2 program 1 rewritten as `00` ("stay put", via the editor)
    kept 0.0–0.3 at their starting tiles after enemy phase 1; in the
    unedited game they march toward Jungby ((45,17), (48,14), (51,13), (58,13)).
- **Kit:** new lines in `ai_orders.evt` can jump to a command of the same
  program with `@Lk` (k = its position in the program, from 0).

## Skills (V)

- **IDs:** 1–29. `HasSkill` (`$87:A19D`, ID in A, unit in `$056F`) tests three
  masks per ID, all in bank `$87`:

| Table | Entry size | Tested against |
|---|---|---|
| `$87:A1EA` | 3 bytes | the unit's 24-bit personal field (record +28), loaded by `$84:A58A` into `$0571/$0572` |
| `$87:A244` | 2 bytes | the class skill word (class +28), read by `$87:A6D1` |
| `$87:A280` | 2 bytes | each carried item's skill word (item +8), checked by `$87:A2EF` |

- **Names and sources:**

| ID | Name | Sources |
|---|---|---|
| 1 | Canto | class 0, item 12 (Knight ring) |
| 2 | Pavise | class 1 |
| 3 | Wrath | personal 0, class 2 |
| 4 | Pursuit | personal 1, class 3, item 11 |
| 5 | Adept | personal 2, class 4 |
| 6 | Steal | class 5, item 0 |
| 8 | Dance | class 7 |
| 10 | ? | class 9 (Troubadour), item 1 |
| 11 | ? | personal 3, class 10 (Knight Lord) |
| 12 | Charm | personal 4, class 11 |
| 13 | story flag | personal 5 (Deirdre, Julia) |
| 14 | Nihil | personal 6 |
| 15 | Miracle | personal 7, item 3 |
| 16 | Critical | personal 8, class 12, item 4 |
| 17 | Vantage | personal 9 |
| 18 | Accost | personal 10 |
| 19 | Astra | personal 11 |
| 20 | Luna | personal 12 |
| 21 | Sol | personal 13 |
| 22, 23 | unused | personal 14, 15 |
| 24 | Renewal | personal 16, item 5 |
| 25 | Paragon | personal 17, item 6 |
| 26 | story flag | personal 18, item 7 (Finn, Quan, Ethlyn) |
| 27 | Recover | personal 19, item 8 |
| 28 | Bargain | personal 20, item 9 |
| 29 | Return | personal 21, item 10 |

- **Skills menu:** lists the IDs in the word table at `$8B:DFBF`
  (2 3 4 5 6 8 12 14 … 28). Its names are pre-drawn tiles.
- **Activation:** `$84:E14C` loops IDs 19–23 for the attacker, unless the
  defender has Nihil (14).
  - The rate is `JSL $849BCB` (Skl), and `$84:EF9C` rolls it against
    `$80:A73A`. The activated ID goes to `$7E:CCDC`.
  - Verified: with a 100% Astra rate, `$7E:CCDC` = 19 and Sigurd strikes five times.
- **Effect constants:**

| Skill | Code | Constant(s) |
|---|---|---|
| Wrath | `$84:E663` | crit = `#100` at `$84:E67F` |
| Charm | `$84:DBDC` | `#10` |
| Miracle | `$84:FAC6` | threshold `#11` (`$84:FADC`, `$84:FAE6`), step `#10` (`$84:FAEB`) |
| Renewal | `$84:AFF9` | `random(#6) + #5` |
| Recover (27) | `$84:B022` | full heal |
| Paragon (25) | `$84:EF35` | experience ×2 (`ASL`) |
| Vantage (17) | `$84:E236` | HP ≤ max/2 |

- **Stat getters:**

| Stat | Getter |
|---|---|
| Str | `$84:9B15` |
| Mag | `$84:9B70` |
| Skl | `$84:9BCB` |
| Spd | `$84:9C26` |
| Def | `$84:9C81` |
| Res | `$84:9CED` |
| Lck | `$84:9D59` |

  Each getter calls `$84:A6B6` (holy-blood bonus) into `$4C`, which shows as
  "+n" on the status page.
- **Kit hooks:**
  - **Stat skills:** `$7D:F400` replaces those six JSLs. It adds `amount` for
    each `[id][stat][amount][0]` entry at `$7D:F480` when `HasSkill` or the
    item check passes. It saves `$0571`–`$0574` and `$0583`–`$0586` around the
    checks.
  - **Rates:** `$7D:F500` replaces `JSL $849BCB` at `$84:E156`. Entries are
    `[stat][pct][flat][0]` at `$7D:F5C0`, and it uses the SNES multiply/divide
    registers.
  - **More skill IDs:** these move the three mask tables to bank `$87`'s free
    tail. The kit patches the 10 operands at `$87:A1BA/A1C2/A1D4/A2D8/A2E0/A319/A38B/A3B1/A3BA/A400`,
    and keeps the names of new skills at `$7D:F600` (`'SKL'` + count).
- **Verified in-game:** a Str +5 personal skill and a Def +3 class skill show
  as "14+5" and "9+3". Knight Lord given Astra lists Sigurd as an Astra
  bearer in the Skills menu.

## Battle engine (V)

Combat structs in bank $7E: attacker (the unit that started the fight) `$4EB5`,
defender `$4F15`, `$60` bytes each.

| Off | Field | Off | Field |
|---|---|---|---|
| +00 | map slot (bit 15 = none) | +2A | weapon type |
| +06 | unit pointer (`$056F`) | +30 | attack speed (signed) |
| +08 / +0A | unit index / class | +32 | displayed hit = clamp(hit − foe avoid) |
| +10 / +12 | HP / max HP at start | +34 / +36 | hit / avoid (signed) |
| +14 | level | +38 / +3A | crit / attack (`$FF` = cannot attack) |
| +24 | flags (`$100` Pavise, `$2000` Adept) | +3C / +3E | defence vs the foe's weapon / bonus damage |
| +28 | item | +40..+5F | unused (cleared at setup) — the kit's scratch |

- **Setup:** `$84:D5DC` and `$84:B79A` end with `JSL $84D9B6` for the second
  side. The combat-bonus hook replaces that call.
- **Rounds:** `$84:DEEB` sets the striker `$CCD8` and target `$CCDA`.
  - `JSR $E0DE` picks the attack skill into `$CCDC`. It is sword-only through
    `JSL $87E48D` at `$84:E13D`; the rate is `JSL $849BCB` at `$84:E156`.
  - It pushes the event `(id<<8)|$FE` with `$82:E465` into the list at `$7E:4F81`.
  - `JSR $E2AB` counts strikes.
- **Per hit (`$84:E4ED`, variants `$E838`/`$E873`):**
  - `$E554` hit roll.
  - `$E5ED` Pavise: rate = level, event `$02FE`.
  - `$E686` crit.
  - `$E6C4` damage: atk + `$0574` − def − bonus, or no defence for Luna `$14`.
  - `$EEFF` Sol heal (`$84:A927`).
  - `$E6F6` apply (`$84:A8C7` subtracts HP from unit +0D).
- **Strike events:** `[flags][damage]`, where flag `$01` = defender struck,
  `$04` crit, `$08` miss, `$10` kill.
- **After the battle:** `$84:DD6B` (player turn) runs Canto `$84:C9E3`, then
  `$84:CAA9` to end the unit's action. That sets slot flag `$08` = done at
  `$84:CB24`. Slot flags are at `$7E:489B`/`$438B` (`$80` on map, `$40` acted,
  `$10` moved). `$7E:4EAA` bit `$30` = the attacker's blow defeated the foe.
- **Kit hooks:**
  - `$7D:E000` region: header `SFX` + table pointers (combat, effects, extra
    lists, menu).
  - JMLs at `$84:E554`, `$E5ED`, `$E6C4`, `$EEFF`, `$DD6B`, `$CB24` and
    `$87:A19D` (HasSkill: IDs 30+ also check the unit/class lists).
  - A trampoline in the `$84` tail replaces `JSR $E0DE` at `$84:DEFD`.

## Skills menu (Naga build) (V)

- **List:** 18 skill IDs at `$8B:DFBF`, read at `$80:D889`, `$8B:D9C6` and
  `$8B:DC58`. The row count is at `$80:D8E2` (CMP #18), the last row at
  `$8B:DCEE` and the bottom scroll at `$8B:DC09` (8-pixel steps).
- **Row text:** 32-byte strings at `$50:7A00` + 32×row, drawn by `$87:9354`
  from 18 unrolled calls at `$80:D523`.
  - Glyph code `$01NN` / `$02NN` = BG3 tile `$NN` / `$1NN` (top) and +16 (bottom).
  - `$8140` is the blank (tile `$FF`).
  - Glyph tiles: raw 2bpp at `$45:0000` (tiles 0–`$13F`) and `$45:D000`
    (`$140`–`$1FF`, bearer names). Free: `$E0`–`$EE`, `$100`–`$10F`,
    `$120`–`$12F`, `$1E6`–`$1EF`.
- **Help pane:** 128×64 2bpp picture per row at `$59:4000` + `$800`×row (name +
  3 lines). `$51:1500` DMAs it to VRAM `$1400` (word).
- **Icons:** 16×16 sprites from groups of 7 rows drawn by `$8B:DAB4`
  (`$80:87C7` lists). The pane icon is per row at `$8B:DB7E` (sprite tile −
  `$20`). Unused icon tiles: `$2A`, `$4C`, `$4E`, `$6A`, `$6C`, `$6E`.
- **Bearers:** `$7F:81F9` + `$40`×row, counts at `$7F:8741` (21 rows of room).
  The kit moves them to `$7F:A000` / `$7F:A800` for longer lists.
- **Status page:** the skill-icon row is built by `$87:A373`/`A39C`/`A3CD`,
  which loop over IDs 0–29 into `$7E:2002+id`. It isn't extended yet.

## Generation 2 (V)

- **Transition:** `$84:81FF`, called from the chapter loader `$84:80EC` when
  the chapter (`$0D6A`) is 6. It walks `$84:8237`: 6-byte entries (unit,
  action, param), ended by `$FFFF`, with handlers at `$84:822D`.
  - 0 = leave (`$84:B1E4`, then `$84:83B8`)
  - 1 = become another record (Finn → 34)
  - 2 = mother: make her children (`$84:BAA1`), then leave
  - 3 = Seliph
  - 4 = Altena
- **`$84:BAA1`** needs the mother alive (flags & `$200` clear), except
  Deirdre and Ethlyn, and married (lover = data block +3).
  - It takes the two children from `$83:8993` (9 offsets by army slot − 16,
    then child pairs) and the born flags from `$84:BB1E` (same layout).
  - It spawns them with `$00` = father and `$02` = mother.
- **A child's record (`$84:8F83`)** copies both parents into `$7F:EB66…`
  (mother) and `$7F:EBF4…` (father), then:

| What | Rule | Code |
|---|---|---|
| Growths | (2 × same-gender parent + other) / 2 | `$87:A9EA` |
| Stats | (2 × same-gender + other) / 10 + level-ups, capped at 15 by `$51:6300` | `$87:A83A` |
| Holy blood | heir's in full + the other parent's halved | `$87:A9FB` |
| Personal skills | (mother \| father) & a 3-byte mask per child at `$87:A975` | `$87:A8E1` |
| Gold | (mother + father) / 10 + 2000 | operands at `0x07A74F` and `0x07A75D` |
| Items | everything the heir carries | `$87:AA39` |

- **Personal block (`$16` bytes):** char ID (2), name ID (2), slot, gender,
  father ID, growths (8), skills (3), blood (4). The status screen's "mother"
  comes from `$84:A40D`, which searches `$83:8993`.
- **Heaps:** child unit objects come from the heap at `$7E:2D4F`, which is
  `$3DA` bytes, exactly 17 × (`$34` + 6). The 18th crashes the allocator
  (`$82:F032`, then BRK). Spawning is at `$84:8FDF` and loading a save at
  `$87:F611`.
- **Born flags:** event flags `$16`–`$23` (`$8680BE` sets, `$86812E` tests).
  Scripts use them as `07 f / 03 T / [substitute] / 02 E / T: [child]`.
  - Chapter 6's opening (scene 217) places Ulster or Rodolbahn, Larcei or
    Radney, Lana or Mana with event `$50` (unit, army, x, y).
  - `$91:AEF2` holds (substitute, child) pairs, with army slots at
    `$91:AF2C`. Scenes use it (`$91:AEAE`) to name whichever of the two exists.
- **Love:**
  - Men are listed at `$83:848D` (38) and women at `$83:84DB` (25).
  - Starting love is at `$83:850F` and growth at `$83:8738`: word offsets per
    woman, then one byte per man. Generation-2 women are indexed from man 15.
  - A start byte of `$FF` means never and `$FE` means 499; otherwise it is ×10.
    Growth bit 7 = negative.
  - Love is added at `$87:AE05`, and 500 marries the pair (`$84:8C31`).
- **Unit-list names:** `$50:A000` + 16 × name ID holds up to 6 big-endian
  tile IDs (top row; bottom = +16). They point into a pre-drawn sheet in VRAM:
  generation 1 `$45:D000` (6 rows), generation 2 `$45:E000` (10 rows), loaded
  at `$80:F64B…`. Entries past name 511 overlap other data; the kit hooks
  `$51:0736` for 570–575.
- **The kit's replacement:** `fe4gen2.py`.
  - It hooks the transition with a trampoline at `$84:8204`.
  - Its table has 16-byte entries: child, parent, flag, always, weights ×4,
    mask ×3, joins, parent's gender.
  - Each couple's children are made, then the mother and (if the transition
    would only send him away) the father leave, which keeps memory free.
  - It hooks the mask, growth and stat code, the child heap, and `$84:A40D`.
- **Verified with `dev/ch6start.py`:** all 17 children plus a new one (18 in
  all); Ced as Lewyn's son; Ulster's substitute swapped; a new child joining
  at chapter 6; save and reload with 18 children.

## Moving script blocks (V)

`fe4asm.py` rebuilds any chapter script, scene or AI program that gained or
lost commands.

- **Where moved blocks go:**
  - into the zero tail of the block's own bank
  - otherwise scenes may go into banks `$70–$7D`, but only when every jump
    stays inside the block
- **What gets repointed:**
  - chapter header ptr24s (`$86:C739` + 2 or + 5)
  - scene table entries (`$8F:E8BF`)
  - army orders lists (army record +7)
- **Jumps:** event `$2B`, scene `$02–$04` (absolute) and `$05/$06`
  (relative), and AI `$01 $1F $20 $21 $22 $23`. Targets inside the block are
  remapped.
- **Checks:** the moved block is decoded again with the game's rules and must
  match the lines written.
- **Dialogue:** messages edited at the same time are repointed at the moved copy.
- **Verified in-game:**
  - A `GIVE_ITEM` added to Prologue scene 20 (moved to `$B1:FDB6`) gives the
    Speed ring on the village visit.
  - A `GIVE_ITEM` added to the Prologue opening script (moved to `$90:F678`)
    starts Sigurd with it.
  - `RAID_ANY_VILLAGE` added to the top of army 2 orders 1 (moved to
    `$90:F682`) sends those four units toward the villages on turn 1.

## Engine routines found so far

| Routine | Purpose |
|---|---|
| `$84:8481` | unit ID → record address |
| `$84:8397` | spawn unit (dispatch by record type) |
| `$84:931A` | spawn by ID |
| `$84:90D4` | build unit object for a type 3 record |
| `$84:87BA` | walk a deploy list |
| `$84:F0E9` | give a unit an item |
| `$82:F4DE` | generic "entry n of a word-offset directory" helper |
| `$86:83D8` | event VM main loop |
| `$80:C1CB` | start scene n |
| `$91:A5FC` | scene VM main loop |
| `$91:8A01` | text control-code dispatch |
| `$80:AA02` | decompress `[$C8]` to `$CD:$CB` (`$80:A9F2`: variant entry, see Compression) |
| `$88:8EBB` | draw map rows from `$7F:2400` |
| `$87:EA09` | find the location covering a map cell |
| `$87:EBC8` | per-location chapter setup: village gold, armory stock |
| `$87:EDEB` | current gold of the visited village |
| `$84:B23C` | add `$0574` gold to a unit (cap 50,000) |
| `$8A:9858` | castle-town menu: hide buttons by facility bits |
| `$87:A082` | pick the arena opponent |
| `$86:C55A` | army ID → record (Y, DB) |
| `$84:BBD2` | set up an army slot: members, castles |
| `$87:D9B9` | select a unit's AI program |
| `$87:CD1E` | AI program interpreter |

## Not yet mapped

- What the map area flags (bits 10–15 of each cell) do.
- Meaning of most remaining event and scene opcodes. They decode and edit
  correctly, but are labeled `OP_xx` / `SC_xx`.
- Army record bytes +1/+2, event `$4D`, and the unidentified AI opcodes
- Text referenced from places other than event and scene commands, such as
  villages and some battle quotes
- The +2, +6 and +8 lists in each chapter's info block
- Holy weapon stat bonuses
- Promotion table
- Engine code (65816)
