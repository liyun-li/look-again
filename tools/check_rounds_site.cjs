// Deals rounds through the standalone page's own optsFor()/docketIds() and checks them with check_rounds.mjs's independent matcher.
// usage: node tools/check_rounds_site.cjs http://localhost:18734/   (needs puppeteer-core in /workspace/tools)
const P=require('/workspace/tools/node_modules/puppeteer-core'),fs=require('fs');
const src=fs.readFileSync(__dirname+'/check_rounds.mjs','utf8');
const FBI=src.match(/const FBI = (\{[\s\S]*?\});/)[1],KW=src.match(/const KW = (\{[\s\S]*?\});/)[1];
(async()=>{const b=await P.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const pg=await b.newPage();
 const errs=[];pg.on('pageerror',e=>errs.push(e.message));pg.on('request',q=>{if(/(^|\.)(fbi|justice|dea|secretservice|usmarshals)\.gov$/i.test(new URL(q.url()).hostname))errs.push('CONTACTED '+q.url())});
 await pg.goto(process.argv[2]+'?t=off',{waitUntil:'networkidle0'});await pg.waitForFunction(()=>typeof POOL==='object'&&Object.keys(POOL).length>0);
 const r=await pg.evaluate((FBIs,KWs)=>{const FBI=eval('('+FBIs+')'),KW=eval('('+KWs+')');
  const txt=c=>[c.title,c.r&&c.r.d,...((c.r&&c.r.t)||[]),...((c.r&&c.r.rm)||[]),c.r&&c.r.rw].filter(Boolean).join(' ');
  const fits=c=>{const s=new Set(),sj=(c.sj||[]).join(' | '),t=txt(c);for(const g of GROUPS)if(FBI[g].test(sj)||KW[g].test(t))s.add(g);return s};
  const fail=[];let n=0;const all=[].concat(...Object.values(POOL));
  const chk=(c,o,tag)=>{n++;const f=fits(c);if(o.length<3||o.length>4)fail.push(tag+' '+c.id+' n='+o.length);
   if(!o.includes(c.g))fail.push(tag+' '+c.id+' no answer');for(const x of o)if(x!==c.g&&(f.has(x)||(c.m||[]).includes(x)))fail.push(tag+' '+c.id+' '+c.g+'+'+x)};
  for(const c of all)for(let k=0;k<60;k++)chk(c,optsFor(c),'endless');
  for(let d=0;d<730;d++){const day=new Date(Date.UTC(2026,10,20+d)).toISOString().slice(0,10),ids=docketIds(day),rr=rng('fopts|'+day);
   if(ids.length!==5)fail.push(day+' docket '+ids.length);for(const id of ids)chk(BYID[id],optsFor(BYID[id],rr),'daily '+day)}
  return {n,cases:all.length,by:Object.fromEntries(Object.entries(POOL).map(([k,v])=>[k,v.length])),fail:fail.slice(0,40),nf:fail.length}},FBI,KW);
 // play one real daily through the UI too (clients must never call fbi.gov)
 await pg.evaluate(()=>{localStorage.clear()});await pg.goto(process.argv[2]+'?t=off&daily',{waitUntil:'networkidle0'});
 for(let i=0;i<5;i++){await pg.waitForSelector('#b0');await new Promise(r=>setTimeout(r,450));await pg.evaluate(j=>document.getElementById('b'+j).click(),i%3);await new Promise(r=>setTimeout(r,450));await pg.evaluate(()=>document.getElementById('next').click())}
 await pg.waitForSelector('#end.on',{timeout:5000}).catch(()=>errs.push('daily did not finish'));
 console.log(JSON.stringify({...r,errs}));await b.close();process.exit(r.nf||errs.length?1:0)})();
