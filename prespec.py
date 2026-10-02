#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사전규격 수집 — 조달청 나라장터 사전규격정보서비스(HrcspSsstndrdInfoService) → docs/data/prespec.json
본공고 2~4주 전에 뜨는 사전규격(과업·예산 초안)을 입찰공고와 같은 필터로 걸러, 제안서 준비 시간을 번다.
 - 용역만 수집 (물품은 우리 사업 아님)
 - 입찰공고 필터(screen_g2b.classify)에서 OPEN 이 되는 건만 보관 = 본공고가 뜨면 검토 대상이 될 사업
 - 본공고 번호가 연결되면 제거(검토 대상에 이미 올라왔거나 끝난 건), 등록일 45일 지나도 자동 제거

사용: python3 prespec.py                  # 마지막 성공일-1 ~ 오늘 (첫 실행은 30일 소급)
      python3 prespec.py 20260901 20260929
      python3 prespec.py --probe          # 연결 확인 + 응답 필드 1건 출력
필요: data.go.kr 「조달청_나라장터 사전규격정보서비스」 활용신청 승인 + G2B_KEY
"""
import os, sys, json, re, time, datetime as dt, urllib.parse, urllib.request, urllib.error

KEY = os.environ.get("G2B_KEY", "")
DATA = "docs/data"
BASES = ["https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService",
         "https://apis.data.go.kr/1230000/HrcspSsstndrdInfoService"]
OPS = ["getPublicPrcureThngInfoServc"]          # 용역 사전규격 목록
KEEP_DAYS = 45

F = {
  "no":     ["bfSpecRgstNo"],
  "name":   ["prdctClsfcNoNm", "bsnsNm", "bidNtceNm"],
  "inst":   ["rlDminsttNm", "orderInsttNm", "dminsttNm"],
  "order":  ["orderInsttNm", "ntceInsttNm"],
  "budget": ["asignBdgtAmt", "bdgtAmt", "presmptPrce"],
  "rgst":   ["rcptDt", "rgstDt", "opninRgstBgnDt"],
  "opnClse":["opninRgstClseDt"],
  "bidNos": ["bidNtceNoList", "bidNtceNo"],
  "sw":     ["swBizObjYn"],
  "ofcl":   ["ofclNm"],
  "tel":    ["ofclTelNo"],
  "dlvr":   ["dlvrTmlmtDt", "dlvrDaynum"],
  "ref":    ["refNo"],
  "div":    ["bsnsDivNm"],
  "dlvrDays": ["dlvrDaynum"],
  "chg":    ["chgDt"],
}
DETAIL = "https://www.g2b.go.kr/link/PRVA004_02/single/?bfSpecRegNo={}"   # 나라장터 사전규격 상세

import importlib.util as _iu
_spec = _iu.spec_from_file_location("screen_g2b", os.path.join(os.path.dirname(os.path.abspath(__file__)), "screen_g2b.py"))
_sg = _iu.module_from_spec(_spec); _spec.loader.exec_module(_sg)

def pick(it, keys):
    for k in keys:
        v = it.get(k)
        if v not in (None, ""): return v
    return ""

def money(v):
    try: return int(float(str(v).replace(",", "") or 0))
    except Exception: return 0

def iso(v):
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) < 8: return ""
    out = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return out + (f" {d[8:10]}:{d[10:12]}" if len(d) >= 12 else "")

LAST_ERR = {}
def _get(url, tries=1):
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r: body = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code} {e.read().decode('utf-8','replace')[:160]}"
        except Exception as e:
            err = repr(e)[:160]
        else:
            if body.lstrip().startswith("<"): err = body[:200]
            else:
                try: j = json.loads(body)
                except Exception: err = body[:160]
                else:
                    hdr = j.get("response", {}).get("header", {})
                    if hdr.get("resultCode") in ("00", "0"): return j, ""
                    err = f"{hdr.get('resultCode')} {hdr.get('resultMsg')}"
        if "403" in err or "NOT_REGISTERED" in err or "NO_OPENAPI" in err: return None, err
        time.sleep(1.5 * (a + 1))
    return None, err

def url_for(base, op, bgn, end, page, rows):
    params = {"inqryDiv": "1", "type": "json", "inqryBgnDt": bgn, "inqryEndDt": end,
              "pageNo": str(page), "numOfRows": str(rows), "ServiceKey": KEY}
    return f"{base}/{op}?" + urllib.parse.urlencode(params, safe="")

def fetch(bgn, end, rows=200, max_pages=25):
    base_used = op_used = None
    for op in OPS:
        for base in BASES:
            j, err = _get(url_for(base, op, bgn, end, 1, 1), tries=4)
            if j is not None: base_used, op_used = base, op; break
            LAST_ERR[f"{base.split('/')[-2]}/{op}"] = err
        if base_used: break
    if not base_used:
        print("  ! 사전규격정보서비스 연결 실패 — " + " | ".join(f"{k}: {v}" for k, v in LAST_ERR.items()), file=sys.stderr)
        return None
    print(f"  · {base_used} / {op_used}", file=sys.stderr)
    got, page, total, failed = [], 1, None, []
    while True:
        j, err = _get(url_for(base_used, op_used, bgn, end, page, rows), tries=6)
        if j is None:
            failed.append(page)
            if total is None: break
        else:
            bd = j.get("response", {}).get("body", {}) or {}
            items = bd.get("items") or []
            if isinstance(items, dict): items = items.get("item", []) or []
            if isinstance(items, dict): items = [items]
            got.extend(items); total = int(bd.get("totalCount") or 0)
        if total is not None and (page * rows >= total or page >= max_pages): break
        page += 1; time.sleep(0.3)
    if failed: print(f"  ! 실패 페이지 {failed} — {len(got)}/{total or '?'}건 부분 수집", file=sys.stderr)
    return got

def main():
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()   # KST
    if "--probe" in sys.argv:
        b = (today - dt.timedelta(days=3)).strftime("%Y%m%d") + "0000"; e = today.strftime("%Y%m%d") + "2359"
        items = fetch(b, e, rows=3, max_pages=1)
        if not items:
            print("PROBE FAILED — 위 오류 참고 (403/NOT_REGISTERED = 사전규격정보서비스 활용신청 필요)", file=sys.stderr); sys.exit(1)
        print(f"== 사전규격(용역) {len(items)}건 — 첫 건 필드")
        print(json.dumps(items[0], ensure_ascii=False, indent=1)[:4000]); return
    if not KEY: print("G2B_KEY 없음", file=sys.stderr); sys.exit(2)

    try: cur = json.load(open(f"{DATA}/prespec.json", encoding="utf-8"))
    except Exception: cur = []
    if len(sys.argv) >= 3 and not sys.argv[1].startswith("--"): b, e = sys.argv[1], sys.argv[2]
    else:
        back = 30
        try:
            last = dt.date.fromisoformat(max(c["fetchedOn"] for c in cur if c.get("fetchedOn")))
            back = max(3, min(30, (today - last).days + 1))
        except Exception: pass
        b = (today - dt.timedelta(days=back)).strftime("%Y%m%d"); e = today.strftime("%Y%m%d")
    print(f"[사전규격] {b} ~ {e}")
    items = fetch(b + "0000", e + "2359")
    if items is None: sys.exit(1)

    by = {c["id"]: c for c in cur}
    added = linked = 0; seen_n = 0
    for it in items:
        name = str(pick(it, F["name"])).strip(); no = str(pick(it, F["no"])).strip()
        if not name or not no: continue
        seen_n += 1
        budget = money(pick(it, F["budget"])); inst = str(pick(it, F["inst"]))
        bucket, reason, score, hit, _d, amt, _inst, pos, flags = _sg.classify(
            {"bidNtceNm": name, "presmptPrce": budget, "dminsttNm": inst}, "용역", today)
        bid_nos = [x for x in re.split(r"[,\s]+", str(pick(it, F["bidNos"]))) if x.strip()]
        files = []
        for i in range(1, 11):
            u = it.get(f"specDocFileUrl{i}")
            if u: files.append({"url": u, "name": it.get(f"specDocFileNm{i}") or f"사전규격 첨부 {i}"})
        rec = {
            "id": no, "name": name, "inst": inst, "order": str(pick(it, F["order"])),
            "amount": budget, "rgst": iso(pick(it, F["rgst"])), "opnClse": iso(pick(it, F["opnClse"])),
            "bidNos": bid_nos, "sw": str(pick(it, F["sw"])), "ofcl": str(pick(it, F["ofcl"])), "tel": str(pick(it, F["tel"])),
            "dlvr": iso(it.get("dlvrTmlmtDt")) or "", "dlvrDays": money(pick(it, F["dlvrDays"])),
            "div": str(pick(it, F["div"])), "chg": iso(pick(it, F["chg"])),
            "url": DETAIL.format(urllib.parse.quote(no)), "files": files,
            "bucket": bucket, "reason": reason, "score": score, "keywords": hit, "position": pos,
            "fetchedOn": today.isoformat(),
        }
        if bucket != "OPEN" or bid_nos:
            # 재판정으로 빠진 건, 본공고가 나온 건(검토 대상 목록에 이미 있거나 끝난 건)은 제거
            if bid_nos and no in by: linked += 1
            by.pop(no, None); continue
        if no in by:
            by[no].update({k: v for k, v in rec.items() if k not in ("fetchedOn",)})
        else:
            by[no] = rec; added += 1
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for k in list(by):                                      # 규칙 변경 반영 — 누적분도 다시 판정
        c = by[k]
        if _sg.classify({"bidNtceNm": c.get("name", ""), "presmptPrce": c.get("amount", 0), "dminsttNm": c.get("inst", "")}, "용역", today)[0] != "OPEN":
            del by[k]
    for c in by.values():                                   # 예전 레코드 보정
        c["url"] = DETAIL.format(urllib.parse.quote(c["id"]))
        d = str(c.get("dlvr") or "")
        if re.fullmatch(r"\d{1,4}", d): c["dlvrDays"] = int(d); c["dlvr"] = ""
    out = [c for c in by.values() if not c.get("bidNos") and (c.get("rgst") or c.get("fetchedOn") or "")[:10] >= cutoff]
    out.sort(key=lambda c: (bool(c.get("bidNos")), -(c.get("score") or 0), c.get("rgst") or ""), reverse=False)
    json.dump(out, open(f"{DATA}/prespec.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0, separators=(",", ":"))
    print(f"[사전규격] 조회 {seen_n}건 → 신규 {added} · 본공고 나와 제거 {linked} · 보관 {len(out)}건 (최근 {KEEP_DAYS}일)")

if __name__ == "__main__":
    main()
