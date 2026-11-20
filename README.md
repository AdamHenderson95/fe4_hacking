# FE4 PC Port and Builder of the Holy War

Two free tools for *Fire Emblem: Genealogy of the Holy War* (FE4), made for the
Project Naga English translation:

- **FE4 PC Port** plays the game as a native Windows program. It has widescreen,
  fast-forward, save states, gamepad support, rank and love trackers, cheats,
  mods, a randomizer and custom music.
- **Builder of the Holy War** is an editor for making hacks and new games on
  FE4. It covers characters, classes, items, skills, maps and tile sets,
  events and dialogue, armies and AI, portraits, sprites, battle animations,
  music and the title screen. It saves your hack as a ROM or an `.ips` patch.

**Nothing from the game is included.** Both tools read your own FE4 ROM;
the Project Naga translation is recommended (headerless SHA-1
`2b6eb74646a527ba293b0e004db3e0134a28dc6c`).

## Download and play

1. Download the latest **FE4Port** zip from [Releases](../../releases) and unzip it anywhere.
2. Put your FE4 ROM next to `FE4.exe` and double-click `FE4.exe`.
3. Read `START HERE.txt` in the folder for the keys and the menu (F1).

The editor is in the `fe4kit` folder of the port's zip, and the newest one is on
its own as the latest **BuilderOfTheHolyWar** zip (1.6). Run
`BuilderOfTheHolyWar.exe`; its manual is `README.html`.

Both are Windows programs. They aren't signed yet, so Windows may show
"Windows protected your PC": click **More info**, then **Run anyway**.

## In this repository

- **`port/`**: the PC port. A static 65816 → C recompiler plus TinyCC, with
  LakeSnes for picture and sound, SDL2, and an in-game menu (Dear ImGui). See
  `port/README.txt` and `port/BUILDING.md`.
- **`kit/`**: fe4kit and Builder of the Holy War (Python). Its command line
  extracts a ROM into a project of CSV and text files and builds it back. See
  `kit/README.md`; `kit/ROM_MAP.md` documents what was found in the game.

## License

The code written for this project is under the MIT license (`LICENSE`).
Third-party code and fonts keep their own licenses:
- port: LakeSnes (MIT), SDL2 (zlib), TinyCC (LGPL; its source is in
  `licenses/tinycc-source.zip` of the release), Dear ImGui (MIT), stb_vorbis /
  dr_libs (public domain / MIT-0), Roboto (Apache 2.0), in `port/licenses/`
- editor: Python, Tcl/Tk, the PyInstaller bootloader and the Inter font, in
  `kit/licenses/`

Fire Emblem is a trademark of Nintendo / Intelligent Systems. This is a fan
project, not affiliated with or endorsed by them.
