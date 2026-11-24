# 32 — Profiling: where the guest spends its instructions

Two instruments live in the library and answer different questions. The PC sampling answers *which
code is hot*; the draw log answers *why a draw that reached the rasterizer did not appear*. Both
are off unless an environment variable asks for them, and neither adds work to a normal run.

## PC sampling

```
ZEEBX_PCSAMPLE=20000 ZEEBX_PCSAMPLE_OUT=profile.txt \
  zeebx run game.mod --seconds=80
```

`ZEEBX_PCSAMPLE=N` makes the interpreter stop the guest every N instructions instead of running to
the budget, and records the PC it stopped on. `ZEEBX_PCSAMPLE_OUT` is where the histogram lands. The
file is rewritten every 2000 samples, so a run that is killed still leaves a usable profile.

Each line is four hex columns: `pc lr saved count`. `lr` is the return address and `saved` is the
word at `sp + 16` — the slot the ARM prologue usually keeps the caller's `lr` in, so it is a
heuristic for "one frame up" and not a promised unwind. The third column exists because of the
soft-float: the Zeebo's ARM11 has no VFP, so every `float` operation is a call into
libgcc, and a sample that lands there is only interesting for the function that asked for it.

`tools/pcsample_report.py` turns the histogram into a per-symbol profile:

```
python3 tools/pcsample_report.py profile.txt --elf build/sa1g.elf --base 0x10200
```

`--base` is the load offset: an applet is linked for `0x0` and runs from wherever the loader put it,
and this is the difference between the two (the Sonic Adventure port, for example, loads at
`0x10200`). With `--nm syms.txt` the script takes an `arm-none-eabi-nm -n` listing instead of the
ELF. It flattens the soft-float helpers into their caller by default and sums them as "soft-float";
`--no-flatten` counts them where they are, which is how the size of the soft-float bill is measured.

On the Sonic Adventure port, at the first boss, 80 seconds and 652 thousand samples:

```
amostras 652000  soft-float 63.7%
  7.7%  sa_ftrv
  7.3%  sprite_view
  5.4%  f__njInvertMatrix
  3.8%  draw_meshset_gl.isra.0
  3.8%  sqrtf
  3.7%  f__polygon_find_heights
```

The profile is an approximation, and it is honest about it: the sample is wherever the interpreter
stopped inside the slice, so a function that is called rarely but runs long is overrepresented in
the same way a wall-clock sampler would represent it. Branch-heavy code is counted by instruction,
not by time — the two agree closely only when the memory system is not the bottleneck, which is the
case here.

## Draw log

```
ZEEBX_DRAWLOG=120000:3 zeebx run game.mod --seconds=20
```

`ZEEBX_DRAWLOG=first:howmany` prints one line per draw whose index falls in the window, with what
the vertex stage kept and what the fragment stage will apply:

```
[draw 120001] mode=5 verts=4 tris=2 tex=59 blend=true 1+771 depth=true 515 atest=false 519
```

`verts` is how many vertices survived the transform, `tris` how many the mode produced after the
near-plane clip, and the numbers after `blend` and `depth` are the GL enums in force. A draw with
`tris=0` never reaches a fragment: the geometry or the matrix is wrong. A draw with `tris>0` and
nothing on screen is the other half of the problem, and the state tells which test rejected it —
`GL_LEQUAL` against a depth buffer that still holds the 3D scene, an alpha test with a reference
that the panel's alpha does not pass, or a blend whose factors cancel.

The window matters because a frame sends hundreds of draws: `ZEEBX_DRAWLOG=0:2` prints the first of
the run, and the index can be found by bisection. The counter is per rasterizer and resets with the
session.

## What the two do not do

Neither of them measures time in the rasterizer: on the software path the fragments are host work,
and no guest instrument sees it. `--dump-surfaces` and the frame counter in the log cover the
picture; the cost of a draw is only visible on the card (`--gpu`) or with a host profiler attached
to the emulator process.
