FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ARG BUILD_REV=source
COPY . /app
RUN python -m pip install --no-cache-dir .[real]

RUN useradd --create-home --user-group --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER 10001:10001
LABEL org.opencontainers.image.revision=$BUILD_REV

EXPOSE 8000
CMD ["uvicorn", "reference_agent.deployment:create_deployment_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
