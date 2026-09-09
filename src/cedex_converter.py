"""
CEDEX Damage Description Converter - Merged Edition
Combines proven logic with DeepSeek vocabulary additions (corrected).
Usage: python cedex_converter.py input.xlsx output.xlsx

======================================================================
WHAT THIS PROGRAM DOES (in plain language)
======================================================================
You give it an Excel file. Column A of that file has messy, free-text
damage descriptions, e.g.:
    "L/SIDE PANEL DENTED TO REPLACE 2 X 3 FT (150USD)"

For every single row, the program reads that sentence and tries to
figure out 6 things, then writes them into a new, clean Excel file:

  1. LOCN   - WHERE on the container is the damage?      (e.g. LXXX)
  2. CMP    - WHAT part is damaged?                       (e.g. PSC)
  3. DMG    - WHAT kind of damage is it?                  (e.g. DT = dent)
  4. RPR    - WHAT repair is needed?                      (e.g. RP = replace)
  5. LENGTH / WIDTH - the SIZE of the damage, in inches
  6. TOTAL(USD) - the COST, if a dollar amount was mentioned

HOW it decides all this: it just reads the sentence and looks for
known keywords/phrases (in English, Turkish and Russian). Every
"if 'WORD' in text: return CODE" line is one simple rule: "if this
word shows up, use this code." The rules are checked from top to
bottom, and the first one that matches wins.

NEW FEATURE - MANUAL_OVERRIDES dictionary (see below):
If you come across a phrase the program keeps getting wrong, you do
NOT need to touch any of the complicated rules. Just add one line to
the MANUAL_OVERRIDES dictionary a few lines down, in the form:
    "PHRASE TO LOOK FOR": "LOCN,CMP,DMG,RPR"
Any row whose text contains that phrase will always use the values
you typed, no matter what the automatic rules would have guessed.
======================================================================
"""
import pandas as pd, re, sys, os

# ── 0. MANUAL OVERRIDES (EDIT THIS BY HAND - NO CODING NEEDED) ───────────────
# If the automatic rules below get something wrong, or you have a special
# phrase you always want mapped to specific codes, add it here.
#
# Format:   "PHRASE TO SEARCH FOR" : "LOCN,CMP,DMG,RPR"
#
# - The phrase is matched anywhere inside the row's text (not case sensitive).
# - The four codes after it must be separated by commas, in this exact order:
#     LOCN (location), CMP (component), DMG (damage type), RPR (repair type)
# - The row's SIZE (length/width) and USD cost are still read automatically -
#   you only need to give the 4 codes here.
# - If two phrases both match the same row, the one listed FIRST wins.
#
# Example (delete the # to activate it, or copy the pattern for your own):
# MANUAL_OVERRIDES = {
#     "SPECIAL CUSTOMER NOTE": "BXXX,FPP,BR,RP",
#     "WATER DAMAGE ON CEILING": "TXXX,RPS,DY,WW",
# }
MANUAL_OVERRIDES = {
    # Add your own lines below this comment, following the format above.
}

# ── 1. RUSSIAN TRANSLATION MAP ────────────────────────────────────────────────
RUSSIAN_MAP = {
    'Передняя сторона':'FRONT SIDE','Панель передняя':'FRONT PANEL',
    'Отверстие':'HOLED','Сварка':'WELD',
    'Пол из доски':'FLOOR PLANK','Пол из ламината':'FLOOR PLY','Пол':'FLOOR',
    'Левая сторона':'L/SIDE','Правая сторона':'R/SIDE',
    'Панель боковая':'SIDE PANEL','Панель крыши рифленая':'ROOF PANEL',
    'Крыша':'ROOF','Двери':'DOOR','Рукоятка дверная':'DOOR HANDLE',
    'Некачественный ремонт':'IMPROPER REPAIR','Искривление':'BENT',
    'Грязный':'DIRTY','Порез':'CUT','Ржавчина':'RUSTY',
    'Вмятина':'DENT','Сломан':'BROKEN','Отсутствует':'MISSING',
    'Пробоина':'HOLED','Расслоение':'DELAMINATION','Царапины':'SCRATCHES',
}

def translate(text):
    t = str(text)
    for phrase, en in RUSSIAN_MAP.items():
        if phrase in t:
            t = t.replace(phrase, en)
    return t

# ── 1b. DISPLAY-ONLY FULL TRANSLATION MAP ─────────────────────────────────────
# A SEPARATE, larger glossary used only to make terminal prompts readable
# during human review. It is never applied to job_description before
# classification (translate() above still does that job, unchanged), so
# this cannot affect LOCN/CMP/DMG/RPR guessing or CEDEX Master matching -
# it only touches what gets printed to the screen.
#
# Covers words seen in real depot estimate sheets that RUSSIAN_MAP above
# doesn't need for classification but a human reader benefits from seeing
# in English. Add more phrases here as new depots send new vocabulary -
# multi-word phrases are listed first so they get replaced before their
# individual words would otherwise match.
DISPLAY_RUSSIAN_MAP = {
    # multi-word phrases first (longest match wins)
    'Передняя сторона':'Front side','Панель передняя':'Front panel',
    'Левая сторона':'Left side','Правая сторона':'Right side',
    'Панель боковая':'Side panel','Панель крыши рифленая':'Corrugated roof panel',
    'Пол из доски':'Board floor','Пол из ламината':'Plywood floor',
    'Рукоятка дверная':'Door handle','Некачественный ремонт':'Improper repair',
    'Кол-во':'Qty','Кол во':'Qty','Ответственность':'Responsibility',

    # single words
    'Отверстие':'Hole','Сварка':'Weld','Пол':'Floor',
    'Крыша':'Roof','Двери':'Door','Искривление':'Bent/warped',
    'Грязный':'Dirty','Порез':'Cut','Ржавчина':'Rust',
    'Вмятина':'Dent','Сломан':'Broken','Отсутствует':'Missing',
    'Пробоина':'Puncture','Расслоение':'Delamination','Царапины':'Scratches',
    'Выпуклость':'Bulge','Выпрямление':'Straighten','Трещина':'Crack',
    'Ремонт':'Repair','Заплатка':'Patch','Замена':'Replace',
    'Крышка':'Cover','Панель':'Panel','Царапина':'Scratch',
    'Заклепка':'Rivet','Болт':'Bolt','Гайка':'Nut','Прокладка':'Gasket',
    'Коррозия':'Corrosion','Загрязнение':'Contamination',
}

def translate_for_display(text):
    """
    Best-effort Russian -> English translation for TERMINAL DISPLAY ONLY.
    Does NOT modify the underlying job_description used for classification
    or written to Excel - call this only at the point text is being printed
    for a human to read (e.g. the human review prompt in workflow.py).
    Words not found in the glossary are left as-is (untranslated), so mixed
    Russian/English output is still possible for unseen vocabulary; extend
    DISPLAY_RUSSIAN_MAP above as new terms come up.
    """
    t = str(text)
    for phrase, en in DISPLAY_RUSSIAN_MAP.items():
        if phrase in t:
            t = t.replace(phrase, en)
    return t

