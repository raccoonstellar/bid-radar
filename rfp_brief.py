# -*- coding: utf-8 -*-
"""
제안요청서·과업지시서 텍스트 → 영업용 요약(brief).
사전영업·검토에 필요한 것만: 사업 목적, 주요 과업, 기능 요구사항 목록, 사업기간·예산, 참가자격,
설명회, 언급 업체(기존 사업자·제품 후보), 포지큐브 접점 키워드, HW 포함 여부.
판단은 하지 않는다 — 원문 줄을 골라 보여줄 뿐.
"""
import re

BRIEF_VER = 1
BULLET = r"^\s*(?:[◦○●◎ㅇ•·▪▶▷■□\-–∙⦁※*]|\(?\d{1,2}[).]|[가-하][.)]|[①-⑳])\s*"
_HEAD_STOP = re.compile(r"^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\.?|\d{1,2}\.\s*\S|제\s*\d+\s*장|□\s*\S|【)")

def _lines(t):
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f 　]", " ", t or "")
    out = []
    for l in t.split("\n"):
        l = re.sub(r"[ \t]+", " ", l).strip()
        if l: out.append(l)
    return out

def _is_toc(lines, i):
    # 목차: 제목 뒤에 쪽번호가 붙거나 다음 줄들이 짧은 제목+숫자 반복
    return bool(re.search(r"\s\d{1,3}$|\d{1,3}$", lines[i])) and len(lines[i]) < 40

def _clean(l, n=130):
    l = re.sub(BULLET, "", l).strip(" :：-")
    l = re.sub(r"\s{2,}", " ", l)
    return (l[:n] + "…") if len(l) > n else l

def section(lines, head_rx, max_items=5, min_len=8, scan=40):
    """head_rx 에 맞는 짧은 제목 줄을 찾아, 그 아래 글머리 줄을 max_items 개까지"""
    rx = re.compile(head_rx)
    for i, l in enumerate(lines):
        if len(l) > 45 or not rx.search(l) or _is_toc(lines, i): continue
        items = []
        # 제목 줄에 내용이 붙은 경우 ("사업기간 : 210일")
        for l2 in lines[i + 1:i + 1 + scan]:
            if items and _HEAD_STOP.match(l2) and not re.match(BULLET, l2): break
            if re.match(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]", l2): break
            c = _clean(l2)
            if len(re.findall(r"[가-힣]", c)) < 4: continue          # 이메일·숫자·코드만 있는 줄
            if len(c) < min_len or re.fullmatch(r"[\d\s.,%()~\-]+", c): continue
            if c in items: continue
            items.append(c)
            if len(items) >= max_items: break
        if items: return items
    return []

def field(lines, rx, n=90):
    r = re.compile(rx)
    for l in lines:
        m = r.search(l)
        if m:
            v = l[m.end():].strip(" :：-")
            if len(v) >= 2: return v[:n]
    return ""

REQ_KIND = {"SFR": "기능", "PER": "성능", "INR": "인터페이스", "DAR": "데이터", "TER": "테스트", "SER": "보안",
            "QUR": "품질", "COR": "제약", "PMR": "관리", "PSR": "지원", "ECR": "장비", "FUR": "기능", "UIR": "UI"}
def requirements(text):
    ids = {}
    for m in re.finditer(r"\b(" + "|".join(REQ_KIND) + r")\s*-\s*(\d{2,3})\b", text):
        ids.setdefault(m.group(1), set()).add(m.group(2))
    counts = {REQ_KIND[k]: len(v) for k, v in ids.items()}
    # 기능 요구사항 명칭: "SFR-001\n\n명칭" 또는 "SFR-001 명칭"
    names, seen = [], set()
    for m in re.finditer(r"\b(SFR|FUR)\s*-\s*(\d{2,3})\b[\s|/]*\n?\s*([^\n|]{3,48})", text):
        k = m.group(1) + m.group(2); nm = m.group(3).strip()
        if k in seen or re.match(r"^(SFR|FUR|PER|요구사항|세부|정의|ID|고유)", nm) or len(re.sub(r"[^가-힣A-Za-z]", "", nm)) < 3: continue
        seen.add(k); names.append(nm)
        if len(names) >= 12: break
    return counts, names

