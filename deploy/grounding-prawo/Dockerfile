# mcp-prawo: wrapper prawo-pl-mcp przed konektorami wdrożonymi na NAS (saos, nsa, ustawy).
# Kontekst budowania: korzeń repo mcp-prawo-wrapper.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN pip install --no-cache-dir ".[asgi]"
ENV PRAWO_PL_MCP_SOURCES=saos,nsa,ustawy
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 3)"
USER 1029:100
CMD ["uvicorn", "prawo_pl_mcp.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
