#!/usr/bin/env bash
# 입찰 레이더 일일 실행 — 수집 → 병합. G2B_KEY 환경변수 필요.
set -euo pipefail
cd "$(dirname "$0")"
: "${G2B_KEY:?G2B_KEY 환경변수가 없습니다 (data.go.kr 일반 인증키 Decoding)}"
python3 screen_g2b.py "$@"
python3 build_data.py
