# TaskQ's admin UI in its own image: its [fastapi] extra needs newer FastAPI, uvicorn and redis than the backend pins,
# and it reads only Postgres and Redis, never Loop Runner's code.
FROM python:3.12-slim

RUN pip install --no-cache-dir "taskq-py[fastapi,redis]==0.2.2"

CMD ["taskq", "ui", "serve", "--host", "0.0.0.0", "--port", "8080"]
