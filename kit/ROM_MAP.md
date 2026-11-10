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
  rows 0–3 (bottom half), 48×64 pixels; tiles 12–15 hold mouth and eye frames.
- Most numbers from 185 on are class pictures for generic units. The status screen loads portraits at `$8A:B369`.

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
| `$0E` | unit16, n | follow/target a unit (?) |
| `$15`/`$16` | flag16, bit | set / clear an event flag (`$8699D6` / `$869A13`) |
| `$17` | – | raid any village |
| `$18` | – | attack anyone |
| `$1F` | turn, addr16 | go to once turn ≥ n (turn at `$0D8F`) |
| `$20`/`$21` | flag16, bit, addr16 | go to if the flag is set / clear (`$868294`) |
| `$22` | addr16 | go to if `$87:D411` succeeds |
| `$23` | ptr24, addr16 | go to if the 65816 routine returns carry |

- **Other arguments:** `$02 $03 $04 $11 $14` take 1 byte, `$0C` 2, `$1E` 3,
  and `$05 $0B $0F $10 $12 $13 $19 $1A–$1D` none. Their effects aren't
  identified yet.
- **Verified in-game:**
  - Setting `orders` to 0 for four Prologue units kept them in place during
    enemy phase 1 while the rest moved as usual.
  - Changing army 2 orders 2 from "turn ≥ 3" to "turn ≥ 1" made exactly
    those four units (0.4–0.6, 0.17) march on turn 1.

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
