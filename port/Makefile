CC ?= gcc
CFLAGS ?= -O2 -g -Wno-format
S = src/snes
CORE = $(S)/spc.c $(S)/dsp.c $(S)/apu.c $(S)/cpu.c $(S)/dma.c $(S)/ppu.c $(S)/cart.c $(S)/cx4.c \
       $(S)/input.c $(S)/statehandler.c $(S)/snes.c $(S)/snes_other.c
HDRS = $(wildcard $(S)/*.h) $(wildcard src/*.h)

work/lsrun: tools/lsrun.c src/fe4wide.c src/music.c $(CORE) $(HDRS)
	$(CC) $(CFLAGS) -I $(S) -I src -o $@ tools/lsrun.c src/fe4wide.c src/music.c $(CORE) -lm

RCINC = -I $(S) -I src/rc -I tools
RT = src/rc/rc_rt.c

work/recomp: src/rc/recomp.c src/rc/recomp.h src/rc/rc_ops.h
	$(CC) $(CFLAGS) -DRECOMP_MAIN -I src/rc -o $@ src/rc/recomp.c

work/gen.o: work/gen.c src/rc/rc_gen.h
	$(CC) -O1 -I src/rc -c -o $@ work/gen.c

work/lockstep: tools/lockstep.c $(RT) $(CORE) $(HDRS) src/rc/rc_rt.h src/rc/rc_gen.h src/rc/rc_ops.h tools/movie.h work/gen.o
	$(CC) $(CFLAGS) $(RCINC) -o $@ tools/lockstep.c $(RT) $(CORE) work/gen.o -lm

TCCL = ext/tcc-linux
src/rc/rc_gen_h.inc: src/rc/rc_gen.h
	python3 tools/str_inc.py $< $@

work/lockstep_jit: tools/lockstep.c $(RT) src/rc/rc_jit.c src/rc/rc_gen_h.inc $(CORE) $(HDRS) src/rc/rc_rt.h src/rc/rc_gen.h tools/movie.h
	$(CC) $(CFLAGS) -DUSE_JIT $(RCINC) -I $(TCCL)/include -o $@ tools/lockstep.c $(RT) src/rc/rc_jit.c $(CORE) $(TCCL)/lib/libtcc.a -lm -ldl -lpthread

APPSRC = src/main.c src/sha1.c src/fe4wide.c src/mods.c src/kit.c src/cheats.c src/music.c $(RT) src/rc/rc_jit.c src/rc/recomp.c
# ---- in-game menu (Dear ImGui, C++) ----
IMGUI = ext/imgui
IMSRC = $(IMGUI)/imgui.cpp $(IMGUI)/imgui_draw.cpp $(IMGUI)/imgui_tables.cpp $(IMGUI)/imgui_widgets.cpp \
        $(IMGUI)/backends/imgui_impl_sdl2.cpp $(IMGUI)/backends/imgui_impl_sdlrenderer2.cpp src/menu.cpp
IMOBJ_L = $(patsubst %.cpp,work/obj/%.o,$(notdir $(IMSRC)))
IMOBJ_W = $(patsubst %.cpp,win/obj/%.o,$(notdir $(IMSRC)))
vpath %.cpp $(IMGUI) $(IMGUI)/backends src
work/obj/%.o: %.cpp src/menu.h src/font_roboto.inc
	@mkdir -p work/obj
	g++ -O2 -I $(IMGUI) -I $(IMGUI)/backends -I src `sdl2-config --cflags` -c -o $@ $<

work/fe4: $(APPSRC) src/rc/rc_gen_h.inc $(CORE) $(HDRS) src/rc/*.h tools/movie.h $(IMOBJ_L)
	$(CC) $(CFLAGS) $(RCINC) -I src -I $(TCCL)/include `sdl2-config --cflags` -o $@ $(APPSRC) $(CORE) $(IMOBJ_L) $(TCCL)/lib/libtcc.a `sdl2-config --libs` -lstdc++ -lm -ldl -lpthread

# ---- Windows (mingw-w64) ----
WCC = x86_64-w64-mingw32-gcc
SDLW = ext/sdl2w/SDL2-2.30.9/x86_64-w64-mingw32
TCCW = ext/tccw
win/FE4.exe: $(APPSRC) src/rc/rc_gen_h.inc $(CORE) $(HDRS) src/rc/*.h tools/movie.h $(IMOBJ_W)
	mkdir -p win
	$(WCC) -O2 -Wno-format $(RCINC) -I src -I $(TCCW) -I $(SDLW)/include/SDL2 -Dmain=SDL_main -o $@ $(APPSRC) $(CORE) $(IMOBJ_W) \
	  -L $(SDLW)/lib -lmingw32 -lSDL2main -lSDL2 $(TCCW)/libtcc.dll -lcomdlg32 -limm32 -mwindows -static-libgcc -Wl,-Bstatic -lstdc++ -Wl,-Bdynamic
win/obj/%.o: %.cpp src/menu.h src/font_roboto.inc
	@mkdir -p win/obj
	x86_64-w64-mingw32-g++ -O2 -I $(IMGUI) -I $(IMGUI)/backends -I src -I $(SDLW)/include/SDL2 -c -o $@ $<
	cp $(SDLW)/bin/SDL2.dll $(TCCW)/libtcc.dll win/
