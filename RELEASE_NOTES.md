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
