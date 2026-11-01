#!/usr/bin/env python3
"""Refresh cases.json from the public FBI Wanted API (https://api.fbi.gov/wanted/v1/list).
Stdlib only. Keeps the previous cases.json if the API can't be read.
Rules: no race/ethnicity/physical-description text, no sex before reveal, no gore, no child-exploitation
or unidentified-remains or homicide/sexual-assault ViCAP files, no deceased-victim cases.
Case text is the FBI's own wording (sentences may be dropped, never rewritten)."""
import json, re, os, sys, time, html, urllib.request, urllib.error, hashlib, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'cases.json')
IMG = os.path.join(ROOT, 'img')
API = 'https://api.fbi.gov/wanted/v1/list?page=%d&pageSize=50'
UA = 'Mozilla/5.0 (compatible; look-again-game/1.0; +https://liyun-li.github.io/look-again/)'

# ---- category buckets (game options) from FBI "subjects" ----
BUCKET = {
 'Ten Most Wanted Fugitives': 'topten',
 'Most Wanted Terrorists': 'terror', 'Seeking Information - Terrorism': 'terror', 'Domestic Terrorism': 'terror',
 'Counterintelligence': 'spy', 'China Threat': 'spy', 'Iran': 'spy', 'Transnational Repression': 'spy',
 "Cyber's Most Wanted": 'cyber',
 'White-Collar Crime': 'money', 'While-Collar Crime': 'money', 'Most Wanted Fraudster': 'money',
 'Parental Kidnapping': 'parental',
 'Kidnappings and Missing Persons': 'missing', 'ViCAP Missing Persons': 'missing', 'Kidnappings/Missing Persons': 'missing',
 'Criminal Enterprise Investigations': 'gangs',
 'Violent Crime - Murders': 'violent', 'Additional Violent Crimes': 'violent', 'Law Enforcement Assistance': 'violent',
 'Seeking Information': 'seeking',
}
PRIORITY = ['topten', 'terror', 'spy', 'cyber', 'money', 'parental', 'missing', 'gangs', 'violent', 'seeking']
EXCLUDE_SUBJ = {'Crimes Against Children', 'ECAP', 'Endangered Child Alert Program', 'Human Trafficking',
                'ViCAP Unidentified Persons', 'ViCAP Homicides and Sexual Assaults', 'ViCap homicides and sexual assaults',
                'John Doe'}
EXCLUDE_PATH = re.compile(r'/(ecap|cac|vicap/(unidentified|homicides)|human-trafficking)', re.I)

GRAPHIC = re.compile(r"dismember|decapitat|mutilat|tortur|\brap(e|ed|es|ing|ist)\b|sexual|\bsex\b|sex traffick|molest|strangl|stabb|bludgeon|"
    r"beaten to death|beat\w* to death|burned alive|set (him|her) on fire|corpse|cadaver|pornograph|exploitation|obscen|"
    r"\bremains\b|skeletal|\bbod(y|ies)\b|decompos|dead body|grave\b|autopsy|blood|gore|severed|throat|naked|nude|"
    r"incest|pedophil|child abuse|minor victim|enticement|lewd|genital", re.I)
DEATH = re.compile(r"murder\w*|\bkill\w*|homicide|\bshot\b|shooting|\bdeath\b|\bdied\b|deceased|found dead|homicide victim|was killed|were killed|murder of (a |an )?(\d|child|infant|baby|toddler|girl|boy)", re.I)

PHYS = re.compile(r"\b(white|black|hispanic|latino|latina|latinx|asian|caucasian|african|race|racial|ethnic\w*|complexion|skin|hair|bald|eyes?|"
    r"tattoo\w*|scars?|pierc\w*|birthmark|mole|weigh\w*|pounds|lbs|height|feet tall|\d'\d|build|freckle\w*|beard|mustache|"
    r"moustache|glasses|teeth|tooth|accent|native american|american indian|alaska native|indigenous|skinned|light-skinned|dark-skinned|"
    r"tribe|tribal|enrolled member|male|female|wearing|wore|dressed|clothing|shirt|pants|jeans|jacket|shoes|sneakers|hoodie|cap)\b", re.I)
