#!/usr/bin/env bash
# 입찰 레이더 일일 실행 — 수집 → 병합 → OPEN 건 공고서 자동 확인. G2B_KEY 환경변수 필요.
set -uo pipefail
cd "$(dirname "$0")"
: "${G2B_KEY:?G2B_KEY 환경변수가 없습니다 (data.go.kr 일반 인증키 Decoding)}"
set -e
python3 screen_g2b.py "$@"
python3 build_data.py
set +e
# Stage 1.5 — 공고서 텍스트 추출. HWP·PDF 파서는 저장소에 동봉(vendor/)돼 있어 설치 불필요. pdftotext 가 있으면 품질만 조금 좋아짐
command -v pdftotext >/dev/null 2>&1 || (apt-get install -y -qq poppler-utils >/dev/null 2>&1 || sudo apt-get install -y -qq poppler-utils >/dev/null 2>&1 || true)
python3 read_notice.py || echo "  ! 공고서 확인 단계 실패 — 수집·병합은 완료됨"
python3 opening.py || echo "  ! 개찰결과 단계 실패 — 낙찰정보서비스 활용신청 확인"
exit 0
