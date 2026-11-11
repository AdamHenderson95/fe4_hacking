# fe4kit: FE4 hacking toolkit (Project Naga ROM)

Make hacks and randomized games of Fire Emblem: Genealogy of the Holy War
(the Project Naga translation). You need your own copy of the ROM; the tools
read everything out of it and never ship any of the game.

## Builder of the Holy War, the editor (Windows)

Run **`BuilderOfTheHolyWar.exe`**. Nothing to install. It opens **Builder of
the Holy War** in its own window (it uses the Edge browser that comes with
Windows, in app mode; if Edge isn't there it uses Chrome, or opens in your
default browser). The editor runs on your PC only: nothing is sent anywhere.
(Up to kit v15 the editor was called FE4 Studio and the program FE4KitEditor.exe.)

1. **Project → Choose your ROM…**, then **New project…** picks a folder and
   a name; the editor reads the whole game into that project folder. Open
   an existing project with **Open a project folder…** or from **Recent**.
2. **Characters** shows every unit as a portrait (read from your ROM). Pick
   one to open their sheet, laid out like the game's status screen:
   - name, class, level, gender, leadership stars and gold;
   - **Fighting skill**: each stat's total (the class base plus the unit's
     own value) with a bar, the unit's own value and its growth;
   - **Holy blood**: minor or major for each of the 13 bloodlines;
   - **Items** (it warns when two units are given the same item),
     **Skills** (click to give or take away), **Love** partners and the
     game IDs.
   - **Children** have their own sheet: the parent, who passes on the holy
     weapon, how much of the parents' growths and stats they inherit, and
     the skills they can inherit.
3. **Classes**: bases, growths, weapon ranks, movement, flying and class
   skills, with the units that use each class.
4. **Skills**: FE4's own skills and new ones, with a line at the top that
   says whether the skills build (checked after every change).
   - FE4's skills: who has them (units, classes, the items that give them)
     and, for Wrath, Charm, Miracle, Renewal, Astra, Luna and Sol, their
     numbers (Astra, Luna and Sol can also work with any weapon).
   - **+ New skill** adds one: a stat bonus, battle bonuses (Atk, Def, Hit,
     Avoid, Crit, attack speed, for the unit or against the foe, always or
     only when attacking, attacked, at low HP, at full HP, or as an aura for
     nearby allies), or an effect from later games (Aether, Ignis, Colossus,
     Vengeance, Deadeye, Lethality, Sure Strike, Great Shield, Aegis, Pray,
     Counter, Galeforce, Lifetaker) with its rate and power.
   - Give a new skill to units and classes, and set its icon, type and help
     text for the map menu's Skills list. Renaming or deleting a skill
     updates every unit, class and item that has it.