# ── 2. iREPAIR VOCABULARIES ───────────────────────────────────────────────────
IR_CMP = {
    'wood floor assembly':'FWA','flooring, plywood plank':'FPP',
    'flooring, plain plank':'FPB','flooring, steel plank':'FPB',
    'locking bar rod/tube':'LBA','locking bar rod (tube)':'LBA',
    'locking bar handle':'LBH','locking bar lug':'LBA','locking bar assembly':'LBA',
    'panel assembly':'PSC','serial number & checkdigit':'MLO',
    'serial number and check digit':'MLO','mass marking':'MLO',
    'single weigh decal':'MLO','caution marking':'MLO','cargo container':'FWA',
    'gasket, outer':'GTO','gasket, inner':'GTI',
    'cross member assembly':'CMS','cross member whole section':'CMS','crossmember':'CMS',
    'forklift pocket whole side assembly':'FLA','forklift pocket assembly':'FLA',
    'rail - assembly':'RLA','rail assembly':'RLA','rail whole section':'RLT',
    'door stiffeners-bottom edge':'DFS',
    'handle retainer':'LBH',
    'corner post assembly':'CPA','corner casting forged':'CCF',
    'roof panel assembly steel':'RPS','roof steel corrugated':'RPS',
    'roof bow':'RBO','door hinge assembly':'DH','door hinges':'DH',
    'door handle lock assembly':'DHL',
}

IR_DMG = {
    'contamination':'CT','bent':'BT','cracked':'CK','broken/split':'BR',
    'debris/dunnage':'DB','loose component':'LO','loose':'LO','dent':'DT',
    'nails':'NL','oil stains':'OS','oil seains':'OS','wear and tear':'WT',
    'blocked':'BK','corroded/rusty':'CH','missing/lost':'MS','holed':'HO',
    'delaminated':'DL','scratched/abraded':'SA','improper repair':'IR',
    'puncture':'HO','bowed':'BW','pin hole':'PH','pin holes':'PH',
}

IR_RPR = {
    'water wash':'WW','chemical clean':'SC','straighten and weld':'WD',
    'straighten':'GS','section':'SN','replace':'RP','remove':'RM',
    'insert':'IT','patch':'PT','resecure':'RE','sanding':'GS',
    'paint':'PA','seal':'SE','weld':'WD','adjust':'AJ',
}

_LOC_PAT = re.compile(r'\b([A-Z]{2}[0-9X][0-9XNA-Z])\b')
VALID_PFX = {'BL','BR','BX','DB','DG','DH','DT','DX','EX','FB','FG','FH',
             'FT','FX','IX','LB','LG','LH','LT','LX','RB','RG','RH','RT',
             'RX','TL','TR','TX','UL','UR','UX','XX'}

def find_embedded_loc(text):
    for m in _LOC_PAT.finditer(text.upper()):
        code = m.group(1)
        if code[:2] in VALID_PFX:
            return code
    return None

# ── 3. USD EXTRACTION ─────────────────────────────────────────────────────────
def extract_usd(vals):
    txt = ' '.join(str(v) for v in vals)
    patterns = [
        r'\((\d+\.?\d*)USD\)',
        r'\(USD\s*(\d+\.?\d*)\)',
        r'USD\s*\$?\s*(\d+\.?\d*)',
        r'\$\s*(\d+\.?\d*)\s*USD',
    ]
    for pat in patterns:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None

def strip_usd(text):
    """Remove USD cost from description text before dimension/location parsing."""
    return re.sub(r'[:\-=>]?\s*USD\s*\$?\s*\d+\.?\d*', '', text, flags=re.IGNORECASE).strip()

# ── 4. DIMENSION EXTRACTION ───────────────────────────────────────────────────
def to_in(val, unit):
    v, u = float(val), str(unit).upper().strip()
    if u in ("'", 'FT','FEET','FOOT'):       return int(round(v*12))
    if u in ('"',"''",'IN','INCH','INCHES'):  return int(round(v))
    if u in ('CM','CM.'):                     return int(round(v/2.54))
    if u in ('M','METER','METERS','METRE'):   return int(round(v*39.3701))
    return int(round(v*12)) if v <= 20 else int(round(v))

def extract_dims(text):
    # Remove container size references
    text = re.sub(r"\b(20|40|45)['\ s]*(?:FT|FEET|FOOT)?\s*CONTAINER\b", '', str(text), flags=re.IGNORECASE)
    # Remove USD cost references to prevent them being picked up as dimensions
    text = re.sub(r'USD\s*\$?\s*\d+\.?\d*', '', str(text), flags=re.IGNORECASE)
    text = re.sub(r'\$\s*\d+\.?\d*\s*USD', '', str(text), flags=re.IGNORECASE)
    t = str(text).upper()
    m = re.search(r"(\d+\.?\d*)\s*(['\"]|FT|CM|M(?!I)|INCH(?:ES)?|METER)\s*[Xx]\s*(\d+\.?\d*)\s*(['\"]|FT|CM|M(?!I)|INCH(?:ES)?|METER)", t)
    if m: return to_in(m.group(1),m.group(2)), to_in(m.group(3),m.group(4))
    m = re.search(r"(\d+\.?\d*)[\"']{1,2}\s*[Xx]\s*(\d+\.?\d*)[\"']{1,2}", t)
    if m: return int(float(m.group(1))), int(float(m.group(2)))
    m = re.search(r"(\d+\.?\d*)\s*[Xx]\s*(\d+\.?\d*)\s*CM", t)
    if m: return to_in(m.group(1),'CM'), to_in(m.group(2),'CM')
    m = re.search(r"(\d+)\s*[Xx]\s*(\d+)", t)
    if m:
        l,w = int(m.group(1)),int(m.group(2))
        return (l*12,w*12) if l<=20 and w<=20 else (l,w)
    for pat,unit in [(r"(\d+\.?\d*)\s*FT","FT"),(r"(\d+\.?\d*)'(?!\d)","'"),(r"(\d+\.?\d*)\s*METER","M"),
                     (r"(\d+\.?\d*)\s*CM","CM"),(r"(\d+\.?\d*)\s*INCH(?:ES)?","INCH"),(r'(\d+\.?\d*)["\']+', "INCH")]:
        m = re.search(pat, t)
        if m: return to_in(m.group(1),unit), 0
    return 0, 0

