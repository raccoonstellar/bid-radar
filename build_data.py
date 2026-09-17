#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
out/screen_YYYYMMDD.json (오늘 수집분) → docs/data/{bids,runs,latest}.json 병합
- bids.json  : 공고 누적. id(공고번호-차수) 기준. 신규는 추가, 기존은 dday·점수·포지션만 갱신 (firstSeen 보존)
- runs.json  : 일별 수집 통계 (총건수·통과·버킷·DROP 사유). 같은 날짜는 덮어씀
- latest.json: 오늘 수집분 그대로 (디버그·재현용)
- 보관 규칙  : 마감이 30일 이상 지났고 lastSeen 도 30일 넘은 건은 제거 (파일 비대화 방지)
사용: python3 build_data.py            # out/ 에서 가장 최근 파일
      python3 build_data.py out/screen_20260916.json
"""
import json, sys, glob, os, datetime as dt

DATA = "docs/data"
REFRESH = ["dday","closeDt","score","bucket","reason","position","flags","tech","joint","arslt","infoBiz",
           "keywords","amount","inst","kind","method","url","docUrl","docUrls","docs","clsfc","clsLrg","reNotice","briefing","contact"]
KEEP_DAYS = 30

def load(p, default):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return default

def save(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=0, separators=(",", ":"))

def ymd(s):
    d = "".join(ch for ch in str(s or "") if ch.isdigit())[:8]
    try: return dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    except Exception: return None

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else (sorted(glob.glob("out/screen_*.json")) or [None])[-1]
    if not src: print("수집 결과 파일 없음 (out/screen_*.json)", file=sys.stderr); sys.exit(2)
    res = json.load(open(src, encoding="utf-8"))
    date = res.get("date") or dt.date.today().isoformat()
    today = dt.date.fromisoformat(date)

    bids = {b["id"]: b for b in load(f"{DATA}/bids.json", [])}
    added = updated = same = 0
    # 규칙 변경으로 오늘 DROP 이 된 건은 누적에서도 제거 (재판정 반영)
    removed = 0
    for r in res.get("rows", []):
        if r.get("bucket") == "DROP" and r.get("id") in bids:
            del bids[r["id"]]; removed += 1
    for r in res.get("rows", []):
        if r.get("bucket") == "DROP" or not r.get("id"): continue
        cur = bids.get(r["id"])
        if not cur:
            bids[r["id"]] = {**r, "firstSeen": date, "lastSeen": date}; added += 1
        else:
            changed = False
            for f in REFRESH:
                if f in r and r[f] != cur.get(f): cur[f] = r[f]; changed = True
            cur["lastSeen"] = date
            updated += changed; same += (not changed)

    # 동일 공고번호 차수 중복: 최신 차수만 남긴다 (재공고·정정으로 -000/-001 이 동시에 뜨는 경우)
    latest = {}
    for b in bids.values():
        no = b.get("bidNo") or str(b.get("id","")).rsplit("-",1)[0]
        ordv = str(b.get("id","")).rsplit("-",1)[-1]
        if no not in latest or ordv > latest[no][0]: latest[no] = (ordv, b["id"])
    keep_ids = {v[1] for v in latest.values()}
    bids = {k: v for k, v in bids.items() if k in keep_ids}

    # 보관 규칙
    kept = []
    for b in bids.values():
        close = ymd(b.get("closeDt")); seen = ymd(b.get("lastSeen"))
        stale_close = close is not None and (today - close).days > KEEP_DAYS
        stale_seen  = seen  is not None and (today - seen).days  > KEEP_DAYS
        if stale_close and stale_seen: continue
        kept.append(b)
    order = {"OPEN": 0, "SIGNAL": 1, "WATCH": 2}
    kept.sort(key=lambda b: (order.get(b.get("bucket"), 9), -(b.get("score") or 0), b.get("dday") if isinstance(b.get("dday"), int) else 999))
    save(f"{DATA}/bids.json", kept)

    runs = [x for x in load(f"{DATA}/runs.json", []) if x.get("date") != date]
    # 집계는 차수 정리 후(대시보드와 일치) — 오늘 수집분 중 보관된 것만
    today_rows = [x for x in kept if x.get("lastSeen") == date]
    buckets = {k: sum(1 for x in today_rows if x.get("bucket") == k) for k in ("OPEN", "SIGNAL", "WATCH")}
    drops = {}
    for r in res.get("rows", []):
        if r.get("bucket") == "DROP":
            k = (r.get("reason") or "").split("(")[0].strip(); drops[k] = drops.get(k, 0) + 1
    runs.append({"date": date, "range": res.get("range"), "total": len(res.get("rows", [])),
                 "pass": sum(buckets.values()), "buckets": buckets, "drops": drops,
                 "added": added, "updated": updated, "same": same, "removed": removed, "builtAt": dt.datetime.now().isoformat(timespec="seconds")})
    runs.sort(key=lambda x: x["date"], reverse=True)
    save(f"{DATA}/runs.json", runs[:90])
    save(f"{DATA}/latest.json", {k: res[k] for k in res if k != "rows"} | {"rows": [r for r in res.get("rows", []) if r.get("bucket") != "DROP"]})
    print(f"[병합] {date} 신규 {added} · 갱신 {updated} · 변동없음 {same} · 재판정 제거 {removed} · 보관 {len(kept)}건 · runs {len(runs)}행")

if __name__ == "__main__":
    main()
