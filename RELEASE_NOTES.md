# Builder of the Holy War 1.6

### New
- **World map narration**: the story told over the map of Jugdral before each chapter's title can now be
  edited. For the Prologue, that's the history of Grannvale a new game opens with. It's listed at the top of each
  chapter's timeline (Events & dialogue > Chapter timeline); **Edit** opens a box like any other message.
  Projects made with older versions pick up the narration the first time 1.6 opens them, and nothing else
  changes.

# Builder of the Holy War 1.5

### New
- **Chapter timeline** (Events & dialogue, the button under the chapter list; also **Timeline** on the Maps
  page): a chapter's whole story in order. It starts with the opening, then each turn's events, then what
  happens when a castle is taken, someone reaches a place, talks, fights or dies, or visits a village. It ends
  with how the chapter is won and lost. Each entry says in plain words who talks, which units come onto the
  map, who joins your army, what is given, and whether it wins or loses the chapter. **Open** jumps to that
  event to change it.

# Builder of the Holy War 1.4

Chapters can now be lost as well as won, and **Check my hack** looks the whole project over for mistakes
before you test. The PC port is unchanged (1.0.1).

### New
- **Lose conditions** (Maps page, next to Win condition, and on the right-click menu): the game is lost when
  someone the player must protect is defeated, or when an enemy takes a castle the player must hold. Pick who
  speaks and what they say; the music fades, the message shows and the Game Over screen follows, as when
  Sigurd falls. The card also shows the rules the game always has (your leader falls, an enemy takes your
  base castle) and lets you remove the ones you added.
- **Check my hack** (under Save): lists problems in every chapter, each with **Show** to go straight there.
  It finds:
  - units placed outside the map, or two units of one group on the same cell;
  - soldiers whose class can't use their weapons, or can't move where they stand;
  - chapters nothing wins, or win conditions that could end a chapter early;
  - messages too wide or too long for the text box;
  - added characters without a name;
  - when room is running out for new scenes or units.
  It can also try a full build. The game's own oddities aren't reported, only your changes.

### Fixed
- Messages longer than three lines ran on in the same box after the button press; they now start a fresh
  box, as the game's own text does. Conversations that go back to the first speaker now clear that speaker's
  box first. This affects talks, recruit events, opening scenes and arriving characters' conversations.
- In messages you write, a new line now starts a new line in the box.

# Builder of the Holy War 1.3.1

A full test pass of the editor (every page, every chapter, the map cards, builds on Linux and Windows, the
new 1.3 features in the game) and the fixes it led to.

### Fixed
- Unnamed enemy commanders (Kinbaith, Gandolf, Elliot…) showed as "unit" in win conditions and event
  descriptions; they now show their names.
- **Place a unit** no longer copies a nearby boss's class and weapons as the starting choice: it starts from
  the nearest ordinary soldier.
- The right-click menu no longer offers "Taking this castle wins the chapter" on a castle you already hold.

### New for people working on the editor
- `dev/selftest.py` and `dev/pagetour.js`: an automatic check of the editor (see "Also included" in the
  manual).

# Builder of the Holy War 1.3

Making story events easier: characters who come onto the map during a chapter, more ways to win a chapter, and
chapters where your army starts without a castle. The PC port is unchanged (1.0.1).

### New
- **A character arrives here:** right-click an empty cell on the Maps page. Pick who arrives and whether
  they **join your army at once** (as Azel and Lex do in the Prologue) or **arrive in another army**, enemy or
  neutral (as Dew does), optionally to be recruited by talking to them. They **walk in** from a cell you pick
  or **appear** on the spot, **when** the opening scene ends, a turn starts, someone reaches an area or a
  castle is taken. A short conversation over the map can follow.
- **More win conditions** in **★ Win condition**:
  - **Boss:** the chapter ends when someone you pick is defeated.
  - **Rout:** the chapter ends when every unit of the armies you tick is gone.
  - **Defend:** survive until a turn starts (the "survive" choice from 1.2, under a clearer name).
  - **Seize** a castle, as before.
- **Chapters without a castle:** on the Armies & AI page, untick all your army's castles and the chapter
  starts with your units in the field. The page explains what that means.

### Fixed
- A colon (`:`) in event text no longer stops the card with "no FE4 text code".

### Good to know
- Rout is checked as each army's phase starts, so the chapter ends at the start of the next phase after the
  last unit falls. An army with no one on the map yet counts as gone: don't tick armies that arrive later,
  or your allies.
