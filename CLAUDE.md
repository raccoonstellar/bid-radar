# 입찰 레이더 (bid-radar)

포지큐브 영업팀의 조달청·나라장터 공고 일일 스크리닝. 매일 07:30 KST 루틴 실행.

## 브랜치 규칙 (중요)
클라우드 루틴은 `claude/` 접두 브랜치에만 push 가능. 데이터 브랜치는 **`claude/radar`** 하나로 고정한다.
GitHub Pages 대시보드도 이 브랜치의 `/docs`를 본다. `main`은 코드 원본이며 루틴이 건드리지 않는다.

## 실행 순서 (루틴이 하는 일)
1. 데이터 브랜치로 이동
   - `git fetch origin claude/radar && git checkout claude/radar` 
   - 원격에 없으면(첫 실행) `git checkout -b claude/radar`
   - 코드가 main보다 오래됐으면 `git merge origin/main --no-edit` (코드 갱신 반영)
2. `bash run_daily.sh` 실행 (환경변수 `G2B_KEY` 필요 — 절대 파일에 쓰지 않는다)
   - `screen_g2b.py`: API 수집 → `out/screen_YYYYMMDD.json` (범위: 마지막 성공일-1 ~ 오늘, 3~14일)
   - `build_data.py`: `docs/data/{bids,runs,latest}.json` 병합
3. `git add docs/data && git commit -m "radar YYYY-MM-DD: 수집 N건 통과 M건" && git push origin claude/radar`
4. 완료 보고: `docs/data/runs.json` 첫 항목(total·pass·buckets·drops) + OPEN 상위 5건(점수·D-day·금액·공고명·포지션)

## 실패 처리
- 스크립트가 페이지 단위로 6회 재시도하고 실패 페이지는 건너뛴다. stderr 에 "부분 수집" 경고가 있으면 보고에 실패 페이지 수를 적는다 (다음 실행이 겹침 범위로 메운다)
- 총 수집 0건이면 "수집 실패 — 네트워크/키 확인"으로 보고하고 커밋하지 않는다
- 0건 수집: 공휴일일 수 있음. `docs/data`는 건드리지 않고 보고만
- 규칙 파일(`screen_g2b.py`)은 루틴에서 수정하지 않는다. 오탐이 보이면 보고에 적기만 한다

## 하지 않는 것
- 공고서 열기, 참여 판단, Decision Card — 사람 영역
- `docs/index.html` 수정 — 대시보드 변경은 별도 작업
- 키·비밀값을 커밋하거나 로그에 출력
- `main` 브랜치에 push

## 파일
- `screen_g2b.py` 필터 v0.4 (기준 문서 `조달청_공고_1차스크리닝_기준_v0.2.md` 기반)
- `test_filter.py` 회귀 67케이스 — 규칙 수정 시 반드시 실행
- `docs/` GitHub Pages 대시보드 (`docs/data/*.json` 을 읽음)