# ── 5. COMPONENT ──────────────────────────────────────────────────────────────
def get_cmp(text):
    t, tl, tu = str(text), str(text).lower(), str(text).upper()
    if 'dope lift' in tl or re.match(r'^lift\b', tl): return 'ZZZ'

    if tl.strip() == 'pti' or re.match(r'^pti\b', tl): return 'MPI'

    for phrase, code in IR_CMP.items():
        if phrase in tl: return code

    if 'serial' in tl and ('number' in tl or 'check' in tl): return 'MLO'
    if 'handle retainer' in tl: return 'LBH'

    wash = ['H/WASH','H/W','N/WASH','REWASH','DIRTY TO H','FLOOR DIRTY','MUD ON FLOOR',
            'WHITE POWDER','OIL STAIN ON FLOOR','CARGO DEBRIS ON FLOOR',
            'COLD WASH','CHEMICAL WASH','CHEMICAL CLEANING','CHEMICAL CLEAN','DETERGENT WASH','HOT WATER WASH','STEAM WASH','HOT WASH',
            'SICAK SU ILE YIKAMA','SICAK YIKAMA','SICAK YIMAMA','KIMYASAL YIKAMA']
    if any(k in tu for k in wash) or tl.strip() in ('h/w','h/wash','n/wash') or 'WASH' in tu or 'YIKAMA' in tu: return 'FWA'

    if any(k in tu for k in ['FLOOR PLY','FLR PLY','FLOOR PLYWOOD','FOOR PLY','FOOR PLYWOOD']):
        return 'FPB' if 'SCREW' in tu else 'FPP'
    # When description starts with BL/BR/BX floor section code, component = FPP
    if re.match(r'^B[LRX]\d', tu.strip()): return 'FPP'
    if any(k in tu for k in ['FLOOR PLANK','FLR PLANK','FASTNER','FASTENER','NAILS',
                              'TABAN TAHTASI','BASEBOARD','BASE BOARD','SCREW','SCREWS',
                              'BREAKING FLOOR','BROKEN FLOOR','CONTAINER BOARD','BOARD BULGE']): return 'FPB'
    if 'STEEL PLATE' in tu: return 'FSP'
    if 'ARALI' in tu or ('BOŞLUK' in tu and ('TAHTA' in tu or 'FLOOR' in tu or 'PANEL' in tu)): return 'FPB'
    if ('GAP' in tu or 'BOŞLUK' in tu) and ('BOARD' in tu or 'TAHTA' in tu): return 'FPB'
    if any(k in tu for k in ['GİRİŞ TAHTASI','GIRIS TAHTASI','ENTRANCE BOARD']): return 'DFS'
    if 'GÖÇÜK' in tu or 'GOCUK' in tu: return 'FPB'
    if 'TABAN TAHTASI' in tu or ('TAHTA' in tu and any(k in tu for k in ['KIRIK','KİRİK','DEGISIM','DEGISİM','HASARLI'])): return 'FPB'
    if any(k in tu for k in ['WOODEN PLATE','WOODEN FLOOR','WOODEN BOARD','WOODEN PLANK']) or ('WOODEN' in tu and 'BOARD' in tu): return 'FPB'
    if 'BASEBOARD' in tu or 'BASE BOARD' in tu: return 'FPB'
    if 'ENTRANCE BOARD' in tu: return 'DFS'
    if 'CEILING' in tu: return 'RPS'

    if any(k in tu for k in ['INT PNL','INT N ','INTERNAL PANEL','INT PANEL','INT. PNL','INT.PNL']):
        if any(k in tu for k in ['CONT NO','DECAL','DEACAL','DEACALS','WEIGHT DECAL',
                                  'MARKING','DECCULS','DEACULS']): return 'MLO'
        if 'TAR' in tu and 'PANEL' not in tu: return 'FPP'
        if 'CHEMICAL BAGS' in tu or ('DEBRIS' in tu and 'PANEL' not in tu): return 'FWA'
        if 'TOP RAIL' in tu: return 'RLT'
        if any(k in tu for k in ['LASHING ROPE','LASHING RING','LASHING BAR','LASHING']): return 'LSR'
        return 'INP'

    if any(k in tu for k in ['OLD RESIDUE','RESIDUE','CARGO RESIDUE']): return 'FWA'
    if any(k in tu for k in ['WASTE OF CNTR','WASTE OF CONTAINER','REMOVING WASTE','WASTE OF']): return 'FWA'
    if 'TAR ' in tu or 'TAR ON' in tu or 'TAR REMOVE' in tu: return 'FPP'
    if 'CHEMICAL BAGS' in tu: return 'FWA'
    if any(k in tu for k in ['STICKY TAPE','GLUE REMOVE','GUM TAPE','GUM STICKER']): return 'INP'

    if any(k in tu for k in ['CONT NO','DECAL','DEACAL','DEACALS','WEIGHT DECAL',
                              'MARKING','DECCULS','DEACULS','STICKER','HAZ STICKER',
                              'CARGO STICKER','HAZ LABEL','LABEL',
                              'CONTAINERNUMBER','CONTAINER NUMBER']): return 'MLO'
    if re.search(r'\bCSC\b', tu): return 'MPS'
    if any(k in tu for k in ['EXT PNL','EXT N ','EXTERNAL PANEL','EXT PANEL']): return 'PSC'

    if 'ROOF BOW' in tu: return 'RBO'
    if any(k in tu for k in ['TARPAULIN','TARPAUL','TARPOULIN','TARPOULING','TARPOULINE','TRAPAULIN','TARPOLING','TARPULIN','TARPOOLINE','TARPOLIN','TARPOLYN','TARPOLINE','TARP']):
        if 'PIN HOLE' in tu: return 'TPH'
        if 'EYELET' in tu or 'GROMMET' in tu: return 'TNG'
        return 'TNA'
    if 'TIR CORD' in tu or ('TIR' in tu and 'CORD' in tu): return 'TIC'
    if any(k in tu for k in ['ROOF','ROOD','TAVAN','TAVANDA','CEILING','TOP PANEL']): return 'RPS'
    if any(k in tu for k in ['X MEMBER','X-MEMBER','XMEMBER','CROSS MEMBER','XMEMB','CMR','C/MR']): return 'CMS'
    if any(k in tu for k in ['FLP','FLT','FORK LIFT','FORKLIFT','POCKET']):
        return 'FSA' if ('STRIP' in tu or 'STRAP' in tu) else 'FLA'
    if any(k in tu for k in ['GOOSENECK','GROOVE','SUPPORT BAR','SIDE BEAM GROOVE']): return 'RLT'
    if any(k in tu for k in ['SILL','F/SILL','GİRİŞ TAHTASI','GIRIS TAHTASI','ENTRANCE BOARD','GİRİŞ','GIRIS']): return 'DFS'
    if 'GUSSET' in tu: return 'CPG'
    if any(k in tu for k in ['CORNER POST','C/POST','CPP']): return 'CPA'
    if any(k in tu for k in ['CASTING','TWIST LOCK']): return 'CCF'
    if any(k in tu for k in ['REMOVING PINS','REMOVE PINS','PINS REMOVE','REMOVING PIN','REMOVE PIN']): return 'INP'
    if any(k in tu for k in ['CONTAINER ROD']) or re.search(r'\bROD\b', tu): return 'LBA'
    if any(k in tu for k in ['DOOR STOPPER','STOPPER']) and 'SEAL' not in tu:
        return 'LBH'
    if 'TAVAN' not in tu and any(k in tu for k in ['GASKET','GSKT','SEAL STOPPER','SEALING STOPPER','DOOR SEAL',
                              'KAPI CONTASI','KAPI CONTA','CONTA']):
        if re.search(r'D/O/V|O/V/GASKET|D/O/V/GASKET', tu): return 'GTO'
        return 'GTI' if ('VERTICAL' in tu or 'L/V/GASKET' in tu) else 'GTO'
    if any(k in tu for k in ['LOCK ROD','L/ROD','L/L/ROD','R/L/ROD','LOCKROD',
                              'LOCKING ROD','LOCKING BAR','CONTAINER ROD',' ROD ','ROD REPAIR']): return 'LBA'
    if any(k in tu for k in ['RETAINER','HANDLE','BTM CAM','CAM','KEEPER','J BAR',
                              'L/CATCH','CATCH','GUIDE','BIG GUIDE','DOOR GUIDE']):
        return 'DHL' if ('HANDLE' in tu or 'J BAR' in tu) else 'LBH'
    if 'HINGE' in tu or 'HNGE' in tu: return 'HGA'
    if any(k in tu for k in ['TOP RAIL','BTM RAIL','BOTTOM RAIL','SIDE BEAM','TUNNEL RAIL']):
        return 'RLF' if 'FLANG' in tu else 'RLT'
    if any(k in tu for k in ['HEADER','HEP','DOOR FRAME','DOOR BTM FRAME',
                              'DOOR TOP FRAME','L/V/FRAME','R/V/FRAME','FRAME']): return 'RLA'
    if any(k in tu for k in ['BOTH DOOR','DOOR ALLIGN','DOOR ALIGN','DOOR JAM',
                              'JAM TO FREE','FREE UP']): return 'DAA'
    if any(k in tu for k in ['V/COVER','VENT COVER','V/COV','AIR VENT']): return 'ARE'
    if any(k in tu for k in ['LASHING ROPE','LASHING RING','LASHING BAR','LASHING']): return 'LSR'
    if 'OUTRIGGER' in tu or 'OUT RIGGER' in tu: return 'BDB'

    if re.match(r'^[LR]X\s', tu): return 'PSC'
    if re.match(r'^TX\s', tu): return 'RPS'
    if re.match(r'^BX\s', tu): return 'FPP'
    if any(k in tu for k in ['L/SIDE','R/SIDE','L/S ','R/S ']) and \
       any(k in tu for k in [' N ',' N\t','2ND','3RD','4TH','1ST','5TH']): return 'PSC'
    if re.search(r'^SIDE\s', tu): return 'PSC'
    if re.search(r'^FRONT N\b', tu): return 'PSC'
    if any(k in tu for k in ['PNL','PANEL','SIDE PNL','SIDE PANEL',
                              'CORRIGATION','CORRUGATION','SIDE WALL']): return 'PSC'
    if any(k in tu for k in ['FLOOR LOOSE','FLOOR BRKN','FLOOR IMPACT',
                              'ALL FLOOR','FULL FLOOR']): return 'FPP'
    if 'INT' in tu: return 'INP'
    if any(k in tu for k in ['FLOOR','FLR']): return 'FPP'
    return 'PSC'

