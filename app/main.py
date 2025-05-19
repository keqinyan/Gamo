from fastapi import FastAPI, Body, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4

from .models import WorldState
from .generator import create_world, generate_event, apply_choice, generate_ending

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://keqinyan.github.io"],  # 你的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"ok": True}

SESSIONS: dict[str, WorldState] = {}

# ─────────────────────────────────────────────
# cookie 助手
# ─────────────────────────────────────────────
from typing import Optional

def get_sid(req: Request, resp: Response, *, create: bool = True) -> Optional[str]:
    sid = req.cookies.get("sid")
    if sid or not create:
        return sid

    sid = uuid4().hex
    resp.set_cookie(
        "sid", sid,
        max_age=60*60*24*30,
        path="/",
        samesite="none", secure=True,
    )
    return sid

# ─────────────────────────────────────────────
# Pydantic bodies
# ─────────────────────────────────────────────
from pydantic import BaseModel

class NewGameIn(BaseModel):
    tags: list[str]
    lang: str = "zh"
    need_avatar: bool = False
    avatar_style: str = "anime"

class ChoiceIn(BaseModel):
    choice_id: str | None = None
    custom_input: str | None = None
    lang: str = "zh"
    sid : str | None = None   # 前端会回传，兜底

# ─────────────────────────────────────────────
# /new
# ─────────────────────────────────────────────
@app.post("/new")
def new_game(
    req : Request,
    resp: Response,
    body: NewGameIn = Body(...),
):
    sid = get_sid(req, resp)

    ws  = create_world(
        body.tags,
        lang          = body.lang,
        need_avatar   = body.need_avatar,
        avatar_style  = body.avatar_style,
    )
    evt = generate_event(ws, body.lang)

    ws.flags.update({
        "current_event_text": evt["text"],
        "last_options"      : evt["options"],
    })
    SESSIONS[sid] = ws

    return {
        "sid"      : sid,
        "summary"  : ws.summary,
        "main_plot": ws.main_plot,
        "characters": {k: c.model_dump() for k, c in ws.characters.items()},
        "event"    : evt,
    }

# ─────────────────────────────────────────────
# /choice
# ─────────────────────────────────────────────
@app.post("/choice")
def choose(
    req : Request,
    resp: Response,
    body: ChoiceIn = Body(...),
):
    sid = body.sid or get_sid(req, resp, create=False)
    if not sid or sid not in SESSIONS:
        raise HTTPException(400, "请先 /new 开局")

    ws = SESSIONS[sid]

    if body.custom_input:
        use_choice_id = None
        options       = []
    else:
        use_choice_id = body.choice_id
        options       = ws.flags.get("last_options", [])

    ws, narration = apply_choice(
        ws,
        choice_id    = use_choice_id,
        options      = options,
        custom_input = body.custom_input,
        lang         = body.lang,
    )

    nxt = generate_event(ws, body.lang)
    ws.flags.update({
        "current_event_text": nxt["text"],
        "last_options"      : nxt["options"],
    })
    SESSIONS[sid] = ws

    return {"result": narration, "event": nxt}

# ─────────────────────────────────────────────
# /end
# ─────────────────────────────────────────────
@app.post("/end")
def end_game(req: Request, resp: Response, body: dict = Body(None)):
    lang = body.get("lang", "zh") if body else "zh"
    sid  = get_sid(req, resp, create=False)
    ws   = SESSIONS.get(sid)
    if not ws:
        raise HTTPException(400, "没有进行中的游戏")

    ending = generate_ending(ws, lang)
    SESSIONS.pop(sid, None)
    return ending