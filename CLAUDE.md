# 입찰 레이더 (bid-radar)

포지큐브 영업팀의 조달청·나라장터 공고 일일 스크리닝. 매일 07:30 KST 루틴 실행.

## 브랜치 규칙 (중요)
클라우드 루틴은 `claude/` 접두 브랜치에만 push 가능. 데이터 브랜치는 **`claude/radar`** 하나로 고정한다.
GitHub Pages 대시보드도 이 브랜치의 `/docs`를 본다. `main`은 코드 원본이며 루틴이 건드리지 않는다.

## 실행 원칙
- **같은 날 이미 실행됐어도 다시 돌린다.** 수집은 3일 겹침 설계라 재실행이 무해하고(공고번호 중복 제거, 같은 날짜 runs 덮어씀), 오후 등록분·정정 차수를 잡으려면 재실행이 필요하다. "중복 API 호출 방지"를 이유로 건너뛰지 않는다 (일일 한도 1,000회 중 한 번에 ~40회 사용).
- 실행 시각·중복 여부는 보고에 적되, 실행 자체를 생략하는 판단은 하지 않는다.

## 실행 순서 (루틴이 하는 일)
1. 데이터 브랜치로 이동
   - `git fetch origin claude/radar && git checkout claude/radar` 
   - 원격에 없으면(첫 실행) `git checkout -b claude/radar`
   - 코드가 main보다 오래됐으면 `git merge origin/main --no-edit` (코드 갱신 반영)
2. `bash run_daily.sh` 실행 (환경변수 `G2B_KEY` 필요 — 절대 파일에 쓰지 않는다)
   - `screen_g2b.py`: API 수집 → `out/screen_YYYYMMDD.json` (범위: 마지막 성공일-1 ~ 오늘, 3~14일)
   - `build_data.py`: `docs/data/{bids,runs,latest}.json` 병합
   - `opening.py`: 낙찰정보서비스로 개찰결과 수집 → `docs/data/competitors.json` (Core 키워드 건만, 유찰·AICC 접점 태그). 활용신청 미승인이면 실패해도 무방
   - `read_notice.py`: OPEN 건 공고서 첨부를 내려받아 5분 게이트 항목(공동수급·하도급·실적·배점·제출방식·대기업제한) 추출 → `docs/data/notices/` (Stage 1.5, 실패해도 무방)
3. `git add docs/data && git commit -m "radar YYYY-MM-DD: 수집 N건 통과 M건" && git push origin claude/radar`
4. 완료 보고: `docs/data/runs.json` 첫 항목(total·pass·buckets·drops) + OPEN 상위 5건(점수·D-day·금액·공고명·포지션) + 개찰결과 신규 건수(유찰 포함) + 공고서 확인 결과(`docs/data/notices/index.json`: ok/실패/첨부없음 건수, 공동수급 불허·차등제·방문제출로 잡힌 건 이름)

## 환경 요구
없음. HWP·PDF 텍스트 추출기는 저장소에 동봉(`vendor/olefile`, `vendor/pypdf`, `hwp_text.py`)돼 있어 pip·apt 설치가 필요 없다. `vendor/`는 수정하지 않는다.

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
