#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 1.5 — OPEN 건 공고서 자동 확인
docs/data/bids.json 의 OPEN 건에 대해 API 첨부(docUrl / docs)를 내려받아 텍스트를 뽑고,
5분 게이트 항목(기준 v0.2 §2)을 정규식으로 추출해 docs/data/notices/<id>.json 에 저장한다.

추출 항목: 공동수급 / 하도급 / 실적요건 / 배점·차등제 / 제출방식 / 대기업 참여제한 / 지역제한 / 사업설명회
판단은 하지 않는다 — 원문 문장을 그대로 잘라 보여주고, 사람이 읽는다.

사용: python3 read_notice.py            # OPEN 전건 (이미 처리한 건은 건너뜀)
      python3 read_notice.py --force    # 전부 다시
      python3 read_notice.py R26BK01726222-000
필요: pip install pyhwp  (hwp5txt) · apt: poppler-utils (pdftotext)
"""
import json, os, re, sys, io, zipfile, subprocess, tempfile, urllib.request, urllib.parse, datetime as dt, hashlib, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))   # olefile·pypdf 동봉 (pip 불필요)
# pypdf 는 import 시 시스템 cryptography 를 자동으로 불러온다. 컨테이너의 cryptography 가 깨져 있으면
# 파이썬 예외가 아닌 러스트 패닉(BaseException)으로 프로세스가 죽으므로, 암호화 PDF 지원을 포기하고 차단한다.
for _m in ("cryptography", "Crypto"):
    sys.modules.setdefault(_m, None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rfp_brief
try:
    import hwp_text   # 내장 HWP 5.0 파서
except Exception as _e:
    hwp_text = None

DATA = "docs/data"; OUT = f"{DATA}/notices"
UA = {"User-Agent": "Mozilla/5.0 (bid-radar; +https://github.com/raccoonstellar/bid-radar)"}
MAX_BYTES = 40 * 1024 * 1024
PARSER = 4

# ── 항목별 패턴: (라벨, 정규식, 앞뒤 문맥 길이) ──────────────────────────
PATTERNS = {
  "공동수급": (r"공동\s*수급|공동\s*도급|공동\s*계약|공동이행|분담이행|주계약자", 70),
  "하도급":   (r"하도급|하수급|재하도급|하청", 80),
  "실적요건": (r"(유사|동종|동일)\s*(용역|사업|실적)|실적\s*(증명|요건|제한|기준)|수행\s*실적|납품\s*실적|최근\s*\d+\s*년", 90),
  "배점":     (r"기술\s*(능력)?\s*평가\s*(\d{2,3})\s*[%점]|가격\s*평가\s*(\d{1,2})\s*[%점]|기술\s*[:：]\s*가격|(기술|가격|배점|평가)[^0-9\n]{0,10}\d{2}\s*[:：]\s*\d{2}(?!\s*[:：~]|\s*까지)|차등\s*(점수|평가|제)|배점\s*(기준|표|한도)|정성\s*평가|정량\s*평가|협상\s*적격|평가\s*항목", 110),
  "제출방식": (r"방문\s*제출|직접\s*제출|우편\s*제출|전자\s*제출|나라장터\s*(를 통해|로)\s*제출|제출\s*(방법|장소|부수)|인쇄본|USB|CD|날인|간인", 80),
  "대기업":   (r"대기업\s*(참여|입찰)\s*(제한|불가)|중소기업\s*(간|자간)\s*경쟁|중견기업|소프트웨어\s*진흥법\s*제?\s*48|상호출자제한", 80),
  "지역제한": (r"지역\s*(제한|의무)|소재지\s*(제한|기준)|본점\s*소재|관내\s*업체", 70),
  "사업설명회": (r"사업\s*설명회|제안\s*설명회|현장\s*설명회", 70),
  "직접생산": (r"직접\s*생산\s*확인|직접생산증명", 70),
  "제안서마감": (r"제안서\s*(제출|접수)\s*(마감|기한|일시)", 70),
  "사업기간": (r"(사업|계약|용역|과업|수행)\s*기간", 60),
  "과업내용": (r"과업\s*(범위|내용|개요)|사업\s*(개요|목적|범위)|주요\s*(과업|내용|기능)", 140),
}
YESNO = {  # 라벨별 빠른 판정 힌트 (문맥에 이 단어가 있으면)
  "공동수급": {"허용": r"허용|가능|인정", "불허": r"불허|불가|허용하지\s*않|금지"},
  "하도급":   {"금지": r"금지|불가|할\s*수\s*없", "승인필요": r"승인|사전\s*협의", "허용": r"허용|가능"},
  "대기업":   {"제한": r"제한|불가|없습니다|없다", "허용": r"허용|가능"},
  "제출방식": {"방문": r"방문|직접|인쇄|USB|CD|날인", "전자": r"전자|나라장터|온라인"},
}

def log(*a): print(*a, file=sys.stderr, flush=True)

# ── 제안요청서(e-발주) 첨부 — 공고 첨부(ntceSpecDocUrl)와 별도 오퍼레이션 ──────────
# 입찰공고정보서비스 getBidPblancListInfoEorderAtchFileInfo: 공고번호 단건 조회 불가 → 날짜 구간(최대 30일)으로 받아 공고번호로 붙인다
EORDER = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoEorderAtchFileInfo"
def eorder_attachments(bgn: dt.date, end: dt.date):
    key = os.environ.get("G2B_KEY", "")
    out = {}
    if not key: return out
    cur = bgn
    while cur <= end:
        stop = min(end, cur + dt.timedelta(days=29))
        page, total = 1, None
        while True:
            q = {"inqryDiv": "1", "type": "json", "inqryBgnDt": cur.strftime("%Y%m%d") + "0000", "inqryEndDt": stop.strftime("%Y%m%d") + "2359",
                 "pageNo": str(page), "numOfRows": "500", "ServiceKey": key}
            j = None
            for a in range(5):
                try:
                    with urllib.request.urlopen(EORDER + "?" + urllib.parse.urlencode(q, safe=""), timeout=60) as r:
                        j = json.loads(r.read().decode("utf-8", "replace")); break
                except Exception as e:
                    last = e; import time; time.sleep(2 * (a + 1))
            if j is None: log(f"  ! 제안요청서 첨부 조회 실패 {cur}~{stop} p{page}"); break
            hdr = j.get("response", {}).get("header", {})
            if hdr.get("resultCode") not in ("00", "0"): log(f"  ! 제안요청서 첨부 {hdr.get('resultCode')} {hdr.get('resultMsg')}"); break
            bd = j.get("response", {}).get("body", {}) or {}
            items = bd.get("items") or []
            if isinstance(items, dict): items = items.get("item", []) or []
            if isinstance(items, dict): items = [items]
            for it in items:
                u = it.get("eorderAtchFileUrl")
                if not u: continue
                bid = f'{it.get("bidNtceNo","")}-{str(it.get("bidNtceOrd") or "000").zfill(3)}'
                out.setdefault(bid, []).append({"url": u, "name": it.get("eorderAtchFileNm") or "", "doc": it.get("eorderDocDivNm") or "제안요청서", "sno": it.get("atchSno")})
            total = int(bd.get("totalCount") or 0)
            if page * 500 >= total or page >= 20: break
            page += 1
        cur = stop + dt.timedelta(days=1)
    return out

def download(url, tries=5):
    last = None
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                cd = r.headers.get("Content-Disposition", "")
                name = ""
                m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
                if m: name = urllib.parse.unquote(m.group(1))
                data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES: raise RuntimeError("파일 40MB 초과")
            return data, name or os.path.basename(urllib.parse.urlparse(url).path)
        except Exception as e:
            last = e; import time; time.sleep(2 * (a + 1))
    raise RuntimeError(f"다운로드 실패({tries}회): {last}")

def sniff(data, name):
    n = name.lower()
    if data[:4] == b"%PDF": return "pdf"
    if data[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(data)); names = z.namelist()
            if any(x.startswith("Contents/") for x in names) or n.endswith(".hwpx"): return "hwpx"
            if any(x.startswith("word/") for x in names): return "docx"
            if n.endswith(".zip"): return "zip"
        except Exception: pass
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or n.endswith(".hwp"): return "hwp"
    if n.endswith(".txt"): return "txt"
    return "unknown"

def text_hwpx(data):
    z = zipfile.ZipFile(io.BytesIO(data)); out = []
    for nm in sorted(z.namelist()):
        if nm.startswith("Contents/section") and nm.endswith(".xml"):
            xml = z.read(nm).decode("utf-8", "replace")
            xml = re.sub(r"</hp:p>|</hp:tc>|<hp:lineBreak/>", "\n", xml)
            out.append(re.sub(r"<[^>]+>", "", xml))
    return "\n".join(out)

def text_docx(data):
    z = zipfile.ZipFile(io.BytesIO(data)); xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>|</w:tc>", "\n", xml); return re.sub(r"<[^>]+>", "", xml)

def run(cmd, data, suffix):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f: f.write(data); p = f.name
    try:
        r = subprocess.run(cmd + [p], capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", "replace")
    finally: os.unlink(p)

def text_pdf(data):
    if shutil.which("pdftotext"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f: f.write(data); p = f.name
        try:
            r = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, timeout=120)
            t = r.stdout.decode("utf-8", "replace")
            if len(t.strip()) > 100: return t
        finally: os.unlink(p)
    try:   # 동봉 pypdf (vendor/)
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data)); return "\n".join((pg.extract_text() or "") for pg in rd.pages[:80])
    except (KeyboardInterrupt, SystemExit): raise
    except BaseException as e:   # 러스트 패닉 등 비표준 예외까지
        return f"[추출 실패: pypdf — {type(e).__name__}: {str(e)[:120]}]"

HWP_TOOL = shutil.which("hwp5txt")
def text_hwp(data):
    # 1) 내장 파서 (설치 불필요)
    if hwp_text:
        try:
            t, note = hwp_text.extract(data)
            if len(t.strip()) > 100: return t
            if note: log(f"    hwp 내장파서: {note}")
        except Exception as e:
            log(f"    hwp 내장파서 오류: {e}")
    # 2) hwp5txt 가 있으면
    if HWP_TOOL:
        t = run([HWP_TOOL], data, ".hwp")
        if len(t.strip()) > 100: return t
    return ""

def _extract_text(data, name):
    kind = sniff(data, name)
    try:
        if kind == "pdf":  return kind, text_pdf(data)
        if kind == "hwpx": return kind, text_hwpx(data)
        if kind == "docx": return kind, text_docx(data)
        if kind == "hwp":  return kind, text_hwp(data)
        if kind == "txt":  return kind, data.decode("utf-8", "replace")
        if kind == "zip":
            z = zipfile.ZipFile(io.BytesIO(data)); parts = []
            for nm in z.namelist():
                if re.search(r"\.(hwpx?|pdf|docx)$", nm, re.I):
                    k, t = extract_text(z.read(nm), nm); parts.append(f"\n\n===== {nm} =====\n{t}")
            return "zip", "".join(parts)
    except (KeyboardInterrupt, SystemExit): raise
    except BaseException as e:
        return kind, f"[추출 실패: {type(e).__name__}: {str(e)[:120]}]"
    return kind, ""

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u00a0\u2000-\u200b\u3000\ufeff]")
def clean_text(t):
    """NUL·제어문자·특수 공백 → 일반 공백 (PDF·HWP 일부가 띄어쓰기를 \\x00 로 내보냄)"""
    return _CTRL.sub(" ", t or "")

def extract_text(data, name):
    kind, text = _extract_text(data, name)
    return kind, clean_text(text)

def scan(text):
    t = re.sub(r"[-–—_=─━~·.]{4,}", " ", text)                    # 구분선
    t = re.sub(r"(?m)^\s*-\s*\d+\s*-\s*$", "", t)                 # 쪽번호 "- 9 -"
    t = re.sub(r"[ \t\u3000]+", " ", t)
    found = {}
    for label, (pat, ctx) in PATTERNS.items():
        hits, last_e = [], -1
        for m in re.finditer(pat, t):
            if m.start() < last_e: continue          # 직전 문맥 창 안에 든 매치는 같은 문장 — 건너뛴다
            s, e = max(0, m.start() - ctx), min(len(t), m.end() + ctx)
            last_e = e
            snippet = re.sub(r"\s*\n\s*", " / ", t[s:e]).strip()
            if snippet not in hits: hits.append(snippet)
            if len(hits) >= 4: break
        verdict = ""
        if label in YESNO and hits:
            joined = " ".join(hits)
            for v, vp in YESNO[label].items():
                if re.search(vp, joined): verdict = v; break
        found[label] = {"n": len(hits), "verdict": verdict, "snippets": hits}
    found["배점"].update(parse_score(t))
    return found

# ── 배점 해석 (v2) — 숫자는 합이 맞을 때만 채택, 시각·날짜 오인 방지 ──────────────
_N = r"(\d{1,3}(?:\.\d)?)"
def _num(x):
    try: return float(x)
    except Exception: return None
def parse_score(t):
    out = {}
    T = re.sub(r"\s+", " ", clean_text(t))
    T = re.sub(r"(?<=\d) (?=\d)", "", T)                 # "9 0 점" → "90점" (HWP 글자 간격)
    T = re.sub(r"\( (?=\d)|(?<=[점%]) \)", lambda m: m.group(0).replace(" ", ""), T)
    # 1) 기술:가격 — "기술능력평가 90점 … 가격평가 10점", "기술(90%) 가격(10%)", "기술:가격 = 80:20"
    cands = []
    for m in re.finditer(r"기술\s*(?:능력)?\s*(?:평가)?\s*(?:점수|배점)?\s*[(:：]?\s*" + _N + r"\s*(?:점|%|％)[^가]{0,60}?가격\s*(?:제안)?\s*(?:평가)?\s*(?:점수|배점)?\s*[(:：]?\s*" + _N + r"\s*(?:점|%|％)", T):
        cands.append((m.group(1), m.group(2)))
    for m in re.finditer(r"가격\s*(?:평가)?\s*(?:점수|배점)?\s*[(:：]?\s*" + _N + r"\s*(?:점|%|％)[^기]{0,40}?기술\s*(?:능력)?\s*(?:평가)?\s*(?:점수|배점)?\s*[(:：]?\s*" + _N + r"\s*(?:점|%|％)", T):
        cands.append((m.group(2), m.group(1)))
    for m in re.finditer(r"기술[^.。]{0,40}?가격[^.。0-9]{0,20}?비율\s*(?:은|는|이)?\s*[:：]?\s*(\d{2})\s*[:：]\s*(\d{1,2})", T):
        cands.append((m.group(1), m.group(2)))
    for m in re.finditer(r"기술\s*[:：]\s*가격\s*[=＝]?\s*[(（]?\s*(\d{2})\s*[:：]\s*(\d{1,2})", T):
        cands.append((m.group(1), m.group(2)))
    for a, b in cands:
        a, b = _num(a), _num(b)
        if a and b is not None and abs(a + b - 100) < 0.01 and a >= 50:
            out["ratio"] = f"{a:g}:{b:g}"; break
    # 2) 정성·정량 (기술평가 내부 구성)
    q1 = re.search(r"정성\s*(?:적)?\s*평가\s*[(:：]?\s*" + _N + r"\s*점", T)
    q2 = re.search(r"정량\s*(?:적)?\s*평가\s*[(:：]?\s*" + _N + r"\s*점", T)
    if q1 and 0 < _num(q1.group(1)) <= 100: out["qual"] = f"{_num(q1.group(1)):g}"
    if q2 and 0 < _num(q2.group(1)) <= 100: out["quant"] = f"{_num(q2.group(1)):g}"
    if "ratio" not in out and out.get("qual") and out.get("quant"):
        tech = _num(out["qual"]) + _num(out["quant"])
        if 60 <= tech <= 95: out["ratio"] = f"{tech:g}:{100 - tech:g}"
    # 3) 협상적격 기준 — "기술능력평가 점수가 배점한도의 85% 이상"
    c = re.search(r"(?:기술\s*(?:능력)?\s*평가\s*(?:점수|결과)?[^.。]{0,30}?(?:배점\s*한도|배점)의?\s*)(\d{2})\s*(?:%|％|퍼센트)\s*이상", T) or \
        re.search(r"협상\s*적격[^.。]{0,40}?(\d{2})\s*(?:%|％|점)\s*이상", T)
    if c and 50 <= int(c.group(1)) <= 95: out["cutoff"] = c.group(1) + "%"
    # 4) 차등점수제 / 계약방식
    out["차등제"] = bool(re.search(r"차등\s*점수", T))
    if re.search(r"협상에\s*의한\s*계약", T): out["method"] = "협상"
    elif re.search(r"2\s*단계\s*경쟁", T): out["method"] = "2단계경쟁"
    elif re.search(r"적격\s*심사", T): out["method"] = "적격심사"
    return out

def urls_for(bid):
    """첨부 목록 [(url, name, doc)] — 공고문 PDF 변환본, 제안요청서(배점표), 나머지 순으로 읽는다"""
    urls = [u for u in (bid.get("docUrls") or []) if u and str(u).startswith("http")]
    names = bid.get("docs") or []
    items = [(u, n, "공고") for u, n in zip(urls, names + [""] * (len(urls) - len(names)))]
    for k in ("docUrl", "url1", "url2"):
        u = bid.get(k)
        if u and str(u).startswith("http") and all(u != p[0] for p in items): items.append((u, "", "공고"))
    for f in bid.get("rfp") or []:
        if all(f["url"] != p[0] for p in items): items.append((f["url"], f.get("name", ""), f.get("doc") or "제안요청서"))
    ext = lambda n: str(n).lower().rsplit(".", 1)[-1] if "." in str(n) else ""
    def rank(p):
        u, n, d = p
        if d == "공고" and ext(n) == "pdf": return 0
        if d != "공고" and re.search(r"제안요청|과업|RFP", d + n, re.I): return 1
        if ext(n) in ("pdf", "hwpx", "docx"): return 2
        return 3
    return sorted(items, key=rank)

def process(bid, force=False):
    bid_id = re.sub(r"[^A-Za-z0-9_.:@+-]", "-", bid["id"])
    path = f"{OUT}/{bid_id}.json"
    if os.path.exists(path) and not force:
        try:
            prev = json.load(open(path, encoding="utf-8"))
            # parser 3 = HWP 빈칸 복원·전 첨부 목록·사업기간·과업내용·배점 시각 오인 수정. 이전 기록은 한 번 다시 읽는다
            have = {f.get("url") for f in prev.get("files", [])}
            new_rfp = any(f["url"] not in have for f in bid.get("rfp") or [])   # 제안요청서가 뒤늦게 올라온 경우 다시 읽는다
            if prev.get("status") in ("ok", "no-attachment") and prev.get("parser", 1) >= PARSER and not new_rfp: return "skip"
        except Exception: pass   # 깨진 기록이면 다시
    items = urls_for(bid); urls = [p[0] for p in items]; meta = {p[0]: p for p in items}
    rec = {"id": bid["id"], "name": bid.get("name"), "parser": PARSER, "checkedAt": dt.datetime.now().isoformat(timespec="seconds"),
           "files": [], "gate": {}, "status": "no-attachment"}
    if not urls:
        json.dump(rec, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1); return "no-attachment"
    texts, read_rfp = [], False
    has_rfp = any(p[2] != "공고" for p in items)
    for u in urls[:7]:
        # 충분히 읽었어도 제안요청서(배점표)는 꼭 읽는다
        if sum(len(t) for t in texts) > 8000 and (read_rfp or not has_rfp): break
        _, nm0, doc = meta[u]
        if sum(len(t) for t in texts) > 8000 and doc == "공고": continue
        try:
            data, name = download(u); kind, text = extract_text(data, name or nm0)
            rec["files"].append({"url": u, "name": name or nm0, "doc": doc, "kind": kind, "bytes": len(data), "chars": len(text)})
            if text and not text.startswith("[추출 실패") and len(text.strip()) >= 200:
                texts.append(f"\n\n##### {name or nm0} #####\n{text}"); read_rfp = read_rfp or doc != "공고"
            elif text: rec["files"][-1]["error"] = f"텍스트 {len(text.strip())}자 — 추출 불충분({kind})"
        except Exception as e:
            rec["files"].append({"url": u, "name": nm0, "doc": doc, "error": str(e)[:200]})
    # 읽지 않은 첨부도 대시보드에서 내려받을 수 있게 목록에 남긴다
    done = {f["url"] for f in rec["files"]}
    for u in urls:
        if u not in done: rec["files"].append({"url": u, "name": meta[u][1] or "", "doc": meta[u][2], "unread": True})
    full = "".join(texts)
    if full.strip():
        rec["gate"] = scan(full); rec["status"] = "ok"; rec["textChars"] = len(full)
        os.makedirs(f"{OUT}/text", exist_ok=True)
        open(f"{OUT}/text/{bid_id}.txt", "w", encoding="utf-8").write(full[:400_000])
    else:
        rec["status"] = "extract-failed"
    json.dump(rec, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rec["status"]

def main():
    if "--brief-only" in sys.argv: build_briefs(); return
    force = "--force" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    os.makedirs(OUT, exist_ok=True)
    bids = json.load(open(f"{DATA}/bids.json", encoding="utf-8"))
    targets = [b for b in bids if b.get("bucket") == "OPEN" and (not only or b["id"] in only)]
    # 사전규격 — 본공고 전 과업 초안. 본공고가 아직 안 난 건만
    try: pre = json.load(open(f"{DATA}/prespec.json", encoding="utf-8"))
    except Exception: pre = []
    for p_ in pre:
        if p_.get("bidNos") or (only and p_["id"] not in only): continue
        fs = [f for f in p_.get("files", []) if f.get("url")]
        targets.append({"id": p_["id"], "name": p_.get("name"), "docUrls": [f["url"] for f in fs], "docs": [f.get("name", "") for f in fs]})
    # 제안요청서 첨부 — OPEN 건 중 가장 먼저 본 날 -3일 ~ 오늘 (최대 60일, 30일 단위 조회)
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()
    try: first = min(dt.date.fromisoformat(b["firstSeen"]) for b in targets if b.get("firstSeen"))
    except ValueError: first = today
    bgn = max(today - dt.timedelta(days=60), first - dt.timedelta(days=3))
    rfp = eorder_attachments(bgn, today)
    n_rfp = 0
    for b in targets:
        if b["id"] in rfp: b["rfp"] = rfp[b["id"]]; n_rfp += 1
    log(f"  · 제안요청서 첨부: 조회 {sum(len(v) for v in rfp.values())}건 · OPEN 중 {n_rfp}건에 붙음")
    stat = {}
    for b in targets:
        try: r = process(b, force)
        except (KeyboardInterrupt, SystemExit): raise
        except BaseException as e: r = f"error: {type(e).__name__}"
        stat[r.split(":")[0]] = stat.get(r.split(":")[0], 0) + 1
        log(f"  [{r}] {b['id']} {b.get('name','')[:40]}")
    # 인덱스
    idx = {}
    for fn in os.listdir(OUT):
        if fn.endswith(".json"):
            try:
                j = json.load(open(f"{OUT}/{fn}", encoding="utf-8"))
                g = j.get("gate", {})
                idx[j["id"]] = {"status": j["status"], "checkedAt": j["checkedAt"],
                    "joint": g.get("공동수급", {}).get("verdict", ""), "sub": g.get("하도급", {}).get("verdict", ""),
                    "ratio": g.get("배점", {}).get("ratio", ""), "diff": g.get("배점", {}).get("차등제", False),
                    "qual": g.get("배점", {}).get("qual", ""), "quant": g.get("배점", {}).get("quant", ""),
                    "cutoff": g.get("배점", {}).get("cutoff", ""), "method": g.get("배점", {}).get("method", ""),
                    "rfp": sum(1 for f in j.get("files", []) if f.get("doc") and f.get("doc") != "공고"),
                    "submit": g.get("제출방식", {}).get("verdict", ""), "big": g.get("대기업", {}).get("verdict", ""),
                    "region": g.get("지역제한", {}).get("n", 0) > 0, "perf": g.get("실적요건", {}).get("n", 0) > 0,
                    "files": len(j.get("files", [])),
                    "period": (g.get("사업기간", {}).get("snippets") or [""])[0][:160]}
            except Exception: pass
    json.dump(idx, open(f"{OUT}/index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    build_briefs()
    print(f"[공고서] 대상 {len(targets)}건 → {stat} · HWP파서={'내장' if hwp_text else ('hwp5txt' if HWP_TOOL else '없음')} · PDF={'pdftotext' if shutil.which('pdftotext') else 'pypdf(내장)'}")

def build_briefs():
    """공고서 텍스트 → 영업용 요약. 사전규격·OPEN 건만 docs/data/briefs.json 로 (대시보드가 바로 읽음)"""
    want = {}
    try: want.update({b["id"]: b.get("inst", "") for b in json.load(open(f"{DATA}/bids.json", encoding="utf-8")) if b.get("bucket") == "OPEN"})
    except Exception: pass
    try: want.update({p["id"]: p.get("inst", "") for p in json.load(open(f"{DATA}/prespec.json", encoding="utf-8"))})
    except Exception: pass
    out = {}
    for bid_id, inst in want.items():
        fn = f"{OUT}/text/{re.sub(r'[^A-Za-z0-9_.:@+-]', '-', bid_id)}.txt"
        if not os.path.exists(fn): continue
        try:
            b = rfp_brief.brief(open(fn, encoding="utf-8").read(), inst)
            if b: out[bid_id] = b
        except Exception as e: log(f"  ! brief {bid_id}: {e}")
    json.dump(out, open(f"{DATA}/briefs.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"[요약] {len(out)}/{len(want)}건")

if __name__ == "__main__":
    main()