NOISE = re.compile(r"anyone with information|contact (the|your)|tips\.fbi\.gov|1-800|call\b|submit a tip|nearest american embassy|"
    r"local fbi office|reward|rewards for justice|@fbi\.gov|https?://|\bvisit\b|phone|tip line|whatsapp|signal|telegram", re.I)

# words that would name the category outright -> redacted in the pre-reveal excerpt
CAT_WORDS = [r"wanted", r"missing", r"disappear\w*", r"vanish\w*", r"last seen", r"abduct\w*", r"kidnap\w*", r"custod\w*", r"parental",
 r"fugitive\w*", r"fle(e|d|eing)", r"flight", r"arrest\w*", r"warrants?", r"charg\w*", r"indict\w*", r"alleg\w*", r"accused", r"convict\w*",
 r"prosecut\w*", r"suspect\w*", r"victims?", r"murder\w*", r"kill\w*", r"homicid\w*", r"shot", r"shoot\w*", r"guns?", r"firearms?", r"armed",
 r"robb\w*", r"bank\w*", r"fraud\w*", r"defraud\w*", r"schemes?", r"launder\w*", r"money", r"wire", r"embezzl\w*", r"ponzi", r"investors?",
 r"hack\w*", r"cyber\w*", r"computers?", r"intrusion\w*", r"ransomware", r"malware", r"botnet\w*", r"crypto\w*", r"bitcoin", r"online", r"internet",
 r"networks?", r"terror\w*", r"bomb\w*", r"explosi\w*", r"hijack\w*", r"aircraft piracy", r"jihad\w*", r"al[- ]qa'?ida", r"isis", r"hizballah",
 r"hezbollah", r"espionage", r"spy\w*", r"spies", r"intelligence", r"sanction\w*", r"export\w*", r"emergency economic powers act", r"ieepa",
 r"drugs?", r"narcotic\w*", r"cocaine", r"crack", r"heroin", r"methamphetamine", r"fentanyl", r"marijuana", r"oxycodone", r"cartels?", r"gangs?",
 r"enterprise", r"racketeer\w*", r"traffick\w*", r"conspir\w*", r"unlawful\w*", r"crimes?", r"criminal\w*", r"felon\w*", r"assault\w*",
 r"violen\w*", r"arson", r"escap\w*", r"prison\w*", r"top ten", r"ten most", r"seeking information", r"identity theft", r"theft", r"steal\w*", r"stolen",
 r"abus\w*", r"endanger\w*", r"foul play", r"hostages?", r"ransom", r"extort\w*", r"smuggl\w*", r"weapons?", r"stalk\w*", r"harass\w*",
 r"investigat\w*", r"fbi", r"police", r"law enforcement", r"sheriff\w*", r"detectives?", r"court", r"district", r"federal", r"prosecutor\w*",
 r"identif\w*", r"unknown", r"locate\w*", r"location", r"whereabouts", r"search\w*", r"reported", r"sightings?", r"heard from", r"contact\w*",
 r"responsible", r"incident", r"seek\w*", r"sought", r"public['’]s assistance", r"assistance", r"asking", r"field office", r"regime", r"military", r"government", r"officials?", r"agents?", r"intelligence service", r"secret",
 r"sexual", r"child(ren)?", r"daughter\w*", r"sons?", r"mother", r"father", r"parents?", r"ex-wife", r"ex-husband", r"wife", r"husband", r"girlfriend",
 r"boyfriend", r"custody", r"mass", r"attack\w*", r"plot\w*"]
CAT_RE = re.compile(r"\b(" + "|".join(CAT_WORDS) + r")\b", re.I)
BLK = '▇▇'

