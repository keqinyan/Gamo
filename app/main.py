from fastapi import FastAPI, Body, HTTPException
from .models import WorldState
from .generator import create_world, generate_event, apply_choice, generate_ending
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 生产时可写具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)

# 给 Render 健康检查用的根路径
@app.get("/")
def root():
    return {"status": "ok"}

SESSION: dict[str, WorldState] = {}

@app.post("/new")
def new_game(tags: list[str] = Body(...)):
    ws = create_world(tags)
    evt = generate_event(ws)

    ws.flags["current_event_text"] = evt["text"]
    ws.flags["last_options"] = evt["options"]
    ws.flags["last_choice_text"] = ""        # 开局为空
    SESSION["ws"] = ws

    return {"world": ws, "event": evt}

class ChoiceIn(BaseModel):
    choice_id: str | None = None
    custom_input: str | None = None

@app.post("/choice")
def choose(payload: ChoiceIn):
    ws = SESSION.get("ws")
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
    SESSION["ws"] = new_ws

    # ─── 生成下一事件 ────────────────────────────────
    nxt_evt = generate_event(new_ws)
    new_ws.flags["current_event_text"] = nxt_evt["text"]
    new_ws.flags["last_options"]       = nxt_evt["options"]

    return {"result": result, "event": nxt_evt}

@app.post("/end")
def end_game():
    ws = SESSION.get("ws")
    if ws is None:
        raise HTTPException(400, "没有进行中的游戏")

    ending = generate_ending(ws)
    # 可在此处把 ws 存档到数据库，然后清 session
    SESSION.pop("ws", None)
    return ending
