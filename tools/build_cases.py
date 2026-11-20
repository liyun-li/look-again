#!/usr/bin/env python3
"""Refresh cases.json from the public FBI Wanted API (https://api.fbi.gov/wanted/v1/list).
Plus the DEA / Secret Service / U.S. Marshals lists saved by tools/agencies.cjs (agencies.json). Needs Pillow.
Keeps the previous cases.json if the API can't be read.
Rules: no race/ethnicity/physical-description text, no sex before reveal, no gore, no child-exploitation
or unidentified-remains or homicide/sexual-assault ViCAP files, no deceased-victim cases, no crimes against children.
Case text is the agency's own wording (sentences may be dropped, never rewritten)."""
import json, re, os, sys, time, html, urllib.request, urllib.error, urllib.parse, hashlib, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cats  # answer categories from the FBI's own lists (see cats.py)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'cases.json')
CLUES = os.path.join(ROOT, 'clues.json')
CLUES2 = os.path.join(ROOT, 'clues2.json')  # 2-clue format {uid: {en:[c1,c2], zh:[c1,c2], meta?}} (preferred when present)   # hand-written clue ladders {uid: {"en": [...], "zh": [...]}}
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

PHYS = re.compile(r"\b(white|black(?! Hills)|hispanic|latino|latina|latinx|asian|caucasian|african|(?<!presidential )race|racial|ethnic\w*|complexion|skin|hair|bald|eyes?|"
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


# ---- clue ladder: short lines, vague -> specific ----
MAX_CLUES = 5
ZH_BAD = re.compile(r'(?<![其利猶吉科])他(?![人國處方者們])|男孩|女孩|兒子|女兒|丈夫|妻子|父親|母親|她|男子|女子|男性|女性|男人|女人|先生|女士|白人|黑人|亞裔|非裔|拉丁裔|西語裔|膚|(?<!理)髮|鬍|刺青|紋身|身高|體重|眼睛|族裔|種族(?!隔離)|原住民')
EN_PRON = re.compile(r"\b(?!Mother of Christ)(he|she|him|her|his|hers|himself|herself|man|woman|men|women|boy|girl|sons?|daughters?|wife|wives|husbands?|mothers?|fathers?|brothers?|sisters?|boys|girls|aunt|uncle|niece|nephew|girlfriend|boyfriend|gentleman|lady)\b", re.I)
EN_TITLE = re.compile(r"\b(Mr|Mrs|Ms|Miss)\b\.?(?!-)")
def _load_hand():
    try: return json.load(open(CLUES))
    except Exception: return {}
HAND = None
NAME_SKIP = {'first', 'last', 'middle', 'name', 'names', 'unknown', 'aka', 'known', 'also'}
def _bad_en(e, names):
    if PHYS.search(e) or EN_PRON.search(e) or EN_TITLE.search(e) or len(e) > 110: return True
    return any(w.strip(".,'’").lower() in names for w in re.findall(r"[A-Za-z][A-Za-z'’.\-]+", e) if len(w) > 2)
def hand_clues(c, names):
    """Hand ladder, minus any line pair (EN+ZH) that fails the safety checks; needs 3+ surviving lines."""
    global HAND
    if HAND is None: HAND = _load_hand()
    h = HAND.get(c['id'])
    if not h: return None
    en = [str(x).strip() for x in (h.get('en') or []) if str(x).strip()]
    zh = [str(x).strip() for x in (h.get('zh') or []) if str(x).strip()]
    names = set() if c.get('c') == 'seeking' else {n for n in names if n not in NAME_SKIP}
    keep = [(e, z) for e, z in zip(en, zh) if not _bad_en(e, names) and not ZH_BAD.search(z) and len(z) <= 60]
    if len(keep) < min(3, len(en)) or len(keep) < 2: return None
    keep = keep[:MAX_CLUES]
    return {'en': [e for e, _ in keep], 'zh': [z for _, z in keep]}

def _money_en(n): return '$%s million' % ('%g' % round(n / 1e6, 1)) if n >= 1e6 else '$' + format(n, ',')
def _money_zh(n):
    w = n / 1e4
    if w >= 1e4: return '%g 億美元' % round(w / 1e4, 1)
    if w >= 1: return '%g 萬美元' % round(w, 1)
    return '%s 美元' % format(n, ',')

def fallback_clues(k):
    """Deterministic ladder from the pre-reveal fields (already free of names, race, sex, appearance)."""
    en, zh = [], []
    if k.get('y'): en.append('The file goes back to %d.' % k['y']); zh.append('檔案可追溯到 %d 年。' % k['y'])
    if k.get('age') is not None: en.append('They were about %d at the time.' % k['age']); zh.append('當時大約 %d 歲。' % k['age'])
    if k.get('lg'): en.append('Speaks %s.' % ', '.join(k['lg'])); zh.append('會說%s。' % '、'.join(k['lgz']))
    where = k.get('pl') or k.get('of'); wz = k.get('plz') or k.get('ofz')
    if where: en.append('Where: %s.' % where); zh.append('地點：%s。' % wz)
    if k.get('oc'): en.append('Work: %s.' % ', '.join(k['oc'])); zh.append('職業（英文原文）：%s。' % ', '.join(k['oc']))
    en.append('Reward: %s.' % _money_en(k['rw']) if k.get('rw') else 'No reward listed.'); zh.append('懸賞：%s。' % _money_zh(k['rw']) if k.get('rw') else '沒有列出懸賞。')
    # keep the four vaguest, then the redacted file line as the most specific clue
    en, zh = en[:MAX_CLUES - 1], zh[:MAX_CLUES - 1]
    ex = (k.get('ex') or '').replace('Case: ', '')
    if len(ex) > 150: ex = ex[:150].rsplit(' ', 1)[0].rstrip(',;:') + ' …'
    if ex: en.append('“%s”' % ex); zh.append('〔英文原文〕“%s”' % ex)
    return {'en': en, 'zh': zh}

# ---- 2-clue format: clue 1 shown at once, clue 2 is the single optional hint. Era/office/reward go to a meta line. ----
META_EN = re.compile(r'^(A case from the|The case dates|No reward amount|Reward offered|Key year on the poster|Listed age about)')
HAND2 = None
def _load_hand2():
    try:
        d = json.load(open(CLUES2))
        d = d.get('cases', d) if isinstance(d, dict) else {}
        return {u: v for u, v in d.items() if isinstance(v, dict) and isinstance(v.get('en'), list)}
    except Exception: return {}

def _ok_pair(e, z, names):
    e, z = str(e).strip(), str(z).strip()
    return bool(e and z) and not _bad_en(e, names) and not ZH_BAD.search(z) and len(z) <= 60 and not re.search(r'9{2},?9{3}', e + z)

def meta_line(k, m=None):
    # m = clues2.json meta; its reward is parsed from the poster's reward text (never the 99999 placeholders)
    if isinstance(m, dict) and 'reward' in m:
        k = dict(k, rw=m['reward'] if isinstance(m['reward'], (int, float)) and m['reward'] > 0 else 0)
    en, zh = [], []
    if k.get('y'): d = k['y'] // 10 * 10; en.append('%ds' % d); zh.append('%d 年代' % d)
    if k.get('of'): en.append('FBI %s' % k['of']); zh.append('FBI %s分局' % k['ofz'])
    elif k.get('pl'): en.append(k['pl']); zh.append(k.get('plz') or k['pl'])
    en.append('Reward up to %s' % _money_en(k['rw']) if k.get('rw') else 'No reward listed')
    zh.append('懸賞最高 %s' % _money_zh(k['rw']) if k.get('rw') else '未列懸賞')
    return {'en': ' · '.join(en), 'zh': ' · '.join(zh)}

def two_clues(c, names):
    """Returns (cl, source). '2' = clues2.json, 'l' = two most specific lines of the old ladder, 'f' = field fallback."""
    global HAND, HAND2
    if HAND2 is None: HAND2 = _load_hand2()
    if HAND is None: HAND = _load_hand()
    names = set() if c.get('c') == 'seeking' else {n for n in names if n not in NAME_SKIP}
    h = HAND2.get(c['id'])
    if h:
        pairs = list(zip(h.get('en') or [], h.get('zh') or []))[:2]
        if len(pairs) == 2 and all(_ok_pair(e, z, names) for e, z in pairs):
            return {'en': [str(e).strip() for e, _ in pairs], 'zh': [str(z).strip() for _, z in pairs]}, '2'
    keep = []
    h = HAND.get(c['id'])
    if h:
        keep = [(str(e).strip(), str(z).strip()) for e, z in zip(h.get('en') or [], h.get('zh') or [])
                if not META_EN.search(str(e).strip()) and _ok_pair(e, z, names)][-2:]
    src = 'l'
    if len(keep) < 2:   # add a hint line: languages, work, the redacted FBI excerpt, or the key year / age line
        src = 'l' if keep else 'f'
        f = fallback_clues(c['k'])
        def _w(t): return {w for w in re.findall(r'[a-z]{4,}', t.lower())}
        def _people(e): return re.search(r"\b[A-Z]{2,} [A-Z][a-z]+|\b[A-Z][a-z]+(?:ovich|evich|ovna|yevich)\b|(?:\b[A-Z][a-z]+ [A-Z][a-z]+, ){2,}", e)
        pad = [(e, z) for e, z in zip(f['en'], f['zh']) if re.match(r'(Speaks|Work:)', e)]
        pad += [(e, z) for e, z in zip(f['en'], f['zh']) if e.startswith('“') and '▇▇' in e and not _people(e)]
        if h: pad += [(e, z) for e, z in zip(h.get('en') or [], h.get('zh') or []) if str(e).startswith(('Key year', 'Listed age'))]
        pad = [(str(e).strip(), str(z).strip()) for e, z in pad if _ok_pair(e, z, names)]
        while len(keep) < 2 and pad:
            e, z = pad.pop(0); W = _w(e)
            if keep and W and len(W & _w(keep[0][0])) * 2 >= len(W): continue   # says the same thing as the clue we have
            keep.append((e, z))
        if not keep: return {'en': f['en'][-2:], 'zh': f['zh'][-2:]}, 'f'
    return {'en': [e for e, _ in keep], 'zh': [z for _, z in keep]}, src

def add_clues(c, names=None):
    names = names if names is not None else set()
    c['k']['cl'], c['k']['cs'] = two_clues(c, names)
    if HAND2 is None: _h2 = _load_hand2()
    else: _h2 = HAND2
    c['k']['mt'] = meta_line(c['k'], (_h2.get(c['id']) or {}).get('meta'))

# ONE switch for missing-person cases (FBI "Kidnappings and Missing Persons" / ViCAP missing). The game
# adapts automatically (daily mix, options, end-screen stats). Env LA_INCLUDE_MISSING=0 overrides for a test run.
INCLUDE_MISSING = os.environ.get('LA_INCLUDE_MISSING', '1') == '1'

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
            print('retry', url, e, file=sys.stderr)
            if getattr(e, 'code', 0) in (403, 404, 410, 500): return None, ''   # gone / blocked: don't hammer
            time.sleep(5 * 2 ** k)
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
    if v and re.fullmatch(r'9{4,}', str(int(v))): v = 0   # FBI placeholder (99999 / 999999), not an amount
    best = v if v and v > 0 else 0
    txt = 0
    for m in MONEY.finditer(it.get('reward_text') or ''):
        try:
            n = float(m.group(1).replace(',', ''))
        except ValueError: continue
        if m.group(2): n *= 1e6 if m.group(2).lower() == 'million' else 1e9
        txt = max(txt, n)
    if txt: best = txt   # the poster's own wording wins over the numeric field
    return int(best) if not re.fullmatch(r'9{4,}', str(int(best))) else 0

def place_of(it):
    d = text(it.get('description') or '')
    lines = [l for l in d.split('\n') if l and not YEAR.search(l) and not re.match(r'^(unknown|january|february|march|april|may|june|july|august|september|october|november|december)\b', l, re.I)]
    for l in lines:
        if ',' in l and len(l) < 70: return l
    return lines[0] if lines and len(lines[0]) < 50 else ''

def zh_place(p):
    parts = [x.strip() for x in p.split(',')]
    return '，'.join(STATES.get(x, x) for x in parts)

SUS_D = re.compile(r'^\s*unknown (suspect|individual|robbery suspect|bank robber|subject)s?(\(s\))?\b', re.I)
SUS_T = re.compile(r'\b(unknown (bank )?(robbery )?(suspect|robber|subject)s?|bank robber)\b', re.I)
VICTIM = re.compile(r'victim|deceased|death investigation|body located|missing|suspicious death|remains', re.I)
def is_unknown_suspect(it):
    """A 'Seeking Information' poster whose photos show the SUSPECT(S) (FBI's description line says 'Unknown Suspect(s)'
    or the title names an unknown suspect / robber) and never a victim poster."""
    if it.get('person_classification') == 'Victim': return False
    d = text(it.get('description')); first = (d.split('\n') or [''])[0]
    if VICTIM.search(first) or VICTIM.search(it.get('title') or ''): return False
    return bool(SUS_D.search(first) or SUS_T.search(it.get('title') or ''))

def sus_charge(it):
    """Unknown-suspect posters carry the crime in the title ('BANK ROBBERY - CLARKSVILLE, VIRGINIA')."""
    return re.split(r' - | — | – ', it.get('title') or '')[0]

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
        st = it.get('status') or 'na'
        if st not in ('na', 'captured', 'surrendered'): skip('status'); continue   # deceased / resolved: not a wanted face
        b, allb = bucket_of(it)
        if not b: skip('category'); continue
        sus = b == 'seeking' and is_unknown_suspect(it)   # 'Seeking Information' about an unknown SUSPECT (never a victim)
        if st != 'na' and b in ('missing', 'parental', 'seeking') and not sus: skip('status'); continue
        if b == 'missing' and not INCLUDE_MISSING: skip('missing-off'); continue
        if EXCLUDE_PATH.search(it.get('url') or ''): skip('path'); continue
        imgs = [i for i in (it.get('images') or []) if i.get('large') or i.get('original')]
        if not imgs: skip('noimage'); continue
        main = text(it.get('caution')) or text(it.get('details'))
        alltext = ' '.join([it.get('title') or '', text(it.get('description')), text(it.get('caution')), text(it.get('details')),
                            text(it.get('remarks')), text(it.get('additional_information'))])
        if GRAPHIC.search(alltext): skip('graphic'); continue
        if b in ('missing', 'seeking') and not sus and DEATH.search(alltext): skip('death'); continue
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
            'alt': [i.get('large') or i.get('original') for i in imgs[1:5]],   # rescue candidates if images[0] is a placeholder
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
        pcs = set(it.get('_pcs') or []) | {it.get('poster_classification')}
        g, ok, m, why = cats.assign(it.get('subjects'), pcs, sus_charge(it) if sus else text(it.get('description')),
                                    alltext + ' ' + (it.get('reward_text') or ''), main)
        c['sj'] = [s for s in (it.get('subjects') or []) if s] or None   # the FBI's own list names, verbatim
        if sus and g: c['sus'] = 1   # scored; c['c'] becomes the answer bucket after the clues are built
        elif b in ('missing', 'parental', 'seeking'): g, ok, why = None, [], 'never scored (%s)' % b
        if st != 'na': c['cap'] = st                                     # FBI API status: captured / surrendered
        c['g'] = g; c['ok'] = ok; c['m'] = m                             # shown answer, every right answer, every defensible match
        if why: c['gx'] = why
        add_clues(c, names)
        if c.get('sus') and ok == ['money'] and not re.search(r'fraud|scam|launder|embezzl|counterfeit', it.get('title') or '', re.I):
            c.pop('sus'); c['g'], c['ok'], c['gx'] = None, [], 'unknown suspect; no FBI crime category'   # e.g. vandalism
        if c.get('sus'): c['c'] = g; c['all'] = [g]
        cases.append(c)
    return cases, skipped

# ---- DEA / Secret Service / U.S. Marshals wanted lists (tools/agencies.cjs -> agencies.json + .agimg/) ----
AGF = os.path.join(ROOT, 'agencies.json'); AGRAW = os.path.join(ROOT, '.agimg')
AG = {'dea': ('DEA Fugitives', 'DEA fugitive', 'DEA 通緝犯'), 'usss': ('U.S. Secret Service Most Wanted', 'Secret Service Most Wanted', '美國特勤局頭號通緝'),
      'usms': ('U.S. Marshals 15 Most Wanted', 'U.S. Marshals 15 Most Wanted', '美國法警局 15 大通緝要犯')}
CHILD = re.compile(r"\b(child|children|minor|juvenile|girl|boy|underage|years? old)\b", re.I)
AG_STRICT = {
    'violent': re.compile(r'murder|homicid|\bkill|manslaughter|assault|robbery|kidnap|abduct|hostage|shoot|carjack|arson|crime of violence|violent', re.I),
    'gangs': re.compile(r'racketeer|(?<!puerto )\brico\b|criminal enterprise|criminal organization|organized crime|mafia|cartel|\bgangs?\b', re.I),
    'money': re.compile(r'fraud|launder|embezzl|ponzi|securities|bribe|kickback|tax evasion|counterfeit|identity theft|\bscams?\b', re.I),
    'cyber': re.compile(r'computer|hack|intrusion|malware|ransomware|botnet|cyber|phishing|unauthorized access|crypto|bitcoin|login credentials|online banking|digital currenc', re.I),
    'terror': re.compile(r'terroris|material support|hijack|aircraft piracy|\bbomb|explosive', re.I),
    'spy': re.compile(r'espionage|agents? of (a|the) foreign|foreign government|national defense information', re.I),
    'drugs': re.compile(r'\bdrugs?\b|narcotic|cocaine|heroin|methamphetamine|fentanyl|marijuana|controlled substance|intent to distribute', re.I)}

def agency_clues(k):
    """Two clues from what the agency poster states, vaguest first (clue 1 is shown at once, clue 2 is the paid hint):
    place / birth year / reward, then the redacted case text when there is one."""
    v_en, v_zh = [], []
    if k.get('pl'): v_en.append('Where: %s.' % k['pl']); v_zh.append('地點：%s。' % k['plz'])
    if k.get('yb'): v_en.append('Year of birth on the poster: %d.' % k['yb']); v_zh.append('通緝海報上的出生年：%d 年。' % k['yb'])
    if k.get('rw'): v_en.append('Reward: %s.' % _money_en(k['rw'])); v_zh.append('懸賞：%s。' % _money_zh(k['rw']))
    ex = (k.get('ex') or '')
    if len(ex) > 150: ex = ex[:150].rsplit(' ', 1)[0].rstrip(',;:') + ' …'
    en, zh = v_en[:1], v_zh[:1]
    if ex: en.append('“%s”' % ex); zh.append('〔英文原文〕“%s”' % ex)
    else: en += v_en[1:2]; zh += v_zh[1:2]
    if not en: en, zh = ['No reward listed.'], ['沒有列出懸賞。']
    return {'en': en[:2], 'zh': zh[:2]}

def add_agencies(cases):
    """Append the other agencies' fugitives. Child-sex cases are left out entirely; other graphic sentences are cut."""
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import cats
    try: d = json.load(open(AGF))
    except Exception: print('no agencies.json'); return cases, {}
    have = {c['id'] for c in cases}; out = []; sk = {}
    def skip(r): sk[r] = sk.get(r, 0) + 1
    allnames = set()   # co-defendants are on each other's pages: redact every listed name from every clue
    for it in d.get('items') or []: allnames |= names_of({'title': it.get('name') or ''})
    AGW = re.compile(r'Marshal|\bDEA\b|Drug Enforcement|Secret Service|USSS|USMS|If (the )?subject|If you have|contact the', re.I)
    raw = {f.split('.')[0]: f for f in (os.listdir(AGRAW) if os.path.isdir(AGRAW) else [])}
    for it in d.get('items') or []:
        if it['id'] in have: continue
        ch = (it.get('d') or '').strip(); story = [x for x in (it.get('t') or []) if x]
        if it['src'] == 'usms' and story:   # the Marshals' card line is the charge summary: "X is wanted (by ...) for A, B and C."
            card, story = story[0], story[1:]
            mm = re.search(r'\bwanted (?:by [^.]*? )?for (?:the )?(.+?)(?:\.|$)', card, re.I)
            ch = '; '.join(x.strip() for x in re.split(r',\s*(?:and\s+)?|\s+and\s+', mm.group(1)) if x.strip()) if mm else card
        if it['src'] == 'dea': ch = '; '.join(x.strip() for x in re.split(r'\.\s+|;\s*', ch.rstrip('. ')) if x.strip())
        alltext = ch + ' ' + ' '.join(story)
        if (GRAPHIC.search(alltext) and CHILD.search(alltext)) or re.search(r'child (sex|porn|exploit|molest)|sexual\w* (abuse|assault|exploit)\w* (of )?(a )?(child|minor)|'
                                                                            r'(to|of|against) (a|the) (child|minor)|\b([1-9]|1[0-7])[- ]year[- ]old', alltext, re.I):   # crimes against children: never in the game
            skip('child-sex'); continue
        rawtext = alltext
        story = [x for x in sentences(' '.join(story)) if not GRAPHIC.search(x) and not PHYS.search(x) and not re.search(r'NOTICE TO LAW ENFORCEMENT|\bNCIC\b|whereabouts known|presumed innocent', x, re.I)][:8]
        if GRAPHIC.search(ch): ch = '; '.join(x.strip() for x in re.split(r',|;| and ', re.sub(r'\.$', '', ch)) if x.strip() and not GRAPHIC.search(x)) or ''
        fn = it['id'] + '.webp'; p = os.path.join(IMG, fn)
        if not (os.path.exists(p) and os.path.getsize(p) > 400):
            r = raw.get(it['id'])
            if not r: skip('noimage'); continue
            try:
                im = Image.open(os.path.join(AGRAW, r)).convert('RGB'); im.thumbnail((300, 380)); im.save(p, 'WEBP', quality=72, method=6)
            except Exception: skip('badimage'); continue
        src = it['src']; lst, en, zh = AG[src]
        g, ok, m, why = cats.assign([lst] if src == 'dea' else [], set(), ch or ' '.join(story[:1]), rawtext, ' '.join(story))
        hits = cats.text_hits(ch)
        # other agencies have no FBI-style crime lists: a right answer needs the agency's own charge wording (strict words only)
        base = ch or ' '.join(story[:3])
        strict = {k for k, r in AG_STRICT.items() if r.search(base)} or {k for k, r in AG_STRICT.items() if r.search(' '.join(story))}
        if src != 'dea' and g:
            keep = [x for x in ok if x in strict] or [x for x in sorted(strict) if x in m] or ok
            if src == 'usss' and set(keep) & {'money', 'cyber'}: keep = [x for x in keep if x != 'terror']   # e.g. laundering FOR terror groups: still a financial case
            ok = sorted(keep); g = next(x for x in cats.PRIMARY if x in ok); m = sorted(set(m) | set(ok))
        if src == 'dea' and g: ok = sorted(set(ok) | (hits & {'money', 'cyber'}) | ({'terror'} if re.search(r'terror', ch, re.I) else set()) | ({'violent'} if re.search(r'murder|homicide|kidnap|\bkill', ch, re.I) else set())); m = sorted(set(m) | set(ok))   # e.g. drugs + money laundering; 'conspiracy' alone stays defensible, not right
        if src == 'usss' and g and not set(ok) & {'money', 'cyber'}: why = (why or '') + ' (Secret Service: no money/cyber wording)'
        names = allnames
        ex = excerpt([x for x in story if not AGW.search(x)], names) if story else ''
        if src == 'dea' and it.get('rw'): it = dict(it, rw=re.sub(r'(?i)^reward:\s*', '', it['rw']))
        c = {'id': it['id'], 'c': g or 'seeking', 'all': [g] if g else [], 'url': it['url'], 'title': it.get('name') or '',
             'src': src, 'ag': {'en': en, 'zh': zh}, 'im': 'img/' + fn,
             'k': {'y': None, 'age': None, 'rw': reward_amt({'reward_text': re.sub(r'(\d)\s*M\b', r'\1 million', it['rw']) if it.get('rw') else ''}), 'of': None, 'ofz': None, 'pl': None, 'plz': None, 'lg': None, 'lgz': None, 'oc': None, 'ex': ex or None},
             'r': {'d': ch or None, 't': story, 'rm': [], 'rw': it.get('rw'), 'w': None, 'sex': None, 'cap': None},
             'sj': [lst], 'g': g, 'ok': ok, 'm': m}
        if why: c['gx'] = why
        pl = it.get('pl') if it.get('pl') and not AGW.search(it['pl']) and not CAT_RE.search(it['pl']) else None
        plz = None
        if pl:   # DEA tags the federal court district: "California Central" -> "Central District of California"
            mm = re.match(r'^(.+?)\s+(Northern|Southern|Eastern|Western|Central|Middle)$', pl)
            if mm: plz = STATES.get(mm.group(1), mm.group(1)) + {'Northern': '北區', 'Southern': '南區', 'Eastern': '東區', 'Western': '西區', 'Central': '中區', 'Middle': '中區'}[mm.group(2)] + '（聯邦法院轄區）'; pl = '%s District of %s' % (mm.group(2), mm.group(1))
            else: plz = zh_place(pl)
        if pl: c['k']['pl'] = pl; c['k']['plz'] = plz
        if it.get('nt') and re.search(r'armed|dangerous|caution', it['nt'], re.I): c['r']['w'] = it['nt'].strip()
        if it.get('yb'): c['k']['yb'] = it['yb']
        c['k']['cl'], c['k']['cs'] = agency_clues(c['k']), 'a'
        c['k']['mt'] = meta_line(dict(c['k'], pl=None))   # the place is already clue 1
        if not g: skip('nocategory')
        out.append(c)
    live = {it['id'] for it in d.get('items') or []}
    for f in os.listdir(IMG):   # a fugitive the agency took down: drop the cached portrait too
        if f.startswith(('dea-', 'usss-', 'usms-')) and f.rsplit('.', 1)[0] not in live: os.remove(os.path.join(IMG, f))
    print('agencies', {s: sum(c['src'] == s for c in out) for s in AG}, 'scored', sum(1 for c in out if c['g']), 'skipped', sk)
    return cases + out, sk

RES_OK = {'captured', 'surrendered', 'located', 'recovered', 'resolved'}
def resolved(items):
    """uid -> status, only where the FBI API itself marks the case resolved (used by the casebook)."""
    return {it['uid']: it['status'] for it in items if it.get('uid') and (it.get('status') or 'na') in RES_OK}

def wayback_img(u):
    """The FBI's own portrait from the Internet Archive's copy (availability API -> exact snapshot, raw 'id_' bytes)."""
    for v in (u, re.sub(r'/large$', '/preview', u)):
        raw, _ = get('https://archive.org/wayback/available?url=' + urllib.parse.quote(v.split('://', 1)[-1], safe='/@'), tries=1, kind='img'); time.sleep(2)
        try: snap = json.loads(raw or b'{}').get('archived_snapshots', {}).get('closest') or {}
        except ValueError: snap = {}
        if snap.get('available') and snap.get('timestamp'):
            data, ct = get('https://web.archive.org/web/%sid_/%s' % (snap['timestamp'], v), tries=1, kind='img'); time.sleep(2)
            if data and ct.startswith('image/'): return data, ct
    return None, ''

def cache_images(cases, prev_ids):
    """Download + shrink portraits for NEW cases only; delete images of pruned cases."""
    from PIL import Image
    import io
    os.makedirs(IMG, exist_ok=True)
    keep = set()
    # portraits fbi.gov failed to serve: wait a week before asking again
    FAILF = os.path.join(os.path.dirname(IMG), 'img_failed.json')
    try: failed = json.load(open(FAILF))
    except Exception: failed = {}
    today = datetime.date.today()
    ids = {c['id'] for c in cases}
    failed = {k: v for k, v in failed.items() if k in ids}
    ALTS = {}
    for f in os.listdir(IMG):
        if '_' in f: ALTS.setdefault(f.split('_')[0], []).append(f)
    for c in cases:
        fn = c['id'] + '.webp'; p = os.path.join(IMG, fn)
        for f in ALTS.get(c['id'], []): keep.add(f)   # a rescued alternate portrait (rescue_images)
        if os.path.exists(p) and os.path.getsize(p) > 400:
            c['im'] = 'img/' + fn; keep.add(fn); continue
        if REQ['img'] >= MAX_IMG: continue   # rest next day
        if c['id'] in failed and (today - datetime.date.fromisoformat(failed[c['id']])).days < 7: continue
        data, ct = get(c['img'], tries=2, kind='img')
        time.sleep(1.0)
        if not (data and ct.startswith('image/')) and c.get('img2') and c['img2'] != c['img']:
            data, ct = get(c['img2'], tries=1, kind='img'); time.sleep(1.0)
        if not (data and ct.startswith('image/')) and c.get('cap'):
            data, ct = wayback_img(c['img'])   # captured posters vanish from fbi.gov; the Internet Archive kept the FBI's own image
        if not (data and ct.startswith('image/')):
            failed[c['id']] = today.isoformat(); continue
        failed.pop(c['id'], None)
        try:
            im = Image.open(io.BytesIO(data)); im = im.convert('RGB')
            im.thumbnail((300, 380))
            im.save(p, 'WEBP', quality=72, method=6)
            c['im'] = 'img/' + fn; keep.add(fn)
        except Exception as e:
            print('img fail', c['id'], e, file=sys.stderr)
    json.dump(failed, open(FAILF, 'w'), indent=0, sort_keys=True)
    for f in os.listdir(IMG):
        if f not in keep and not f.startswith(('dea-', 'usss-', 'usms-')):   # agency portraits: add_agencies owns them
            os.remove(os.path.join(IMG, f))
    for c in cases: c.pop('img', None); c.pop('img2', None)   # clients never touch fbi.gov images (c['alt'] goes after rescue)

ALTF = os.path.join(ROOT, 'img_alt.json')
def rescue_images(cases):
    """Scored-poster cases whose first FBI image failed the face check: try the poster's other images (max 4) once.
    The result is remembered in img_alt.json ({id: index used, or 0 = none usable}) so the daily run never re-asks."""
    from PIL import Image
    import io
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import faces
    try: done = json.load(open(ALTF))
    except Exception: done = {}
    ids = {c['id'] for c in cases}; done = {k: v for k, v in done.items() if k in ids}
    n = 0
    for c in cases:
        alt = c.pop('alt', None) or []
        if c.get('fq') or not c.get('g') or c.get('c') in faces.NEVER: continue
        k = done.get(c['id'])
        if k:   # rescued earlier: reuse the cached file
            fn = '%s_%d.webp' % (c['id'], k)
            if os.path.exists(os.path.join(IMG, fn)): c['im'] = 'img/' + fn; c['ii'] = k; faces.mark([c])
            continue
        if k == 0 or not alt: continue
        done[c['id']] = 0
        for j, u in enumerate(alt, 1):
            if REQ['img'] >= MAX_IMG: done.pop(c['id'], None); break
            data, ct = get(u, tries=2, kind='img'); time.sleep(1.0)
            if not (data and ct.startswith('image/')): continue
            try:
                im = Image.open(io.BytesIO(data)).convert('RGB'); im.thumbnail((300, 380))
                fn = '%s_%d.webp' % (c['id'], j); p = os.path.join(IMG, fn); im.save(p, 'WEBP', quality=72, method=6)
            except Exception: continue
            t = dict(c, im='img/' + fn, ii=j)
            if faces.mark([t]):
                c['im'] = t['im']; c['ii'] = j; done[c['id']] = j; n += 1; break
            os.remove(p)
    json.dump(done, open(ALTF, 'w'), indent=0, sort_keys=True)
    print('rescued portraits', n)
    return n

def _faces(cases):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import faces
        print('clear faces', faces.mark(cases))
    except Exception as e:
        print('face check skipped', e, file=sys.stderr)

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
    cases, _ = add_agencies(cases)
    _faces(cases)
    if '--no-images' not in sys.argv: rescue_images(cases)
    for c in cases: c.pop('alt', None)
    mix = {}
    for c in cases: mix[c['c']] = mix.get(c['c'], 0) + 1
    out = {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'total': total,
           'n': len(cases), 'mix': mix, 'cfg': {'missing': INCLUDE_MISSING}, 'res': resolved(items), 'cases': cases}
    s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    old = open(OUT).read() if os.path.exists(OUT) else ''
    if old:
        try:
            o = json.loads(old); o['updated'] = out['updated']
            if o == json.loads(s):
                print('no change; requests api=%d img=%d' % (REQ['api'], REQ['img'])); return 0
        except ValueError: pass
    open(OUT, 'w').write(s)
    print('cases', len(cases), 'mix', mix, 'skipped', skipped)
    print('requests this refresh: api=%d img=%d' % (REQ['api'], REQ['img']))
    return 0

if __name__ == '__main__':
    if '--reclue' in sys.argv:   # re-apply clues.json / fallback to the cached cases.json, no network
        d = json.load(open(OUT))
        if not INCLUDE_MISSING: d['cases'] = [c for c in d['cases'] if c['c'] != 'missing']
        d['cfg'] = {'missing': INCLUDE_MISSING}
        d['n'] = len(d['cases']); d['mix'] = {}
        for c in d['cases']: d['mix'][c['c']] = d['mix'].get(c['c'], 0) + 1
        for c in d['cases']:
            c['k']['rw'] = reward_amt({'reward_max': c['k'].get('rw') or 0, 'reward_text': c['r'].get('rw') or ''})
            add_clues(c, names_of({'title': c['title']}))
        _faces(d['cases'])
        open(OUT, 'w').write(json.dumps(d, ensure_ascii=False, separators=(',', ':')))
        print('reclued', len(d['cases']), 'sources', {x: sum(c['k']['cs'] == x for c in d['cases']) for x in '2lf'}); sys.exit(0)
    if '--reclassify' in sys.argv:   # offline: re-apply cats.py to the cached cases.json from a raw API dump
        d = json.load(open(OUT)); raw = {it['uid']: it for it in dedupe(json.load(open(sys.argv[sys.argv.index('--reclassify') + 1])))}
        n = 0
        for c in d['cases']:
            it = raw.get(c['id'])
            if not it: continue
            alltext = ' '.join([it.get('title') or '', text(it.get('description')), text(it.get('caution')), text(it.get('details')),
                                text(it.get('remarks')), text(it.get('additional_information')), it.get('reward_text') or ''])
            g, ok, m, why = cats.assign(it.get('subjects'), set(it.get('_pcs') or []) | {it.get('poster_classification')},
                                        sus_charge(it) if c.get('sus') else text(it.get('description')), alltext, text(it.get('caution')) or text(it.get('details')))
            if c['c'] in ('missing', 'parental', 'seeking') and not c.get('sus'): g, ok, why = None, [], 'never scored (%s)' % c['c']
            c['sj'] = [s for s in (it.get('subjects') or []) if s] or None; c['g'] = g; c['ok'] = ok; c['m'] = m; c.pop('gx', None)
            if why: c['gx'] = why
            n += 1
        open(OUT, 'w').write(json.dumps(d, ensure_ascii=False, separators=(',', ':'))); print('reclassified', n, 'of', len(d['cases'])); sys.exit(0)
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
