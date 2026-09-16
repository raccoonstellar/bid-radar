# 입찰 레이더 (bid-radar)

포지큐브 영업팀의 조달청·나라장터 공고 일일 스크리닝. 매일 07:30 KST 예약 실행.

## 실행 순서 (예약 작업이 하는 일)
1. `./run_daily.sh` 실행 (환경변수 `G2B_KEY` 필요 — 절대 파일에 쓰지 않는다)
   - `screen_g2b.py`: 나라장터 API 수집 → `out/screen_YYYYMMDD.json` (범위: 마지막 성공일-1 ~ 오늘, 3~14일)
   - `build_data.py`: `docs/data/{bids,runs,latest}.json` 병합
2. `git add docs/data && git commit -m "radar YYYY-MM-DD: 수집 N건 통과 M건" && git push`
3. 완료 보고: `docs/data/runs.json` 첫 항목(total·pass·buckets·drops) + OPEN 상위 5건(점수·D-day·금액·공고명·포지션)

## 실패 처리
- API 403/타임아웃: 1분 후 1회 재시도. 그래도 실패면 "수집 실패 — 네트워크/키 확인"으로 보고하고 커밋하지 않는다
- 0건 수집: 공휴일일 수 있음. `docs/data`는 건드리지 않고 보고만
- 규칙 파일(`screen_g2b.py`)은 예약 실행에서 수정하지 않는다. 오탐이 보이면 보고에 적기만 한다

## 하지 않는 것
- 공고서 열기, 참여 판단, Decision Card — 사람 영역
- `docs/index.html` 수정 — 대시보드 변경은 별도 작업
- 키·비밀값을 커밋하거나 로그에 출력

## 파일
- `screen_g2b.py` 필터 v0.4 (기준 문서 `조달청_공고_1차스크리닝_기준_v0.2.md` 기반)
- `test_filter.py` 회귀 67케이스 — 규칙 수정 시 반드시 실행
- `docs/` GitHub Pages 대시보드 (`docs/data/*.json` 을 읽음)
