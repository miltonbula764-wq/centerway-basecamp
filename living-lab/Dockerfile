FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 lab && useradd --uid 10001 --gid lab --no-create-home lab && mkdir /data && chown lab:lab /data
COPY --chown=lab:lab lab /app/lab
USER 10001:10001
EXPOSE 8765
CMD ["python", "-m", "lab", "--config", "/etc/secrets/lab_config.json", "serve", "--bind", "0.0.0.0", "--port", "8765"]
