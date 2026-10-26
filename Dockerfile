# 실사용자 웹 서비스 이미지. 학습 번들·계정 DB·운영 기록은 이미지에 넣지 않고 /app/runs(볼륨·디스크)에 둔다.
# 첫 실행 때 번들 학습·운영 등록부·관리자 계정을 자동으로 준비한다(deploy/start.sh, 이미 있으면 건너뜀).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-core.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY etfrec ./etfrec
COPY deploy/start.sh ./deploy/start.sh

# 서버는 root가 아닌 etfrec 사용자로 돈다(start.sh가 /app/runs 권한을 맞춘 뒤 권한을 내린다).
RUN useradd --create-home --uid 10001 etfrec && mkdir -p /app/runs && chown etfrec /app/runs && chmod +x deploy/start.sh
VOLUME ["/app/runs"]
EXPOSE 8000
ENTRYPOINT ["/app/deploy/start.sh"]
