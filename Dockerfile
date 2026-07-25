FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/llmwho
COPY packages/python/ /opt/llmwho/
RUN python -m pip install --no-cache-dir . \
    && adduser --disabled-password --gecos "" --uid 10001 llmwho \
    && mkdir -p /data \
    && chown llmwho:llmwho /data

USER 10001:10001
VOLUME ["/data"]
EXPOSE 7734
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:7734/api/health', timeout=2).read()"]

ENTRYPOINT ["llmwho"]
CMD ["collector", "--host", "0.0.0.0", "--port", "7734", "--database", "/data/collector.sqlite3"]