OFFICE = {'albany':('Albany','奧本尼'),'albuquerque':('Albuquerque','阿布奎基'),'anchorage':('Anchorage','安克拉治'),'atlanta':('Atlanta','亞特蘭大'),
 'baltimore':('Baltimore','巴爾的摩'),'billings':('Billings','比林斯'),'birmingham':('Birmingham','伯明罕'),'boston':('Boston','波士頓'),
 'buffalo':('Buffalo','水牛城'),'charlotte':('Charlotte','夏洛特'),'chicago':('Chicago','芝加哥'),'cincinnati':('Cincinnati','辛辛那提'),
 'cleveland':('Cleveland','克里夫蘭'),'columbia':('Columbia, SC','哥倫比亞（南卡）'),'dallas':('Dallas','達拉斯'),'denver':('Denver','丹佛'),
 'detroit':('Detroit','底特律'),'elpaso':('El Paso','艾爾帕索'),'honolulu':('Honolulu','檀香山'),'houston':('Houston','休士頓'),
 'indianapolis':('Indianapolis','印第安納波利斯'),'jackson':('Jackson','傑克森'),'jacksonville':('Jacksonville','傑克森維爾'),
 'kansascity':('Kansas City','堪薩斯城'),'knoxville':('Knoxville','諾克斯維爾'),'lasvegas':('Las Vegas','拉斯維加斯'),'littlerock':('Little Rock','小岩城'),
 'losangeles':('Los Angeles','洛杉磯'),'louisville':('Louisville','路易維爾'),'memphis':('Memphis','曼菲斯'),'miami':('Miami','邁阿密'),
 'milwaukee':('Milwaukee','密爾瓦基'),'minneapolis':('Minneapolis','明尼亞波利斯'),'mobile':('Mobile','莫比爾'),'newhaven':('New Haven','紐哈芬'),
 'neworleans':('New Orleans','紐奧良'),'newyork':('New York','紐約'),'newark':('Newark','紐華克'),'norfolk':('Norfolk','諾福克'),
 'oklahomacity':('Oklahoma City','奧克拉荷馬市'),'omaha':('Omaha','奧馬哈'),'philadelphia':('Philadelphia','費城'),'phoenix':('Phoenix','鳳凰城'),
 'pittsburgh':('Pittsburgh','匹茲堡'),'portland':('Portland','波特蘭'),'richmond':('Richmond','里奇蒙'),'sacramento':('Sacramento','沙加緬度'),
 'saltlakecity':('Salt Lake City','鹽湖城'),'sanantonio':('San Antonio','聖安東尼奧'),'sandiego':('San Diego','聖地牙哥'),
 'sanfrancisco':('San Francisco','舊金山'),'sanjuan':('San Juan','聖胡安'),'seattle':('Seattle','西雅圖'),'springfield':('Springfield','春田'),
 'stlouis':('St. Louis','聖路易'),'tampa':('Tampa','坦帕'),'washingtondc':('Washington, D.C.','華盛頓特區')}
STATES = {'Alabama':'阿拉巴馬州','Alaska':'阿拉斯加州','Arizona':'亞利桑那州','Arkansas':'阿肯色州','California':'加州','Colorado':'科羅拉多州',
 'Connecticut':'康乃狄克州','Delaware':'德拉瓦州','Florida':'佛羅里達州','Georgia':'喬治亞州','Hawaii':'夏威夷州','Idaho':'愛達荷州',
 'Illinois':'伊利諾州','Indiana':'印第安納州','Iowa':'愛荷華州','Kansas':'堪薩斯州','Kentucky':'肯塔基州','Louisiana':'路易斯安那州',
 'Maine':'緬因州','Maryland':'馬里蘭州','Massachusetts':'麻州','Michigan':'密西根州','Minnesota':'明尼蘇達州','Mississippi':'密西西比州',
 'Missouri':'密蘇里州','Montana':'蒙大拿州','Nebraska':'內布拉斯加州','Nevada':'內華達州','New Hampshire':'新罕布夏州','New Jersey':'紐澤西州',
 'New Mexico':'新墨西哥州','New York':'紐約州','North Carolina':'北卡羅來納州','North Dakota':'北達科他州','Ohio':'俄亥俄州','Oklahoma':'奧克拉荷馬州',
 'Oregon':'奧勒岡州','Pennsylvania':'賓州','Rhode Island':'羅德島州','South Carolina':'南卡羅來納州','South Dakota':'南達科他州',
 'Tennessee':'田納西州','Texas':'德州','Utah':'猶他州','Vermont':'佛蒙特州','Virginia':'維吉尼亞州','Washington':'華盛頓州',
 'West Virginia':'西維吉尼亞州','Wisconsin':'威斯康辛州','Wyoming':'懷俄明州','Puerto Rico':'波多黎各','Mexico':'墨西哥','Canada':'加拿大',
 'Italy':'義大利','Syria':'敘利亞','Iraq':'伊拉克','Afghanistan':'阿富汗','Yemen':'葉門','Northern Mariana Islands':'北馬里亞納群島',
 'District of Columbia':'哥倫比亞特區','Guam':'關島','Iran':'伊朗','China':'中國','Russia':'俄羅斯','Colombia':'哥倫比亞','India':'印度'}
