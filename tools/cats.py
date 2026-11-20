"""Look Again answer categories, taken from the FBI's own poster lists (the API's `subjects`).

Each playable case gets:
  g  = the one answer: the FBI crime list the poster is filed under
  m  = every category the case could defensibly match: its FBI crime lists, the
       country/program tags (Iran, China Threat, Transnational Repression -> state-linked),
       and anything its own charge text obviously implies (a cartel hitman matches
       Violent too; a state hacker matches Counterintelligence too).
Rounds may only show the answer plus categories NOT in m, so two right answers can't appear.
Cases with no FBI crime list, or two different crime lists, or whose matches leave fewer than
2 wrong options, get g=None and are never played.
"""
import re

GROUPS = ['violent', 'gangs', 'money', 'cyber', 'spy', 'terror', 'drugs']   # drugs: DEA's fugitives list (and any drug charge)

# FBI crime-type lists -> category (the FBI's own wording is shown on the reveal)
LIST = {
    'Violent Crime - Murders': 'violent', 'Additional Violent Crimes': 'violent',
    'Criminal Enterprise Investigations': 'gangs',
    'White-Collar Crime': 'money', 'While-Collar Crime': 'money', 'Most Wanted Fraudster': 'money',
    "Cyber's Most Wanted": 'cyber',
    'DEA Fugitives': 'drugs',
    'Counterintelligence': 'spy',
    'Most Wanted Terrorists': 'terror', 'Most Wanted Terrorist': 'terror',
    'Seeking Information - Terrorism': 'terror', 'Domestic Terrorism': 'terror',
}
PC_LIST = {'terrorist': 'terror', 'fraudster': 'money'}
# country / program tags: not a crime type, but they make "foreign state" a defensible reading
STATE_TAGS = {'Iran', 'China Threat', 'Transnational Repression'}
# lists that say how wanted someone is, not what for: the charge text must point at exactly one category
CHARGE_ONLY = {'Ten Most Wanted Fugitives', 'Law Enforcement Assistance'}

KW = {
 'violent': r"murder|homicid|\bkill|manslaughter|assault|robbery|kidnap|abduct|hostage|shooting|\bshot\b|carjack|"
            r"firearm|machine gun|weapons?(?! of mass)(?! program)|crime of violence|violent|threats?(?! actor)|stalking|arson|by means of fire|attempted murder|torture",
 'gangs':   r"cartel|\bgangs?\b|mara salvatrucha|ms-13|drug|narcotic|cocaine|heroin|methamphetamine|fentanyl|marijuana|"
            r"controlled substance|racketeer|(?<!puerto )\brico\b|criminal enterprise|organized crime|mafia|crime family|gambling|"
            r"continuing criminal|smuggl|traffick",
 'drugs':   r"\bdrugs?\b|narcotic|cocaine|heroin|methamphetamine|\bmeth\b|fentanyl|marijuana|cannabis|opium|opioid|oxycodone|controlled substance|"
            r"intent to distribute|manufactur\w* (and|or) distribut|drug traffick|cartel|narco",
 'money':   r"fraud|defraud|launder|embezzl|ponzi|securities|investor|bribe|bribery|kickback|tax|counterfeit|"
            r"identity theft|trade secret|theft of (government|public)|false claims|health care|medicare|insurance|"
            r"money transmitting|bank fraud|bank secrecy|financial institution",
 'cyber':   r"computer|hack|intrusion|malware|ransomware|botnet|cyber|phishing|unauthorized access|internet|online|"
            r"crypto|bitcoin|dark ?web|access device|\bdata\b|software",
 'spy':     r"espionage|\bspy|spies|intelligence (service|officer|agency|services)|ministry of state security|\bmss\b|"
            r"people'?s liberation army|\bpla\b|\bgru\b|\bfsb\b|\bsvr\b|\bkgb\b|revolutionary guard|irgc|qods|quds|"
            r"agents? of (a|the) foreign|foreign (government|power|principal)|illegal agent|national defense information|"
            r"emergency economic powers|ieepa|export (control|administration)|arms export|sanction|transnational repression|"
            r"government of (iran|china|the people|russia|north korea)|(iranian|chinese|russian|north korean) government|"
            r"\bprc\b|\bdprk\b|north korea|on behalf of the (government|regime)|at the direction of|weapons? of mass|proliferat",
 'terror':  r"terror|bomb|explosive|destructive device|material support|hijack|aircraft piracy|al[- ]?qa'?ida|\bisis\b|\bisil\b|"
            r"islamic state|hizballah|hezbollah|hamas|jihad|foreign terrorist|qods|quds|irgc|revolutionary guard|"
            r"narco-?terror|lethal plots",
}
KWR = {k: re.compile(v, re.I) for k, v in KW.items()}

def text_hits(t):
    return {k for k, r in KWR.items() if r.search(t or '')}

PRIMARY = ['terror', 'spy', 'cyber', 'money', 'drugs', 'gangs', 'violent']   # g = the most specific of a case's right answers

def assign(subjects, pcs, charge_text, all_text, story_text=''):
    """-> (g, ok, m, why).
    ok = every category that counts as RIGHT: the FBI crime lists the poster is filed under; with no crime list
         (Ten Most Wanted, Law Enforcement Assistance, captured / unknown-suspect posters) the categories the FBI's
         charge line names; if the charge line names none (e.g. "Escape from Custody"), what the FBI's own case text
         says they did (e.g. the bank fraud they were serving time for).
    m  = every category a player could defensibly argue for (ok + state tags + every keyword in all FBI text).
    A round shows ONE category from ok plus up to 3 from outside m (2-choice round if only one is left), so a shown
    option is either right or clearly wrong. Nothing is dropped unless the FBI text names no category at all."""
    subjects = list(subjects or []); pcs = set(pcs or [])
    lists = {LIST[s] for s in subjects if s in LIST} | {PC_LIST[p] for p in pcs if p in PC_LIST}
    m = set(lists) | text_hits(all_text)
    if any(s in STATE_TAGS for s in subjects): m.add('spy')
    why = ''
    if lists: ok = set(lists)
    else:
        ok = text_hits(charge_text); why = 'charge line'
        if not ok: ok = text_hits(story_text); why = 'case text'
    if not ok: return None, [], sorted(m), 'FBI text names no category'
    m |= ok
    g = next(x for x in PRIMARY if x in ok)
    if len(GROUPS) - len(m) < 1: return None, sorted(ok), sorted(m), 'every category fits'
    if len(ok) > 1: why = (why + '; ' if why else '') + 'right: ' + '+'.join(sorted(ok))
    return g, sorted(ok), sorted(m), why
