# 셋업 — 처음 한 번

## 1. 파일 올리기 (GitHub 웹, 5분)
1. https://github.com/raccoonstellar/bid-radar → **Add file → Upload files**
2. 이 zip을 푼 폴더 안의 내용물 전체(폴더 포함)를 드래그 → Commit changes
   - 올라가야 할 것: `screen_g2b.py` `test_filter.py` `build_data.py` `run_daily.sh` `CLAUDE.md` `README.md` `.gitignore` `docs/`(안에 index.html, data/)
3. 확인: 저장소 첫 화면에 `docs` 폴더와 `CLAUDE.md`가 보이면 됨

## 2. 대시보드 켜기 (GitHub Pages, 2분)
1. 저장소 **Settings → Pages**
2. Source: **Deploy from a branch** / Branch: **main** / 폴더: **/docs** → Save
3. 1~2분 뒤 `https://raccoonstellar.github.io/bid-radar/` 열림 — "아직 수집 데이터가 없습니다" 문구가 정상 (첫 실행 전)

## 3. Claude Code 웹 연결 + 인증키 (5분)
1. claude.ai → 왼쪽 **Code** → 저장소 연결(GitHub 인증) → `raccoonstellar/bid-radar` 선택
2. 환경 설정에서 **환경변수** 추가: 이름 `G2B_KEY`, 값 = `g2b.env` 안의 키 (따옴표 없이)
3. 같은 환경 설정에서 **네트워크 접근**을 가장 넓게 (Full internet / 제한 없음)

## 4. 첫 실행 — 여기서 네트워크가 뚫리는지 확인
Claude Code 새 세션에 아래 그대로:

```
CLAUDE.md 대로 오늘 수집을 한 번 돌려줘. 시작 전에
curl -s -o /dev/null -w "%{http_code}" "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc?inqryDiv=1&type=json&inqryBgnDt=202609150000&inqryEndDt=202609162359&pageNo=1&numOfRows=1&ServiceKey=$G2B_KEY"
로 API 응답코드부터 확인해. 200이 아니면 그 코드와 응답 본문 앞 300자를 보고하고 멈춰.
200이면 ./run_daily.sh 실행 → docs/data 커밋·푸시 → runs.json 첫 항목과 OPEN 상위 5건 보고.
```

- 200 → 성공. 2~3분 뒤 대시보드 새로고침하면 데이터가 보임
- 403 / 연결 실패 → 네트워크 차단. 관리자에게 "Claude Code 환경 네트워크에 apis.data.go.kr 허용" 요청

## 5. 예약 등록
4가 성공한 세션에서 예약 작업 생성:
- 이름: `입찰 레이더`
- 주기: 매일 07:30 (KST)
- 프롬프트:
```
CLAUDE.md 대로 오늘 수집을 돌리고 docs/data를 커밋·푸시한 뒤 보고해줘.
```
(PC·크롬 무관. 놓친 날은 다음 실행이 자동으로 따라잡음 — 범위가 마지막 성공일 기준)

## 매일
- 대시보드 URL 열기. 끝.
- status 버튼(신규→검토중→제안준비→드롭)은 이 브라우저에 저장됨. 금요일에 "엑셀(CSV) 내보내기" 한 번
- OPEN 건 판단·Decision Card는 「입찰 레이더」 채팅 프로젝트에서