- Boss can only pick characters used by one unit on the map. Most soldiers share theirs with others.
- Defend can't make losing a castle a game over yet.
- Without a castle there are no shops, arena or retreating until your army takes one, and characters who
  join have no home castle. Tested in the Prologue.

Download **BuilderOfTheHolyWar-1.3.zip** and replace your old editor folder's files with it; your projects
keep working.

# Builder of the Holy War 1.2

Everything a brand-new chapter needs. Most of it is on the **Maps** page: in the buttons above the map and in
the right-click menu. Every change is one Ctrl+Z. The PC port is unchanged (1.0.1).

### New
- **★ Win condition:** the chapter ends when you take a castle you pick, or when a turn starts ("survive
  until turn 8"). The chapter's own ending scene, the Save Game screen and the next chapter follow as before.
  The winning castle shows a ★ on the map.
- **Chapter title:** type a new title and the editor draws the title card in the game's style (light letters
  with a black outline), with a preview of the card. Pick the font, size and width. The chapter's name in the
  game's text and in the editor's chapter list changes too.
- **Opening scene:** build what plays when the chapter starts from simple steps: music, camera, units
  arrive, a conversation over the map, a pause, fade the music. Replace the game's opening (its map set-up is
  always kept) or keep it and play your steps after it.
- **Add and remove castles and villages:** right-click an empty cell to add one, or right-click one to
  remove it. A new one can copy the map tiles of one of the chapter's own castles or villages; a castle gets a
  name and the army that holds it, a village its gold. Removing one keeps the numbering in order and updates
  the events, armies and enemy orders that point at the others. Up to 16 per chapter.
- **New first-generation characters:** **+ New character** on the Characters page. The game has 24
  character places and all are used, so a new character takes the place of someone your story leaves out
  (their love and children rules come with it). It can start in Sigurd's army instead of them.
- **New armies:** **+ New army** on the Armies & AI page adds an army to the chapter in its next free slot,
  with its own phase, working like an army you pick (its side, allies and enemies, and AI orders).

### Fixed
- New data the build puts in free space never starts at an address ending in `0000`, which the game reads
  as "nothing" in places.
- Map cards close when you go to another page, and Esc closes any card even before you click in it.

### Good to know
- A new character's name can show blank in unit lists that have no room left for drawn names (new
  children have the same limit).
- A new army shares the AI orders of the army it copies: changing one changes both.
- Win conditions are "take a castle" and "survive until a turn" for now. Chapter 2's ending is part of its
  story sequence and can't be changed.

The guide **Your first chapter** walks through making a chapter with all of this.

Download **BuilderOfTheHolyWar-1.2.zip** and replace your old editor folder's files with it; your projects
are kept.

---

# Builder of the Holy War 1.1

Placing units and making events on a map now happen right on the **Maps** page, in small pop-up cards.
The PC port is unchanged (1.0.1).

- **Right-click anything on the map** for what you can do there. Each choice opens one card with the
  values filled in from the nearest enemy; Enter confirms, Esc closes, and everything is one Ctrl+Z.