LANG = {'English':'英語','Spanish':'西班牙語','Arabic':'阿拉伯語','Farsi':'波斯語','Persian (Farsi)':'波斯語','Persian':'波斯語',
 'Chinese':'中文','Mandarin':'華語','Mandarin Chinese':'華語','Cantonese':'粵語','Korean':'韓語','Russian':'俄語','German':'德語',
 'French':'法語','Tagalog':'他加祿語','Swedish':'瑞典語','Punjabi':'旁遮普語','Haitian Creole':'海地克里奧爾語','Portuguese':'葡萄牙語',
 'Turkish':'土耳其語','Somali':'索馬利語','Pashto':'普什圖語','Hindi':'印地語','Vietnamese':'越南語','Italian':'義大利語',
 'Serbo-Croatian':'塞爾維亞－克羅埃西亞語','Kurdish':'庫德語','Bulgarian':'保加利亞語','Dari':'達利語','Urdu':'烏爾都語',
 'Ukrainian':'烏克蘭語','Azeri':'亞塞拜然語','Navajo':'納瓦荷語','Japanese':'日語','Hebrew':'希伯來語','Greek':'希臘語','Polish':'波蘭語',
 'Thai':'泰語','Uzbek':'烏茲別克語','Bengali':'孟加拉語','Gujarati':'古吉拉特語','Romanian':'羅馬尼亞語','Hungarian':'匈牙利語'}

REQ = {'api': 0, 'img': 0}
MAX_API = 60
MAX_IMG = int(os.environ.get('LA_MAX_IMG', '400'))   # hard caps per refresh

def get(url, tries=4, kind='api'):
    for k in range(tries):
        if REQ[kind] >= (MAX_API if kind == 'api' else MAX_IMG): return None, ''
        REQ[kind] += 1
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read(), r.headers.get('Content-Type', '')
        except Exception as e:
            print('retry', url, e, file=sys.stderr); time.sleep(5 * 2 ** k)
    return None, ''

def text(h):
    if not h: return ''
    h = re.sub(r'<br\s*/?>|</p>|</li>|</div>', '\n', h, flags=re.I)
    h = re.sub(r'<[^>]+>', '', h)
    h = html.unescape(h).replace('\xa0', ' ')
    h = re.sub(r'[ \t]+', ' ', h)
    return '\n'.join(l.strip() for l in h.split('\n') if l.strip())

SENT = re.compile(r'(?<=[.!?])\s+(?=[A-Z"“(])')
ABBR = re.compile(r'\b(Mr|Mrs|Ms|Dr|Jr|Sr|St|U\.S|a\.m|p\.m|No|Co|Inc|Ft|Mt|Lt|Sgt|approx)\.$', re.I)
def sentences(t):
    out = []
    for para in t.split('\n'):
        parts = SENT.split(para)
        buf = ''
        for p in parts:
            buf = (buf + ' ' + p).strip() if buf else p
            if ABBR.search(buf) or re.search(r'\b[A-Z]\.$', buf): continue
            out.append(buf); buf = ''
        if buf: out.append(buf)
    return out

def clean_for_reveal(t):
    """FBI wording, minus sentences about race/appearance and contact boilerplate."""
    keep = [s for s in sentences(t) if not PHYS.search(s) and not NOISE.search(s)]
    return keep

def names_of(it):
    toks = set()
    for n in [it.get('title') or ''] + (it.get('aliases') or []):
        n = re.split(r' - |—|–', n)[0]
        for w in re.findall(r"[A-Za-z][A-Za-z'’.\-]+", n):
            if len(w) > 1 and w.lower() not in {'and', 'aka', 'the', 'jr.', 'sr.', 'jr', 'sr', 'iii', 'ii', 'family', 'unknown', 'individual', 'individuals'}:
                toks.add(w.strip('.').lower())
    return toks

