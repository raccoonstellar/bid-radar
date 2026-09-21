# -*- coding: utf-8 -*-
"""260911 KBID 실제 공고명으로 노이즈 필터 검증 (수기 판정 vs 자동 판정 대조)"""
import datetime as dt, importlib.util
spec = importlib.util.spec_from_file_location("s", "screen_g2b.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
TODAY = dt.date(2026, 9, 11)

# (공고명, 업무구분, 추정가격, 마감일, 수기판정)
CASES = [
 ("AI 기반 MSDS 통합관리 기능 구축 용역","용역",306918182,"20260930","OPEN"),
 ("[재공고]콜센터 보이는 디지털 ARS 서비스 개발용역","용역",443997000,"20260921","OPEN"),
 ("[한남대학교 산학협력단]2026-13호 철도 도메인 특화 RAG 기반 AI 실시간 안전교관 시스템 구축 및 연동 용역","용역",118181818,"20260921","OPEN"),
 ("연암공과대학교 AI Agent 성과관리 및 회계/구매 시스템 구축 (재공고)","용역",318181818,"20260921","OPEN"),
 ("2026년 AI활용 초기상담정보시스템 업무 편의성 개선","용역",334545455,"20261001","OPEN"),
 ("(취소공고)대학혁신지원사업 홍익대학교 RAG 기반 챗봇 클라우드 서비스 구축 업체 선정","물품",136363636,"20261002","WATCH"),
 ("통합 업무정보관리 시스템(ECM) 구축 사업","용역",5723036364,"20261021","OPEN"),   # v0.5: 대형 건도 OPEN(구성사)
 ("출입국심사 여권 판독 고도화 사업 감리 및 개인정보영향평가 용역","용역",145762727,"20260911","SIGNAL"),
 ("[사전규격공개] 지방세 AI 상담 서비스 개인정보 영향평가","용역",0,"20260913","SIGNAL"),
 ("빛의 혁명 디지털 아카이브 구축 BPR/ISP 사업","용역",156363636,"20260930","SIGNAL"),
 # ── 노이즈 (전부 DROP 이어야 함) ──
 ("고성능 GPU 서버 구매_260962","물품",172700000,"20260918","DROP"),
 ("인류클램프 AITC240D 등 2품목 62EA","물품",22885130,"20260918","DROP"),
 ("AIP 수소 구매","물품",872727272,"20260910","DROP"),
 ("AI 플랫폼 Elasticsearch 라이선스 연장","물품",35250000,"20260918","DROP"),
 ("[7-20260909-18](AI대학원/최재영교수님) 공기청정기 구매","물품",0,"20260911","DROP"),
 ("2026학년도 AI취업캠프 프로그램 위탁용역","용역",23636364,"20260928","DROP"),
 ("제조AI솔루션 공모전 및 K-제조 AI 그랜드 챌린지 행사 홍보·운영 대행","용역",45454545,"20260921","DROP"),
 ("AI 연산용 워크스테이션 장비 구매","물품",27258000,"20260916","DROP"),
 ("2027~2028년도 온라인교육 위탁 운영 용역","용역",658600000,"20261021","DROP"),
 ("임금체계 및 인력운용 실태조사","용역",81818182,"20260921","DROP"),
 ("2026년 기후에너지환경 정책 국민만족도 조사","용역",36363636,"20260930","DROP"),
 ("CST Studio Suite 유지보수","용역",65454545,"20260918","DROP"),
 ("AI 산불감시카메라 구축 물품 구입","물품",29344000,"20260917","DROP"),
 ("클라우드 서버 서비스(GPU Server)_PA202601978","물품",100129091,"20260918","DROP"),
]
ok = bad = 0
print(f"{'판정':<7}{'수기':<7}  점수  공고명")
print("-"*92)
for nm, kind, amt, clse, expect in CASES:
    it = {"bidNtceNm": nm, "presmptPrce": amt, "bidClseDt": clse, "dminsttNm": ""}
    b, reason, score, hit, d, a, inst, pos, fl = s.classify(it, kind, TODAY)
    mark = "✓" if b == expect else "✗"
    if b == expect: ok += 1
    else: bad += 1; 
    print(f"{mark} {b:<6}{expect:<7}{score:>4}  {nm[:52]}")
    if b != expect: print(f"        └ 사유: {reason}")
print("-"*92)
print(f"일치 {ok}/{len(CASES)}  불일치 {bad}")

print("\n── 260914 오탐 회귀 ──")
EXTRA=[
 ("[진료재료]SCECM(재공고)","물품",332727273,"20260922","DROP",{"sucsfbidMthdNm":"적격심사제"}),
 ("합천군 소하천정비종합계획 전략환경영향평가 및 기후변화영향평가 용역","용역",1615454545,"20260922","DROP",{}),
 ("주택건설공사 감리자(건축) 모집 공고(장위11-2구역 가로주택정비사업)","용역",1132939000,"20260922","DROP",{}),
 ("웅동지구(1지구) 개발사업 잔여 기반시설 공사 시공단계 감독권한대행 등 건설사업관리용역 가격입찰 공고","용역",2258000000,"20260921","DROP",{}),
 ("2026학년도 AI특화인재양성 활용 AI 도구(Claude Max)","물품",16000000,"20260922","DROP",{"sucsfbidMthdNm":"소액수의견적"}),
 ("제4기 AI ADVANCED 과정 운영 용역","용역",41818182,"20260928","DROP",{}),
 ("초거대 제조AI 서비스 개발·실증사업 무선통신망 보안 시스템 설치 공사","용역",90000000,"20260928","DROP",{}),
 ("생성형 AI 플랫폼 구축 및 AX 개발 사업 감리용역","용역",271577591,"20261027","SIGNAL",{}),
 ("HS코드 생성 AI 모델 및 서비스 개발","용역",90909091,"20260922","DROP",{"techAbltEvlRt":"90","sucsfbidMthdNm":"협상에의한계약"}),  # v0.6: 1억 미만
]
ok2=0
for nm,kind,amt,clse,expect,extra in EXTRA:
    it={"bidNtceNm":nm,"presmptPrce":amt,"bidClseDt":clse,"dminsttNm":"",**extra}
    b,reason,score,*_=s.classify(it,kind,TODAY)
    m="✓" if b==expect else "✗"; ok2+= b==expect
    print(f"{m} {b:<6}{expect:<7}{score:>4}  {nm[:52]}" + ("" if b==expect else f"\n        └ {reason}"))
print(f"회귀 {ok2}/{len(EXTRA)}")

print("\n── 260914 4일치 수집 오탐 회귀 (v0.3) ──")
EXTRA2=[
 ("AX-sprint AI-로드세이버 라바콘 자동 설치 차량 개조 용역","용역",755000000,"20260921","DROP",{}),
 ("AX-sprint K-ACC Guard 주행테스트 및 알고리즘 무결성 검증 용역","용역",530000000,"20260921","DROP",{}),
 ("AX-sprint K-ACC Guard 국내외 최신 시장분석 용역","용역",120000000,"20260921","DROP",{}),
 ("AX-sprint AI-로드세이버 통합 운영 소프트웨어 및 현장운영 지원 용역","용역",470000000,"20260921","DROP",{}),
 ("설비 진단용 AI 모델의 시뮬레이션 환경 구축","용역",45000000,"20260928","DROP",{}),
 ("K-Health AI 실증병원 구축을 위한 의료정보시스템(PACS) 구축","물품",436181818,"20260928","DROP",{}),
 ("(재공고)AI기반 도금액 개발 시스템","용역",448000000,"20260921","DROP",{}),
 ("2차년도 항공 부품 CNC 가공 휴먼에러 방지를 위한 AI 기반 실시간 검증 시스템 개발 및 실증","물품",40000000,"20260921","DROP",{}),
 ("SBS 창사특집 대기획 가제:미래인류 AI 페르소나 소프트웨어 구축 및 콘텐츠 제작 용역","용역",50000000,"20260928","DROP",{}),
 ("서일대학교 신입생 안정화 15주 영상콘텐츠 및 운영 LMS 구축","용역",90909091,"20260928","DROP",{}),
 ("HOP(HIRA, Open AI Hub, Private) Biohealth AI Challenge","용역",109090909,"20260922","DROP",{}),
 ("울산 자동차 부품 산업 AI 전환(AX) 전략 수립 연구용역","용역",45454545,"20260922","SIGNAL",{}),
 ("K-택소노미 평가 고도화를 위한 AI 도입방안 연구","용역",90909091,"20260929","SIGNAL",{}),
 ("2026년 연인산도립공원 하반기 소나무재선충병 방제사업 감리용역","용역",11795455,"20260928","DROP",{}),
 ("2026년 여수시 가막만 일대(1권역)  해양폐기물 정화사업 감리","용역",99290909,"20260928","DROP",{}),
 ("국립진주박물관 이전건립공사 전기감리용역","용역",916810000,"20260928","DROP",{}),
 ("생성형 AI 플랫폼 구축 및 AX 개발 사업 감리용역","용역",271577591,"20261027","SIGNAL",{}),
 ("2026년 미디어 AI 플랫폼 고도화 감리","용역",27272727,"20260928","SIGNAL",{}),
 ("(긴급)2026년 AI 기반 지역현황 진단시스템 구축 사업 용역 재공고","용역",272727273,"20260922","OPEN",{"techAbltEvlRt":"90","sucsfbidMthdNm":"협상에의한계약","cmmnSpldmdMethdNm":"(수기)공동이행"}),
 ("AI 적용 비축사업 통합정보시스템 고도화 용역","용역",550000000,"20261022","DROP",{"techAbltEvlRt":"90","sucsfbidMthdNm":"협상에의한계약"}),  # v0.4: AI만+고도화 → 9점 저점 (경계 케이스)
 ("OnDevice STT 모듈 및 성폭력 KeyWord 도출 NER(Name Entity Recognition) 모듈 개발","용역",80000000,"20260922","DROP",{"techAbltEvlRt":"90","sucsfbidMthdNm":"협상에의한계약"}),  # v0.6: 1억 미만
]
ok3=0
for nm,kind,amt,clse,expect,extra in EXTRA2:
    it={"bidNtceNm":nm,"presmptPrce":amt,"bidClseDt":clse,"dminsttNm":"",**extra}
    b,reason,score,*_=s.classify(it,kind,TODAY)
    m="✓" if b==expect else "✗"; ok3+= b==expect
    print(f"{m} {b:<6}{expect:<7}{score:>4}  {nm[:52]}" + ("" if b==expect else f"\n        └ {reason}"))
print(f"v0.3 회귀 {ok3}/{len(EXTRA2)}")

print("\n── v0.4 Core 보호·토큰경계 회귀 ──")
EXTRA3=[
 ("IPCC 연계 AI 콜센터 상담 시스템 구축","용역",500000000,"20261020","OPEN",{}),
 ("차세대 IPCC 고도화 구축 사업","용역",600000000,"20261020","OPEN",{}),
 ("생성형 AI 학습데이터 가공 및 구축 용역","용역",300000000,"20261020","OPEN",{}),
 ("비정형 문서 데이터 가공 용역","용역",200000000,"20261020","OPEN",{}),
 ("AI 챗봇 상담 서비스 구축 및 교육 지원","용역",400000000,"20261020","OPEN",{}),
 ("민원 콜센터 AI 상담 도입 컨설팅 및 구축","용역",500000000,"20261020","OPEN",{}),
 ("차세대 그룹웨어 재구축 사업 감리","용역",300000000,"20261020","DROP",{}),
 ("일반 회계시스템 구축 감리용역","용역",200000000,"20261020","DROP",{}),
 ("AI 상담 챗봇 운영 및 유지관리 용역","용역",200000000,"20261020","OPEN",{}),   # STRONG → 보호, D1 플래그
 ("PC 및 주변기기 구매","물품",30000000,"20261020","DROP",{}),
 ("생성형 AI 기반 민원상담 챗봇 구축","용역",2000000000,"20261020","OPEN",{"cmmnSpldmdMethdNm":"공동이행"}),  # v0.5: 20억 → OPEN, 포지션 구성사
 ("AI 기반 콜센터 상담 품질관리 시스템 구축","용역",900000000,"20261020","OPEN",{"arsltCmptYn":"N"}),
]
ok4=0
for nm,kind,amt,clse,expect,extra in EXTRA3:
    it={"bidNtceNm":nm,"presmptPrce":amt,"bidClseDt":clse,"dminsttNm":"",**extra}
    b,reason,score,hit,d,a,inst,pos,fl=s.classify(it,kind,TODAY)
    m="✓" if b==expect else "✗"; ok4+= b==expect
    print(f"{m} {b:<6}{expect:<7}{score:>4}  {nm[:40]:<42} → {pos}" + (f" ⚑{fl}" if fl else "") + ("" if b==expect else f"\n        └ {reason}"))
print(f"v0.4 회귀 {ok4}/{len(EXTRA3)}")
it={"bidNtceNm":"소형 무인기 탐지식별 테스트베드","presmptPrce":1950000000,"bidClseDt":"20261001","dminsttNm":""}
b,*_=s.classify(it,"용역",TODAY); print(("✓" if b=="DROP" else "✗")+" 탐지식별 오탐 →",b)

print("\n── v0.4.2 상담회 오탐 ──")
for nm,exp in [("제9회 한국-중국(산둥) 경제통상협력 교류회 상담회장 조성 및 운영 용역","DROP"),
               ("AI 상담 챗봇 구축 및 상담회 운영","OPEN"),
               ("민원 상담 콜센터 AI 도입","OPEN")]:
    b,*_=s.classify({"bidNtceNm":nm,"presmptPrce":159090909,"bidClseDt":"20261020","dminsttNm":""},"용역",TODAY)
    print(("✓" if b==exp else "✗")+f" {b:<6}{exp:<7} {nm[:50]}")

print("\n── v0.6 공통키워드·1억 하한·포지션 ──")
C6=[
 ("AI 상담 SaaS 구독 서비스 도입","용역",150000000,"20261020","OPEN",{}),
 ("robi형 콜센터 SaaS 구독형 서비스 계약","용역",300000000,"20261020","OPEN",{}),
 ("2027년 전자저널 및 학술DB 구독","용역",500000000,"20261020","DROP",{}),
 ("차세대 통합행정정보시스템 구축","용역",800000000,"20261020","WATCH",{"pubPrcrmntLrgClsfcNm":"ICT 서비스"}),
 ("차세대 통합행정정보시스템 구축","용역",80000000,"20261020","DROP",{"pubPrcrmntLrgClsfcNm":"ICT 서비스"}),
 ("주차장 관리시스템 구축","용역",800000000,"20261020","DROP",{"pubPrcrmntLrgClsfcNm":"시설관리"}),
 ("AI 챗봇 상담 시스템 구축","용역",50000000,"20261020","DROP",{}),
 ("생성형 AI 플랫폼 구축 감리","용역",30000000,"20261020","SIGNAL",{}),
]
ok6=0
for nm,kind,amt,clse,exp,extra in C6:
    b,r,sc,hit,d,a,inst,pos,fl=s.classify({"bidNtceNm":nm,"presmptPrce":amt,"bidClseDt":clse,"dminsttNm":"",**extra},kind,TODAY)
    ok6+= b==exp; print(("✓" if b==exp else "✗")+f" {b:<6}{exp:<7}{sc:>3}  {nm[:34]:<36} {r[:28]}" + ("" if b==exp else " ✗"))
b,r,sc,hit,d,a,inst,pos,fl=s.classify({"bidNtceNm":"AI 챗봇 구축","presmptPrce":900000000,"bidClseDt":"20261020","dminsttNm":"","cmmnSpldmdMethdNm":"(전자)공동이행"},"용역",TODAY)
print("포지션 예:", pos)
print(f"v0.6 회귀 {ok6}/{len(C6)}")

print("\n── v0.6.1 STRONG 보호 예외 ──")
C7=[
 ("Claude Pro 등 생성형AI 단기 사용권 구매","물품",101000000,"20260928","DROP",{}),
 ("생성형 AI 플랫폼 라이선스 및 구축","용역",300000000,"20260928","OPEN",{}),
 ("제조 AX Agent 로봇 현장 데이터 실증","용역",130000000,"20260928","DROP",{}),
 ("AI 챗봇 상담 로봇 안내 서비스 구축","용역",200000000,"20260928","OPEN",{}),
]
ok7=0
for nm,kind,amt,clse,exp,extra in C7:
    b,r,sc,*_=s.classify({"bidNtceNm":nm,"presmptPrce":amt,"bidClseDt":clse,"dminsttNm":"",**extra},kind,TODAY)
    ok7+= b==exp; print(("✓" if b==exp else "✗")+f" {b:<6}{exp:<7}{sc:>3}  {nm[:40]:<42} {r[:30]}")
print(f"v0.6.1 회귀 {ok7}/{len(C7)}")

print("\n── v0.6.3 마감 지남만 제외, D-7 미만은 플래그 ──")
for nm,clse,exp in [("AI 챗봇 상담 시스템 구축","20260905","DROP"),("AI 챗봇 상담 시스템 구축","20260916","OPEN"),("AI 챗봇 상담 시스템 구축","20260925","OPEN")]:
    b,r,*_=s.classify({"bidNtceNm":nm,"presmptPrce":300000000,"bidClseDt":clse,"dminsttNm":""},"용역",TODAY)
    print(("✓" if b==exp else "✗")+f" {b:<6}{exp:<7} 마감 {clse} (D-{(dt.datetime.strptime(clse,'%Y%m%d').date()-TODAY).days}) {r[:24]}")
