#!/bin/bash
# ETF 학습 추천 파일럿 서버(맥·리눅스). 처음 실행하면 가상환경(.venv)을 만들고 패키지를 설치한 뒤 "python -m etfrec desktop"을 띄운다.
cd "$(dirname "$0")/../.." || exit 1
if [ ! -x .venv/bin/python ]; then
  PY=""
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then PY="$c"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "Python 3.11 이상이 필요합니다. 맥: brew install python@3.12 (또는 python.org 설치 파일)"
    [ -t 0 ] && read -r -p "엔터를 누르면 닫힙니다"
    exit 1
  fi
  echo "처음 실행: 가상환경을 만들고 패키지를 설치합니다(몇 분 걸립니다)…"
  if ! { "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements-web.txt; }; then
    echo "패키지 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요"
    [ -t 0 ] && read -r -p "엔터를 누르면 닫힙니다"
    exit 1
  fi
fi
exec .venv/bin/python -m etfrec desktop "$@"
