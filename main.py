import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import SQLAgentRouter

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = SQLAgentRouter()


class QueryRequest(BaseModel):
    question: str
    session_id: str = "default_session"


# ─── Mevcut senkron endpoint (geriye dönük uyumluluk) ────────────────────────

@app.post("/api/chat")
async def chat_with_db(payload: QueryRequest):
    try:
        answer = router(payload.question, payload.session_id)
        return {"answer": answer}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Streaming endpoint ───────────────────────────────────────────────────────

@app.post("/api/chat/stream")
async def stream_chat(payload: QueryRequest):
    async def event_generator():
        try:
            async for chunk in router.stream(payload.question, payload.session_id):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error_chunk = {"type": "error", "content": str(exc)}
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
