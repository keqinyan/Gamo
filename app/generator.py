"""
app/generator.py ― 连续剧情 + 主线目标 版
"""
from __future__ import annotations
import os, json, re, time
from uuid import uuid4
from typing import List, Dict, Tuple

from jinja2 import Template
from openai import OpenAI
from .models import WorldState, Character

# ────────── 配置 ──────────
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
STYLE_HINT = (
    "作品风格充满脑洞与幽默、惊悚与反转，但不失深度；"
    "请用第二人称，尽可能让玩家身临其境，参与感拉满。"
)

client = OpenAI()

# ────────── Prompt 模板 ──────────
WORLD_PROMPT = Template("""
你是高自由度 RPG 的世界生成器，玩家关键词：{{ keywords }}。
请严格以 JSON 返回：
{
  "summary": "...(≤200 字世界观)...",
  "main_plot": "...(一句话主线目标，例如“揭开灵石真相”)...",
  "characters": {
    "MAIN": { "name":"...", "role":"主角", "traits":["..."] },
    "NPC1": { "name":"...", "role":"引路人", "traits":["..."] },
    "NPC2": { "name":"...", "role":"路人甲", "traits":["..."] }
  }
}
""".strip())

EVENT_PROMPT = Template("""
<世界观>{{ summary }}</世界观>
<主线目标>{{ main_plot }}</主线目标>

{% if last_event %}
<上轮事件>
{{ last_event }}
玩家上轮选择：{{ last_choice }}
</上轮事件>
{% endif %}

请编排下一幕，**必须推动主线目标至少一点**，并提供 3 个选项。
严格返回 JSON：
{
  "text":"...",
  "options":[
    {"id":"A","text":"...","impact":1},
    {"id":"B","text":"...","impact":0},
    {"id":"C","text":"...","impact":-1}
  ]
}
""".strip())

ENDING_PROMPT = Template("""
<世界观>{{ summary }}</世界观>
<主线目标>{{ main_plot }}</主线目标>

<玩家旅程大事记>
{% for t in timeline[-5:] %}
- {{ loop.index }}. {{ t.event|truncate(50) }} → 选择 {{ t.choice }} (业障±{{ t.impact }})
{% endfor %}
</玩家旅程大事记>

玩家最终业障值：{{ karma }}
请写 150~200 字结局，基于业障展现善果/恶果/平淡收场。
严格返回 JSON：
{ "title":"...", "ending":"..." }
""".strip())

# ────────── 工具函数 ──────────
def _safe_json_parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group())
        raise

# ────────── 生成世界观 ──────────
def create_world(tags: List[str]) -> WorldState:
    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":STYLE_HINT},
            {"role":"user","content":WORLD_PROMPT.render(keywords="、".join(tags))},
        ],
        response_format={"type":"json_object"},
        max_tokens=600,
    )
    data = _safe_json_parse(rsp.choices[0].message.content)
    chars: Dict[str, Character] = {
        k: Character(id=str(uuid4()), **v) for k, v in data["characters"].items()
    }
    return WorldState(
        genre_tags=tags,
        summary=data["summary"],
        main_plot=data["main_plot"],
        characters=chars,
        timeline=[],
        flags={},  # current_event_text / last_options / last_choice_text / karma
    )

# ────────── 生成事件 ──────────
def generate_event(world: WorldState, retry:int=1) -> dict:
    prompt = EVENT_PROMPT.render(
        summary     = world.summary,
        main_plot   = world.main_plot,
        last_event  = world.flags.get("current_event_text",""),
        last_choice = world.flags.get("last_choice_text",""),
    )
    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":STYLE_HINT},
            {"role":"user","content":prompt},
        ],
        response_format={"type":"json_object"},
        max_tokens=500,
        temperature=0.7,
    )
    try:
        return _safe_json_parse(rsp.choices[0].message.content)
    except json.JSONDecodeError:
        if retry:
            time.sleep(0.5)
            return generate_event(world, retry-1)
        raise

# ────────── 处理选择 ──────────
def apply_choice(
    world: WorldState,
    choice_id: str | None,
    options: list[dict],
    custom_input: str | None = None,
) -> Tuple[WorldState, str]:

    # 1) 解析 impact & narration
    if custom_input:
        prompt = (
            f"玩家自由行动：{custom_input}\n"
            "请严格返回 JSON：{\"narration\":\"...\",\"impact\":(-1|0|1)}"
        )
        rsp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role":"system","content":STYLE_HINT},
                {"role":"user","content":prompt},
            ],
            response_format={"type":"json_object"},
            max_tokens=200,
            temperature=0.7,
        )
        data = _safe_json_parse(rsp.choices[0].message.content)
        narration = data.get("narration","")
        impact    = data.get("impact",0)
    else:
        opt = next(o for o in options if o["id"] == choice_id.upper())
        narration = f"你选择了【{opt['text']}】。"
        impact    = opt.get("impact",0)

    # 2) 更新业障
    karma = world.flags.get("karma",0) + impact
    world.flags["karma"] = karma

    # 3) 写时间线
    world.timeline.append({
        "event":  world.flags.get("current_event_text",""),
        "choice": custom_input or (opt["text"] if not custom_input else custom_input),
        "impact": impact,
        "karma":  karma,
    })

    # 4) 写 last_choice_text（供下一幕承接）
    world.flags["last_choice_text"] = custom_input or (opt["text"] if not custom_input else custom_input)

    narration += f" 业障变化 {impact:+d}，当前业障 {karma}。"
    return world, narration

# ────────── 生成结局 ──────────
def generate_ending(world: WorldState, retry:int=1) -> dict:
    prompt = ENDING_PROMPT.render(
        summary  = world.summary,
        main_plot= world.main_plot,
        timeline = world.timeline,
        karma    = world.flags.get("karma",0),
    )
    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":STYLE_HINT},
            {"role":"user","content":prompt},
        ],
        response_format={"type":"json_object"},
        max_tokens=500,
        temperature=0.7,
    )
    try:
        return _safe_json_parse(rsp.choices[0].message.content)
    except json.JSONDecodeError:
        if retry:
            time.sleep(0.5)
            return generate_ending(world, retry-1)
        raise