# ── 6. DAMAGE ─────────────────────────────────────────────────────────────────
def get_dmg(text):
    t, tl, tu = str(text), str(text).lower(), str(text).upper()
    if 'dope lift' in tl or re.match(r'^lift\b', tl): return 'ZZ'

    wash = ['H/WASH','H/W','N/WASH','REWASH','DIRTY TO H','FLOOR DIRTY','MUD ON FLOOR',
            'COLD WASH','CHEMICAL WASH','CHEMICAL CLEANING','CHEMICAL CLEAN',
            'DETERGENT WASH','HOT WATER WASH','STEAM WASH','HOT WASH',
            'SICAK SU ILE YIKAMA','SICAK YIKAMA','SICAK YIMAMA','KIMYASAL YIKAMA']
    if any(k in tu for k in wash) or tl.strip() in ('h/w','h/wash','n/wash') or 'WASH' in tu or 'YIKAMA' in tu:
        if any(k in tu for k in ['WHITE POWDER','CONTAMINA','CHEMICAL WASH','CHEMICAL CLEANING','CHEMICAL CLEAN','CHEMICAL','DETERGENT','KIMYASAL']): return 'CT'
        if 'OIL STAIN' in tu or 'GREASY' in tu or 'YAGLI' in tu or 'OILY' in tu: return 'OS'
        if 'CARGO DEBRIS' in tu or 'DEBRIS' in tu: return 'DB'
        return 'DY'

    for phrase, code in IR_DMG.items():
        if phrase in tl: return code

    if 'WHITE POWDER' in tu: return 'CT'
    if 'CHEMICAL REACTION' in tu: return 'CT'
    if 'TAR ' in tu or 'TAR ON' in tu or 'TAR REMOVE' in tu: return 'CT'
    if 'OIL STAIN' in tu or 'GREASY' in tu or 'YAGLI' in tu or 'OILY' in tu: return 'OS'
    if any(k in tu for k in ['STICKY TAPE','GUM TAPE','GUM STICKER']) or ('GLUE' in tu and 'REMOVE' in tu): return 'GT'
    if 'CARGO DEBRIS' in tu or 'CHEMICAL BAGS' in tu: return 'DB'
    if 'NAILS' in tu: return 'NL'
    if 'CONTAMINA' in tu: return 'CT'
    if 'DELAMINATION' in tu or 'DELAMIANTION' in tu or 'DELAMIN' in tu: return 'DL'
    if re.search(r'\bDL\b', tu): return 'DL'
    if 'DLM' in tu or 'DELAM' in tu: return 'DL'
    if any(k in tu for k in ['DECOMPOSE','RTN','ROTTEN']): return 'RO'
    if 'IMPROPER REPAIR' in tu: return 'IR'
    if re.search(r'\bIR\b', tu): return 'IR'
    if 'PUSHED OUT' in tu or 'P/OUT' in tu or re.search(r'\bP/O\b', tu): return 'PO'
    if 'CORRIGATION OUT' in tu or 'CORRUGATION OUT' in tu: return 'PO'
    if any(k in tu for k in ['PUSHED IN','P/IN','BULGE','BULGING','BOMBE','DOME','DOMED']) and not any(k in tu for k in ['DELİK','DELIK','HOLE','HOLED']): return 'BU'
    if any(k in tu for k in ['PIN HOLE','PIN HOLES','PINHOLE','PINHOLES']): return 'PH'
    if 'THROUGH HOLE' in tu or 'THROUGH CORROSION' in tu: return 'HO'
    if any(k in tu for k in ['HOLED','HOLE IN','TEAR IN','TEARS IN','DELIK','DELİK','YIRTIK','THERE ARE TEARS','TEAR','HOLE']): return 'HO'
    if 'CRACKED WELD' in tu or 'WELD CRACK' in tu: return 'CW'
    if any(k in tu for k in ['CROSSMEMBER','CROSS MEMBER']) and 'WELD' in tu: return 'CW'
    if re.search(r'\bBRK\b', tu): return 'BR'
    if re.search(r'\bBR\b', tu): return 'BR'
    if any(k in tu for k in ['CRACK','CRK']): return 'CK'
    if any(k in tu for k in ['BROKEN','BRKN','BROCKEN','BRKEN','BREAKING FLOOR','BROKEN FLOOR','HASARLI','KIRIK','KİRİK','DAMAGED','DEGISIM','DEGISIMI','DEGISİMİ','TO BE REPLACED']): return 'BR'
    if 'IMPACT' in tu: return 'BR'
    if 'WAVY' in tu or 'WAVEY' in tu or 'CURVED' in tu: return 'WA'
    if 'DEFORME' in tu or 'DEFORMED' in tu: return 'DT'
    if 'GOCUK' in tu or 'GÖÇÜK' in tu: return 'DT'
    if 'TWIST' in tu: return 'BT'
    if 'BOWED' in tu: return 'BW'
    if re.match(r'^ROOF BOW\s+INSTALL', tu.strip()): return 'MS'
    if re.match(r'^ROOF BOW', tu.strip()): return 'BW'
    if any(k in tu for k in ['BENT','CURVATURE','CURVY','CURVE']): return 'BT'
    if re.search(r'\bBT\b', tu): return 'BT'
    if 'DENT' in tu or 'DANTED' in tu: return 'DT'
    if re.search(r'\bDT\b', tu): return 'DT'
    if any(k in tu for k in ['TORN']) and not any(k in tu for k in ['CEILING','ROOF','PANEL']): return 'CU'
    if 'CUT' in tu and 'TOP COAT' not in tu: return 'CU'
    if re.search(r'\bCT\b', tu) and 'TOP COAT' not in tu: return 'CU'
    if 'RUSTY' in tu or 'RUST' in tu or 'CORRODED' in tu or 'CORROSION' in tu: return 'CH'
    if re.search(r'\bCH\b', tu): return 'CH'
    if re.search(r'\bCCH\b', tu): return 'CH'
    if 'GOUGES' in tu or 'GOUGE' in tu or 'GAUGE' in tu: return 'GD'
    if any(k in tu for k in ['STICKER','HAZ STICKER','CARGO STICKER','LABEL','HAZ LABEL']) and \
       any(k in tu for k in ['RMV','REMOVE','RM ']): return 'ML'
    if any(k in tu for k in ['SCRATCHES','SCRATCH','SCRTCH','SCRACH','SCRACTH',
                              'C/ABB','ABB','MACHINE MARKS','MACHINE MARK','BLACK STAIN','C/A']): return 'SA'
    if any(k in tu for k in ['REMOVING PINS','REMOVE PINS','REMOVING PIN']): return 'MS'
    if 'MISSING' in tu or re.search(r'\bMISS\b', tu): return 'MS'
    if any(k in tu for k in ['RETAINER','VALVE','STOPPER']) and \
       not any(k in tu for k in ['BENT','BT','CUT','BROKEN','DENT','CRACK',
                                  'RUSTY','MISSING','MISS','LOOSE']): return 'WT'
    if 'FLOOR LOOSE' in tu or 'FASTNER' in tu or 'FASTENER' in tu: return 'FL'
    if 'LOOSE' in tu or ('RMV' in tu and 'REFIX' in tu) or ('REMOVE' in tu and 'REFIX' in tu): return 'LO'
    if any(k in tu for k in ['MISALIGN','ALLIGN','ALIGN','ALLAIGH','JAM']): return 'MA'
    if 'DIRTY' in tu: return 'DY'
    if 'BURN' in tu: return 'BN'
    if any(k in tu for k in ['LEAK','GAP','ARALI','BOŞLUK','BOŞLU']): return 'LK'
    if 'WARPED' in tu: return 'WA'
    if 'AŞINMA' in tu or 'ASINMA' in tu or 'WEAR' in tu: return 'WT'
    if 'MISS MATCH' in tu or 'MISMATCH' in tu: return 'DS'
    if 'DISCOLOUR' in tu: return 'DS'
    if any(k in tu for k in ['OLD RESIDUE','CARGO RESIDUE']) or ('RESIDUE' in tu and 'REMOVE' in tu): return 'CR'
    if any(k in tu for k in ['REMOVING WASTE','REMOVE WASTE','WASTE OF CNTR','WASTE OF CONTAINER']): return 'DB'
    if 'LASHING' in tu: return 'MS'
    if 'REMOVE' in tu: return 'MS'
    return 'WT'

