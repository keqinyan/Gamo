from fastapi import FastAPI, Body, HTTPException, Request, Response
from .models import WorldState
from .generator import create_world, generate_event, apply_choice, generate_ending
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://keqinyan.github.io"],  # 或你的自定义域名
    allow_credentials=True,                        # ★ 必须
    allow_methods=["*"],
    allow_headers=["*"],
)


# 给 Render 健康检查用的根路径
@app.get("/")
def root():
    return {"status": "ok"}

SESSIONS: dict[str, WorldState] = {}

def get_sid(req: Request, resp: Response) -> str:
    sid = req.cookies.get("sid")
    if not sid:
        sid = uuid4().hex
        resp.set_cookie("sid", sid, max_age=60*60*24*30)   # 30 天
    return sid

@app.post("/new")
def new_game(tags: list[str], req: Request, resp: Response):
    sid = get_sid(req, resp)
    ws = create_world(tags)
    evt = generate_event(ws)
    ws.flags["current_event_text"] = evt["text"]
    ws.flags["last_options"] = evt["options"]
    SESSIONS[sid] = ws
    return {"world": ws, "event": evt}

class ChoiceIn(BaseModel):
    choice_id: str | None = None
    custom_input: str | None = None

@app.post("/choice")
def choose(payload: ChoiceIn, req: Request, resp: Response):
    sid = get_sid(req, resp)
    ws = SESSIONS.get(sid)
    if not ws:
        raise HTTPException(400, "请先 /new 开局")
    if ws is None:
        raise HTTPException(400, "请先 /new 开局")

    # ─── 判断是按钮还是自由文本 ───────────────────────
    if payload.custom_input:
        use_choice_id = None
        options = []                         # 按钮选项用不到
    else:
        use_choice_id = payload.choice_id
        options = ws.flags.get("last_options", [])

    # ─── 结算本轮 ───────────────────────────────────
    new_ws, result = apply_choice(
        ws,
        choice_id = use_choice_id,
        options   = options,
        custom_input = payload.custom_input,
    )
    SESSIONS["ws"] = new_ws

    # ─── 生成下一事件 ────────────────────────────────
    nxt_evt = generate_event(new_ws)
    new_ws.flags["current_event_text"] = nxt_evt["text"]
    new_ws.flags["last_options"]       = nxt_evt["options"]

    return {"result": result, "event": nxt_evt}

@app.post("/end")
def end_game():
    ws = SESSIONS.get("ws")
    if ws is None:
        raise HTTPException(400, "没有进行中的游戏")

    ending = generate_ending(ws)
    # 可在此处把 ws 存档到数据库，然后清 session
    SESSIONS.pop("ws", None)
    return ending
