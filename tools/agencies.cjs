// Fetch the public wanted lists of three more U.S. federal agencies (public-domain U.S. government works) into
// agencies.json + raw portraits in .agimg/ (converted to img/*.webp by tools/build_cases.py). Clients never call these sites.
//   DEA fugitives (dea.gov/fugitives/all, ~52 pages of 10) · U.S. Secret Service Most Wanted · U.S. Marshals 15 Most Wanted
// Their CDNs refuse plain HTTP clients (and any non-browser User-Agent), so this drives headless Chrome, one page at a time with a pause in between.
// Only names, the agency's own charge wording, its case summary, the poster URL and the portrait are kept (no physical
// descriptions, no seals/logos). A failed source keeps its previous entries.
//   node tools/agencies.cjs [--max-img N]      (CHROME=/path/to/chrome, default /usr/bin/google-chrome)
const fs = require('fs'), path = require('path');
const P = require(process.env.PUPPETEER || 'puppeteer-core');
const ROOT = path.join(__dirname, '..'), OUT = path.join(ROOT, 'agencies.json'), RAW = path.join(ROOT, '.agimg'), IMG = path.join(ROOT, 'img');
const sl = ms => new Promise(r => setTimeout(r, ms));
const ONLY = ((process.argv.find(a => a.startsWith('--only=')) || '').split('=')[1] || 'dea,usss,usms').split(',');
const MAXDET = +((process.argv.find(a => a.startsWith('--max-detail=')) || '').split('=')[1] || 600);
const MAXIMG = +((process.argv.find(a => a.startsWith('--max-img=')) || '').split('=')[1] || 600);
const ent = s => String(s || '').replace(/<[^>]+>/g, ' ').replace(/&nbsp;|&#160;/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#0?39;|&rsquo;|&#8217;/g, '’').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/\s+/g, ' ').trim();
const slug = u => u.replace(/\/+$/, '').split('/').pop().toLowerCase().replace(/[^a-z0-9-]/g, '');
let prev = {}; try { for (const c of JSON.parse(fs.readFileSync(OUT, 'utf8')).items) prev[c.id] = c } catch (e) { }
(async () => {
  const b = await P.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox'] });
  const pg = await b.newPage();
  await pg.setUserAgent('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36');
  let req = 0;
  async function html(u) { for (let k = 0; k < 2; k++) { try { req++; const r = await pg.goto(u, { waitUntil: 'domcontentloaded', timeout: 60000 }); await sl(2500); if (r && r.status() < 400) return await pg.content(); console.error('http', r && r.status(), u) } catch (e) { console.error('err', u, e.message) } await sl(8000) } return null }
  const got = { dea: [], usss: [], usms: [] }, ok = { dea: false, usss: false, usms: false };
  // ---- DEA: every listing page (teaser = portrait + name + "Wanted for the following alleged federal violations: ...")
  for (let p = 0; ONLY.includes('dea') && p < 80; p++) {
    const h = await html('https://www.dea.gov/fugitives/all' + (p ? '?page=' + p : '')); if (!h) break;
    const rows = h.split('teaser-content').slice(1); if (!rows.length) { ok.dea = p > 0; break }
    for (const r of rows) {
      const a = r.match(/<a href="(\/fugitives\/[^"?#]+)">([\s\S]*?)<\/a>/), im = r.match(/<img[^>]+src="([^"]+)"/), tx = r.match(/teaser__text[^>]*>([\s\S]*?)<\/div>/);
      if (!a) continue;
      const ch = ent(tx && tx[1]).replace(/^wanted for the following alleged federal violations:\s*/i, '');
      got.dea.push({ id: 'dea-' + slug(a[1]), src: 'dea', name: ent(a[2]), url: 'https://www.dea.gov' + a[1], img: im ? new URL(im[1], 'https://www.dea.gov').href : null, d: ch });
    }
    if (rows.length < 10) { ok.dea = true; break }
  }
  // DEA profile pages (once per fugitive, kept in agencies.json): year of birth, reward, office tag, notes
  if (ONLY.includes('dea') && ok.dea) {
    let n = 0;
    for (const c of got.dea) {
      const o = prev[c.id];
      if (o && o.dt) { Object.assign(c, { yb: o.yb, rw: o.rw, pl: o.pl, nt: o.nt, dt: 1 }); continue }
      if (n++ >= MAXDET) continue;
      const h = await html(c.url); if (!h) continue;
      const cell = k => ent((h.match(new RegExp('<td scope="row">' + k + '</td>\\s*<td>([\\s\\S]*?)</td>')) || [])[1]);
      c.yb = +cell('Year of Birth') || null; c.nt = cell('Notes') || null;
      c.rw = ent((h.match(/fugitive__reward">([\s\S]*?)<\/div>/) || [])[1]) || null;
      c.pl = [...h.matchAll(/button--tag">([\s\S]*?)<\/a>/g)].map(x => ent(x[1])).filter(Boolean)[0] || null; c.dt = 1;
    }
  }
  // ---- Secret Service: list cards, then each profile's case summary + charges
  const hs = ONLY.includes('usss') && await html('https://www.secretservice.gov/investigations/mostwanted');
  if (hs) {
    const cards = [...hs.matchAll(/<div class="wanted-card[^"]*">([\s\S]*?)View More<\/a>/g)];
    for (const m of cards) {
      const a = m[1].match(/href="(\/investigations\/mostwanted\/[^"]+)"/), nm = m[1].match(/<h3>([\s\S]*?)<\/h3>/); if (!a) continue;
      const ci = m[1].match(/<img[^>]+src="([^"]+)"/), rw = ent((m[1].match(/class="reward">([\s\S]*?)<\/div>/) || [])[1]);
      const id = 'usss-' + slug(a[1]); if (got.usss.some(x => x.id === id)) continue;
      const h = await html('https://www.secretservice.gov' + a[1]); if (!h) { if (prev[id]) got.usss.push(prev[id]); continue }
      const main = h.slice(h.indexOf('CASE SUMMARY') > 0 ? h.indexOf('CASE SUMMARY') : 0);
      const ps = [...main.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/g)].map(x => ent(x[1])).filter(t => t.length > 40).slice(0, 6);
      const imgs = [...h.matchAll(/<img[^>]+src="([^"]*\/inline-images\/[^"]+)"/g)].map(x => new URL(x[1], 'https://www.secretservice.gov').href);
      const fo = (ent(h).match(/SECRET SERVICE FIELD OFFICE:\s*([A-Za-z .'-]{3,40}?)\s+(CASE SUMMARY|CHARGES|$)/i) || [])[1];
      const cimg = ci ? new URL(ci[1], 'https://www.secretservice.gov').href : null;
      got.usss.push({ id, src: 'usss', name: ent(nm && nm[1]), url: 'https://www.secretservice.gov' + a[1], img: cimg || imgs[0] || null, alt: imgs.slice(0, 2), d: '', t: ps.filter(t => !/presumed innocent|Relevant Links/i.test(t)), of: fo || null, rw: rw || null });
    }
    ok.usss = got.usss.length >= 10;
  }
  // ---- U.S. Marshals 15 Most Wanted: card = name + portrait + "X is wanted for ..." blurb
  const hm = ONLY.includes('usms') && await html('https://www.usmarshals.gov/what-we-do/fugitive-investigations/15-most-wanted-fugitive');
  if (hm) {
    for (const li of hm.split('class="usa-card ').slice(1)) {
      const nm = li.match(/usa-card__heading">([\s\S]*?)<\/h2>/), im = li.match(/<img[^>]+src="([^"]+)"/), bd = li.match(/usa-card__body">([\s\S]*?)<\/div>\s*<\/div>/), a = li.match(/href="([^"]*15-most-wanted[^"]*\/[^"\/#]+)"/);
      if (!nm || !a) continue;
      const id = 'usms-' + slug(a[1]), url = new URL(a[1], 'https://www.usmarshals.gov').href;
      const h = await html(url); let ps = [], rw = null;   // profile: the Marshals' own case summary + reward line
      if (h) { const mm = h.slice(Math.max(0, h.indexOf('<main')), h.indexOf('</main>') > 0 ? h.indexOf('</main>') : undefined);
        ps = [...mm.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/g)].map(x => ent(x[1])).filter(t => t.length > 40 && !/^(If you have|Anyone with|Tips can|Submit a tip|Download)/i.test(t)).slice(0, 8);
        rw = (ent(mm).match(/reward of up to \$[\d,]+|\$[\d,]+ reward/i) || [null])[0]; }
      got.usms.push({ id, src: 'usms', name: ent(nm[1]), url, img: im ? new URL(im[1], 'https://www.usmarshals.gov').href : null, d: '', t: [ent(bd && bd[1]), ...ps].filter(Boolean), rw });
    }
    ok.usms = got.usms.length >= 5;
  }
  // keep the previous copy of any source that failed this time
  const items = [];
  for (const s of ['dea', 'usss', 'usms']) items.push(...(ok[s] ? got[s] : Object.values(prev).filter(c => c.src === s)));
  for (const s in ok) if (!ok[s] && !ONLY.includes(s)) ok[s] = 'kept';
  // portraits: only for entries without a cached webp; fetched through the same browser session
  fs.mkdirSync(RAW, { recursive: true }); let ni = 0;
  for (const c of items) {
    if (!c.img || ni >= MAXIMG) continue;
    if (fs.existsSync(path.join(IMG, c.id + '.webp')) || fs.readdirSync(RAW).some(f => f.startsWith(c.id + '.'))) continue;
    for (const u of [c.img, ...(c.alt || [])]) {
      try { req++; ni++; const r = await pg.goto(u, { waitUntil: 'load', timeout: 45000 }); const buf = r && r.ok() ? await r.buffer() : null;
        if (buf && buf.length > 1500) { fs.writeFileSync(path.join(RAW, c.id + '.' + ((r.headers()['content-type'] || '').split('/')[1] || 'jpg').replace(/[^a-z]/g, '')), buf); break } } catch (e) { console.error('img', u, e.message) }
      await sl(1500);
    }
  }
  await b.close();
  const n = items.reduce((o, c) => (o[c.src] = (o[c.src] || 0) + 1, o), {});
  if (!items.length) { console.log('agencies: nothing read; keeping previous file'); return }
  fs.writeFileSync(OUT, JSON.stringify({ updated: new Date().toISOString().slice(0, 16) + 'Z', ok, n, items }, null, 0));
  console.log('agencies', JSON.stringify(n), 'fresh', JSON.stringify(ok), 'requests', req);
})();
