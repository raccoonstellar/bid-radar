#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조달청 나라장터 입찰공고 일일 수집·스크리닝
기준 문서: 조달청_공고_1차스크리닝_기준_v0.2.md + v0.4 필터 개정(260914) · v0.4.2 페이징·재시도·상담회 오탐(260916) · v0.5 대형 건 OPEN(260916) · v0.6 공통키워드·1억 하한·하도급 표기(260917)

사용:
  export G2B_KEY="<data.go.kr 일반 인증키(Decoding)>"
  python3 screen_g2b.py                 # 어제~오늘
  python3 screen_g2b.py 20260910 20260911
출력:
  out/screen_YYYYMMDD.json   (대시보드 db 적재용)
"""
import os, sys, json, re, time, datetime as dt, urllib.parse, urllib.request

KEY = os.environ.get("G2B_KEY", "")
BASES = [
    "https://apis.data.go.kr/1230000/ad/BidPublicInfoService",
    "https://apis.data.go.kr/1230000/BidPublicInfoService",
]
# 업무구분별 오퍼레이션 — 용역이 주채널, 물품도 수집(솔루션 도입이 물품으로 나오는 사례 있음)
OPS = {"용역": "getBidPblancListInfoServc", "물품": "getBidPblancListInfoThng"}

# ── v0.4 (260914) 키워드 3단계 — 토큰 경계 매칭 ───────────────────────
# 규칙 요약: ① 품명분류로 먼저 자른다 ② STRONG 키워드는 노이즈 필터 면제 ③ 금액은 컷이 아니라 포지션 추천
KW_STRONG = ["챗봇","콜봇","AICC","IPCC","생성형","LLM","RAG","OCR","콜센터","상담","음성인식","에이전트","Agent"]
KW_MID    = ["ECM","EDMS","전자문서","기록물","아카이브","지식관리","비정형","문서","STT","TTS","민원","자연어",
             "학습데이터","디지털전환","AX","튜터","LMS","검색","콘텐츠관리","NER","텍스트","판독","SaaS","구독"]
KW_WEAK   = ["AI","인공지능"]
KW_CORE   = KW_STRONG + KW_MID + KW_WEAK

# ── 노이즈 필터 (STRONG 매칭 시 N2·N3·N4·N8·N9 면제) ──────────────────
N2_DEVICE  = ["GPU","서버","워크스테이션","노트북","모니터","스토리지","카메라","로봇","항온항습기","변압기","클램프",
              "프린터","복합기","공기청정기","태블릿","PC","장비","기자재","스캐너","어댑터","케이블","서버랙"]
N3_LICENSE = ["라이선스","라이센스","사용권","유지보수","유지관리","갱신","임차","렌탈","임대"]   # v0.6: 구독은 MID 키워드로 이동
N4_EDU     = ["급식","부식","수학여행","체험학습","교육","과정 운영","캠프","공모전","챌린지","Challenge","포럼","메이커톤",
              "홍보","운영 대행","대행용역","커리큘럼","영상콘텐츠","콘텐츠 제작","행사","위탁운영","위탁 운영","프로그램 운영",
              "컨설팅","만족도","설문","여론조사","실태조사"]
N5_SIGNAL  = ["감리","개인정보영향평가","영향평가","ISMP","ISP","정보화전략","사전협의","BPR"]
N5_NOT     = ["건축","토목","환경","기후","소하천","주택","도로","교량","하수","상수","조경","전기공사","소방",
              "산림","재선충","방제","해양","정화","항만","건립","전기감리","도시정비","낙농"]
N6_FALSE   = [r"AITC\d", r"SCECM", r"DGX"]
N7_CIVIL   = ["설치 공사","설치공사","토목","건설사업관리","감독권한","정비사업"]
N8_HW      = ["AX-sprint","라바콘","차량 개조","차량개조","주행테스트","자율주행","스마트크루즈","도금","CNC","부품 가공",
              "금속 가공","설비 진단","임베디드 포팅","로보틱스","감속 유도","무결성 검증","PACS"]
N9_STUDY   = ["연구용역","전략 수립","도입방안","시장분석","효과분석","효과성 분석","비즈니스 모델","타당성"]
# 품명 대분류/중분류 기반 (API pubPrcrmntLrgClsfcNm / MidClsfcNm)
CLS_DROP   = ["건설","건축","토목","폐기물","시설","운송","환경","보건","의료","급식","청소","경비","임업","농업","수산","광업","조경"]
CLS_STUDY  = ["연구조사"]
CLS_EDU    = ["교육","행사"]
CLS_OPS    = ["운영 및 유지관리"]
GAIN = {"재공고":"재공고(유찰 흔적)", "긴급":"긴급(경쟁 참여율 하락)"}

# 포지션 추천 구간 — 컷이 아니라 추천. 단일 최대 완료실적 6.5억(경동나비엔 AICC, company-data 26-07-21) 기준
SOLO_MAX  = 650_000_000      # 실적요건 100%여도 단독
JOINT_MAX = 1_300_000_000    # 실적요건 50%면 단독, 아니면 컨소
LEAD_MAX  = 3_000_000_000    # 대표사 불가, 구성사
MIN_AMT   =   100_000_000    # v0.6: 추정가격 1억 미만은 OPEN/WATCH 제외 (SIGNAL 은 유지)


def fetch(op, bgn, end, rows=200, max_pages=25, tries=6):
    """inqryDiv=1 : 공고게시일시 기준. totalCount 까지 페이징.
    v0.4.2 — 프록시 간헐 단절 대응: 페이지당 재시도 6회(백오프), 실패해도 모은 페이지는 살린다."""
    base = BASES[0]
    got, page, total, failed_pages = [], 1, None, []
    while True:
        params = {"inqryDiv": "1", "type": "json", "inqryBgnDt": bgn, "inqryEndDt": end,
                  "pageNo": str(page), "numOfRows": str(rows), "ServiceKey": KEY}
        url = f"{base}/{op}?" + urllib.parse.urlencode(params, safe="")
        j, last = None, None
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    body = r.read().decode("utf-8", "replace")
                if body.lstrip().startswith("<"): raise RuntimeError(body[:200])
                j = json.loads(body)
                hdr = j.get("response", {}).get("header", {})
                if hdr.get("resultCode") not in ("00", "0", None):
                    raise RuntimeError(f"{hdr.get('resultCode')} {hdr.get('resultMsg')}")
                break
            except Exception as e:
                last = repr(e); j = None; time.sleep(1.5 * (attempt + 1))
        if j is None:
            failed_pages.append(page)
            print(f"  ! {op} page {page} 실패 ({last}) — 건너뜀", file=sys.stderr)
            if total is None: break          # 첫 페이지부터 실패면 total 을 몰라 종료
        else:
            bd = j.get("response", {}).get("body", {}) or {}
            page_items = bd.get("items") or []
            if isinstance(page_items, dict): page_items = page_items.get("item", []) or []
            got.extend(page_items)
            total = int(bd.get("totalCount") or 0)
        if total is not None and (page * rows >= total or page >= max_pages): break
        page += 1; time.sleep(0.3)
    if failed_pages:
        print(f"  ! {op}: 실패 페이지 {failed_pages} — {len(got)}/{total or '?'}건 부분 수집", file=sys.stderr)
    return got

def money(v):
    try: return int(float(str(v).replace(",", "") or 0))
    except Exception: return 0

def ddays(clse, today):
    m = re.sub(r"\D", "", str(clse or ""))[:8]
    if len(m) != 8: return None
    try: return (dt.datetime.strptime(m, "%Y%m%d").date() - today).days
    except Exception: return None

_ASCII = re.compile(r"[A-Za-z]")
def has(nm, tok):
    """짧은 영문 토큰(PC, AI, AX…)은 영문자 경계로만 매칭. 한글은 부분문자열."""
    if _ASCII.match(tok[0]) and len(tok) <= 4:
        return re.search(r"(?<![A-Za-z])" + re.escape(tok) + r"(?![A-Za-z])", nm) is not None
    return tok in nm
_NOT_COUNSEL = re.compile(r"상담회|상담소|상담원 ?(모집|채용)|상담부스")
_NOT_SUBSCR  = re.compile(r"저널|잡지|신문|학술|DB|데이터베이스|뉴스|정기간행물|e-?book|전자책|논문")
def anyk(nm, ks):
    out = []
    for k in ks:
        if k == "상담" and _NOT_COUNSEL.search(nm) and nm.count("상담") == len(_NOT_COUNSEL.findall(nm)): continue
        if k == "구독" and _NOT_SUBSCR.search(nm): continue
        if has(nm, k): out.append(k)
    return out

def position(amt, arslt, joint_ok, joint_txt=""):
    base = _position(amt, arslt, joint_ok)
    jtx = re.sub(r"^\(.*?\)", "", joint_txt or "").strip()          # "(전자)공동이행" → "공동이행"
    jt = "공동수급 " + ("불허" if not joint_ok else (f"허용·{jtx}" if jtx else "미기재"))
    return f"{base} · {jt} · 하도급 공고서 확인(SW사업 50% 상한·사전승인)"

def _position(amt, arslt, joint_ok):
    """금액대 + 실적경쟁 여부 → 단독/컨소 추천"""
    if arslt == "N":
        return "단독 — 실적경쟁 아님(실적 벽 없음)"
    if amt <= 0: return "금액 미공개 — 공고서 확인"
    if amt <= SOLO_MAX:  return "단독"
    if amt <= JOINT_MAX: return ("단독 가능 — 실적요건 50% 기준이면 통과, 100%면 컨소" if joint_ok
                                 else "단독 실적요건 확인 필수 — 공동수급 불허")
    if amt <= LEAD_MAX:  return "컨소 구성사 — 대표사 불가, 구성사 지분 참여" if joint_ok else "참여 불가 추정 — 공동수급 불허"
    return "대형사 컨소 구성사 — 대표사 수배 필요" if joint_ok else "참여 불가 추정 — 공동수급 불허"

def classify(it, kind, today):
    nm   = it.get("bidNtceNm", "") or ""
    inst = it.get("dminsttNm") or it.get("ntceInsttNm") or ""
    amt  = money(it.get("presmptPrce") or it.get("asignBdgtAmt"))
    clse = it.get("bidClseDt") or it.get("opengDt") or ""
    d    = ddays(clse, today)
    lrg  = it.get("pubPrcrmntLrgClsfcNm", "") or ""
    midc = it.get("pubPrcrmntMidClsfcNm", "") or ""
    strong = anyk(nm, KW_STRONG); midk = anyk(nm, KW_MID); weak = anyk(nm, KW_WEAK)
    hit = strong + midk + weak
    why, flags = [], []
    tech  = money(it.get("techAbltEvlRt") or 0)
    joint = it.get("cmmnSpldmdMethdNm", "") or ""
    meth  = it.get("sucsfbidMthdNm", "") or ""
    arslt = it.get("arsltCmptYn", "") or ""
    info  = it.get("infoBizYn", "") or ""
    re_y  = (it.get("reNtceYn") == "Y") or ("재공고" in nm)
    joint_ok = "불허" not in joint
    pos   = position(amt, arslt, joint_ok, joint)
    R = lambda b, r, s=0: (b, r, s, hit, d, amt, inst, pos, flags)

    # N6 오탐(제품코드)
    for pat in N6_FALSE:
        if re.search(pat, nm): return R("DROP", "N6 오탐(제품코드)")
    # 품명 대분류 비IT → 즉시 DROP (STRONG이 있어도 분류가 건설·폐기물이면 오탐)
    if any(k in lrg for k in CLS_DROP): return R("DROP", f"C1 품명분류 비IT({lrg.strip()})")
    # 감리·영평·ISP → AI 키워드 동반 시에만 SIGNAL
    if anyk(nm, N5_SIGNAL):
        if anyk(nm, N5_NOT): return R("DROP", "N5 비IT 감리·평가")
        if hit: return R("SIGNAL", "N5 감리·영향평가 = 본사업 존재 신호")
        return R("DROP", "N5 일반 SI 감리 — AI 키워드 없음")
    if not hit:
        # v0.6 공통키워드: 구축·개발·SaaS 만 걸린 건 — ICT 분류 + 1억 이상이면 WATCH (과업 내 AI 요건 확인용, OPEN 아님)
        if kind == "용역" and re.search(r"구축|개발", nm) and amt >= MIN_AMT \
           and ("ICT" in lrg or "SW" in lrg or "정보" in lrg) \
           and not anyk(nm, N3_LICENSE + N4_EDU + N5_NOT + N7_CIVIL + N8_HW):
            return R("WATCH", "일반 SI 구축·개발 — 과업 내 AI·비정형 요건 확인", 6)
        return R("DROP", "키워드 미매칭")
    if anyk(nm, N7_CIVIL): return R("DROP", "N7 토목·설치공사")
    # 연구조사 분류 → SIGNAL
    if any(k in lrg for k in CLS_STUDY) and not strong: return R("SIGNAL", "C2 연구조사 분류 = 본사업 선행 신호")
    # 물품 구매성
    if kind == "물품" and (re.search(r"구매|구입|임차|렌탈|설치|납품|도구", nm) or "수의" in meth) and not strong:
        return R("DROP", "N1 물품 구매")
    # ── STRONG 보호: 아래 노이즈 필터 면제 ──
    if not strong:
        if any(k in midc for k in CLS_EDU) or anyk(nm, N4_EDU): return R("DROP", "N4 교육·행사·대행")
        if any(k in midc for k in CLS_OPS) or anyk(nm, N3_LICENSE): return R("DROP", "N3 라이선스·운영·유지관리")
        if anyk(nm, N2_DEVICE): return R("DROP", "N2 장비")
        if anyk(nm, N8_HW): return R("DROP", "N8 제조·모빌리티 하드웨어 도메인")
        if anyk(nm, N9_STUDY): return R("SIGNAL", "N9 연구·전략 용역 = 본사업 선행 신호")
    else:
        if any(k in midc for k in CLS_OPS) or anyk(nm, N3_LICENSE): flags.append("D1 운영·유지관리 — 기존 운영사 우위 확인")
        if anyk(nm, N4_EDU): flags.append("교육·대행 요소 포함 — 과업 비중 확인")

    # ── 스코어 20점: Fit 8 · Win 4 · 배점 2 · 여력 4 · 장벽 2 ──
    s_fit = 6 if strong else 4 if midk else 2
    if re.search(r"구축|개발|시스템", nm): s_fit += 2
    if not strong and not midk: s_fit = min(s_fit, 3)          # AI만 걸린 건은 상한 3
    s_fit = min(8, s_fit)
    s_win = 2
    if re_y: s_win += 1; why.append(GAIN["재공고"])
    if "긴급" in nm: s_win += 1; why.append(GAIN["긴급"])
    if re.search(r"개선|고도화|확대|2차|3차|차년도", nm): s_win -= 1; why.append("기존 구축사 존재 추정(F2)")
    s_win = max(0, min(4, s_win))
    if tech >= 95: s_bid = 2
    elif tech >= 80: s_bid = 1
    elif tech: s_bid = 0
    else: s_bid = 1
    if tech: why.append(f"기술{tech}:가격{100-tech}")
    if "최저가" in meth or "적격심사" in meth: s_bid = 0; why.append("가격 중심 낙찰")
    s_cap = 2 if amt <= 0 else 4 if amt <= SOLO_MAX else 3 if amt <= JOINT_MAX else 2   # v0.5: 13억 초과는 2점(컨소 전제)
    s_bar = 0
    if arslt == "N": s_bar += 1; why.append("실적경쟁 아님")
    if info == "Y" or re.search(r"중소기업|대기업 ?참여 ?제한|소기업", nm): s_bar += 1; why.append("정보화사업·대기업 참여제한 추정")
    score = s_fit + s_win + s_bid + s_cap + s_bar
    if joint_ok and joint: why.append("공동수급 허용")

    if 0 < amt < MIN_AMT: return R("DROP", f"소액({amt/1e8:.2f}억 < 1억)", score)
    if "취소" in nm: return R("WATCH", "취소공고 — 재공고 대기", score)
    if d is not None and d < 5: return R("DROP", "D4 마감 임박(D-5 이내)", score)
    # v0.5: 금액으로 WATCH 보내지 않는다 — 컨소 구성사 실적(100억대 참여 이력)이 있으므로 대형 건도 OPEN, 포지션만 "구성사"
    if score <= 9: return R("DROP", f"저점({score}) Fit{s_fit}", score)   # 임계값 — 남혁님 리뷰 항목
    return R("OPEN", (" · ".join(why) or "키워드 적합"), score)

def main():
    if not KEY and not os.environ.get("G2B_FROM_FILE"):
        print("G2B_KEY 환경변수가 없습니다. data.go.kr 일반 인증키(Decoding)를 넣어주세요.", file=sys.stderr)
        sys.exit(2)
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()   # KST — 클라우드 컨테이너는 UTC
    if len(sys.argv) >= 3: b, e = sys.argv[1], sys.argv[2]
    else:
        # 마지막 성공일 하루 전 ~ 오늘 (최소 3일, 최대 14일) — 며칠 건너뛰어도 다음 실행이 갭을 메운다
        back = 3
        last = None
        try: last = dt.date.fromisoformat(open("out/last_run.txt").read().strip())
        except Exception:
            try:   # 클라우드 실행: 저장소의 runs.json 에서 마지막 성공일
                runs = json.load(open("docs/data/runs.json", encoding="utf-8"))
                last = dt.date.fromisoformat(max(r["date"] for r in runs))
            except Exception: pass
        if last: back = max(3, min(14, (today - last).days + 1))
        b = (today - dt.timedelta(days=back)).strftime("%Y%m%d"); e = today.strftime("%Y%m%d")
    bgn, end = b + "0000", e + "2359"
    print(f"[수집] {bgn} ~ {end}")

    seen, rows = set(), []
    src = os.environ.get("G2B_FROM_FILE")           # 크롬 경유 수집 JSON {"용역":[...], "물품":[...]}
    pre = json.load(open(src, encoding="utf-8")) if src else None
    for kind, op in OPS.items():
        items = pre.get(kind, []) if pre is not None else fetch(op, bgn, end)
        print(f"  {kind}: {len(items)}건")
        for it in items:
            no = f"{it.get('bidNtceNo','')}-{it.get('bidNtceOrd','')}"
            if no in seen: continue                     # N7 dedupe
            seen.add(no)
            bucket, reason, score, hit, d, amt, inst, pos, flags = classify(it, kind, today)
            rows.append({
                "id": re.sub(r"[^A-Za-z0-9_.:@+-]", "-", no)[:200],
                "bidNo": it.get("bidNtceNo",""), "kind": kind,
                "name": it.get("bidNtceNm",""), "inst": inst,
                "amount": amt, "closeDt": it.get("bidClseDt") or it.get("opengDt") or "",
                "dday": d, "bucket": bucket, "reason": reason, "score": score,
                "keywords": hit, "position": pos, "flags": flags, "url": it.get("bidNtceDtlUrl",""),
                "collectedOn": today.isoformat(),
                "tech": it.get("techAbltEvlRt",""), "method": it.get("sucsfbidMthdNm",""),
                "compete": it.get("cntrctCnclsMthdNm",""), "joint": it.get("cmmnSpldmdMethdNm",""),
                "reNotice": it.get("reNtceYn",""), "briefing": it.get("dcmtgOprtnDt",""),
                "qualDt": it.get("bidQlfctRgstDt",""), "contact": it.get("ntceInsttOfclTelNo",""),
                "docs": [it.get(f"ntceSpecFileNm{i}") for i in range(1,11) if it.get(f"ntceSpecFileNm{i}")],
                "docUrl": it.get("ntceSpecDocUrl2") or it.get("ntceSpecDocUrl1") or "",
                "docUrls": [it.get(f"ntceSpecDocUrl{i}") for i in range(1,11) if it.get(f"ntceSpecDocUrl{i}")],
                "clsfc": it.get("pubPrcrmntClsfcNm",""), "clsLrg": it.get("pubPrcrmntLrgClsfcNm",""), "arslt": it.get("arsltCmptYn",""), "infoBiz": it.get("infoBizYn",""),
            })

    order = {"OPEN": 0, "SIGNAL": 1, "WATCH": 2, "DROP": 3}
    rows.sort(key=lambda r: (order[r["bucket"]], -r["score"], r["dday"] if r["dday"] is not None else 999))
    stat = {k: sum(1 for r in rows if r["bucket"] == k) for k in order}
    os.makedirs("out", exist_ok=True)
    path = f"out/screen_{today.strftime('%Y%m%d')}.json"
    json.dump({"date": today.isoformat(), "range": [bgn, end], "stats": stat, "rows": rows},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[결과] 총 {len(rows)}건 → OPEN {stat['OPEN']} / SIGNAL {stat['SIGNAL']} / WATCH {stat['WATCH']} / DROP {stat['DROP']}")
    print(f"[저장] {path}")
    open("out/last_run.txt", "w").write(today.isoformat())
    for r in rows:
        if r["bucket"] in ("OPEN", "WATCH"):
            print(f"  [{r['bucket']}] {r['score']:>2}점 D-{r['dday']} {r['amount']:,}원 · {r['name'][:50]} · {r['reason']} → {r['position']}")

if __name__ == "__main__":
    main()
