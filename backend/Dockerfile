# 백엔드 — Python 버전을 3.13 으로 고정 (PC마다 Python 버전 맞출 필요 없음)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# 코드는 docker-compose 에서 backend 폴더를 그대로 연결(마운트)하므로 이미지에는 참고용으로만 복사
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
