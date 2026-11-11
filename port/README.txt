Fire Emblem: Genealogy of the Holy War - PC port (fe4port) 0.8.1
==============================================================

This is a native Windows build of FE4. It runs from YOUR OWN ROM: the
program contains no game code, graphics, music or text. On first launch it
reads your ROM, translates the game's 65816 machine code into C, and compiles
that C in memory with a small built-in compiler (TinyCC). The translated
code then runs on a software SNES (picture, sound and DMA from LakeSnes).

Recommended ROM: the Project Naga English translation (v1.0,
SHA-1 2b6eb74646a527ba293b0e004db3e0134a28dc6c). Other FE4 ROMs, including
hacks made with fe4kit and randomizer output, also work: the translation is
always made from whatever ROM you give it.


Getting started
---------------
1. Unzip this folder anywhere you like.
2. Put your FE4 ROM (.sfc or .smc) in the same folder as FE4.exe,
   or just run FE4.exe and pick the ROM when asked (only needed once).
3. Play. The first launch takes a second or two longer while the code is
   translated; later launches reuse the translation in the cache folder.


Controls (keyboard)                  Gamepad (Xbox/PlayStation/Switch pads)
-------------------                  ---------------------------------------
D-pad ........ arrow keys            D-pad or left stick
A ............ X                     right face button (B on Xbox)
B ............ Z                     bottom face button (A on Xbox)
X ............ S                     top face button
Y ............ A                     left face button
L / R ........ Q / W                 shoulder buttons
Start ........ Enter                 Start / Menu
Select ....... Right Shift           Back / View

Keys and gamepad buttons can be changed in the menu (F1 > Controls): click
the box next to a button, then press the key or gamepad button you want.
They're saved in fe4port.ini (key_A=Space, pad_A=b and so on). Gamepad
buttons are named by position, so the defaults work the same on Xbox,
PlayStation and Switch pads.


The menu (F1)
-------------
Press F1 or Esc (gamepad: click the right stick) to open the menu bar at
the top of the window; press it again to close it. The game pauses while
the menu is open (you can turn that off). Everything takes effect at once
and is saved in fe4port.ini.
  Game ........ save / load state, pick one of 9 state slots (with the time
                each was saved), pause, reset, quit
  Graphics .... widescreen, square pixels or TV shape, fullscreen, window
                size 1x-6x, smooth scaling, vsync, FPS counter
  Audio ....... volume, mute
  Enhancements  unit stats in the map box, fast-forward on/off and speed,
                automatic speed-ups, pause while the menu is open
  Controls .... click a box, then press the key or gamepad button you want
  Cheats ...... restore HP, gold, EXP for the unit under the cursor or the
                whole army
  Mods ........ switch mods on and off, change their order, the randomizer
  Help ........ list of shortcuts, About
Mouse, keyboard (arrow keys + Enter, Esc to go back) and gamepad (d-pad,
bottom face button to choose, right face button to go back) all work in
the menu. Hover over an option to
see what it does.


Widescreen
----------
With widescreen on (the default) the picture is 400x224 instead of 256x224,
about 16:9, and nothing is stretched. The extra area only ever shows what the
game itself has:
  * Map: more of the map, drawn from the game's own map data and tiles,
    including units (the game draws them; the port widens the area in which
    it draws units) and the blue/orange movement range.
  * Battles: the battle backgrounds are about 400 pixels wide in the game's
    own art; the screen normally shows only the middle 256. Where the battle
    camera is panned to one side and the art ends, that side shows black.
  * Everything else (menus, the title, story scenes, the status screen)
    stays 4:3 with black sides.
Past the edge of the area the camera is allowed to show, the map side is
black. A few animated map tiles (e.g. a village under attack) stand still
while they're in the extra area.
F4 or the menu switches widescreen on and off at any time, including the
units in the extra area.

Unit stats on the map
---------------------
Hovering over a unit shows a bigger version of the game's own name/HP box
with two extra lines, in the game's own font:
    MT24 HIT102      MT  = attack (strength or magic + weapon might)
    AS 9 AVO 25      HIT = hit rate, AS = attack speed, AVO = avoid
The numbers come from the same game routines the status screen uses (avoid
without the terrain bonus, as on the status screen). A unit with no usable
weapon shows "--" for MT and HIT; negative values show as 0.
Switch it on or off in the menu (Enhancements); the box changes the next
time it's drawn. If your ROM's code is different where the box is drawn
(some hacks), the option is greyed out and the game's box is left as is.