# ── 7. REPAIR ─────────────────────────────────────────────────────────────────
DMG_DEF = {
    'BR':'SN','BT':'GS','DT':'GS','CU':'SN','CH':'SN','DL':'SN','GD':'SN',
    'HO':'WD','IR':'SN','LO':'RE','MS':'RP','PO':'GS','BU':'GS','SA':'PA',
    'CT':'SC','DY':'WW','CK':'WD','OS':'WW','FL':'RE','NL':'RM','DB':'RM',
    'RO':'SN','MA':'AJ','BN':'SN','GT':'RM','DS':'PA','WA':'SN','WT':'SN',
    'CW':'WD','LK':'SE','BW':'SN','BK':'AJ','PH':'SE','ML':'RM','CR':'RM',
}

def get_rpr(text, dmg):
    t, tl, tu = str(text), str(text).lower(), str(text).upper()
    if 'dope lift' in tl or re.match(r'^lift\b', tl): return 'ZZ'

    # These must be checked BEFORE IR_RPR dict (which has 'replace'→RP and 'remove'→RM)
    if 'BADLY BENT' in tu or 'BADLY DENT' in tu: return 'SN'
    if 'TORN' in tu and any(k in tu for k in ['TARP','TARPAUL','TARPOL','TARPOUL']): return 'RP'
    if 'INSTALLATION' in tu or 'INSTALL' in tu: return 'IT'
    if any(k in tu for k in ['REMOVING PINS','REMOVE PINS','REMOVING PIN','REMOVE PIN']): return 'RM'
    if any(k in tu for k in ['TO REFIX','REFIX','RIFIX','& REFIX','AND REFIX',
                              'REMOVE & REFIX','RMV REFIX','SABITLEME']): return 'RE'

    for phrase, code in IR_RPR.items():
        if phrase in tl: return code

    if any(k in tu for k in ['H/WASH','H/W','N/WASH','REWASH','COLD WASH','CHEMICAL WASH','CHEMICAL CLEANING','CHEMICAL CLEAN','DETERGENT WASH','HOT WATER WASH','STEAM WASH','HOT WASH',
                             'SICAK SU ILE YIKAMA','SICAK YIKAMA','SICAK YIMAMA','KIMYASAL YIKAMA']) or \
       tl.strip() in ('h/w','h/wash','n/wash') or 'WASH' in tu or 'YIKAMA' in tu:
        return 'SC' if any(k in tu for k in ['CHEMICAL','STEAM','DETERGENT','KIMYASAL']) else 'WW'
    if 'BADLY BENT' in tu or 'BADLY DENT' in tu: return 'SN'
    if any(k in tu for k in ['TO WELD','CUT TO WELD','CUT & WELD','& WELD','WELD','WELDING FILLER']): return 'WD'
    if any(k in tu for k in ['TO PATCH','TO PH']): return 'PT'
    if any(k in tu for k in ['SEALANT','SELENT','SILEND','FILL UP SEAL','FILLUP','FILL UP','TO SEAL','SEALING','SILIKONLAMA','SILICONE']): return 'SE'
    if any(k in tu for k in ['TO SPP','SPP']): return 'SP'
    if any(k in tu for k in ['TOP COAT','TO TOP COAT','TO PAINT','TO REPAINT','TO COAT','T/UP','TOUCH UP','T/COAT']):
        return 'SP' if 'SPP' in tu else 'PA'
    if any(k in tu for k in ['SAND BLAST','REFERBRISHMENT','REFURBISHMENT','REFER BISHMENT']): return 'SP'
    if any(k in tu for k in ['TO REFIX','REFIX','RIFIX','& REFIX','AND REFIX','SABITLEME','SECURING','FASTENING','REMOVE & REFIX','RMV REFIX']): return 'RE'
    if any(k in tu for k in ['TO REMOVE','REMOVE','TO BE RMV','TO RMV','RMV']): return 'WW' if 'REWASH' in tu else 'RM'
    if any(k in tu for k in ['REALLIGN','REALIGN','REALLAIGH','TO ALLIGN','TO ALIGN',
                              'FREE UP','ALLIGNMENT','ALLAIGHMENT']): return 'AJ'
    if any(k in tu for k in ['RENEW','TO RENEW','REPLCE','REPLAC','DEGISIM','DEGISIMI','REPLACEMENT']): return 'RP'
    if any(k in tu for k in ['TO INSERT','TO INS']) and 'SEALANT' not in tu: return 'IT'
    if any(k in tu for k in ['TO INSTALL','TO INST']) and 'SEALANT' not in tu: return 'IT'
    if any(k in tu for k in ['TO STN','STN','TO STRAIGHTEN','STRAIGHTEN']): return 'GS'
    if 'TO NAT' in tu or 'TO NATURAL' in tu: return 'SP' if dmg == 'DL' else 'GS'
    if any(k in tu for k in ['CUT OUT REP','CUT OUT TO REP']): return 'SN'
    if 'TO REPLACE' in tu or 'TO REP' in tu:
        return 'SN' if any(k in tu for k in ['TO SEC','SECTION','TO SECTION']) else 'RP'
    if any(k in tu for k in ['TO SEC','TO SECTION']): return 'SN'
    if 'PATCH' in tu: return 'PT'
    if 'FULLY' in tu or 'FULL' in tu:
        if 'TOP COAT' in tu: return 'PA'
        if 'SPP' in tu: return 'SP'
        if any(k in tu for k in ['REPLACE','REP','SECTION']): return 'SN'
        if 'WASH' in tu: return 'WW'
    return DMG_DEF.get(dmg, 'SN')

