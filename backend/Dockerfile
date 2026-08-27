FROM python:3.12-slim

WORKDIR /app

# Keep dependency installation in its own cached layer. Source code is mounted
# by Docker Compose during development, so editing it does not reinstall the
# ML stack every time the backend container starts.
ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=5
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
