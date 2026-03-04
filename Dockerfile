FROM python:3.12-slim

WORKDIR /app

COPY . /app/

RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir '.[web,db]'

EXPOSE $PORT

CMD gunicorn 'auto_goldfish.web:create_app()' --bind 0.0.0.0:${PORT:-8000}