# ── 8. LOCATION ───────────────────────────────────────────────────────────────
CMP_DEFAULT_LOC = {
    'FPP':'BXXX','FPB':'BXXX','FWA':'BXXX','FSP':'BXXX',
    'LBA':'DXXX','LBH':'DXXX','DH':'DXXX','DHL':'DXXX','DAA':'DXXX',
    'GTO':'DGXX','GTI':'DGXX',
    'DFS':'DBXX',
    'CMS':'UXXX','FLA':'UXXX','FSA':'UXXX','BDB':'UXXX',
    'RPS':'TXXX','RBO':'TXXX','TNA':'TXXX','TPH':'TXXX','TNG':'TXXX',
    'TIC':'EXXX','MLO':'EXXX',
    'INP':'IXXX','LSR':'IXXX',
    'CCF':'BXXX','RLA':'DXXX','CPG':'FXXX',
    'PSC':'XXXX','RLT':'XXXX','RLF':'XXXX','CPA':'XXXX','ARE':'XXXX',
}

def get_locn(text, cmp_code='', dmg_code='', rpr_code=''):
    t = str(text).upper().strip()

    # Special early returns
    if re.search(r'\bCSC\b', t): return 'DXXX'
    if 'TOP PANEL' in t: return 'TXXX'
    if any(k in t for k in ['OLD RESIDUE','CARGO RESIDUE','WASTE OF CNTR','WASTE OF CONTAINER','WASTE OF','REMOVING WASTE']) or ('RESIDUE' in t and 'REMOVE' in t): return 'IXXX'
    if 'CONTAINERNUMBER' in t or 'CONTAINER NUMBER' in t: return 'EXXX'

    m = re.search(r'\(([A-Z]{2}[\dA-Z]{1,2})\)', t)
    if m:
        code = m.group(1)
        if code[:2] in VALID_PFX and re.search(r'[0-9X]', code):
            return code.ljust(4,'X')[:4]

    emb = find_embedded_loc(t)
    if emb: return emb

    if 'DOPE LIFT' in t or re.match(r'^LIFT\b', t): return 'XXXX'

    wash = ['H/WASH','H/W','N/WASH','REWASH','WHITE POWDER','DIRTY TO H',
            'FLOOR DIRTY','MUD ON FLOOR','OIL STAIN ON FLOOR',
            'CARGO DEBRIS ON FLOOR','CHEMICAL CLEANING']
    if any(k in t for k in wash) or t.strip() in ('H/W','H/WASH','N/WASH'): return 'IXXX'

    if re.match(r'^LX\s*(\d)', t):
        n = int(re.match(r'^LX\s*(\d)', t).group(1)); return f"LX{n:02d}"
    if t.startswith('LX '): return 'LXXX'
    if re.match(r'^RX\s*(\d)', t):
        n = int(re.match(r'^RX\s*(\d)', t).group(1)); return f"RX{n:02d}"
    if t.startswith('RX '): return 'RXXX'

    # Ordinal cross member: '1st CMR', '2nd CMR' etc
    m_cmr = re.match(r'^(\d+)(?:ST|ND|RD|TH)?\s+CMR\b', t)
    if m_cmr: return f"UX{int(m_cmr.group(1)):02d}"
    if t.startswith('U/S') or 'UNDERSIDE' in t:
        if any(k in t for k in ['FLP','FLT','FORK LIFT','FORKLIFT','POCKET']):
            m2 = re.search(r'(\d+)', t); return f"UX{int(m2.group(1)):02d}" if m2 else 'UXXX'
        if any(k in t for k in ['X MEMBER','X-MEMBER','XMEMBER','CROSS MEMBER','XMEMB','CMR','C/MR']):
            m2 = re.search(r'(\d+)', t); return f"UX{int(m2.group(1)):02d}" if m2 else 'UXXX'
        if 'TUNNEL RAIL' in t:
            return 'RBXX' if ('R/SIDE' in t or 'RIGHT' in t) else 'LBXX'
        m2 = re.search(r'(\d+)', t); return f"UX{int(m2.group(1)):02d}" if m2 else 'UXXX'

    if any(k in t for k in ['ROOF BOW','ROOF PANEL','ROOF PNL','ROOD ','TARPAULIN','TARPAUL','TARPOULIN','TARPOULING','TARPOULINE','TRAPAULIN','TARPOLING','TARPULIN','TARPOLIN','TARPOLYN','TARPOLINE']) \
       or re.match(r'^ROOF\b', t):
        if 'BOW' in t or 'TARPAULIN' in t or 'TARPAUL' in t: return 'TXXX'
        m2 = re.search(r'(\d+)(?:ST|ND|RD|TH|N)?\s*P', t)
        return f"TX{int(m2.group(1)):02d}" if m2 else 'TXXX'

    if 'TIR CORD' in t or ('TIR' in t and 'CORD' in t): return 'EXXX'

    if any(k in t for k in ['GİRİŞ TAHTASI','GIRIS TAHTASI','ENTRANCE BOARD']): return 'FXXX'
    if 'WOODEN' in t and 'BOARD' in t: return 'BXXX'
    floor_kw = ['FLOOR PLY','FLR PLY','FOOR PLY','FLOOR PLANK','FLR PLANK','FLOOR LOOSE','BREAKING FLOOR','BROKEN FLOOR','CONTAINER BOARD','TAHTA','WOODEN PLATES','WOODEN PLATE','WOODEN BOARD','WOODEN BOARDS','WOODEN PLANK','TABAN TAHTASI','BASEBOARD','BASE BOARD',
                'FLOOR IMPACT','ALL FLOOR','FULL FLOOR','FASTNER','FASTENER',
                'NAILS','FLOOR BRKN','FLR BRKN','FLOOR DIRTY','FLOOR GOUGES',
                'FLOOR DL','FLOOR SEC','TAR REMOVE','TAR ','BASEBOARD','BASE BOARD']
    if any(k in t for k in floor_kw): return 'BXXX'

    if any(k in t for k in ['ENTRANCE BOARD','GİRİŞ TAHTASI','GIRIS TAHTASI']): return 'FXXX'
    if 'CEILING' in t or 'TAVAN' in t: return 'TXXX'

    if any(k in t for k in ['COLD WASH','CHEMICAL WASH','DETERGENT WASH','HOT WATER WASH','STEAM WASH','HOT WASH',
                            'SICAK SU ILE YIKAMA','SICAK YIKAMA','SICAK YIMAMA','KIMYASAL YIKAMA']) or 'WASH' in t or 'YIKAMA' in t: return 'IXXX'

    if any(k in t for k in ['INT PNL','INT N ','INTERNAL PANEL','INT PANEL',
                              'INT. PNL','INT.PNL','LASHING','GUM TAPE','GUM STICKER',
                              'OLD RESIDUE','RESIDUE','CARGO RESIDUE']): return 'IXXX'
    if ('GAP' in t or 'BOŞLUK' in t) and any(k in t for k in ['BOARD','TAHTA','FLOOR']): return 'BXXX'
    if any(k in t for k in ['EXT PNL','EXT N ','EXTERNAL PANEL','EXT PANEL']): return 'EXXX'
    if any(k in t for k in ['DECAL','DECULS','DECCULS','DEACULS','WEIGHT DECAL',
                              'CONT NO','CSC PLATE','CSC','DEACAL',
                              'STICKER','HAZ STICKER','CARGO STICKER','HAZ LABEL','LABEL']) and 'DOOR' not in t: return 'EXXX'
    if any(k in t for k in ['DECAL','DECULS','DECCULS','DEACULS','WEIGHT DECAL',
                              'CONT NO']) and 'DOOR' in t: return 'DXXX'

    if ('FRONT' in t and 'SILL' in t) or 'F/SILL' in t: return 'FXXX'
    if ('REAR' in t and 'SILL' in t) or 'DOOR SILL' in t: return 'DBXX'
    if 'ARKA PANEL' in t or 'BACK PANEL' in t: return 'DXXX'
    if ('FRONT' in t and 'HEADER' in t) or 'F/HEADER' in t: return 'FTXX'
    if 'FRONT' in t and 'HEP' in t: return 'FTXX'
    if 'FRONT TOP RAIL' in t: return 'FTXX'
    if any(k in t for k in ['FRONT PNL','FRONT PANEL','F/PNL','FRONT N ','ÖN PANEL','ON PANEL','ÖN PANELDE']): return 'FXXX'
    if 'FRONT' in t and 'GUSSET' in t: return 'FXXX'
    if 'REAR' in t and ('HEADER' in t or 'HEP' in t): return 'DBXX'
    if 'DOOR HEADER' in t: return 'DTXX'
    if 'GOOSENECK' in t or ('GROOVE' in t and 'SIDE BEAM' in t): return 'FGXX'

    door_kw = ['R/DOOR','L/DOOR','B/DOOR','BOTH DOOR','R/D ','L/D ','DOOR','KAPI CONTASI','KAPI CONTA','CONTA','DOOR STOPPER','STOPPER','HNGE','GUIDE','BIG GUIDE','CONTAINER ROD',' ROD ',
               'KEEPER','LOCK ROD','L/ROD','BTM CAM','LOCKROD','L/CATCH',
               'J BAR','HINGE','ALLIGN','ALIGN','JAM TO FREE','FREE UP',
               'BTM GASKET','TOP GASKET','V/GASKET','GSKT','RETAINER']
    if any(k in t for k in door_kw):
        if 'TOP GASKET' in t or 'TOP FRAME' in t: return 'DTXX'
        if 'BTM GASKET' in t or 'BTM FRAME' in t: return 'DGXX'
        return 'DXXX'

    if any(k in t for k in ['L/SIDE','L/S ','LEFT SIDE','SOL ','SOL	']) or re.match(r'^L/S\b', t) or t.startswith('SOL '):
        if 'TOP RAIL' in t: return 'LTXX'
        if 'BTM RAIL' in t or 'BOTTOM RAIL' in t: return 'LBXX'
        if 'CORNER POST' in t or 'C/POST' in t or 'F/C/POST' in t: return 'LXXX'
        m2 = re.search(r'(\d+)(?:ST|ND|RD|TH)?', t)
        return f"LX{int(m2.group(1)):02d}" if m2 else 'LXXX'

    if any(k in t for k in ['R/SIDE','R/S ','RIGHT SIDE','SAG ','SAĞ ','SAĞ PANEL','SAG PANEL','RIGHT PANEL']) or re.match(r'^R/S\b', t):
        if 'TOP RAIL' in t: return 'RTXX'
        if 'BTM RAIL' in t or 'BOTTOM RAIL' in t: return 'RBXX'
        if 'CORNER POST' in t or 'C/POST' in t or 'F/C/POST' in t: return 'RXXX'
        m2 = re.search(r'(\d+)(?:ST|ND|RD|TH)?', t)
        return f"RX{int(m2.group(1)):02d}" if m2 else 'RXXX'

    if 'TOP RAIL' in t: return 'TXXX'
    if any(k in t for k in ['CORNER POST','C/POST','CPP']): return 'XXXX'

    # Generic panel with side/position keywords (no L/SIDE or R/SIDE prefix used)
    if 'PANEL' in t or 'PNL' in t:
        if 'UPPER LEFT' in t and 'FRONT' in t: return 'FXXX'
        if 'UPPER LEFT' in t and 'REAR' in t: return 'DTXX'
        if 'UPPER RIGHT' in t: return 'EXXX'
        if 'LEFT' in t: return 'LXXX'
        if 'RIGHT' in t: return 'RXXX'
        if 'REAR' in t: return 'DXXX'
        if 'FRONT' in t: return 'FXXX'
        return 'EXXX'

    return CMP_DEFAULT_LOC.get(cmp_code, 'XXXX')