_CO_EXCL = r"^(조달청|발주|수요|계약|제안|사업|용역|중앙회|재단|공사|공단|본|당사|귀사|업체|회사|기관|정보)"
_CO_STOP = {"내용","기타","가짐","사항","공고한","번지","수행사인","제안사","입찰자","낙찰자","계약자","참가자","사업자","발주처","귀하","대표자"}
def companies(text, inst=""):
    found = {}
    for m in re.finditer(r"(?:㈜|\(주\)|주식회사)\s*([가-힣A-Za-z][가-힣A-Za-z0-9&]{1,14})|([가-힣A-Za-z][가-힣A-Za-z0-9&]{1,14})\s*(?:㈜|\(주\))", text):
        nm = (m.group(1) or m.group(2)).strip()
        nm = re.sub(r"(의|에서|에게|와|과|는|은|이|가|를|을|로|으로|에)$", "", nm)
        if len(nm) < 3 or re.fullmatch(r"[O○X×]+", nm) or nm in _CO_STOP or re.search(r"(하고자|하여|에서|하는|한다|합니다)$", nm): continue
        if re.match(_CO_EXCL, nm) or (inst and nm in inst): continue
        found[nm] = found.get(nm, 0) + 1
    return [k for k, _ in sorted(found.items(), key=lambda x: -x[1])][:6]

POSI = ["챗봇", "콜봇", "보이스봇", "AICC", "IPCC", "콜센터", "상담", "STT", "TTS", "음성인식", "음성합성",
        "LLM", "생성형", "RAG", "에이전트", "OCR", "문서", "검색", "지식", "요약", "민원"]
def posi_hits(text):
    out = []
    for k in POSI:
        n = len(re.findall(re.escape(k), text, re.I if k.isascii() else 0))
        if n: out.append((k, n))
    out.sort(key=lambda x: -x[1])
    return out[:8]

def brief(text, inst=""):
    if not text or len(text) < 300: return {}
    L = _lines(text)
    b = {"v": BRIEF_VER}
    b["purpose"] = section(L, r"(추진\s*배경|배경\s*및\s*(목적|필요성)|사업\s*(목적|배경|필요성)|추진\s*목적|필요성)", 3)
    b["scope"] = section(L, r"(주요\s*(사업|과업)\s*(내용|범위)|사업\s*(내용|범위)|과업\s*(내용|범위|개요|목록)|주요\s*내용|추진\s*내용|구축\s*범위|용역\s*(범위|내용))", 6)
    b["period"] = field(L, r"(사업|계약|용역|과업|수행)\s*기간\s*[:：]")
    b["budget"] = field(L, r"(사업|소요|배정)\s*(예산|금액)\s*[:：]")
    b["method"] = field(L, r"계약\s*방법\s*[:：]")
    # 참가자격: 법령 상투 문구는 빼고 업종·중소기업·공동수급·직접생산처럼 판단에 쓰는 줄만
    q = section(L, r"입찰\s*참가\s*자격|참가\s*자격", 12, 10, 60)
    keep = re.compile(r"업종|소프트웨어사업자|중소|소상공인|공동\s*수급|컨소시엄|직접생산|실적|지역|본사|소재|대기업|중견")
    drop = re.compile(r"부정당|제12조|제14조|제76조|제27조|요건을\s*갖춘\s*자$|다음\s*요건|서약|이의\s*제기")
    b["qual"] = [x for x in q if keep.search(x) and not drop.search(x)][:4]
    br = ""
    for l in L:
        if re.search(r"(제안\s*요청|사업|제안|현장)\s*설명회", l) and re.search(r"\d{1,2}\s*[월./]\s*\d{1,2}|\d{4}\s*[.\-년]", l):
            br = _clean(l, 100); break
    b["briefing"] = br
    cnt, names = requirements(text)
    b["reqCount"] = cnt; b["reqNames"] = names
    b["companies"] = companies(text, inst)
    b["posi"] = posi_hits(text)
    hw = len(re.findall(r"GPU|서버\s*(도입|구매|구축)|스토리지|H100|H200|A100|L40S|하드웨어\s*도입", text))
    if hw >= 3: b["hw"] = hw
    b["closedInfo"] = bool(re.search(r"비공개.{0,20}(방문\s*열람|열람\s*가능)", text))
    return {k: v for k, v in b.items() if v not in ("", [], {}, None, False)}