Cheats
------
Menu (F1) > Cheats, during a chapter. The top part works on the unit the
cursor was last on (one of yours), the bottom part on your whole army:
  * Restore HP: back to full.
  * Gold 50,000: the most a unit can carry.
  * EXP 99: the unit levels up after its next fight, through the game's own
    level-up (so its stats grow the normal way).
Cheats change your game for good; make a save state first if unsure.

Mods
----
Put patches (.ips or .bps files) in the mods folder next to FE4.exe:
hacks made with fe4kit, randomizer seeds, or other FE4 patches. Open the
menu (F1) > Mods > Mods... to switch them on or off and change the order
they're applied in (top first); press "Restart the game with these mods"
to play with your choice. New files in the folder start switched on.
  * Your ROM file isn't changed; the patches are applied in memory.
  * Each set of mods has its own save files (saves\<rom>+mods-....srm),
    so a hack or a randomized game never mixes with your normal saves.
  * Patches made for a ROM with or without the 512-byte copier header both
    work (the port checks which fits). A .bps patch must be made for your
    ROM (it checks), or for the result of the mods above it.
  * If a patch can't be applied, the Mods window says why and the game
    starts without it.
  * The widescreen and unit-stats options keep working on hacks unless the
    hack changed the same code (then the option is greyed out).

Randomizer
----------
Menu (F1) > Mods > Randomizer... makes a randomized game with fe4kit's
randomizer (fe4kit comes with this download, in the fe4kit folder):
  1. Pick a preset (light, standard, chaos), optionally type a seed, and
     open Options to change anything (hover an option to see what it does).
  2. Press Randomize. It takes about half a minute.
  3. The result is added to your mods as "Randomizer <preset> <seed>.ips"
     with a spoiler log next to it (the Mods window has a button for it).
     Other randomizer seeds are switched off. Press "Restart the game with
     these mods" and start a New Game.
The seed is made from your ROM plus the mods that are switched on, so you
can randomize a hack too. The same seed and options always give the same
game, also in the kit's editor and command line.

Making hacks: fe4kit
--------------------
The fe4kit folder has BuilderOfTheHolyWar.exe, the editor for making
your own FE4 hacks: characters with their portraits, stats, holy blood,
items and skills; love and children; classes; skills (FE4's and brand-
new ones); chapter maps (paint them with the game's tiles, redraw tiles
and change their terrain, drag castles, villages and units into place);
chapter events and all the dialogue (speech bubbles with portraits),
including new talks, turn events, village visits and battle quotes;
weapons, rings, shops, villages and the arena; the enemy armies and what
their units do; and the portraits and map sprites (replace any face or
unit with your own drawing). Its manual is fe4kit\README.html. Two
things connect it to this port:
  * Test play (F6, or the Test play button) builds your project and opens
    it here at once, without your mods, with its own saves.
  * "Add unit stats to the map box" (Project page) puts the MT/HIT/AS/AVO
    box into the ROMs you build, so players on emulators get it too.
When your hack is done, the .ips patch the editor writes can be shared;
players drop it in their mods folder.

Automatic speed-ups
-------------------
Menu (F1) > Enhancements > Automatic speed-ups. Each one is off until you
set a speed (2x-8x):
  * Faster text: while text is being written out (story scenes,
    conversations, village visits, battle quotes). It goes back to normal
    when the text waits for your button press.
  * Faster battles: the animated battle scenes.
  * Faster enemy phase: while the other armies (enemies and allies) move.
  * Faster cursor: while you hold a direction on the map in your phase, so
    the cursor and the map scroll faster.
The game itself is unchanged: it just runs more frames per second at those
moments, and the music keeps its normal speed. A small "» 4x" in the top
right corner shows when the game is sped up.

Fast-forward keeps the music at normal speed
--------------------------------------------
The SNES plays music on its own sound chip. While fast-forwarding, the port
runs the game faster but keeps the sound chip in real time, so the music
keeps its normal tempo and pitch. Sound effects also play at normal speed,
so at high speeds they can trail behind the action or cut each other off.
Set the speed (2x-8x, default 4x) in the menu (Enhancements). Frames
that are skipped aren't drawn, which keeps fast-forward cheap to run.

Other keys
  Tab (hold) ....... fast-forward (gamepad: hold the right trigger)
  F3 ............... fast-forward on/off (handy for long enemy phases)
  F1 / Esc ......... menu
  F11 / Alt+Enter .. fullscreen
  F2 ............... switch between square pixels (8:7) and 4:3
  F4 ............... widescreen on/off
  P / Pause ........ pause
  F5 / F7 .......... save state / load state
  F6 / F8 .......... previous / next state slot (1-9)


