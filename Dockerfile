# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# --mount=type=tmpfs stellt ein echtes beschreibbares tmpfs bereit,
# das auch in noexec-Umgebungen funktioniert
RUN --mount=type=tmpfs,target=/tmp \
    pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]