# fe4_hacking

Source for two projects around *Fire Emblem: Genealogy of the Holy War* (FE4) with the
Project Naga English translation:

- **`port/`** — FE4 PC port: a native Windows/Linux program that runs the game from **your own
  ROM** (static 65816 → C recompiler + TinyCC, LakeSnes for picture and sound, SDL2, an in-game
  menu with enhancements, mods, randomizer, cheats). See `port/BUILDING.md`.
- **`kit/`** — fe4kit and **Builder of the Holy War**, the hacking editor: extract a ROM into a
  project of CSV and text files, edit characters, classes, maps, events and dialogue, and build a
  patched ROM plus an `.ips` patch. See `kit/README.md`.

Nothing from the game is in this repository: no ROM, no extracted projects, no generated code
from the ROM. Both programs read the user's own ROM (headerless SHA-1
`2b6eb74646a527ba293b0e004db3e0134a28dc6c`).

Third-party code and fonts keep their own licences: LakeSnes (MIT), Dear ImGui (MIT, fetched at
build time into `port/ext/imgui`), TinyCC (LGPL, shipped as libtcc.dll), SDL2 (zlib), Roboto
(Apache 2.0), and the editor's fonts (SIL OFL, `kit/studio/fonts/`). See `port/licenses/`.
