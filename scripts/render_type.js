#!/usr/bin/env node
// Renders a type/<project>.html overlay frame-by-frame into transparent PNGs (<build>/type/%05d.png),
// driven by <build>/timeline.json so every text cue is locked to the cut.
// usage: node scripts/render_type.js <overlay.html> <build dir> [frame,list]
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const HTML = process.argv[2] || path.join(ROOT, 'type', 'bracelets.html');
const BUILD = process.argv[3] || path.join(ROOT, 'build', 'bracelets');
const OUT = path.join(BUILD, 'type');

(async () => {
  const tl = JSON.parse(fs.readFileSync(path.join(BUILD, 'timeline.json'), 'utf8'));
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await page.addInitScript(`window.__TL = ${JSON.stringify(tl)};`);
  await page.goto('file://' + path.resolve(HTML));
  await page.evaluate(() => window.ready);

  const only = process.argv[4] ? process.argv[4].split(',').map(Number) : null; // optional: frame list
  const frames = only || [...Array(tl.total_frames).keys()];
  for (const f of frames) {
    await page.evaluate((t) => window.render(t), f / tl.fps);
    await page.screenshot({ path: path.join(OUT, String(f).padStart(5, '0') + '.png'), omitBackground: true });
    if (f % 60 === 0) process.stderr.write(`type ${f}/${tl.total_frames}\n`);
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
