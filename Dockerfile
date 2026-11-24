# syntax=docker/dockerfile:1

# ========== 1. 构建前端静态资源 ==========
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ========== 2. 运行时镜像 ==========
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY Raw/ /app/Raw/
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

# 运行目录放在 backend，这样 `app.main:app` 可直接导入，
# 且 config.py 推导出的 BASE_DIR 正好是 /app（Raw/ 与 frontend/dist 所在处）。
WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
