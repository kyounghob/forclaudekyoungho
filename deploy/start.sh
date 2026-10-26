#!/bin/sh
# 컨테이너 시작 스크립트.
# 1) root로 시작했으면 기록 폴더(/app/runs) 소유자를 맞춘 뒤 일반 사용자(etfrec)로 다시 실행한다
#    (Docker 이름 있는 볼륨, Render·Railway 디스크는 root 소유로 붙는 경우가 있다).
# 2) 인자가 있으면 그 명령만 실행한다(예: docker compose run --rm app python -m etfrec web stats).
# 3) 인자가 없으면 첫 실행 준비(번들·운영 등록부·관리자, 이미 있으면 건너뜀) 뒤 공개 모드 서버를 띄운다.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/runs
  chown -R etfrec:etfrec /app/runs
  exec setpriv --reuid=etfrec --regid=etfrec --init-groups env HOME=/home/etfrec "$0" "$@"
fi
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
python -m etfrec web bootstrap --db runs/web/etfrec.db --bundle runs/seed42 --ops-dir runs/ops
exec python -m etfrec serve --public --host 0.0.0.0 --port "${PORT:-8000}" --trust-proxy \
  --ops-dir runs/ops --db runs/web/etfrec.db --designs runs/designs
