# bid-radar
조달청·나라장터 공고 일일 스크리닝 (포지큐브 영업팀). 대시보드: `https://raccoonstellar.github.io/bid-radar/`

- 수집·판정 규칙: `screen_g2b.py` / 회귀 테스트: `python3 test_filter.py`
- 데이터: `docs/data/bids.json`(누적), `runs.json`(일별 통계), `latest.json`(당일)
- 인증키는 저장소에 없음 — 실행 환경의 `G2B_KEY` 환경변수
