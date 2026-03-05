FROM python:3.12-slim

WORKDIR /app

COPY . /app/

RUN pip install --no-cache-dir -U pip build && \
    pip install --no-cache-dir '.[web]' && \
    python -m build --wheel --outdir dist/

EXPOSE $PORT

CMD gunicorn 'auto_goldfish.web:create_app()' --bind 0.0.0.0:${PORT:-8000} --preload --access-logfile - --error-logfile - --capture-output
