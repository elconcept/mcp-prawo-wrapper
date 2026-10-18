FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src/ /app/src/
RUN pip install --no-cache-dir ".[asgi]" && python -m compileall -q /app/src
USER 1026:100
EXPOSE 8000
CMD ["uvicorn", "prawo_pl_mcp.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
