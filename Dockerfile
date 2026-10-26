# 실사용자 웹 서비스 이미지. 학습 번들·계정 DB·운영 기록은 이미지에 넣지 않고 /app/runs 볼륨에 둔다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-core.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY etfrec ./etfrec

# root가 아닌 사용자로 실행. 이름 있는 볼륨은 처음 붙을 때 이 폴더의 소유자를 물려받는다.
RUN useradd --create-home --uid 10001 etfrec && mkdir -p /app/runs && chown etfrec /app/runs
USER etfrec
VOLUME ["/app/runs"]
EXPOSE 8000

CMD ["python", "-m", "etfrec", "serve", "--public", "--host", "0.0.0.0", "--port", "8000", "--trust-proxy", \
     "--ops-dir", "runs/ops", "--db", "runs/web/etfrec.db", "--designs", "runs/designs"]
