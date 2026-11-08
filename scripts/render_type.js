#!/usr/bin/env node
// Renders type/overlay.html frame-by-frame into transparent PNGs (build/type/%05d.png),
// driven by build/timeline.json so every text cue is locked to the cut.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const BUILD = path.join(ROOT, 'build');
const OUT = path.join(BUILD, 'type');

(async () => {
  const tl = JSON.parse(fs.readFileSync(path.join(BUILD, 'timeline.json'), 'utf8'));
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await page.addInitScript(`window.__TL = ${JSON.stringify(tl)};`);
  await page.goto('file://' + path.join(ROOT, 'type', 'overlay.html'));
  await page.evaluate(() => window.ready);

  const only = process.argv[2] ? process.argv[2].split(',').map(Number) : null; // optional: frame list
  const frames = only || [...Array(tl.total_frames).keys()];
  for (const f of frames) {
    await page.evaluate((t) => window.render(t), f / tl.fps);
    await page.screenshot({ path: path.join(OUT, String(f).padStart(5, '0') + '.png'), omitBackground: true });
    if (f % 60 === 0) process.stderr.write(`type ${f}/${tl.total_frames}\n`);
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
