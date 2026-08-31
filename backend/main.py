from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routes.sessions import router as sessions_router
from routes.analytics import router as analytics_router
from routes.ws import router as ws_router
from routes.chat import router as chat_router
from routes.keys import router as keys_router
from routes.test_gen import router as test_gen_router

app = FastAPI(title="Loop Runner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(analytics_router)
app.include_router(ws_router)
app.include_router(chat_router)
app.include_router(keys_router)
app.include_router(test_gen_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():
    init_db()
