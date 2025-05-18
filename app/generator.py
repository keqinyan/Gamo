"""
app/generator.py
连续剧情版
"""
from __future__ import annotations
import os, json
from uuid import uuid4
from typing import List, Dict, Tuple

from jinja2 import Template
from openai import OpenAI
from .models import WorldState, Character
import json, re, time
from openai import OpenAI

# ────────── 配置 ──────────
# 你也可以直接写 MODEL = "gpt-4o-mini"，但硬编码后切模型要改代码。
MODEL = "gpt-4o-mini"#os.getenv("LLM_MODEL", "gpt-4o-mini")   # 没配就默认 mini
STYLE_HINT = (
    "作品风格充满脑洞与幽默、惊悚与反转，但又不失深度。用简体中文。非常非常吸引人，掌握流量密码，作品读起来不像ai写的。请用第二人称，尽可能让玩家身临其境，参与感拉满。"
)

client = OpenAI()

# ────────── Prompt 模板 ──────────
WORLD_PROMPT = Template(
    """
你是高自由度 RPG 的世界生成器。请用第二人称，尽可能让玩家身临其境，参与感拉满。玩家关键词：{{ keywords }}。
请严格以 JSON 返回：
{
  "summary": "...(≤200 字世界观)...",
  "characters": {
    "MAIN": { "name":"...", "role":"主角", "traits":["..."] },
    "NPC1": { "name":"...", "role":"引路人", "traits":["..."] },
    "NPC2": { "name":"...", "role":"路人甲", "traits":["..."] }
  }
}
""".strip()
)

EVENT_PROMPT = Template(
    """
<世界观>
{{ summary }}
</世界观>

{% if last_event %}
<上轮事件>
{{ last_event }}
玩家上轮选择：{{ last_choice }}
</上轮事件>
{% endif %}

- 若上轮事件留悬念，请优先续写其后续。  
- 若无悬念，可开新事件，但需与世界观和时间线呼应。  

输出严格 JSON：
{
  "text": "...",
  "options": [
    {"id":"A","text":"...","impact":1},
    {"id":"B","text":"...","impact":0},
    {"id":"C","text":"...","impact":-1}
  ]
}
""".strip()
)

# ────────── 生成世界观 ──────────
def create_world(tags: List[str]) -> WorldState:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": STYLE_HINT},
            {"role": "user", "content": WORLD_PROMPT.render(keywords="、".join(tags))},
        ],
        response_format={"type": "json_object"},
        max_tokens=600,
    )
    data = json.loads(resp.choices[0].message.content)

    chars: Dict[str, Character] = {
        k: Character(id=str(uuid4()), **v) for k, v in data["characters"].items()
    }

    return WorldState(
        genre_tags=tags,
        summary=data["summary"],
        characters=chars,
        timeline=[],
        flags={},        # current_event_text / last_options / last_choice_text / karma
    )

# ────────── 生成事件 ──────────
def _safe_json_parse(text: str) -> dict:
    """
    尝试把模型输出解析成 dict：
    1. 直接 json.loads
    2. 正则提取首个 {...}
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group())
        raise  # 留给调用方处理

def generate_event(world: WorldState, retry: int = 1) -> dict:
    prompt = EVENT_PROMPT.render(
        summary=world.summary,
        last_event=world.flags.get("current_event_text", ""),
        last_choice=world.flags.get("last_choice_text", ""),
    )

    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": STYLE_HINT},
            # 额外强调只能 JSON
            {"role": "user",    "content": prompt + "\n\n⚠️ 请严格仅输出 JSON 对象，禁止任何注释或多余文本。"},
        ],
        response_format={"type": "json_object"},
        max_tokens=500,
        temperature=0.7,
    )

    content = rsp.choices[0].message.content
    try:
        return _safe_json_parse(content)
    except json.JSONDecodeError as e:
        if retry > 0:
            print("WARN json decode error, retry once …")
            time.sleep(0.5)                 # 给模型节拍
            return generate_event(world, retry - 1)
        # 把错误写入日志并抛，让前端看到可提示“服务器繁忙”
        print("FATAL cannot parse LLM JSON:\n", content[:800])
        raise e

# ────────── 结算选择 ──────────
def apply_choice(
    world: WorldState, choice_id: str, options: List[Dict]
) -> Tuple[WorldState, str]:
    if not options:
        raise ValueError("缺少上一轮选项")
    if custom_input:
        prompt = f"玩家说：{custom_input}。你作为旁白叙述后果并返回 impact。"
        # 让 GPT 输出 {"narration":"...", "impact":0, "new_flag":{...}}
    else:
        opt = next((o for o in options if o["id"] == choice_id.upper()), None)
        if not opt:
            raise ValueError("非法选项 id")

        karma = world.flags.get("karma", 0) + opt["impact"]
        world.flags["karma"] = karma
        world.flags["last_choice_text"] = opt["text"]          # 记录给下一轮

        world.timeline.append(
            {
                "event": world.flags.get("current_event_text", ""),
                "choice": opt["text"],
                "impact": opt["impact"],
                "karma": karma,
            }
        )

        narr = (
            f"你选择了【{opt['text']}】。"
            f"业障变化 {opt['impact']:+d}，当前业障 {karma}。"
        )
    return world, narr
