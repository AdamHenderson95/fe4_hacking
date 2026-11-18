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
