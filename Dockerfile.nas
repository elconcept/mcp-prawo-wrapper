FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . "uvicorn>=0.30,<1"
RUN mkdir -p /tmp/prawo-audit && chown 1029:100 /tmp/prawo-audit
ENV HOME=/tmp PRAWO_PL_MCP_AUDIT_DIR=/tmp/prawo-audit
USER 1029:100
EXPOSE 8000
CMD ["uvicorn","prawo_pl_mcp.asgi:app","--host","0.0.0.0","--port","8000","--log-level","warning"]