5. **Maps**: each chapter's map drawn with the game's own tiles, with its
   castles, villages and units on top.
   - **Paint** (B): pick a tile in the **Tiles** panel and paint. Drag across
     several tiles in the panel to paint them as a block (a house, a castle
     wall). Right-click (or Alt+click) on the map picks the tile under the
     pointer. The **terrain** list in the Tiles panel shows only the tiles of
     one terrain (all the forest tiles, all the water tiles…).
   - **Fill** (G) fills the area of the same tile that you click.
   - **Pick** (I): click to pick one tile, or drag over the map to copy a
     block of tiles and paint it elsewhere.
   - **Select** (V): click a castle, village or unit to see it and change
     its position, AI orders or village gold; drag it to move it. Clicking
     the ground shows its terrain.
   - The terrain comes with the tile: painting water makes the cell water
     for the game too. **Show → Terrain** colours the map by terrain; the
     status line under the map names the terrain under the pointer.
   - **Edit tile…** (on the Tiles panel, or for the cell you clicked) shows a
     tile large with how many cells use it.
     - **Terrain in this chapter** changes what the game thinks the tile is
       (make a decorative tile a forest, a wall passable…), for every tile.
     - **Replace drawing…** redraws one of the chapter's own tiles (0–255)
       from a picture: 16 × 16 pixels, or bigger pixel art (2× to 8×), or any
       picture (it is shrunk). Colours become the nearest of the chapter's map
       palettes. Each 8 × 8 quarter that isn't already in the chapter needs
       a free 8 × 8 tile: the chapter's own (3–22 of them), then a pool of 25
       shared by all chapters and handed out from the Prologue on (the dialog
       says how many are left). Drawings that reuse the map's own grass, water
       or walls fit best. Redrawing a tile the map doesn't use frees
       its quarters. Tiles 256–1023 are shared by every chapter and can't be
       redrawn.
   - Units come onto the map in groups (deploy lists) as the chapter goes on;
     the **Units** panel shows or hides each group.
   - **Event areas** outlines each area event of the chapter (*Sigurd
     reaches …*); with the Select tool, click its label to open the event.
   - **Area flags** shows bits stored with each map cell above the tile
     number. The game uses them (what for isn't known yet); painting keeps
     them as they are.
   - Zoom with − / + or Ctrl+mouse wheel; drag with the middle mouse button
     (or Shift+drag) to move around.
6. **Events & dialogue**: each chapter's script as a list of events in
   plain words: *Turn 3*, *Sigurd talks to Ayra*, *Someone visits village 5*,
   *Midir fights Gerrard*, *Sigurd reaches (12, 38)–(17, 43)*, … with the
   first line of what's said. Filter by talks, turns, villages, battles and
   areas, or **search all dialogue** in the game.
   - **When**: the condition's settings as fields (the turn, who talks to
     whom, which village, the area's corners, who fights whom). Pick people
     from a list of names.
   - **Then**: the steps that follow. *Play scene N* and *Show a message*
     open the conversation right there; *Units arrive: deploy list N* has a
     **See them on the map** button; items given, stat boosts and army
     changes have their own fields.
   - **Conversations** are speech bubbles with the speakers' portraits, left
     and right as in the game. Each bubble is one box of text (one button
     press): type into it, Enter starts a new line. Click a portrait to
     change who speaks. Under each box, a gauge measures the widest line
     with the game's own letter widths: the box holds 224 pixels and 3 lines.
     Letters the game has: A–Z, a–z, 0–9, space and `. , : ? ! ' - " á é ö`.
   - **Show codes** shows the whole message with its control codes for
     anything else (new boxes, pauses, portraits coming and going).
   - Steps and conditions whose meaning isn't known yet say so; their bytes
     can still be changed under **Bytes** (same length).
   - **+ New event** adds a talk, a turn event, a village visit, an area
     someone reaches, a battle quote or a death quote. Each new event comes
     with a fresh conversation to write in; new talks get their own scene
     and an entry in the chapter's **Talk menu**, so the map menu offers
     *Talk* for that pair until the talk has played. New turn events on a
     turn that already plays a scene add their message to that scene (the
     game plays one scene per check).
   - Add steps to an event (*someone says something*, *give an item*,
     *raise a stat*, *units arrive*), remove steps with ×, or **Delete
     event**. Messages only a deleted event used go with it. Every one of
     these is one undo step.
   - Area events show a picture of their part of the map. Click it (or
     **Pick on map**) and drag a box across the chapter map, with castles,
     villages, starting units and the chapter's other areas drawn on it.
     New area events have the same picker.
   - Talk events show whether the pair is in the Talk menu, with a button
     to add or remove it. Changing who talks keeps the menu entry in step.
7. **Items, shops & villages**, in three tabs:
   - **Weapons & items**: every weapon, staff and ring, grouped by type.
     Rename it, and set Might, Hit, Weight, range, uses, price, rank, weapon
     type, what it's effective against, its special effect (brave, magic
     sword spell, status edge…), which holy blood it needs, and the skills
     it gives while equipped. **Copies in the game** lists each of the
     item's numbered copies (FE4 has 141) with who starts with it, which
     shop sells it and which event gives it; any copy can be turned into
     another item, and unused copies can be turned into this one.
   - **Shops & villages**, per chapter: each castle's town buttons (Armory,
     Pawnbroker, Blacksmith, Supply, Augury, Arena) and what its Armory
     sells (add or remove item copies; it warns when someone already starts
     with a copy, since that copy won't go on sale). Each village's gold and
     what visiting gives (the item, or the stat and amount), with a link to
     the visit event.
   - **Arena**: the seven opponents per chapter for melee and ranged
     fighters, with each opponent's class and level.
8. **Armies & AI**, per chapter: the armies the chapter sets up, by slot
   (slot 0 is yours).
   - **The army**: its name on the map, the castles it holds and its
     members (units that join when it's set up).
   - **What its units do**: each AI program in words (*Seize Jungby*,
     *From turn 3 on, go to step 4*, *Attack anyone*…), with fields for the
     castle, turn or target. **Change what it does…** rewrites a program:
     attack anyone, attack only what's in reach, seize a castle, guard a
     castle, raid villages, go after one unit, or stay put, optionally
     only from a given turn (until then they wait or attack what's in reach).
   - **Units on the map**: every deployed unit of the army, grouped by
     deploy list, with the program it follows. **Set all to…** changes a
     whole list at once.
9. **Portraits**: all 247 faces with who uses each one (units, generic
   classes, people who only speak). Pick one to see it large, with a
   talking preview.
   - **Replace with a picture…** takes any image. It is fitted to 48 × 64
     (fill and crop, or fit inside) and reduced to the 15 colours a
     portrait can have. The colour in the corners becomes transparent
     unless you keep the background.
   - **Download PNG** gives the 80 × 64 sheet: the face, plus the two
     talking-mouth frames at the right (each is the face's 32 × 16 block at
     the left, 32 pixels down, with the mouth open). Edit it and replace
     with it to draw your own talking frames.
   - **Use the original** goes back to the game's picture. On a character's
     sheet, **Change picture** opens that character's portrait.
10. **Map sprites**: the little unit each class shows on the map.
   - The list shows every class's sprite, animated, in the army colour you
     pick (player, enemy, ally, other, has moved).
   - Some classes have extra entries the game checks first: one for women,
     or one for a single character (Knight Lord: Sigurd and Seliph each have
     their own). **Use another sprite…** picks from all 63 sprites on foot
     and 31 mounted or flying ones.
   - **Add a sprite for** adds a row for one character (say, Noish gets his
     own look as a Cavalier) or for all women or all men of the class;
     **Remove** takes a row out. Rows are checked from the top, so new ones
     go above "Everyone else".
   - **Edit drawing** shows a sprite's three frames. **Replace drawing…**
     takes a PNG of the three frames side by side (48 × 16 on foot, 48 × 24
     mounted; 2× to 4× bigger also works); colours become the nearest of the
     map palette, so every army recolours it. **Download PNG** gives the
     current drawing to edit. Classes that share a sprite all change.
11. Changes are checked as you type (a value out of range turns red and
   says why). **Undo / Redo** (Ctrl+Z / Ctrl+Y) cover every change (a whole
   paint stroke or fill is one step); **Save** (Ctrl+S) writes the project
   files.
12. **Build ROM** writes the hacked ROM plus a shareable `.ips` patch next to
   the project folder. **Test play** (F6) builds it and opens it straight
   away in the FE4 PC port (FE4Port.zip), without your mods and with its own
   saves. The editor finds FE4.exe when the kit sits in the port's `fe4kit`
   folder (as it comes in FE4Port.zip) or next to it; otherwise it asks once.
13. On the Project page, **Add unit stats to the map box** puts the PC port's
   MT / HIT / AS / AVO box into the ROMs and patches you build, so players
   on emulators get it too (the port can still switch it off).

The **classic editor** (link on the Project page, or run
`BuilderOfTheHolyWar.exe classic`) still has every table as rows, for the
few things the new editor doesn't show yet (AI orders, armies, love
growth). Adding or removing event steps is done by hand in the `.evt` files
(see below). In the classic editor, pick a page on the left, select a row, edit it in the panel on the right and press Apply. Its
Build menu also has **Test generation 2**, which writes a copy whose New Game
opens on chapter 6, and **Test play generation 2 in the PC port**.

**Maps in projects from kit v15 or older:** those kits read the chapter 5 and
endgame maps wrongly (and drew the chapter 9 map picture with the wrong
tiles). The editor re-reads those two maps from your ROM when it opens the
project, as long as they haven't been edited; building still works with the
old files either way.

The project folder is plain CSV and text files, so you can also edit it in a
spreadsheet. The editor, the classic editor and the Python scripts below all
read the same projects. Run the editor from Python with `python fe4studio.py`.

## Randomizer

The **Randomizer** page (or `BuilderOfTheHolyWar.exe rando ROM out.smc --preset standard`)
makes a randomized ROM, an `.ips` patch and a spoiler log, from the clean game
or from your own hack.

| Option | What it does |
|---|---|
| Growth rates | vary each growth, redistribute the same total, or pick freely between a min and max |
| Personal base stats | vary or redistribute each character's stat bonuses |
| Playable classes | a random class of the same tier and gender; starting weapons change to match |
| Keep Sigurd, Seliph and Julia / dancers | story units and dancers keep their class |
| Healers stay healers | units who start with staves get a class that can use them |
| Holy blood keeps its weapon | major blood (Lewyn's Forseti, Quan's Gáe Bolg…) and carried holy weapons stay usable. Children follow the parent they're tied to |
| Personal skills | random personal skills, plus extra ones |
| Skills from later games | Aether, Galeforce, Vengeance, Great Shield, Lifetaker, Pray, Counter… join the pool |
| Random minor holy blood | generation-1 units may gain a minor blood, which their children inherit |
| Child parents | `split` gives each sibling a different mother. `any_parent` ties children to fathers too, e.g. Ced to Lewyn and Fee to Ayra |
| Children per parent | at most this many children per parent |
| Inheritance weights | how much of each parent the children get |
| Love affinities | random starting love and growth for every pair |
| Weapon stats | Mt, Hit and Wt of ordinary weapons vary |
| Enemy classes | generic enemies get a class that moves on the same terrain; their weapons follow |

- **Presets:** `light`, `standard` and `chaos`.
- **Seeds:** the same seed and options always make the same ROM.
- **Substitutes:** a substitute always shares a weapon type with the child it
  replaces, because they share their starting items.

## Command line (Python 3, no extra packages)

```
python fe4hack.py extract  "Fire Emblem....smc"  myhack          # once: dump editable CSVs
python fe4hack.py build    "Fire Emblem....smc"  myhack  myhack.smc  --ips myhack.ips
python fe4hack.py build    "Fire Emblem....smc"  myhack  myhack.smc  --hover-stats   # with the unit stats box
python fe4hack.py diff     "Fire Emblem....smc"  myhack.smc     # see exactly what changed
python fe4rando.py "Fire Emblem....smc" rando.smc --seed 42 --preset chaos --opt parents=any_parent
python fe4rando.py --list                                        # every randomizer option
python fe4rando.py --list-tsv options.tsv                        # the same, for other programs
python fe4rando.py ... --log run.txt                             # output and errors to a file
```

`BuilderOfTheHolyWar.exe extract|build|diff|rando …` takes the same arguments.

Play the ROM in the FE4 PC port or any SNES emulator: Snes9x, bsnes or
RetroArch. The `.ips` file is a shareable patch, since it contains only your
changes; PC port players drop it in their `mods` folder. The PC port also
runs this randomizer from its own menu (Mods → Randomizer).

## What you can edit

| File | Rows | Contents |
|---|---|---|
| `units_playable.csv` | 46 | Gen 1 characters and gen 2 substitutes: starting HP/stats, class, level, authority, gold, growths, skills, holy blood, starting items |
| `units_children.csv` | 17+ | Seliph, Leif, Altena and the other children: class, level, starting items, and generation 2: whose child each one is, what they inherit, their substitute. New children can be added |
| `lovers.csv` | 503 | Starting love and love growth per turn for every couple the game tracks |
| `gen2_rules.csv` | 3 | Children's gold and the cap on inherited stats |
| `units_npc.csv` | 53 | Named NPCs and bosses with full personal data (Eldigan and others) |
| `units_generic.csv` | 453 | Class-based enemies and bosses (Gerrard, DiMaggio…): class, level, authority, items |
| `deploy.csv` | 1328 | Where every unit spawns: list.entry, unit ID, X/Y, AI orders, army slot, leader flag |
| `classes.csv` | 72 | Base stats, class growths, weapon ranks (A/B/C/-), movement |
| `items.csv` | 106 | Weapons and staves: Mt, Hit, Wt, range, uses, price, rank, effectiveness, special effects |
| `rings.csv` | 16 | Rings: price, stat bonus, skill bits |
| `item_instances.csv` | 141 | Which item type each physical item in the campaign is |
| `events/chNN_*.evt` | 2,643 | Each chapter's opening script and trigger list: turn, talk, area, battle and death conditions; scenes to run; deployments |
| `events/scenes.evt` | 12,170 | All 562 cutscenes and conversations |
| `events/dialogue.txt` | 785 | Every message those scripts show, as editable text |
| `locations.csv` | 132 | Every castle and village: position, castle name, castle-town facilities, armory stock, village gold |
| `arena.csv` | 71 | Arena opponents for each chapter and rank |
| `talks.csv` | 42 | Each chapter's Talk menu: which unit can Talk to which, until which event flag is set |
| `map_terrain.csv` | 12,288 | The terrain type of each chapter's 1024 tiles |
| `maps/tiles/<map>/tNNN.png` | – | Your own drawings for a chapter's tile NNN (0–255), 16 × 16 or bigger pixel art; only redrawn ones exist |
| `map_sprites.csv` | 119 | Which map sprite each class uses (`S0`–`S62` on foot, `T0`–`T30` mounted/flying), with the per-gender and per-character rows; a class's last row is `default`, and a class can have up to 30 rows |
| `sprites/sNN.png`, `sprites/tNN.png` | – | Your own drawings for map sprites (48 × 16 or 48 × 24, the map palette's colours); only replaced ones exist |
| `portraits/pNNN.png` | – | Your own pictures for portrait NNN (80 × 64 sheet or 48 × 64 face, 15 colours + transparency); only replaced ones exist |
| `armies.csv` | 72 | Every army: name, member units, castles it holds |
| `ai_orders.evt` | 737 | Enemy AI programs: which castle to seize, which turn to march, what to attack |
| `skills.csv` | 29+ | Every skill: who has it, activation rates and effect numbers, plus new skills from later games (Aether, Galeforce, Great Shield…) with their Skills-menu entries |
| `names.csv` | 810 | Character, class, item and castle names as shown in game |
| `maps/chNN_*.csv` | 12 maps | Each battlefield as a 64-column grid of tile numbers, with a `.png` preview and a `_tiles.png` tile sheet |

## Column conventions

- **`index`** is the unit ID in the unit files and `list.entry` in `deploy.csv`.
- **Rows** can be edited in every file. Rows can also be added to `units_generic.csv`,
  `units_children.csv` and `deploy.csv`, and removed from `deploy.csv` (see "Adding new things").
- **`portrait`** (all four unit files) is the face a unit shows. Write a number or
  another unit's name to borrow theirs, e.g. `Lex`.
- **Unit stats** (`str` … `res`) are bonuses added to the class bases, which is how FE4 itself works. `hp` and `lck` are absolute.
- **Item columns**
  - Playable and children files use item **instance** numbers (see `item_instances.csv`).
  - NPC and generic files use item **type** numbers (see `items.csv`).
  - `255` = empty.
- **Skills** are written by name, separated by `;`: `Pursuit;Astra;Sol`. Names follow `skills.csv`. Use `bit3` and so on for unnamed bits.
- **Holy blood** is written like `Baldur:major;Naga:minor`.
- **Weapon ranks** are `A`, `B`, `C`, `-`, or `*` for holy weapons.
- **Columns starting with `_`** are for reference only and ignored on build.
- **Names:** the `_name` columns are reference only. Rename things in `names.csv`.

## Events and dialogue

**`.evt` lines** look like this:

```
86C8A7: 02 00 00 00 01 00      ; COND_TURN      turn 1
908106: 30 FF 18 00            ; RUN_SCENE      scene 24
```

- Edit the hex bytes; the part after `;` is a comment.
- An edited command must keep its length. To add or remove commands, see
  "Adding new things".
- Examples of edits: change which scene a talk or visit triggers, the turn a
  reinforcement wave arrives, a deploy list number, or a unit ID in a condition.
- Names ending in `?` are educated guesses.
- `OP_xx` / `SC_xx` commands aren't identified yet, but they still edit safely.

**`dialogue.txt`** holds one block per message:

```
@602487  ; ch00 908141 TALK
{07}{00 3D}{00 3F 07 00}{09}Urgh...{02}
Milady, I...{02}
Forgive me...{08}{01}
```

- Change the words freely, and make a message as long as you like.
  - Changed messages are moved into empty ROM space.
  - Every script that uses the message is repointed.
- Keep the `{..}` control codes:
  - `{02}` = new line
  - `{08}` = wait for button
  - `{06}`/`{07}` = left/right speaker
  - `{00 3F pp 00}` = portrait
  - `{01}` = end
- Line breaks in the file itself are ignored.
- Lines in the game box fit about 44 characters.

**`talks.csv`** is the map menu's Talk list for each chapter:

| column | meaning |
|---|---|
| `chapter` | 0–11 |
| `flag` | the event flag the talk event sets; once set, *Talk* is no longer offered |
| `from` | unit who talks, or `any` |
| `to` | unit talked to |
| `needs` | empty = always; `gold10000` = only while the talker has 10,000 gold (hiring Beowulf) |
| `flag_chapter` | the chapter whose flags hold `flag` (normally the same chapter) |

A row only makes *Talk* appear. What happens is the chapter's talk event
(`COND_TALK` `04`, or `16` from chapter 6 on) with the same units and flag.
Same-army talks need both; the editor's **+ New event** writes both.

## Maps

- **Easiest:** the **Maps** page of Builder of the Holy War (above).
- **Without the editor:** open `map_editor.html` in a browser. Load a chapter's
  `maps/chNN_*.csv` and its `chNN_*_tiles.png`, then paint:
  - Click a tile, or drag across the tile sheet to pick a block such as a castle.
  - Right-click the map to copy tiles from it.
  - **Fill box** paints a rectangle.
  - Save the CSV back into `maps/`.
- **By hand:** edit the CSV values directly. Each number is a tile from the
  tile sheet, counted left to right, top to bottom, 32 per row.
- **Rules:**
  - Keep the same number of cells (every map is 64 × 64).
  - The bits above the tile number (`value >> 10`) are per-cell area flags; keep them.
  - Terrain follows the tile, so water tiles block walking.
  - Edited maps are recompressed and stored in free ROM space automatically.
- **Previews:** PNGs need Pillow (`pip install pillow`). Everything else needs only Python.

## Castles and villages

`locations.csv` has one row per castle or village in each chapter.

| Column | Applies to | What it does |
|---|---|---|
| `x`, `y` | both | A castle's seize point, or the spot you stand on to visit a village |
| `castle_id` | castles | The castle's name, from the game's list of 46 castles |
| `facilities` | castles | Castle-town buttons, separated by `;`: `Armory`, `Pawnbroker`, `Blacksmith`, `Supply`, `Augury`, `Arena`. Use `-` for none |
| `shop` | castles | What the Armory sells: item **instance** numbers separated by `;` (see `item_instances.csv`). Usually only the chapter's first castle has one |
| `gold` | villages | Gold paid on the first visit, 1–50000 (the game's default is 5000 for every village) |

- **The map is separate:** the castle or village graphics are map tiles, so
  paint them in the map painter too when you move one.
- **Previews:** map PNGs outline each location, labelled with its index.
- **Shop rules:**
  - Each item instance is a single physical item, so a shop sells one of each.
  - An item only goes on sale if nobody owns it yet when the chapter starts.
  - The `Armory` button must be in `facilities` for the shop to be reachable.
    The Prologue has neither by default, but both can be added.
  - Shops can be longer than the original; extra space comes from free space
    in the same ROM bank (about 300–2,500 bytes per chapter group).
- **Village gold** only changes the first-visit payout. Brigands still loot it as normal.
- **Limits:** rows can't be added yet, and a castle can't become a village.

### What a village gives besides gold

Item and stat rewards are scene commands in `events/scenes.evt`. Find the
scene from the village's `COND_VISIT` line in the chapter's `.evt` file:

```
B18627: 4A 57 FF FF 7B   ; EVENT  GIVE_ITEM visitor gets Speed ring(#123)
9D914C: 4A 70 FF 05 01   ; EVENT  STAT_UP visitor Def +1
```

- `GIVE_ITEM`: the last byte is the item instance. `FF FF` means the visiting unit.
- `STAT_UP`: the bytes are the unit (`FF` = visitor), the stat (0 HP, 1 Str,
  2 Mag, 3 Skl, 4 Spd, 5 Def, 6 Res, 7 Lck) and the amount.

## Arena

`arena.csv` lists the 7 arena opponents for each chapter.

- **`melee` / `ranged`** are unit IDs. The game uses the `ranged` opponent
  when your fighter's weapon reaches 2 or more spaces.
- **Changing an opponent's stats:** opponents are ordinary units, so their
  class, level and weapons are in `units_generic.csv` (IDs 480 onward).
- **Rank 8 rows** are fallbacks. If the rank 7 opponent has already joined
  your army, the game uses rank 8 instead. That is how chapter 2's Holyn is
  replaced by Chaimos once he joins.
- **New arenas:** the Prologue and chapter 6 have no arena. Add 7 rows for
  that chapter, and add `Arena` to its home castle's `facilities`.

## Armies and enemy AI

FE4 groups units into armies, for example "Evans" (Gandolf's Verdane force)
or "Jungby". Three files work together:

- **Which army a unit is in:** in `deploy.csv`, `army_slot` puts the unit in
  one of the chapter's army slots (0 is always you). The chapter's opening
  script fills the slots with `SET_ARMY` lines, such as
  `4B 01 02 ; slot 1 = army 2`.
- **`armies.csv`:** one row per army.
  - `name`: the castle name it uses.
  - `members`: units that join it when it's set up. Sigurd's army lists Sigurd, Noish, Alec and Arden.
  - `castles`: location indices it holds from the start. When two armies
    claim the same castle, the one set up later wins.
  - `_orders`: how many AI programs it has.
- **How a unit behaves:** `orders` in `deploy.csv` picks one of its army's
  programs (1, 2, …; 0 = stands still). The programs are in `ai_orders.evt`:

```
== army 2 orders 2 @9081A8
9081A8: 1F 03 AE 81   ; IF_TURN_GOTO      turn >= 3 -> 81AE
9081AC: 0A            ; ATTACK_IN_REACH
9081AD: FF            ; END
9081AE: 06 01 01      ; SEIZE_CASTLE      location 1 (Jungby)
9081B1: 06 00 01      ; SEIZE_CASTLE      location 0 (Chalphy)
9081B4: 18            ; ATTACK_ANY
```

  Each turn a unit runs its program from the top, and the first command that
  can act does. This one means "until turn 3, only attack what's in reach;
  from turn 3, march on Jungby, then Chalphy, then attack anyone". Change
  `03` to `01` and that group marches on turn 1.
- **Useful commands:**

| Command | Bytes | Meaning |
|---|---|---|
| `SEIZE_CASTLE` | `06 loc mode` | march on and take an enemy castle |
| `GUARD_CASTLE` | `07 loc mode` | go back to and hold one of its own castles |
| `RAID_VILLAGE` | `08 loc` | destroy a village |
| `RAID_ANY_VILLAGE` | `17` | destroy any village |
| `ATTACK_IN_REACH` | `0A` | attack only what it can reach this turn |
| `ATTACK_ANY` | `18` | go after any enemy |
| `ATTACK_UNIT` | `0D unit` | target one unit (word) |
| `MOVE_TO` | `09 flag bit x y` | walk to (x, y) unless the event flag is set; set it on arrival |
| `IF_TURN_GOTO` | `1F turn addr` | jump once the turn number is reached |
| `IF_FLAG_GOTO` / `IF_NOT_FLAG_GOTO` | `20`/`21 flag bit addr` | jump on an event flag |
| `GOTO` | `01 addr` | jump |
| `STOP` / `END` | `00` / `FF` | do nothing more this turn |

- **Editing rules:** the same as the other `.evt` files (see "Adding new things").
  Jump addresses are the low 16 bits of an address in
  the same bank. A new line can jump to another command of the same
  program by its position instead: `@L3` is the program's 4th command
  (counting from 0), wherever the build puts it:

```
== army 2 orders 1 @9081A0
+ 1F 03 @L2   ; from turn 3, go to the third command
+ 00          ; until then: stay put
+ 18          ; attack anyone
+ FF
```
- **Old projects:** older `deploy.csv` files use `army` and `faction` for
  `orders` and `army_slot`, and they still build.

## Skills

`skills.csv` has one row per skill. Rows 1–29 are FE4's own skills; add rows
from id 30 up for new ones.

### Who has a skill

| Column | Gives the skill to | Notes |
|---|---|---|
| `personal_bit` | units that list it in their `skills` column | 24 bits; 22 and 23 are free |
| `class_bit` | classes that list it in `classes.csv` `skills` | 16 bits; 13–15 are free |
| `item_bit` | anyone carrying an item/ring that lists it | 16 bits; 13–15 are free |
| `units` | these units, e.g. `Sigurd;Ayra;769` | new skills only, no bit needed |
| `classes` | these classes, e.g. `Swordmaster;Bow Knight` | new skills only, no bit needed |

Bits are scarce, so for new skills use `units` and `classes`. They take names
or index numbers. Write the index when a name repeats: Finn has two records,
so he is `5` or `34`.

### FE4's own skills

`stat`, `amount` and `amount2` tune the built-in effects:

| Skill | What the numbers mean | Game default |
|---|---|---|
| Astra, Luna, Sol | activation % = `stat` × `amount` / 100 + `amount2` | Skl × 100 + 0 |
| Wrath | crit % when HP ≤ half | 100 |
| Charm | hit/avoid bonus given to nearby allies | 10 |
| Miracle | below `amount` HP, avoid + (`amount` − HP) × `amount2` | 11, 10 |
| Renewal | heals `amount` + random(`amount2`) HP per turn | 5, 6 |

- **`weapons`:** in FE4, Astra, Luna and Sol only trigger with swords. Set
  `weapons` to `any` and they trigger with any weapon except staves. Leave it
  blank, or set `sword`, to keep FE4's rule.
- **`stat`:** Str, Mag, Skl, Spd, Def, Res or Lck.

### New skills (id 30+)

The `effect` column picks what a new skill does.

**`stat`:** a permanent stat bonus, `stat` + `amount` (1–30), e.g. `Str` `5`.
It shows on the status page like a ring.

**`combat`:** battle bonuses, written in `bonus` with an optional `when`.

| Column | Values |
|---|---|
| `bonus` | `atk`, `def`, `hit`, `avoid`, `crit`, `speed` with + or −, separated by `;`. Prefix `foe_` to change the enemy's number instead. |
| `when` | blank = always, `attacking` (you started the fight), `defending`, `hp<=50`, `hp<=25`, `hp_full`, `ally_near` |

`ally_near` turns the skill into an aura: allies within 3 spaces of the skill
holder get the bonus, but the holder doesn't. The bonuses show in the battle
forecast. Examples:

| Skill | `bonus` | `when` |
|---|---|---|
| Death Blow | `atk+6` | `attacking` |
| Darting Blow | `speed+5` | `attacking` |
| Defiant Str | `atk+7` | `hp<=25` |
| Fortune | `foe_crit-100` | |
| Hit +20 | `hit+20` | |
| Rally | `atk+3;def+3` | `ally_near` |

**Skills from later games.** The activation rate is `stat` × `amount` / 100 +
`amount2`, like Astra; blank columns use the defaults below. `stat` can also
be `Lv` or `none`. `power` is the effect's strength.

| `effect` | What it does | Default rate | `power` |
|---|---|---|---|
| `aether` | ignores defence and heals the damage dealt (Sol + Luna) | Skl × 50% | |
| `ignis` | damage + a stat | Skl | `Def 50` (half Def) |
| `colossus` | damage + a stat | Str | `Str 100` |
| `vengeance` | damage + HP lost | Skl × 200% | `50` (half) |
| `deadeye` | damage × power % | Skl × 50% | `200` |
| `lethality` | defeats the enemy outright | Skl × 25% | |
| `sure_strike` | attacks always hit | Skl | |
| `great_shield` | blocks a hit completely (Pavise effect) | Lv | |
| `aegis` | damage × power % from magic or ranged hits | Skl | `50` |
| `pray` | survive a deadly hit with 1 HP (needs 2+ HP) | Lck | |
| `counter` | the attacker takes the same damage when hitting from 1 space (never below 1 HP) | always | `100` |
| `galeforce` | player units: after defeating an enemy, act again | always | |
| `lifetaker` | after defeating an enemy, heal power % of max HP | always | `50` |

- **When they trigger:** attack skills work like Astra/Luna/Sol. They are rolled
  when the unit's attack starts, apply to that whole attack, always hit, and
  show Luna's or Sol's battle effect. Defensive skills roll on each hit.
- **Nihil:** blocks both attack and defensive skills from the other side.
- **Weapons:** new attack skills work with any weapon except staves. Set
  `weapons` to `sword` for FE4's swords-only rule.
- **Counter:** its damage shows on the map after the battle, not in the battle
  animation.

### The Skills menu

New skills appear in the map menu's Skills list, after FE4's 18. Each one gets
its name, an icon, a type and a help text, and the bearers are listed just
like FE4's own skills.

| Column | Meaning |
|---|---|
| `menu` | `no` hides the skill |
| `icon` | borrow a listed skill's icon (`Pavise`, `Luna`, `Charm`…), or use one of the six unused ones, `spare1`–`spare6` |
| `type` | `Combat`, `Field` or `Sword` |
| `description` | help text, wrapped to 3 lines; `/` forces a line break. Defaults to a short description of the effect. |

**Limits:**
- The menu holds 32 rows, so up to 14 new skills can be listed.
- The names share 57 spaces 8 pixels wide. A name like "Vengeance" uses 7 and
  "Rally" uses 3, and a name can be at most 56 pixels.
- Help text is limited to 3 lines of about 96 pixels each. The build tells you
  when something doesn't fit.

### Other limits
- New skills don't show yet in the row of skill icons on a unit's status page.
- Changing the names of FE4's own skills in the menu isn't supported yet.
- The effects of Pavise, Adept, Vantage, Accost, Pursuit and Paragon are fixed.
  Who has them can still be changed.

## Generation 2

Everything about who the children are and what they get from their parents
is in `units_children.csv`, `lovers.csv` and `gen2_rules.csv`.

### How children are born

At the end of chapter 5 FE4 makes each married mother's two children, then
sends the generation-1 cast away. The kit replaces that step:

- Any unit can be a child's **`parent`**, father or mother. The other parent
  is whoever that unit married. FE4's pairs are the defaults: Ulster and
  Larcei are Ayra's, Ced and Fee are Erin's, and so on.
- To tie Ced to Lewyn instead of Erin, write `Lewyn` in Ced's `parent`. Ced is
  then Lewyn's son with whoever Lewyn marries. Fee stays Erin's daughter.
- A parent can have any number of children: give several rows the same parent.
- Children are made in row order, one couple at a time.

### `units_children.csv` columns

| Column | Meaning |
|---|---|
| `parent` | the unit the child is tied to (name or ID) |
| `always` | `yes`: born even if that parent has died. FE4 does this for Deirdre and Ethlyn. The parent still has to have married |
| `born_flag` | event flag set when the child is born. Scripts test it to choose the child or the substitute. Fixed for FE4's own children; new children get one from 128 up when left blank |
| `substitute` | who appears instead when the child isn't born (Rodolbahn for Ulster, …) |
| `joins` | for new children: the chapter (6–11) whose opening adds them to Seliph's army |
| `inherit_skills` | which of the parents' personal skills pass down, e.g. `Pursuit;Astra`. Blank on FE4's own children means none; blank on a new child means all |
| `growth_father`, `growth_mother` | percent of each parent's growth rates the child gets. FE4: 100 from the same-gender parent, 50 from the other |
| `stats_father`, `stats_mother` | percent of each parent's stats added to the child's base. FE4: 20 and 10 |
| `heir` | `father` or `mother`: whose holy blood passes in full and whose items the child inherits |

Example (Ced as Lewyn's son, with more of his father's growths):

```
index,_name,...,parent,always,born_flag,substitute,joins,inherit_skills,growth_father,growth_mother,...
53,Ced,...,Lewyn,,25,Hawke,,Pursuit;Adept;...,120,50,...
```

### New children

Add a row to `units_children.csv` with the next free ID (769, or after your new
generic units). Fill in at least `class`, `level`, `gender`, `parent` and `joins`.
Blank cells get defaults.

- **`name_id`** defaults to an empty name slot (570–575). Name it in
  `names.csv`, e.g. `character,570,Kian`. The build stops if a new unit has no name.
- **`portrait`:** borrow one, e.g. `Lex`.
- **`slot`** (the army and love slot) defaults to the substitute's slot, or to
  128 (none) if there is no substitute.
- **Joining:** `joins` adds the child at the start of that chapter (or the
  substitute, if the child wasn't born). The commands go into the chapter's
  opening scene. To recruit them some other way, write your own events and
  test the child's `born_flag`.

Limits of new children:

- **Saves.** FE4's save slot is nearly full at the start of chapter 6: about
  1,900 of its 1,982 bytes with the usual 17 children. Every extra child who
  is born adds about 50 bytes, so one extra child fits. More than that can
  break saving. The build prints a note when more than 18 children can be born.
  Substitutes cost nothing extra.
- **Love.** New children have no love slot, so they can't fall in love or have
  lover conversations.
- **Unit lists.** Lists such as the Unit list draw names from a pre-drawn sheet,
  and generation 2's sheet has room for about 5 more tiles (one short name).
  - Any further names show blank in those lists only. Status pages, battles
    and dialogue show them normally.
  - Renamed characters are redrawn in their sheet when they fit.
- **Memory.** FE4 keeps children in a heap that holds exactly 17. Extra
  children go in the generation-1 heap, which the departing cast frees.

### Substitutes

Changing `substitute` puts the new unit wherever a script picks between the
child and the substitute, such as the chapter-6 opening.

- Conversations written for the old substitute still use the old one. Edit
  those in `events/` if needed.
- A generation-1 character used as a substitute shows a wrong name in unit
  lists, because the lists use generation 2's name sheet.

### `lovers.csv`

One row per woman–man pair the game tracks. Generation-1 women pair with
generation-1 men, and generation-2 women with generation-2 men.

| Column | Meaning |
|---|---|
| `start` | love at the start of the chapter, in points: `0`–`2530` in steps of 10, `499`, or `no` (never) |
| `growth` | love gained every turn they stand near each other; negative values lower it |

At 500 points they become lovers.

### `gen2_rules.csv`

| Rule | FE4 | Meaning |
|---|---|---|
| `gold_divisor` | 10 | a child's gold = (mother's + father's) / this + `gold_base` |
| `gold_base` | 2000 | |
| `stat_cap` | 15 | highest inherited Str, Mag, Skl, Spd, Def and Res (not HP or Luck) |

### Testing generation 2 quickly

`dev/ch6start.py` makes a test copy of your built ROM whose New Game opens
straight on chapter 6, with the generation-1 cast married as you choose:

```
python dev/ch6start.py myhack.smc test6.smc --marry Lewyn-Ayra,Lex-Erin --single Bridget
```

The children are born through the real transition, with your parent links and
rules. Generation-1 stats are their starting values, so the children come out
weaker than in a full playthrough.

## Names

`names.csv` has one row per name the game draws. Change the `name` column to rename it.

| `kind` | `id` is |
|---|---|
| `character` | the `name_id` from the unit files (Sigurd = 0) |
| `class` | the class number (`classes.csv` index) |
| `item` | the item number (`items.csv` / `rings.csv` index) |
| `castle` | the castle number (`castle_id` in `locations.csv`) |

- **How it works:** Project Naga stores English names as pre-drawn pictures,
  so the build draws the new name with the game's own name font. That font
  was lifted from the existing names and re-draws them pixel-for-pixel. The
  new picture goes into free space.
  - Castles are drawn in all five places they appear, including the map's
    terrain window.
  - The class and item text tables are updated too.
- **Characters you can use:** letters, digits, spaces and `. , ' - ! ? : / & ( )`.
- **Length limits:** the build stops if a name is too wide for its window.
  Roughly 7–9 letters, depending on the letters.

| Kind | Widest |
|---|---|
| Characters | 7 tiles (56 px) |
| Classes | 8 tiles |
| Items | 9 tiles |
| Castles | 7 tiles |

- **Several slots per name:** generic units share names such as "Verdane", and
  each slot is renamed separately. To rename one enemy group, give its units
  a `name_id` of their own.
- **Empty slots:** character slots 570–575 are empty and listed too. Use
  them to name new units.
- **Unit lists:** the Unit list and similar screens use a separate pre-drawn
  sheet per generation. Renamed player characters are redrawn there too, when
  the sheet has room (see "Generation 2").
- **Not covered:** names inside dialogue are ordinary text in
  `events/dialogue.txt`.

## Adding new things

**New enemies in a chapter.** Add rows to `deploy.csv` with the next entry
number in a list, e.g. `0.34` and `0.35` after the Prologue's `0.33`.

- Fill in every column. `army_slot` 1 is the Prologue's Verdane army, and
  `orders` 0 makes a unit stand still.
- To remove an entry, delete its row.
- Each list is spawned by an event `DEPLOY` command, so its units appear when
  that command runs. List 0 is the Prologue's opening army.
- Lists that grow move into free space automatically (about 4.6 KB is free).
  New list numbers can't be added.

**New unit types.** Add rows to `units_generic.csv` with IDs from 769 up:
769, 770, … (new children in `units_children.csv` share the same numbering).

- IDs 570–768 aren't units: the game's scripts use them for the portraits of
  people who only talk (narrators, villagers). The kit keeps them that way.
  - Projects from before v12 that start at 570 still build, with a note.
  - Saves now keep unit IDs in 10 bits instead of 9, so units past 511 survive
    saving and loading. That makes saves from an earlier build of your hack
    unreadable.
- Copy `char_id` and `name_id` from the unit you based it on, e.g. `69` and `68`
  for a Verdane axe fighter. Menus take the name from `name_id`, and the
  battle screen takes it from name slot `char_id − 1`.
- Then use the new ID in `deploy.csv`, `arena.csv` or `armies.csv`.
- About 30 new units fit.

**New script commands.** In any `.evt` file (`events/chNN_*.evt`,
`events/scenes.evt`, `ai_orders.evt`), a line starting with `+` adds a
command after the line above it, and deleting a line removes a command:

```
908040: 30 FF 01 00   ; RUN_SCENE scene 1
+ 57 01 00 7B         ; new: Sigurd starts with the Speed ring
908044: FF FF         ; END
```

- A block that changes size is moved into free space and everything that
  starts it is repointed. That means the chapter header, the scene table or
  the army's orders list.
- Jumps inside the block are fixed up. Write jump targets as the original
  addresses shown in the file.
- The build checks each new command against the game's own length rules and
  names the line if one is wrong.
- Some AI programs share code with one listed earlier, marked
  "(shared, listed above)". Add commands to the earlier program instead.

**New messages.** In `events/dialogue.txt`, a block headed `@N00001`
(`@N` and five digits) is a new message. Use it in any `.evt` file by
writing `@N00001` where its 3-byte address goes:

```
+ 0C @N00001          ; SC_TEXT  a new line of dialogue
```

- The build puts new messages into free space and fills in their addresses.
- The editor makes these for you when you add an event or a step.

**New conversations (scenes).** 88 of the 562 scenes are empty and nothing
starts them. The editor uses those for new events: it writes the scene in
`scenes.evt` under its `scene N` label and starts it with `RUN_SCENE`.
Only one scene plays per event check, so an event should start one scene.

## Also included

- **`ROM_MAP.md`:** every offset and field, how each one was verified, and the engine routines found so far.
- **`map_editor.html`:** the map painter described above, also usable as a hosted page.
- **`fe4locations.py`:** castles, villages, shops, village gold and arenas.
- **`fe4armies.py`:** armies and the enemy AI program decoder.
- **`fe4names.py`, `fe4font.py`:** name drawing and the name font.
- **`fe4skills.py`:** skill tables, effect numbers and the hooks for rates and new skills.
- **`fe4skillfx.py`:** the engine code for new skills: combat bonuses, attack and defensive skills, kill triggers, and the extra `units`/`classes` lists.
- **`fe4skillmenu.py`:** the Skills menu extension: names, icons, help text and bearers.
- **`fe4studio.py`, `studio/`:** Builder of the Holy War, the visual editor: a small local web server with the interface in `studio/` (fonts: Pirata One and Alegreya Sans, SIL Open Font License, see `studio/fonts/`).
- **`fe4gfx.py`:** pictures for the editor without Pillow: portraits (tables at `$8B:9A88`, `$8A:B4F9`, `$8A:B7E1`) and each chapter's tile sheet with its terrain.
- **`fe4project.py`:** project files with undo, shared by both editors.
- **`fe4editor.py`:** the app's entry point and the classic table editor (`BuilderOfTheHolyWar.exe` is this, packaged for Windows).
- **`fe4rando.py`:** the randomizer.
- **`fe4gen2.py`:** generation 2: parent links, inheritance, new children, substitutes, love tables.
- **`asm65816.py`:** the small 65816 assembler those hooks are written with.
- **`fe4maps.py`, `fe4lz.py`:** map export/import and the game's compression format.
- **`fe4events.py`:** the event/scene/dialogue decoder used by `extract` and `build`.
- **`cpu65816.py`:** a small 65816 CPU emulator. It measures command lengths by running the game's own handlers.
- **`dis65816.py`:** a 65816 disassembler for reading the game's code: `python dis65816.py rom.smc 848397 40 --m16 --x16`.
- **`dev/`:** the headless test harness used to verify edits, `ch6start.py` (see "Generation 2"), plus `snes9x_trace.patch`.
  - The patch adds read, write and exec tracing to Snes9x (upstream commit `1bcc369`).
  - It's how the engine routines in `ROM_MAP.md` were located.
  - To build it, apply the patch, then run `make` in `snes9x/libretro`.