def redact(s, names):
    s = CAT_RE.sub(BLK, s)
    def nm(m):
        w = m.group(0); base = re.sub(r"['’]s$", '', w).strip('.').lower()
        return BLK if base in names else w
    s = re.sub(r"[A-Za-z][A-Za-z'’.\-]*[A-Za-z]", nm, s)
    PREP = r"(?=\s*(?:$|[.,;:)]|\s(?:to|in|on|at|from|with|by|for|of|and|or|as|after|before|since|was|is|were|had|has|into|until|during|while|when|that)\b))"
    s = re.sub(r'\bher\b' + PREP, 'them', s); s = re.sub(r'\bHer\b' + PREP, 'Them', s)
    MAP = {'he':'they','she':'they','him':'them','her':'their','his':'their','hers':'theirs','himself':'themself','herself':'themself'}
    s = re.sub(r'\b(he|she|him|her|his|hers|himself|herself)\b', lambda m: MAP[m.group(0).lower()] if m.group(0).islower() else MAP[m.group(0).lower()].capitalize(), s, flags=re.I)
    s = re.sub(r'\b([Tt]hey) was\b', r'\1 were', s); s = re.sub(r'\b([Tt]hey) is\b', r'\1 are', s); s = re.sub(r'\b([Tt]hey) has\b', r'\1 have', s)
    s = re.sub(r'\b([Tt]hey) does\b', r'\1 do', s)
    s = re.sub(r'(▇▇)([\s,\'’s\-]*▇▇)+', BLK, s)
    return s

