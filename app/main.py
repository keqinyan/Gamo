from uuid import uuid4
from typing import Dict

from fastapi import FastAPI, Body, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models     import WorldState
from .generator  import (
    create_world, generate_event, apply_choice, generate_ending,
)

# ────────── FastAPI & CORS ──────────
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["https://keqinyan.github.io"],  # 前端域名
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ────────── 内存存档 ──────────
SESSIONS: Dict[str, WorldState] = {}

def get_sid(req: Request, resp: Response) -> str:
    sid = req.cookies.get("sid")
    if not sid:
        sid = uuid4().hex
        resp.set_cookie(
            "sid", sid,
            max_age  = 60*60*24*30,
            path     = "/",
            samesite = "none",
            secure   = True,            # 线上 https
        )
    return sid

# ────────── 请求体模型 ──────────
class NewGameIn(BaseModel):
    tags: list[str]
    lang: str = "zh"

class ChoiceIn(BaseModel):
    sid: str
    choice_id: str | None = None
    custom_input: str | None = None
    lang: str = "zh"

class EndIn(BaseModel):
    sid: str
    lang: str = "zh"

# ────────── 路由 ──────────
@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/new")
def new_game(
    req : Request,
    resp: Response,
    body: NewGameIn = Body(...),
):
    sid = get_sid(req, resp)

    ws  = create_world(body.tags, body.lang)
    evt = generate_event(ws, body.lang)

    ws.flags["current_event_text"] = evt["text"]
    ws.flags["last_options"]       = evt["options"]
    SESSIONS[sid] = ws

    return {
        "sid": sid,   
        "summary"   : ws.summary,
        "main_plot" : ws.main_plot,
        "event"     : evt,
    }

@app.post("/choice")
def choose(
    req : Request,
    resp: Response,
    body: ChoiceIn = Body(...),
):
    sid = body.sid
    if not sid or sid not in SESSIONS:
        raise HTTPException(400, "请先开局")
    ws  = SESSIONS.get(sid)
    if ws is None:
        raise HTTPException(400, "请先开局")

    # 判定按钮 / 自定义
    if body.custom_input:
        use_choice_id = None
        options       = []                      # 用不到
    else:
        use_choice_id = body.choice_id
        options       = ws.flags.get("last_options", [])

    # 结算 & 生成下一幕
    new_ws, narration = apply_choice(
        ws,
        choice_id   = use_choice_id,
        options     = options,
        custom_input= body.custom_input,
        lang        = body.lang,
    )
    nxt_evt = generate_event(new_ws, body.lang)

    new_ws.flags["current_event_text"] = nxt_evt["text"]
    new_ws.flags["last_options"]       = nxt_evt["options"]
    SESSIONS[sid] = new_ws             # 更新存档

    return {"result": narration, "event": nxt_evt}


@app.post("/end")
def end_game(
    req: Request,
    resp: Response,
    body: EndIn = Body(...)):
    sid  = body.sid
    lang = body.lang

    ws = SESSIONS.get(sid)
    if ws is None:
        raise HTTPException(400, "没有进行中的游戏")

    ending = generate_ending(ws, lang)
    SESSIONS.pop(sid, None)      # 清存档
    return ending