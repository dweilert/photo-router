# ---- Stage 1: dependency builder ----------------------------------------
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime image ---------------------------------------------
FROM python:3.11-slim AS runtime
RUN useradd --no-create-home --shell /bin/false router
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
RUN chmod -R 755 /app/app
ENV PHOTO_ROUTER_CONFIG=/config/config.yaml
ENV PYTHONPATH=/app
EXPOSE 8000
USER router
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]