# ── 8b. CHECK THE MANUAL_OVERRIDES DICTIONARY ────────────────────────────────
def check_manual_override(text):
    """
    Looks through MANUAL_OVERRIDES (defined near the top of the file) to see
    if any of the phrases you typed in show up in this row's text.
    - If a match is found, returns the 4 codes you typed as a dictionary.
    - If nothing matches, returns None, and the automatic rules run as normal.
    """
    tu = str(text).upper()
    for phrase, codes in MANUAL_OVERRIDES.items():
        if phrase.upper() in tu:
            parts = [p.strip() for p in codes.split(',')]
            if len(parts) == 4:
                return {'LOCN': parts[0], 'CMP': parts[1], 'DMG': parts[2], 'RPR': parts[3]}
            print(f"Warning: MANUAL_OVERRIDES entry '{phrase}' should have exactly "
                  f"4 comma-separated codes (LOCN,CMP,DMG,RPR) - got '{codes}'. Skipping it.")
    return None

# ── 9. PROCESS ONE ROW ────────────────────────────────────────────────────────
def process_row(text, row_vals=None):
    raw = str(text).strip()
    if not raw or raw.lower() == 'nan': return None   # preserve empty row gaps
    if re.search(r'\bSEVERAL\b', raw.upper()) and 'MISSING' in raw.upper():
        l, w = extract_dims(raw)
        return dict(LOCN='XXXX', CMP='ZZZ', DMG='ZZ', RPR='ZZ', LENGTH=l, WIDTH=w, USD=None)
    if re.match(r'^MOVE\b', raw.upper()) or re.match(r'^LIFT\b', raw.upper()):
        usd_val = extract_usd([raw]) if raw else None
        return dict(LOCN='XXXX', CMP='ZZZ', DMG='ZZ', RPR='ZZ', LENGTH=0, WIDTH=0, USD=usd_val)

    # Check your manual dictionary FIRST, before any automatic guessing happens.
    override = check_manual_override(raw)
    if override:
        raw_clean = translate(strip_usd(raw))
        l, w = extract_dims(raw_clean)
        usd  = extract_usd(row_vals) if row_vals else None
        return dict(LOCN=override['LOCN'], CMP=override['CMP'], DMG=override['DMG'],
                     RPR=override['RPR'], LENGTH=l, WIDTH=w, USD=usd)

    raw   = translate(strip_usd(raw))
    cmp_  = get_cmp(raw)
    dmg   = get_dmg(raw)
    rpr   = get_rpr(raw, dmg)
    locn  = get_locn(raw, cmp_, dmg, rpr)
    l, w  = extract_dims(raw)
    usd   = extract_usd(row_vals) if row_vals else None
    return dict(LOCN=locn, CMP=cmp_, DMG=dmg, RPR=rpr, LENGTH=l, WIDTH=w, USD=usd)

