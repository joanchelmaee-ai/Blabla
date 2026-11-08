# Editorial TikTok edits

Minimal, editorial TikTok affiliate edits (1080×1920, 30 fps): a soft shared grade, locked-off stop-motion, gentle transitions, and at most one natural-sounding title. Each product is its own project:

| Project | Deliverable | Length | Title |
|---|---|---|---|
| Non-tarnish bracelets | `out/bracelets/final_1080x1920.mp4` | 15.7s | none (no on-screen text) |
| Power strip | `out/power_strip/final_1080x1920.mp4` | 15.3s | none (no on-screen text) |
| USB hub | `out/usb_hub/final_1080x1920.mp4` | 7.4s | none (no on-screen text) |
| Glasses + pouch | `out/glasses/final_1080x1920.mp4` | 6.2s | none (no on-screen text) |

Each `out/<project>/` folder also has `contact_sheet.jpg` and `previews/`. Put "linked below" in the post caption, next to the shop tag.

## Bracelets: beat by beat
| Time | Shot | Transition in |
|---|---|---|
| 0.0–2.8 | Close-up of the finished stack, slow-mo pull-out | — |
| 2.8–6.7 | Locked-off stop-motion: the bracelets appear one by one under one slow push; the last is placed by hand with a speed ramp | zoom-through, then 3-frame pop fades |
| 6.7–9.2 | The full stack, eased push-in | continuous |
| 9.2–12.9 | Slow-mo detail close-ups | zoom-through, then soft-focus dissolve |
| 12.9–15.7 | Hero close-up, soft fade into the loop | soft-focus dissolve |

## Power strip: beat by beat
| Time | Shot | Transition in |
|---|---|---|
| 0.0–3.0 | Strip held up to camera, slow-mo pull-out | — |
| 3.0–5.2 | Tight slow-mo close-up on the three universal sockets | zoom-through |
| 4.9–7.4 | The strip in the desk setup | soft-focus dissolve |
| 7.1–11.9 | Locked-off stop-motion: plugs appear one by one with soft clicks; the black adapter goes in by hand with a speed ramp | zoom-through, then pop fades |
| 11.9–15.3 | Fully plugged-in setup, eased push-in, soft fade into the loop | pop fade |

## USB hub: beat by beat (short, punchy recut)
| Time | Shot | Motion | Transition in |
|---|---|---|---|
| 0.0–1.2 | Hub swings into frame, logo side | fast→slow speed ramp, quick pull-back | — (moving from frame 1) |
| 1.2–2.4 | Port side (USB ports, card slots) held up close | fast→slow ramp, slow push | zoom-through |
| 2.3–3.1 | Spins back to the logo side | slow→fast→slow ramp | 2-frame pop |
| 3.0–4.2 | Dual-head cable connector close-up | real speed, slow push | zoom-through |
| 4.2–5.0 | Set down on the desk | slow→fast ramp into the cut | 2-frame pop |
| 4.9–7.4 | Hub on the desk | ease-out push, soft fade into the loop | pop fade |

## Glasses + pouch: beat by beat
| Time | Shot | Motion | Transition in |
|---|---|---|---|
| 0.0–1.5 | Close shot of the glasses in front of the pouch | fast pull-back reveal | — |
| 1.5–2.4 | Punch-in on the frames | slow push | zoom-through |
| 2.2–3.9 | Glasses on the tray with the pouch behind | slow push + drift | focus-pull dissolve |
| 3.7–6.2 | Wide desk shot: glasses resting on the pouch | ease-out push, soft fade into the loop | zoom-through |

The camera was bumped slightly partway through the power strip's plugging section. The renderer corrects this automatically (feature-matched alignment to a reference frame, `align_ref` in the edit file) so the stop-motion stays rock-steady.

## Look
- **Grade** (`edit/grade.txt`, shared): removes the yellow cast from the wall and desk, keeps gold warm and whites clean, adds a soft highlight roll-off, a slight matte lift and gentle vibrance.
- **Fonts** (`type/fonts`, all OFL licensed): Pinyon Script for the cursive line, and Montserrat as a stand-in for Gotham on the lowercase line. To use real Gotham, drop the file in and edit its `@font-face` rule in `type/<project>.html`.
- **Audio:** a silent-ready bed (room tone, soft clinks or plug clicks as items appear, airy whooshes on transitions), kept low so a trending sound added in the TikTok app sits on top.

## Re-render
```
pip install numpy opencv-python-headless   # plus ffmpeg, node + playwright (chromium)
python3 scripts/render.py bracelets        # -> out/bracelets/final_1080x1920.mp4
python3 scripts/render.py power_strip      # -> out/power_strip/final_1080x1920.mp4
python3 scripts/render.py usb_hub          # -> out/usb_hub/final_1080x1920.mp4
python3 scripts/render.py glasses          # -> out/glasses/final_1080x1920.mp4
```
- `edit/<project>.json`: the timeline (source in/out, speed and ramps (`ramp_shape`: bell / in / out), zoom/center moves and easing, shared camera moves, alignment, transitions, SFX)
- `type/<project>.html`: the title layout and animation, locked to the shot timing (an edit with `"typography": false` renders with no text; the overlay files are kept in case a title comes back)
- `scripts/render.py`: cuts, ramps, zooms, alignment and transitions, then grades, composites the type and encodes
- `scripts/render_type.js`: renders the type layer to transparent PNG frames with Playwright

### Swapping in the original footage
The current renders use WhatsApp copies in `raw/proxy/` (464×832), upscaled with Lanczos and sharpened. To get sharper renders, put the full-resolution phone originals in `raw/originals/`, point `sources` in the edit file at them, and re-run. The cut timings carry over unchanged. HDR (HLG/PQ) iPhone clips are tone-mapped to SDR automatically.
