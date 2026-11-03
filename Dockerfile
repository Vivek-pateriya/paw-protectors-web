FROM node:22-alpine AS website
WORKDIR /build
COPY website/package.json website/package-lock.json ./
RUN npm ci
COPY website/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY backend/requirements-lock.txt /app/backend/requirements-lock.txt
RUN pip install --no-cache-dir -r backend/requirements-lock.txt
COPY backend/ /app/backend/
COPY database/ /app/database/
COPY scripts/__init__.py scripts/init_db.py scripts/start_render.py /app/scripts/
COPY website/package.json /app/website/package.json
COPY --from=website /build/dist /app/website/dist
EXPOSE 10000
CMD ["python", "-m", "scripts.start_render"]
