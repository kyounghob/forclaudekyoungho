#!/usr/bin/env bash
# 보고서 두 개(중간보고서·비판 검토 보고서)를 다시 만든다. 먼저 번들이 있어야 한다(bundle.pkl은 저장소에 없으므로 학습):
#   python -m etfrec train --out artifacts/bundle_v2
#   python scripts/regression_check.py artifacts/bundle_v1      # 노트북 v1 세계
# 필요: pip install matplotlib pillow(그림, requirements.txt 밖), node와 docx 패키지(npm i docx). 순서: 그림 → 데이터(report_data.json) → Word → docs/report로 복사
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; PY="${PYTHON:-python}"
"$PY" "$HERE/make_figures.py"
"$PY" "$HERE/export_data.py"
node "$HERE/build_report.js" "$ROOT/docs/report/중간보고서_ETF_교육_콘텐츠_추천시스템.docx"
node "$HERE/build_critique_response.js" "$ROOT/docs/report/비판검토_보완보고서.docx"
cp "$HERE"/fig/fig*.png "$ROOT/docs/report/"
