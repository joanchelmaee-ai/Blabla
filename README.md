# Build my stack — editorial TikTok edit

A 15.9s, 1080×1920 TikTok edit for a non-tarnish gold bracelet stack. The look is clean and editorial, and typography carries the video.

**Deliverable:** `out/final_1080x1920.mp4` (H.264 High, 30 fps, bt709, AAC, faststart)

## Story (beat by beat)
| Time | Shot | Type |
|---|---|---|
| 0.0–2.0 | Close-up of the finished stack, slow-mo pull-out (hook) | *build my* / **STACK** / *with me*, plus a "N° 05 pieces" tag |
| 2.0–7.4 | Stop-motion build on the cloud tray, with speed ramps (real shutter blur) on each placement | Numbered layers: N° 01 *the clover*, N° 02 *the tennis*, N° 03 *the snake chain*, N° 04 *the woven chain*, N° 05 *the pearl clover*, with a 5-bar progress rule |
| 7.4–9.6 | The full stack, eased push-in | **05** / *pieces, one stack* / "non-tarnish · made to layer" |
| 9.6–13.1 | Slow-mo detail close-ups, soft dissolves | "fig. 01 — the finish" / *non-tarnish* |
| 13.1–15.9 | Hero close-up, whip-in, soft fade so the loop restarts cleanly | *effortless,* / **ALWAYS.** / "linked below" (sits just above the TikTok Shop tag) |

All text stays inside TikTok's safe zones: clear of the top bar, the right-hand action rail, and the caption/shop-tag area (see `out/safezone_check.jpg`).

## Look
- **Grade** (`edit/grade.txt`): removes the yellow cast from the wall and tray, keeps the gold warm and the pearl white, adds a soft highlight roll-off, a slight matte lift and gentle vibrance. One chain is applied to every shot.
- **Fonts** (`type/fonts`, all OFL licensed): Montserrat stands in for Gotham, Syne 800 for Advercase, and Pinyon Script is the cursive. To use the real Gotham/Advercase files, drop them in and edit the `@font-face` rules in `type/overlay.html`.
- **Audio:** a silent-ready bed (room tone, soft clinks on each placement, whooshes on transitions) at about −32 LUFS, so a trending sound added in the TikTok app sits on top.

## Re-render
```
pip install numpy opencv-python-headless   # plus ffmpeg, node + playwright (chromium)
python3 scripts/render.py                  # -> out/final_1080x1920.mp4
```
- `edit/edl.json`: the timeline (source in/out, speed and ramps, zoom/center moves, transitions, SFX)
- `type/overlay.html`: the typography layout and animation cues, locked to the shot timing
- `scripts/render.py`: cuts, ramps, zooms and transitions, then grades, composites the type and encodes
- `scripts/render_type.js`: renders the type layer to transparent PNG frames with Playwright

### Swapping in the original footage
The current render uses the WhatsApp copies in `raw/proxy/` (464×832), upscaled with Lanczos and sharpened. To get a sharper render, put the full-resolution phone originals in `raw/originals/`, point `sources` in `edit/edl.json` at them, and re-run. The cut timings carry over unchanged. HDR (HLG/PQ) iPhone clips are tone-mapped to SDR automatically.
