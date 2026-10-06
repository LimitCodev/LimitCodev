// Renderiza SVGs como <img> (contexto SVG-as-image, igual que GitHub) y captura PNG.
//
// Nota: hay que navegar a un archivo HTML real en disco. `page.setContent()`
// deja la página en `about:blank` y Chromium bloquea `file://` desde ese origen
// ("Not allowed to load local resource"), lo que produce imágenes rotas que
// parecen renders válidos — el error que costó descubrir.
const fs = require('fs');
const path = require('path');
// Playwright is not a project dependency (Chromium is ~150 MB); point
// PLAYWRIGHT_PATH at any local install, e.g. some-project/node_modules/playwright.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');

const items = JSON.parse(process.argv[2]); // [{file, out, label, width}]
const outdir = process.env.OUTDIR || '/tmp/preview';
fs.mkdirSync(outdir, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  for (const scheme of ['dark', 'light']) {
    const ctx = await browser.newContext({
      viewport: { width: 1100, height: 900 },
      colorScheme: scheme,
    });
    const page = await ctx.newPage();
    page.on('requestfailed', r =>
      console.log(`  ✗ request falló: ${r.url().slice(0, 90)} :: ${r.failure()?.errorText}`));

    const rows = items.map(it => `
      <figure style="margin:0 0 14px">
        <figcaption style="font:12px monospace;color:${scheme === 'dark' ? '#8b949e' : '#57606a'};padding:4px 0">
          ${it.label || path.basename(it.file)} · ${scheme}
        </figcaption>
        <img id="i${items.indexOf(it)}" src="${path.basename(it.file)}"
             width="${it.width || 960}"
             style="display:block;border:1px solid ${scheme === 'dark' ? '#30363d' : '#d0d7de'};border-radius:6px">
      </figure>`).join('');

    const htmlPath = path.join(outdir, `page-${scheme}.html`);
    fs.writeFileSync(htmlPath, `<!doctype html><meta charset="utf-8"><body style="margin:0;padding:16px;background:${
      scheme === 'dark' ? '#0d1117' : '#ffffff'}">${rows}</body>`);

    await page.goto('file://' + htmlPath);
    await page.waitForTimeout(Number(process.env.WAIT || 1800));

    const broken = await page.evaluate(() =>
      [...document.images].filter(i => !i.complete || i.naturalWidth === 0).length);
    if (broken) console.log(`  ⚠ ${broken} imagen(es) NO cargada(s) en ${scheme}`);

    await page.screenshot({ path: `${outdir}/render-${scheme}.png`, fullPage: true });
    await ctx.close();
    console.log(`capturado: ${outdir}/render-${scheme}.png`);
  }
  await browser.close();
})().catch(e => { console.error('FALLO:', e.message); process.exit(1); });
