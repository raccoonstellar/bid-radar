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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import hwp_text   # 내장 HWP 5.0 파서
except Exception as _e:
    hwp_text = None

DATA = "docs/data"; OUT = f"{DATA}/notices"
UA = {"User-Agent": "Mozilla/5.0 (bid-radar; +https://github.com/raccoonstellar/bid-radar)"}
MAX_BYTES = 40 * 1024 * 1024

# ── 항목별 패턴: (라벨, 정규식, 앞뒤 문맥 길이) ──────────────────────────
PATTERNS = {
  "공동수급": (r"공동\s*수급|공동\s*도급|공동\s*계약|공동이행|분담이행|주계약자", 70),
  "하도급":   (r"하도급|하수급|재하도급|하청", 80),
  "실적요건": (r"(유사|동종|동일)\s*(용역|사업|실적)|실적\s*(증명|요건|제한|기준)|수행\s*실적|납품\s*실적|최근\s*\d+\s*년", 90),
  "배점":     (r"기술\s*(능력)?\s*평가\s*(\d{2,3})\s*[%점]|가격\s*평가\s*(\d{1,2})\s*[%점]|기술\s*[:：]\s*가격|(\d{2})\s*[:：]\s*(\d{2})|차등\s*(점수|평가|제)|배점\s*(기준|표)", 90),
  "제출방식": (r"방문\s*제출|직접\s*제출|우편\s*제출|전자\s*제출|나라장터\s*(를 통해|로)\s*제출|제출\s*(방법|장소|부수)|인쇄본|USB|CD|날인|간인", 80),
  "대기업":   (r"대기업\s*(참여|입찰)\s*(제한|불가)|중소기업\s*(간|자간)\s*경쟁|중견기업|소프트웨어\s*진흥법\s*제?\s*48|상호출자제한", 80),
  "지역제한": (r"지역\s*(제한|의무)|소재지\s*(제한|기준)|본점\s*소재|관내\s*업체", 70),
  "사업설명회": (r"사업\s*설명회|제안\s*설명회|현장\s*설명회", 70),
  "직접생산": (r"직접\s*생산\s*확인|직접생산증명", 70),
  "제안서마감": (r"제안서\s*(제출|접수)\s*(마감|기한|일시)", 70),
}
YESNO = {  # 라벨별 빠른 판정 힌트 (문맥에 이 단어가 있으면)
  "공동수급": {"허용": r"허용|가능|인정", "불허": r"불허|불가|허용하지\s*않|금지"},
  "하도급":   {"금지": r"금지|불가|할\s*수\s*없", "승인필요": r"승인|사전\s*협의", "허용": r"허용|가능"},
  "대기업":   {"제한": r"제한|불가|없습니다|없다", "허용": r"허용|가능"},
  "제출방식": {"방문": r"방문|직접|인쇄|USB|CD|날인", "전자": r"전자|나라장터|온라인"},
}

def log(*a): print(*a, file=sys.stderr, flush=True)

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
    except Exception as e:
        return f"[추출 실패: pdftotext/pypdf 없음 — {e}]"

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

def extract_text(data, name):
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
    except Exception as e:
        return kind, f"[추출 실패: {e}]"
    return kind, ""

def scan(text):
    t = re.sub(r"[ \t\u3000]+", " ", text)
    found = {}
    for label, (pat, ctx) in PATTERNS.items():
        hits = []
        for m in re.finditer(pat, t):
            s, e = max(0, m.start() - ctx), min(len(t), m.end() + ctx)
            snippet = re.sub(r"\s*\n\s*", " / ", t[s:e]).strip()
            if snippet not in hits: hits.append(snippet)
            if len(hits) >= 4: break
        verdict = ""
        if label in YESNO and hits:
            joined = " ".join(hits)
            for v, vp in YESNO[label].items():
                if re.search(vp, joined): verdict = v; break
        found[label] = {"n": len(hits), "verdict": verdict, "snippets": hits}
    # 배점 숫자 추출 (기술:가격)
    m = re.search(r"기술[^0-9]{0,12}(\d{2,3})\s*[%점][^0-9]{0,20}가격[^0-9]{0,12}(\d{1,2})\s*[%점]", t) or \
        re.search(r"(\d{2})\s*[:：]\s*(\d{2})", " ".join(found["배점"]["snippets"]))
    if m: found["배점"]["ratio"] = f"{m.group(1)}:{m.group(2)}"
    found["배점"]["차등제"] = bool(re.search(r"차등", " ".join(found["배점"]["snippets"])))
    return found

