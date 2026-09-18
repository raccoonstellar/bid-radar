#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개찰결과 수집 — 조달청 낙찰정보서비스(ScsbidInfoService) → docs/data/competitors.json
기준 v0.2 §11: 우리 Core 영역에서 낙찰된 건·낙찰사·투찰률을 매일 쌓아 경쟁사 DB로 쓴다.
 - 유찰(낙찰금액 0·"공고문참조")은 재공고 신호로 별도 표기
 - 콜센터·BPO 운영 낙찰사는 경쟁자가 아니라 AICC 도입 접점 → tag "partner"

사용: python3 opening.py                 # 마지막 성공일-1 ~ 오늘 (3~14일)
      python3 opening.py 20260910 20260917
      python3 opening.py --probe         # API 응답 필드명 1건 출력 (첫 연결 확인용)
필요: data.go.kr 「조달청_나라장터 낙찰정보서비스」 활용신청 승인 + G2B_KEY
"""
import os, sys, json, re, time, datetime as dt, urllib.parse, urllib.request, urllib.error

KEY = os.environ.get("G2B_KEY", "")
DATA = "docs/data"
# 낙찰정보서비스 — 신규(as) 경로 우선, 구 경로 폴백
# 오퍼레이션 후보 — 낙찰정보서비스 1.1: 낙찰 목록(getScsbidListSttus*) / 개찰결과 목록(getOpengResultListInfo*). 첫 응답하는 것을 쓴다
OPS = {"용역": ["getScsbidListSttusServc"], "물품": ["getScsbidListSttusThng"]}   # 고정 — 필드 구성이 섞이지 않게
BASES = ["https://apis.data.go.kr/1230000/as/ScsbidInfoService"]

# 필드명 후보 (버전·오퍼레이션에 따라 다름) — 첫 매치 사용
F = {
  "name":   ["bidNtceNm"],
  "no":     ["bidNtceNo"],
  "ord":    ["bidNtceOrd"],
  "inst":   ["dminsttNm", "ntceInsttNm"],
  "winner": ["bidwinnrNm", "sucsfbidCorpNm", "scsbidCorpNm", "opengCorpInfo", "prtcptCnum"],
  "amount": ["sucsfbidAmt", "scsbidAmt", "bidwinnrAmt", "opengAmt"],
  "rate":   ["sucsfbidRate", "scsbidRate", "bidwinnrRate", "opengRate"],
  "date":   ["rlOpengDt", "opengDt", "fnlSucsfDate", "sucsfbidDt"],
  "budget": ["presmptPrce", "asignBdgtAmt", "bssamt"],
  "flag":   ["progrsDivCdNm", "sucsfbidMthdNm", "bidClseExcpYn"],
}
import importlib.util as _iu
_spec = _iu.spec_from_file_location("screen_g2b", os.path.join(os.path.dirname(os.path.abspath(__file__)), "screen_g2b.py"))
_sg = _iu.module_from_spec(_spec); _spec.loader.exec_module(_sg)
STRONG = ["챗봇","콜봇","AICC","IPCC","생성형","LLM","RAG","OCR","콜센터","상담","음성인식","에이전트","Agent","AI","인공지능","비정형","문서","STT","TTS","민원"]
PARTNER = re.compile(r"콜센터.*(운영|위탁)|상담센터.*(운영|위탁)|BPO|고객센터 운영")

def pick(it, keys):
    for k in keys:
        v = it.get(k)
        if v not in (None, ""): return v
    return ""

def money(v):
    try: return int(float(str(v).replace(",", "") or 0))
    except Exception: return 0

LAST_ERR = {}
def _try(base, op, bgn, end):
    params = {"inqryDiv": "1", "type": "json", "inqryBgnDt": bgn, "inqryEndDt": end, "pageNo": "1", "numOfRows": "1", "ServiceKey": KEY}
    url = f"{base}/{op}?" + urllib.parse.urlencode(params, safe="")
    try:
        with urllib.request.urlopen(url, timeout=60) as r: body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} {e.read().decode('utf-8','replace')[:160]}"
    except Exception as e:
        return None, repr(e)[:160]
    if body.lstrip().startswith("<"): return None, body[:160]
    try: j = json.loads(body)
    except Exception: return None, body[:160]
    hdr = j.get("response", {}).get("header", {})
    if hdr.get("resultCode") not in ("00", "0"): return None, f"{hdr.get('resultCode')} {hdr.get('resultMsg')}"
    return j, ""

def fetch(ops, bgn, end, rows=200, max_pages=25, tries=6):
    """ops: 오퍼레이션 후보 리스트. 첫 성공 조합으로 페이징."""
    base_used = op = None
    for o in (ops if isinstance(ops, list) else [ops]):
        for base in BASES:
            for a in range(5):
                j, err = _try(base, o, bgn, end)
                if j is not None: base_used, op = base, o; break
                LAST_ERR[o] = err; time.sleep(1.5 * (a + 1))
                if err.startswith("HTTP 403") or "NOT_REGISTERED" in err or "NO_OPENAPI" in err: break
            if base_used: break
        if base_used: break
    if not base_used:
        print(f"  ! 낙찰정보서비스 연결 실패 — " + " | ".join(f"{k}: {v}" for k, v in LAST_ERR.items()), file=sys.stderr); return []
    print(f"  · 오퍼레이션 {op}", file=sys.stderr)
    got, page, total, failed = [], 1, None, []
    while True:
        params = {"inqryDiv": "1", "type": "json", "inqryBgnDt": bgn, "inqryEndDt": end, "pageNo": str(page), "numOfRows": str(rows), "ServiceKey": KEY}
        url = f"{base_used}/{op}?" + urllib.parse.urlencode(params, safe="")
        j = None
        for a in range(tries):
            try:
                with urllib.request.urlopen(url, timeout=60) as r: j = json.loads(r.read().decode("utf-8", "replace")); break
            except Exception: j = None; time.sleep(1.5 * (a + 1))
        if j is None:
            failed.append(page)
            if total is None: break
        else:
            bd = j.get("response", {}).get("body", {}) or {}
            items = bd.get("items") or []
            if isinstance(items, dict): items = items.get("item", []) or []
            got.extend(items); total = int(bd.get("totalCount") or 0)
        if total is not None and (page * rows >= total or page >= max_pages): break
        page += 1; time.sleep(0.3)
    if failed: print(f"  ! {op}: 실패 페이지 {failed}", file=sys.stderr)
    return got

def main():
    if "--probe" in sys.argv:
        t = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date(); b = (t - dt.timedelta(days=2)).strftime("%Y%m%d") + "0000"; e = t.strftime("%Y%m%d") + "2359"
        ok = False; fails = []
        for kind, ops in OPS.items():
            items = fetch(ops, b, e, rows=3, max_pages=1)
            print(f"== {kind} {len(items)}건")
            if not items: fails.append(kind)
            if items: ok = True; print(json.dumps(items[0], ensure_ascii=False, indent=1)[:3000])
        if not ok: print("PROBE FAILED — 위 오류 참고", file=sys.stderr); sys.exit(1)
        if fails: print(f"PROBE PARTIAL — 실패: {fails}", file=sys.stderr); sys.exit(1)
        return
    if not KEY: print("G2B_KEY 없음", file=sys.stderr); sys.exit(2)
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()   # KST — 클라우드 컨테이너는 UTC
    if len(sys.argv) >= 3 and not sys.argv[1].startswith("--"): b, e = sys.argv[1], sys.argv[2]
    else:
        comps = []
        try: comps = json.load(open(f"{DATA}/competitors.json", encoding="utf-8"))
        except Exception: pass
        back = 3
        try:
            last = dt.date.fromisoformat(max(c["fetchedOn"] for c in comps if c.get("fetchedOn")))
            back = max(3, min(14, (today - last).days + 1))
        except Exception: pass
        b = (today - dt.timedelta(days=back)).strftime("%Y%m%d"); e = today.strftime("%Y%m%d")
    bgn, end = b + "0000", e + "2359"
    print(f"[개찰결과] {bgn} ~ {end}")

    try: comps = json.load(open(f"{DATA}/competitors.json", encoding="utf-8"))
    except Exception: comps = []
    seen = {c["id"] for c in comps}
    try: est = {b.get("bidNo") or str(b["id"]).rsplit("-",1)[0]: b.get("amount") for b in json.load(open(f"{DATA}/bids.json", encoding="utf-8"))}
    except Exception: est = {}
    added = 0
    for kind, ops in OPS.items():
        items = fetch(ops, bgn, end)
        print(f"  {kind}: {len(items)}건")
        for it in items:
            name = str(pick(it, F["name"]))
            if not _sg.anyk(name, STRONG): continue
            if re.search(r"AITC\d|SCECM|DGX|GPU|서버|노트북|워크스테이션|장비 구매|라이선스", name): continue
            no = str(pick(it, F["no"])); ord_ = str(pick(it, F["ord"]) or "000")
            cid = f"{no}-{ord_}"
            if cid in seen: continue
            amt = money(pick(it, F["amount"])); budget = money(pick(it, F["budget"])) or money(est.get(no) or 0)
            rate = pick(it, F["rate"]); rate_est = None
            try: rate = round(float(str(rate).replace("%", "")), 2) if rate != "" else None
            except Exception: rate = None
            if rate is None and amt and budget: rate_est = round(amt / budget * 100, 1)   # 추정가격 대비 (예정가격 미공개)
            winner = str(pick(it, F["winner"]))
            failed = (amt == 0) or ("유찰" in str(pick(it, F["flag"]))) or (winner == "")
            comps.append({
                "id": cid, "kind": kind, "name": name, "inst": str(pick(it, F["inst"])),
                "winner": winner, "amount": amt, "budget": budget, "rate": rate, "rateEst": rate_est, "bidders": money(pick(it, ["prtcptCnum"])),
                "date": re.sub(r"\D", "", str(pick(it, F["date"])))[:8] and dt.datetime.strptime(re.sub(r"\D", "", str(pick(it, F["date"])))[:8], "%Y%m%d").date().isoformat(),
                "result": "유찰" if failed else "낙찰",
                "tag": "partner" if PARTNER.search(name) else "competitor",
                "fetchedOn": today.isoformat(),
                "raw": {k: it.get(k) for k in ("bidwinnrNm","sucsfbidAmt","sucsfbidRate","opengDt","progrsDivCdNm") if it.get(k) not in (None, "")},
            })
            seen.add(cid); added += 1
    comps.sort(key=lambda c: (c.get("date") or ""), reverse=True)
    comps = comps[:400]
    json.dump(comps, open(f"{DATA}/competitors.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0, separators=(",", ":"))
    print(f"[개찰결과] 신규 {added}건 · 누적 {len(comps)}건 (유찰 {sum(1 for c in comps if c['result']=='유찰')})")

if __name__ == "__main__":
    main()
