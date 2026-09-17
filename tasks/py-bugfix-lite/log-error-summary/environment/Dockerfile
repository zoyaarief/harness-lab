FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY app/ /app/
RUN python _build.py && rm _build.py
