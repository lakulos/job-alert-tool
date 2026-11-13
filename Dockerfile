# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-compile .

FROM python:3.12-slim-bookworm AS runtime

ARG VERSION=dev
ARG SOURCE_URL=https://github.com/lakulos/job-alert-tool
ARG REVISION=unknown
LABEL org.opencontainers.image.title="job-alert" \
      org.opencontainers.image.description="Rule-based Cloud, DevOps, and SRE email digests" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.source="$SOURCE_URL" \
      org.opencontainers.image.revision="$REVISION" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JOB_ALERT_CONFIG=/app/config.yaml \
    JOB_ALERT_HEALTH_FILE=/app/.cache/job-alert/health \
    JOB_ALERT_TIMEZONE=Africa/Lagos \
    JOB_ALERT_TIMES=07:07,19:07 \
    RUN_ON_START=true

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates tini tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 jobalert \
    && useradd --uid 10001 --gid jobalert --home-dir /app --create-home --shell /usr/sbin/nologin jobalert \
    && mkdir -p /app/.cache/job-alert \
    && chown -R jobalert:jobalert /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=jobalert:jobalert config.yaml /app/config.yaml

WORKDIR /app
USER 10001:10001
VOLUME ["/app/.cache/job-alert"]

HEALTHCHECK --interval=1m --timeout=5s --start-period=30s --retries=3 \
    CMD test -s "$JOB_ALERT_HEALTH_FILE" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "job_alert.scheduler"]
