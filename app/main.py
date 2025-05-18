from fastapi import FastAPI, Body, HTTPException
from .models import WorldState
from .generator import create_world, generate_event, apply_choice

app = FastAPI()
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

@app.post("/choice")
def choose(choice_id: str = Body(..., embed=True)):
    ws = SESSION.get("ws")
    if ws is None:
        raise HTTPException(400, "请先 /new 开局")

    options = ws.flags.get("last_options")
    new_ws, result = apply_choice(ws, choice_id, options)

    nxt = generate_event(new_ws)
    new_ws.flags["current_event_text"] = nxt["text"]
    new_ws.flags["last_options"] = nxt["options"]
    SESSION["ws"] = new_ws

    return {"result": result, "event": nxt}