def excerpt(sents, names):
    best = None
    for s in sents[:6]:
        r = redact(s, names)
        r = re.sub(r'^▇▇,?\s+(is|are)\s+(an?\s+)?▇▇\s+(for questioning\s+)?(for|in connection with|by the ▇▇ for)\s+(their\s+)?(▇▇\s+)?(involvement|role|roles|participation|part)\s+(in|with)\s+', 'Case: ', r)
        r = re.sub(r'^▇▇,?\s+(is|are)\s+(an?\s+)?▇▇\s+(for questioning\s+)?(in connection with|for)\s+', 'Case: ', r)
        words = re.findall(r"[A-Za-z0-9]+", r)
        blanks = r.count(BLK)
        if len(words) >= 7 and blanks <= max(3, len(words) // 3):
            best = r; break
    if not best: return ''
    if len(best) > 230:
        cut = best[:230].rsplit(' ', 1)[0].rstrip(',;:')
        best = cut + ' …'
    return best

YEAR = re.compile(r'\b(19[2-9]\d|20[0-3]\d)\b')
def event_year(it, main):
    for src in (it.get('description') or '', main):
        m = YEAR.search(src)
        if m: return int(m.group(1))
    p = it.get('publication') or ''
    return int(p[:4]) if p[:4].isdigit() else None

def birth_year(it):
    for d in it.get('dates_of_birth_used') or []:
        m = YEAR.search(d or '') or re.search(r'\b(19\d\d|20\d\d)\b', d or '')
        if m: return int(m.group(1))
    return None

MONEY = re.compile(r'\$\s?([\d,.]+)\s*(million|billion)?', re.I)
def reward_amt(it):
    v = it.get('reward_max') or 0
    best = v if v and v > 0 else 0
    for m in MONEY.finditer(it.get('reward_text') or ''):
        try:
            n = float(m.group(1).replace(',', ''))
        except ValueError: continue
        if m.group(2): n *= 1e6 if m.group(2).lower() == 'million' else 1e9
        best = max(best, n)
    return int(best)

def place_of(it):
    d = text(it.get('description') or '')
    lines = [l for l in d.split('\n') if l and not YEAR.search(l) and not re.match(r'^(unknown|january|february|march|april|may|june|july|august|september|october|november|december)\b', l, re.I)]
    for l in lines:
        if ',' in l and len(l) < 70: return l
    return lines[0] if lines and len(lines[0]) < 50 else ''

def zh_place(p):
    parts = [x.strip() for x in p.split(',')]
    return '，'.join(STATES.get(x, x) for x in parts)

def bucket_of(it):
    subj = it.get('subjects') or []
    if any(s in EXCLUDE_SUBJ for s in subj): return None, []
    bs = {BUCKET[s] for s in subj if s in BUCKET}
    for pc in set(it.get('_pcs') or []) | {it.get('poster_classification')}:
        if pc == 'ten': bs.add('topten')
        if pc == 'terrorist': bs.add('terror')
        if pc == 'fraudster': bs.add('money')
        if pc == 'missing': bs.add('missing')
    if not bs: return None, []
    for p in PRIORITY:
        if p in bs: return p, sorted(bs)
    return None, []

def norm_key(it):
    t = re.split(r' - |—|–', (it.get('title') or '').upper())[0]
    t = re.sub(r'[^A-Z ]', '', t).strip()
    dob = ((it.get('dates_of_birth_used') or [''])[0] or '')
    return t + '|' + dob

def dedupe(items):
    groups = {}
    for it in items: groups.setdefault(norm_key(it), []).append(it)
    out = []
    for g in groups.values():
        if len(g) == 1: out.append(g[0]); continue
        g.sort(key=lambda x: (bool(x.get('reward_text')), len(x.get('caution') or x.get('details') or ''), len(x.get('images') or [])), reverse=True)
        base = dict(g[0]); subj = []
        for x in g:
            for sb in x.get('subjects') or []:
                if sb not in subj: subj.append(sb)
        base['subjects'] = subj
        pcs = {x.get('poster_classification') for x in g}
        base['_pcs'] = sorted(p for p in pcs if p)
        if any((x.get('status') or 'na') != 'na' for x in g): base['status'] = 'captured'
        out.append(base)
    return out

def build(items):
    items = dedupe(items)
    cases = []; skipped = {}
    def skip(r): skipped[r] = skipped.get(r, 0) + 1
    for it in items:
        if (it.get('status') or 'na') != 'na': skip('status'); continue
        b, allb = bucket_of(it)
        if not b: skip('category'); continue
        if EXCLUDE_PATH.search(it.get('url') or ''): skip('path'); continue
        imgs = [i for i in (it.get('images') or []) if i.get('large') or i.get('original')]
        if not imgs: skip('noimage'); continue
        main = text(it.get('caution')) or text(it.get('details'))
        alltext = ' '.join([it.get('title') or '', text(it.get('description')), text(it.get('caution')), text(it.get('details')),
                            text(it.get('remarks')), text(it.get('additional_information'))])
        if GRAPHIC.search(alltext): skip('graphic'); continue
        if b in ('missing', 'seeking') and DEATH.search(alltext): skip('death'); continue
        if b == 'seeking' and it.get('person_classification') == 'Victim': skip('seeking-victim'); continue
        names = names_of(it)
        sents = clean_for_reveal(main)
        ex = excerpt(sents, names)
        if not ex: skip('noexcerpt'); continue
        y = event_year(it, main); by = birth_year(it)
        age = None
        if it.get('age_min'): age = int(it['age_min'])
        elif by and y and y >= by: age = y - by
        if age is not None and (age < 0 or age > 100): age = None
        fo = (it.get('field_offices') or [None])[0]
        office = OFFICE.get(fo, (fo.title(), fo.title())) if fo else None
        pl = place_of(it) if b in ('missing', 'seeking') or not office else ''
        if pl and CAT_RE.search(pl): pl = ''
        langs = []
        for l in it.get('languages') or []:
            for x in re.split(r'[;,]| and ', l):
                x = x.strip()
                if x in LANG: langs.append(x)
        occ = [o for o in (it.get('occupations') or []) if o and len(o) < 40 and not CAT_RE.search(o)][:2]
        rev_main = sents
        remarks = [s for s in clean_for_reveal(text(it.get('remarks')))]
        c = {
            'id': it['uid'], 'c': b, 'all': allb, 'url': it.get('url'),
            'img': (imgs[0].get('large') or imgs[0].get('original')),
            'img2': imgs[0].get('original'),
            'title': (it.get('title') or '').strip(),
            'k': {  # pre-reveal clues
                'y': y, 'age': age, 'rw': reward_amt(it),
                'of': office[0] if office else None, 'ofz': office[1] if office else None,
                'pl': pl or None, 'plz': zh_place(pl) if pl else None,
                'lg': langs[:3] or None, 'lgz': [LANG[x] for x in langs[:3]] or None,
                'oc': occ or None, 'ex': ex,
            },
            'r': {  # reveal: FBI wording
                'd': text(it.get('description')).replace('\n', ' · ') if b not in ('missing',) else text(it.get('description')).replace('\n', ' · '),
                't': rev_main[:14], 'rm': remarks[:4],
                'rw': (it.get('reward_text') or '').strip() or None,
                'w': (it.get('warning_message') or '').strip() or None,
                'sex': it.get('sex') or None,
                'cap': (imgs[0].get('caption') or '').strip() or None,
            },
        }
        cases.append(c)
    return cases, skipped

def cache_images(cases, prev_ids):
    """Download + shrink portraits for NEW cases only; delete images of pruned cases."""
    from PIL import Image
    import io
    os.makedirs(IMG, exist_ok=True)
    keep = set()
    for c in cases:
        fn = c['id'] + '.webp'; p = os.path.join(IMG, fn)
        if os.path.exists(p) and os.path.getsize(p) > 400:
            c['im'] = 'img/' + fn; keep.add(fn); continue
        if REQ['img'] >= MAX_IMG: continue   # rest next day
        data, ct = get(c['img'], tries=2, kind='img')
        time.sleep(1.0)
        if not (data and ct.startswith('image/')) and c.get('img2') and c['img2'] != c['img']:
            data, ct = get(c['img2'], tries=1, kind='img'); time.sleep(1.0)
        if not (data and ct.startswith('image/')): continue
        try:
            im = Image.open(io.BytesIO(data)); im = im.convert('RGB')
            im.thumbnail((300, 380))
            im.save(p, 'WEBP', quality=72, method=6)
            c['im'] = 'img/' + fn; keep.add(fn)
        except Exception as e:
            print('img fail', c['id'], e, file=sys.stderr)
    for f in os.listdir(IMG):
        if f not in keep:
            os.remove(os.path.join(IMG, f))
    for c in cases: c.pop('img', None); c.pop('img2', None)   # clients never touch fbi.gov images

def main():
    items = []; page = 1; total = None
    while True:
        raw, _ = get(API % page)
        if raw is None: break
        try: d = json.loads(raw)
        except ValueError: break
        total = d.get('total'); got = d.get('items') or []
        items += got
        if not got or len(items) >= (total or 0): break
        page += 1; time.sleep(1.2)
    if total is None or len(items) < 0.9 * total or len(items) < 300:
        print('API read incomplete (%s of %s); keeping previous cases.json' % (len(items), total)); return 0
    cases, skipped = build(items)
    if len(cases) < 150:
        print('Too few cases after filtering (%d); keeping previous file' % len(cases)); return 0
    print('requests so far: api=%d' % REQ['api'])
    if '--no-images' not in sys.argv:
        cache_images(cases, None); cases = [c for c in cases if c.get('im')]
    mix = {}
    for c in cases: mix[c['c']] = mix.get(c['c'], 0) + 1
    out = {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'total': total,
           'n': len(cases), 'mix': mix, 'cases': cases}
    s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    old = open(OUT).read() if os.path.exists(OUT) else ''
    if old:
        try:
            o = json.loads(old); o['updated'] = out['updated']
            if json.dumps(o, ensure_ascii=False, separators=(',', ':')) == s:
                print('no change; requests api=%d img=%d' % (REQ['api'], REQ['img'])); return 0
        except ValueError: pass
    open(OUT, 'w').write(s)
    print('cases', len(cases), 'mix', mix, 'skipped', skipped)
    print('requests this refresh: api=%d img=%d' % (REQ['api'], REQ['img']))
    return 0

if __name__ == '__main__':
    if '--from' in sys.argv:
        items = json.load(open(sys.argv[sys.argv.index('--from') + 1]))
        cases, skipped = build(items)
        mix = {}
        for c in cases: mix[c['c']] = mix.get(c['c'], 0) + 1
        print(len(cases), mix, skipped)
        if '--write' in sys.argv:
            if '--no-images' not in sys.argv:
                cache_images(cases, None); cases = [c for c in cases if c.get('im')]
                mix = {}
                for c in cases: mix[c['c']] = mix.get(c['c'], 0) + 1
            print('requests: img=%d' % REQ['img'])
            json.dump({'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'total': len(items), 'n': len(cases), 'mix': mix, 'cases': cases},
                      open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
        sys.exit(0)
    sys.exit(main())
