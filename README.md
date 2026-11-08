# Build my stack — editorial TikTok edit

A 15.4s, 1080×1920 TikTok edit for a non-tarnish gold bracelet stack. It's minimal and editorial: three text moments, with the footage doing the rest.

**Deliverable:** `out/final_1080x1920.mp4` (H.264 High, 30 fps, bt709, AAC, faststart)

## Story (beat by beat)
| Time | Shot | Transition in | Text |
|---|---|---|---|
| 0.0–2.1 | Close-up of the finished stack, slow-mo pull-out (hook) | — | *build my* / **STACK** |
| 2.1–6.0 | Locked-off stop-motion: the bracelets appear one by one under one continuous slow push; the final piece is placed by hand with a speed ramp | zoom-through, then 3-frame "pop" fades | — |
| 6.0–8.5 | The full stack, eased push-in toward the tray | continuous | — |
| 8.5–12.2 | Slow-mo detail close-ups | zoom-through, then soft-focus dissolve | — NON-TARNISH |
| 12.2–15.4 | Hero close-up, soft fade so the loop restarts cleanly | soft-focus dissolve | *effortless,* / **ALWAYS.** |

All text hangs from the same 96px left margin and stays inside TikTok's safe zones: clear of the top bar, the right-hand action rail, and the caption/shop-tag area (see `out/safezone_check.jpg`).

## Look
- **Grade** (`edit/grade.txt`): removes the yellow cast from the wall and tray, keeps the gold warm and the pearl white, adds a soft highlight roll-off, a slight matte lift and gentle vibrance. One chain is applied to every shot.
- **Fonts** (`type/fonts`, all OFL licensed): Montserrat stands in for Gotham, Syne 800 for Advercase, and Pinyon Script is the cursive. To use the real Gotham/Advercase files, drop them in and edit the `@font-face` rules in `type/overlay.html`.
- **Audio:** a silent-ready bed (room tone, soft clinks as each piece appears, airy whooshes on transitions) at about −35 LUFS, so a trending sound added in the TikTok app sits on top.

## Re-render
```
pip install numpy opencv-python-headless   # plus ffmpeg, node + playwright (chromium)
python3 scripts/render.py                  # -> out/final_1080x1920.mp4
```
- `edit/edl.json`: the timeline (source in/out, speed and ramps, zoom/center moves, shared camera moves, transitions, SFX)
- `type/overlay.html`: the typography layout and animation cues, locked to the shot timing
- `scripts/render.py`: cuts, ramps, zooms and transitions, then grades, composites the type and encodes
- `scripts/render_type.js`: renders the type layer to transparent PNG frames with Playwright

### Swapping in the original footage
The current render uses the WhatsApp copies in `raw/proxy/` (464×832), upscaled with Lanczos and sharpened. To get a sharper render, put the full-resolution phone originals in `raw/originals/`, point `sources` in `edit/edl.json` at them, and re-run. The cut timings carry over unchanged. HDR (HLG/PQ) iPhone clips are tone-mapped to SDR automatically.