# ── 10. MAIN ──────────────────────────────────────────────────────────────────
def main(inp, out):
    try:
        df = pd.read_excel(inp, header=None, dtype=str, engine='openpyxl')
    except Exception:
        df = pd.read_excel(inp, header=None, dtype=str)

    rows_out, has_usd = [], False
    for _, row in df.iterrows():
        desc = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ''
        res  = process_row(desc, [str(v) for v in row])
        if res and res['USD'] is not None: has_usd = True
        rows_out.append(res)

    cols = ['LOCN','CMP','DMG','RPR','LENGTH','WIDTH']
    if has_usd: cols.append('TOTAL(USD)')

    out_data = []
    for res in rows_out:
        if res is None:
            out_data.append({c:'' for c in cols})
        else:
            rd = {c: res.get(c,'') for c in cols}
            if has_usd: rd['TOTAL(USD)'] = res['USD'] if res['USD'] is not None else ''
            out_data.append(rd)

    out_df = pd.DataFrame(out_data, columns=cols)
    try:
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            out_df.to_excel(writer, index=False, sheet_name='CEDEX')
            ws = writer.sheets['CEDEX']
            from openpyxl.styles import Font, PatternFill, Alignment
            hf = PatternFill('solid', start_color='1F4E79')
            for cell in ws[1]:
                cell.fill = hf
                cell.font = Font(bold=True, color='FFFFFF', name='Arial', size=10)
                cell.alignment = Alignment(horizontal='center')
            widths = {'LOCN':9,'CMP':8,'DMG':7,'RPR':7,'LENGTH':9,'WIDTH':8,'TOTAL(USD)':13}
            for i,col in enumerate(cols,1):
                ws.column_dimensions[ws.cell(1,i).column_letter].width = widths.get(col,10)
            lf = PatternFill('solid', start_color='EBF3FB')
            for ri, rd in enumerate(out_data, 2):
                is_empty = all(str(v)=='' for v in rd.values())
                for cell in ws[ri]:
                    cell.font = Font(name='Arial', size=10)
                    cell.alignment = Alignment(horizontal='center')
                    if not is_empty and ri % 2 == 0: cell.fill = lf
    except Exception:
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            out_df.to_excel(writer, index=False, sheet_name='CEDEX')

    total = sum(1 for r in rows_out if r is not None)
    print(f"Done — {total} rows written to: {out}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python cedex_converter.py input.xlsx output.xlsx"); sys.exit(1)
    if not os.path.exists(sys.argv[1]):
        print(f"Error: {sys.argv[1]} not found"); sys.exit(1)
    main(sys.argv[1], sys.argv[2])