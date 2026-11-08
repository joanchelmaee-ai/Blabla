#!/usr/bin/env bash
# Re-render every edit (or the ones named) at full quality, then refresh its contact sheet.
# Each video renders to build/ first and is moved into out/ only when complete, so out/ never holds a
# half-written file.
#   scripts/render_all.sh                  # all edits in edit/*.json
#   scripts/render_all.sh glasses usb_hub  # just these
set -euo pipefail
cd "$(dirname "$0")/.."
projects=("$@")
if [ ${#projects[@]} -eq 0 ]; then
  for f in edit/*.json; do projects+=("$(basename "$f" .json)"); done
fi
for p in "${projects[@]}"; do
  echo "== $p ($(date +%H:%M:%S))"
  mkdir -p "build/$p" "out/$p"
  python3 scripts/render.py "$p" --out "build/$p/final_1080x1920.mp4"
  mv "build/$p/final_1080x1920.mp4" "out/$p/final_1080x1920.mp4"
  ffmpeg -v error -y -i "out/$p/final_1080x1920.mp4" -vf "fps=6,scale=150:-1,tile=15x4" -frames:v 1 "out/$p/contact_sheet.jpg"
  echo "== done $p ($(date +%H:%M:%S))"
done
echo "== all done ($(date +%H:%M:%S))"
