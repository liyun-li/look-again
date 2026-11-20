// Fails (exit 1) if any playable Look Again case could ever show two options that both fit it.
// Independent of tools/cats.py: its own reading of the FBI list names (c.sj) and its own charge keywords.
//   node tools/check_rounds.mjs [cases.json]              data check (runs in the daily Action)
//   node tools/check_rounds.mjs cases.json --prune        daily Action: benches (g=null) any case it flags, rewrites the file, then re-checks
//   node tools/check_rounds.mjs cases.json --hub mod.js   also deals 20k real rounds through the TELL. hub module's own pick()
import fs from 'fs';
const file = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : new URL('../cases.json', import.meta.url).pathname;
const D = JSON.parse(fs.readFileSync(file, 'utf8'));
const GROUPS = ['violent', 'gangs', 'money', 'cyber', 'spy', 'terror'];
const NEVER = new Set(['missing', 'parental', 'seeking']);
const FBI = { violent: /violent crime|additional violent/i, gangs: /criminal enterprise/i, money: /white-collar|while-collar|fraudster/i,
  cyber: /cyber/i, spy: /counterintelligence|iran|china threat|transnational repression/i, terror: /terroris/i };
const KW = {
  violent: /murder|homicid|\bkill|manslaughter|assault|robbery|kidnap|abduct|hostage|shoot|\bshot\b|carjack|firearm|machine gun|crime of violence|violent|stalk|arson|torture/i,
  gangs: /cartel|\bgangs?\b|ms-13|drug|narcotic|cocaine|heroin|methamphetamine|fentanyl|marijuana|controlled substance|racketeer|\brico\b|criminal enterprise|organized crime|mafia/i,
  money: /fraud|launder|embezzl|ponzi|securities|bribe|kickback|tax evasion|counterfeit|trade secret|identity theft/i,
  cyber: /computer|hack|intrusion|malware|ransomware|botnet|cyber|phishing|unauthorized access|crypto|bitcoin/i,
  spy: /espionage|\bspy|spies|intelligence (service|officer|agency)|ministry of state security|liberation army|\bgru\b|\bfsb\b|revolutionary guard|irgc|agents? of (a|the) foreign|foreign government|national defense information|emergency economic powers|ieepa|sanction|north korea|\bdprk\b/i,
  terror: /terror|bomb|explosive|material support|hijack|aircraft piracy|qa'?ida|\bisis\b|islamic state|hizballah|hezbollah|hamas|jihad|irgc|revolutionary guard/i };
const txt = c => [c.title, c.r && c.r.d, ...((c.r && c.r.t) || []), ...((c.r && c.r.rm) || []), c.r && c.r.rw].filter(Boolean).join(' ');
function fits(c) { // every category a reasonable player could argue for
  const s = new Set(), sj = (c.sj || []).join(' | '), t = txt(c);
  for (const g of GROUPS) { if (FBI[g].test(sj) || KW[g].test(t)) s.add(g) }
  return s;
}
if (process.argv.includes('--prune')) { // bench flagged cases instead of shipping them
  let pr = 0, benched = 0;
  for (let pass = 0; pass < 3; pass++) {
    const P = D.cases.filter(c => c && c.im && c.fq === 1 && GROUPS.includes(c.g) && Array.isArray(c.m) && !NEVER.has(c.c));
    const lv = GROUPS.filter(g => P.some(c => c.g === g));
    for (const c of P) { const own = new Set([c.g, ...c.m]), f = fits(c), bad = lv.filter(x => !own.has(x) && f.has(x));
      if (bad.length) { c.m = [...new Set([...c.m, ...bad])].sort(); pr++ }
      if (lv.filter(x => !new Set([c.g, ...c.m]).has(x)).length < 2) { c.gx = 'checker: too many fits'; c.g = null; benched++ } }
  }
  for (const c of D.cases) if (c && c.g && NEVER.has(c.c)) { c.g = null; benched++ }
  if (pr || benched) fs.writeFileSync(file, JSON.stringify(D));
  console.log('prune: widened', pr, 'benched', benched);
}
const fail = [], stat = { playable: 0, by: {}, choices: { 3: 0, 4: 0 } };
const playableRaw = D.cases.filter(c => c && c.id && c.im && c.fq === 1 && GROUPS.includes(c.g) && Array.isArray(c.m) && !NEVER.has(c.c) && !(c.all || []).some(a => NEVER.has(a)));
const live = GROUPS.filter(g => playableRaw.some(c => c.g === g));
for (const c of D.cases) {
  if (!c) continue;
  if (c.g && NEVER.has(c.c)) fail.push(`${c.id} ${c.c} has an answer but must never be scored`);
}
for (const c of playableRaw) {
  const own = new Set([c.g, ...c.m]), free = live.filter(x => !own.has(x));
  if (free.length < 2) continue; // clients drop it (fewer than 3 choices)
  stat.playable++; stat.by[c.g] = (stat.by[c.g] || 0) + 1; stat.choices[Math.min(4, free.length + 1)]++;
  const f = fits(c), sj = (c.sj || []).join(' | ');
  // the answer must be the FBI's own list (or, for Ten Most Wanted / LEA-only posters, the charge's only category)
  if (!FBI[c.g].test(sj) && !KW[c.g].test(c.r && c.r.d || '')) fail.push(`${c.id} answer ${c.g} not backed by FBI list "${sj}" or charges`);
  for (const x of free) if (f.has(x)) fail.push(`${c.id} "${c.title}" could show ${c.g} AND ${x} (FBI: ${sj}; charge: ${String(c.r && c.r.d || '').slice(0, 90)})`);
}
if (stat.playable < 150) fail.push('pool too small: ' + stat.playable);
if (GROUPS.filter(g => stat.by[g]).length < 4) fail.push('fewer than 4 live categories');
// optional: deal real rounds through the hub module's own load()/pick()
const hi = process.argv.indexOf('--hub');
if (hi > 0) {
  const src = process.argv[hi + 1], tmp = fs.mkdtempSync('/tmp/lookchk-');
  fs.copyFileSync(src, tmp + '/mod.mjs'); fs.copyFileSync(src.replace(/mod\.js$/, 'intro.js'), tmp + '/intro.js');
  fs.writeFileSync(tmp + '/mod.mjs', fs.readFileSync(tmp + '/mod.mjs', 'utf8').replace("from './intro.js'", "from './intro.mjs'")); fs.renameSync(tmp + '/intro.js', tmp + '/intro.mjs');
  globalThis.fetch = async () => ({ ok: true, json: async () => D });
  const mod = (await import(tmp + '/mod.mjs')).default, pool = await mod.load({ base: 'x' });
  let a = 1; const rng = () => { a = (a * 1103515245 + 12345) % 2147483648; return a / 2147483648 };
  let n = 0; const seen = new Set();
  for (let i = 0; i < 20000; i++) {
    const r = mod.pick(pool, rng, 1 + i % 3), c = r.c, f = fits(c); n++; seen.add(c.id);
    const right = r.opts.filter(b => b === c.g || (c.m || []).includes(b));
    if (r.opts.length < 3 || r.opts.length > 4) fail.push(`hub ${c.id} ${r.opts.length} options`);
    if (right.length !== 1 || right[0] !== c.g) fail.push(`hub ${c.id} options ${r.opts} answer ${c.g}`);
    for (const b of r.opts) if (b !== c.g && f.has(b)) fail.push(`hub ${c.id} distractor ${b} also fits`);
    if (new Set(r.opts).size !== r.opts.length) fail.push(`hub ${c.id} duplicate option`);
  }
  console.log(`hub: dealt ${n} rounds over ${seen.size} of ${pool.cases.length} hub cases`);
}
console.log(`playable ${stat.playable} ${JSON.stringify(stat.by)} rounds with 4 choices: ${stat.choices[4]}, with 3: ${stat.choices[3]}`);
if (fail.length) { console.log('FAIL ' + fail.length + '\n' + [...new Set(fail)].slice(0, 60).join('\n')); process.exit(1) }
console.log('PASS: no playable case can show two fitting options');