def urls_for(bid):
    """첨부 URL 목록 — 나라장터는 HWP 원본과 PDF 변환본을 병행 등록하므로 PDF 를 앞에 둔다"""
    urls = [u for u in (bid.get("docUrls") or []) if u and str(u).startswith("http")]
    names = bid.get("docs") or []
    pairs = list(zip(urls, names + [""] * (len(urls) - len(names))))
    for k in ("docUrl", "url1", "url2"):
        u = bid.get(k)
        if u and str(u).startswith("http") and all(u != p[0] for p in pairs): pairs.append((u, ""))
    rank = lambda p: (0 if str(p[1]).lower().endswith(".pdf") else 1 if str(p[1]).lower().endswith(".hwpx") else 2 if str(p[1]).lower().endswith(".docx") else 3)
    pairs.sort(key=rank)
    return [p[0] for p in pairs]

def process(bid, force=False):
    bid_id = re.sub(r"[^A-Za-z0-9_.:@+-]", "-", bid["id"])
    path = f"{OUT}/{bid_id}.json"
    if os.path.exists(path) and not force:
        try:
            prev = json.load(open(path, encoding="utf-8"))
            if prev.get("status") in ("ok", "no-attachment"): return "skip"
        except Exception: pass   # 깨진 기록이면 다시
    urls = urls_for(bid)
    rec = {"id": bid["id"], "name": bid.get("name"), "checkedAt": dt.datetime.now().isoformat(timespec="seconds"),
           "files": [], "gate": {}, "status": "no-attachment"}
    if not urls:
        json.dump(rec, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1); return "no-attachment"
    texts = []
    for u in urls[:5]:
        if sum(len(t) for t in texts) > 8000: break   # 이미 충분히 읽음
        try:
            data, name = download(u); kind, text = extract_text(data, name)
            rec["files"].append({"url": u, "name": name, "kind": kind, "bytes": len(data), "chars": len(text)})
            if text and not text.startswith("[추출 실패") and len(text.strip()) >= 200: texts.append(f"\n\n##### {name} #####\n{text}")
            elif text: rec["files"][-1]["error"] = f"텍스트 {len(text.strip())}자 — 추출 불충분({kind})"
        except Exception as e:
            rec["files"].append({"url": u, "error": str(e)[:200]})
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
    force = "--force" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    os.makedirs(OUT, exist_ok=True)
    bids = json.load(open(f"{DATA}/bids.json", encoding="utf-8"))
    targets = [b for b in bids if b.get("bucket") == "OPEN" and (not only or b["id"] in only)]
    stat = {}
    for b in targets:
        try: r = process(b, force)
        except Exception as e: r = f"error: {e}"
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
                    "submit": g.get("제출방식", {}).get("verdict", ""), "big": g.get("대기업", {}).get("verdict", ""),
                    "region": g.get("지역제한", {}).get("n", 0) > 0, "perf": g.get("실적요건", {}).get("n", 0) > 0,
                    "files": len(j.get("files", []))}
            except Exception: pass
    json.dump(idx, open(f"{OUT}/index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"[공고서] 대상 {len(targets)}건 → {stat} · HWP파서={'내장' if hwp_text else ('hwp5txt' if HWP_TOOL else '없음')} · PDF={'pdftotext' if shutil.which('pdftotext') else 'pypdf(내장)'}")

if __name__ == "__main__":
    main()