Your saves
----------
In-game saves are written to saves\<rom name>.srm (the same format as
SNES emulators, so you can copy saves between this port and an emulator
such as Snes9x).
Save states are saves\<rom name>.state1 ... state9. They belong to this
port only.


Settings (fe4port.ini, created on first launch)
------------------------------------------------
  scale=3          window size multiplier (1-8)
  fullscreen=0
  aspect=8:7       or 4:3
  smooth=0         1 = smooth (bilinear) scaling
  vsync=1
  volume=100
  mute=0
  pause_in_menu=1  pause the game while the F1 menu is open
  show_fps=0       FPS counter in the corner
  fast_forward=4   fast-forward speed, 2-8
  faster_text=1    automatic speed-ups, 1 = off, 2-8 = speed
  faster_battles=1
  faster_enemy_phase=1
  faster_cursor=1
  widescreen=1     16:9 maps and battles
  hover_stats=1    MT/HIT/AS/AVO in the map unit box
  recompiled=1     0 = run the game in the interpreter instead of the
                   translated code (for troubleshooting)
  learn=1          see below


How the translation works, and "learning"
-----------------------------------------
fe4port.cov lists the places in the game's code where translated blocks
start (addresses only, no game data). It was recorded by playing from the
opening through Chapter 1 battles and menus, plus the start of Chapter 6
(the generation 2 handover and its first enemy phase), and covers more than
99% of the code those parts run.

When the game reaches code that hasn't been translated yet, that code runs
in the built-in interpreter instead, so nothing breaks; it is only a little
slower. With learn=1 the port remembers those places in cache\learned.cov
and translates them too on the next launch. You can delete the cache folder
at any time; it is rebuilt automatically.

The translated C is kept in cache\fe4_*.c if you want to read it. It
corresponds one-to-one to the original assembly, with the original
instruction shown in a comment above each translated line. Because it is
made from your ROM, don't share it.


Hacks
-----
Besides mods, a patched ROM also runs here as-is: put it next to FE4.exe,
or set rom= in fe4port.ini, or start "FE4.exe --play yourhack.smc" to play
it once without changing your default ROM. New code added by a hack is
picked up automatically the same way as above. The cache folder keeps the
translations of the last few ROM versions you played.


Troubleshooting
---------------
* fe4port.log next to FE4.exe has details from the last run.
* If the game doesn't start after a hack, try recompiled=0. If that fixes
  it, please send the log.
* No sound: check that a Windows audio output device is enabled.


Verification
------------
The translated code was checked against the LakeSnes interpreter
instruction by instruction: after every translated block, every CPU
register, the cycle counter and the screen position must be identical, and
after every frame all of RAM, video RAM, palettes, sprites, sound RAM and
save RAM must be identical. This held for the full run from power-on to
Chapter 1 (including an in-game save), and for three 11-minute random-input
sessions in Chapter 1 (moving units, battles, enemy phases, scripted events,
menus): about 2 billion instructions in total, with zero differences. The
picture at the end of the Chapter 1 run is also identical to Snes9x's.
It also held for a run into Chapter 6 (a test copy of the ROM whose New
Game jumps there, with the usual couples married): the children's births,
the chapter 6 opening scenes, the map, unit lists and menus, ending the
turn and the enemy phase, then turn 2. That is 42,000 frames and 586
million more instructions with zero differences. Later chapters and a save
made in generation 2 haven't been checked yet.

Tested on: Linux, and the Windows build under Wine. It has not yet been run
on a real Windows PC.


Credits and licenses
--------------------
* fe4port: frontend, recompiler and runtime. Source code is in source.zip.
* LakeSnes by angelo_wf and contributors (dinkc64 fork), MIT license:
  SNES picture, sound, DMA and interpreter. See licenses\LakeSnes.txt.
* SDL2 (zlib license): window, input and audio. See licenses\SDL2.txt.
* Dear ImGui by Omar Cornut (MIT license): the in-game menu.
  See licenses\DearImGui.txt.
* Roboto font by Christian Robertson (Apache License 2.0): menu text.
  See licenses\Roboto-Apache-2.0.txt.
* TinyCC (GNU LGPL 2.1): libtcc.dll compiles the translated code. Its
  unmodified source is in licenses\tinycc-source.zip. You can replace
  libtcc.dll with your own build.
* fe4kit (fe4kit folder) is the FE4 hacking kit. BuilderOfTheHolyWar.exe contains
  Python (PSF license) and Tcl/Tk (BSD-style license), packaged with
  PyInstaller.
* Fire Emblem is (c) Nintendo / Intelligent Systems. The Project Naga
  translation is by its respective authors. This program contains none of
  their work; you need your own copy of the game.
