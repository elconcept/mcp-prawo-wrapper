FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=3.4,<4" "httpx>=0.27,<1" "beautifulsoup4>=4.12,<5" "uvicorn>=0.30,<1"
COPY server.py asgi.py ./
USER 1029:100
EXPOSE 8000
CMD ["uvicorn","asgi:app","--host","0.0.0.0","--port","8000","--log-level","warning"]