- **Place enemies and allies:** class, level, up to three weapons or items (the ones the class can use are
  listed first, and a class change picks one it can use), the name shown on the map, or a named character;
  their army, what they do (the army's AI programs in words), army leader, and when they arrive.
  Double-click an empty spot, or point and press E, for the same card.
- **Reinforcements:** "Reinforcements arrive here…" makes a new group that comes in at the start of a turn
  or when someone reaches an area you pick on the map. More units can join the group later.
- **Shared soldiers:** many enemies share one record. Changing one asks whether to change just that one
  (it gets its own copy) or all of them, and lists where the others are.
- **Events from the map:** talks, recruiting by talking, battle and death quotes from a unit; area,
  village and start-of-turn events from the ground. Type the words in the card (they are wrapped to the
  game's text box) or write them later on the Events page.
- **Copy, paste, duplicate and remove units** (Ctrl+C, Ctrl+V, Ctrl+D, Delete). Drag across the map to
  select several; dragging one of them moves them all. Pasting into another chapter asks for the army and
  when they arrive.
- **Danger zones:** where an enemy can move (red) and hit (orange), for one unit or all of them, using the
  game's own terrain costs.
- **▶ Test this chapter** builds your game and opens the PC port with New Game going straight to the
  chapter on screen. For chapters 1-5, press A through the earlier chapters' opening scenes and save at each
  Save Game screen.
- **More room:** up to 70 new groups of units (deploy lists 58-127) and about 100 new kinds of unit
  (was about 30).
- **Fix:** steps added to an event on the Events page (give an item, raise a stat, units arrive) now go
  into the event's scene. Before, they were written after the event's action, where the game runs them on
  every event check. Events that still have such steps show a warning: remove the extra steps and add them
  again.

Download **BuilderOfTheHolyWar-1.1.zip** and replace your old editor folder's files with it; your projects
are kept. The PC port's zip still has editor 1.0 in its `fe4kit` folder: replace those files with this
zip's to use 1.1 from there.

---

# FE4 PC Port 1.0.1

A fix release for the PC port's widescreen. The editor (Builder of the Holy War) is unchanged at 1.0.

- **Units in the extra area:** the map now shows every unit in the widescreen area at the sides, enemies
  included. Before, the game only drew units inside the original 4:3 area.
- **No more black sides on some maps:** on chapters whose maps carry area flags (chapters 2–5 and 7–11),
  the widescreen area could turn black, partly or completely. The map is now drawn there as everywhere else.
- **Battles:** when the battle camera pans past the end of the background art, the art now continues as its
  mirror image instead of a black edge.

Download **FE4Port-1.0.1.zip** and replace your old FE4Port folder's files with it (your saves, settings,
mods and music stay where they are). The first start translates the game again, which takes a few seconds.

---

# FE4 PC Port 1.0 and Builder of the Holy War 1.0

The first public release of a native PC port of *Fire Emblem: Genealogy of the
Holy War* and of an editor for making hacks and new games on it. Both run from
**your own ROM** (the Project Naga English translation is recommended) and
contain nothing from the game.

## Downloads

- **FE4Port-1.0.zip**: the PC port, with the editor included in its `fe4kit`
  folder. Unzip it, put your ROM next to `FE4.exe` and run it.
  `START HERE.txt` explains the rest.
- **BuilderOfTheHolyWar-1.0.zip**: the editor on its own, with the
  command-line kit (Python source) and the full manual.

64-bit Windows. The programs aren't signed yet, so Windows may show
"Windows protected your PC": click **More info**, then **Run anyway**.

## FE4 PC Port

- Runs the game as a native program: the game's code is translated to C on the
  first launch, which takes a few seconds.
- Widescreen (400 × 224, more of the map without stretching), fullscreen,
  window sizes, square or TV-shaped pixels.
- Fast-forward with music at normal speed, and automatic speed-ups for text,
  battles and enemy turns.
- 9 save-state slots. The game's own saves use the emulator `.srm` format.
- Keyboard and gamepad (Xbox, PlayStation, Switch), with every button
  remappable.
- Unit stats (Mt / Hit / AS / Avo) in the map's unit box.
- Rank tracker (F9): turns, level-ups and deaths, with the grade each would
  give.
- Love tracker (F10): every couple's love points, with an optional pop-up
  whenever they go up.
- Cheats: restore HP, gold, EXP.
- Mods folder (.ips / .bps, with load order). Each set of mods keeps its own
  saves.
- Randomizer built in (F1 > Mods > Randomizer).
- Custom music: drop OGG / FLAC / MP3 / WAV / MSU-1 files in the music folder.

## Builder of the Holy War

- Edits characters, classes, items, shops, villages and the arena.
- Skills: new skills with their own effects, menu icons and status-page
  entries.
- Love, children and generation 2, including new children.
- Maps: paint them; resize them up to 64 × 64; redraw tiles; give a chapter a
  whole new tile set, or draw a whole map as one picture.
- Castles and villages, armies and AI, including formations and fight styles.
- Events and dialogue: a conversation editor, new talk / turn / visit / area
  events.
- Portraits, map sprites, walking pictures, battle animations, spell effects,
  skill animations and map battles.
- Music: where songs play, your own music files, and MSU-1 for emulators.
- Title screen: your own background, logo and emblem.
- Builds a patched ROM or an `.ips` patch with a read-me, and has a Test play
  button that opens the hack in the PC port.

## Known limits

- Windows only for now. The port builds on Linux from source
  (`port/BUILDING.md`).
- The game has 12 chapters, and new chapters can't be added yet.
- Maps can be at most 64 × 64.

## License

MIT for this project's code; third-party parts keep their licenses
(`licenses` folders). Fire Emblem is a trademark of Nintendo / Intelligent
Systems. This is a fan project, not affiliated with or endorsed by them.
