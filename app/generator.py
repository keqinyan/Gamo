"""
连续剧情 + 主线目标 + zh/en + 属性点 + 可选头像
"""
from __future__ import annotations
import json, os, re, time, random
from uuid import uuid4
from typing import Any, List, Dict

from jinja2 import Template
from openai import OpenAI
from .models import WorldState, Character

MODEL      = os.getenv("LLM_MODEL", "gpt-4o-mini")
STYLE_HINT = (
    "作品风格充满脑洞与幽默、惊悚与反转，但不失深度；"
    "请用第二人称，尽可能让玩家身临其境，参与感拉满。"
)
client = OpenAI()

# 语言附加提示
LANG_HINT = {"zh":"用简体中文。","en":"Write in vivid English."}

def lang_hint(l:str)->str: return LANG_HINT.get(l, LANG_HINT["zh"])

# ---------- 属性点 ----------
STAT_KEYS = ["STR","DEX","CON","INT","WIS","CHA"]

def roll_stats():
    return {k: random.randint(8,18) for k in STAT_KEYS}

def fill_stats(d:dict[str,Any]):
    return {k: int(d.get(k) or random.randint(8,18)) for k in STAT_KEYS}

# ────────── Prompt 模板 ──────────
WORLD_PROMPT = Template("""
你是高自由度 RPG 的世界生成器，玩家关键词：{{ keywords }}。

请严格输出 JSON：
{
  "summary": "...(≤200 字世界观)...",
  "main_plot": "...(一句话主线目标)...",
  "characters": {
    "MAIN": {
      "name": "...", "role": "主角",
      "traits": ["...","..."],
      "backstory": "50 字经历",         // ★ 新字段
      "goal": "个人目标",                // ★ 新字段
      "stats": { "STR":?, "DEX":?, "CON":?, "INT":?, "WIS":?, "CHA":? }
    },
    "NPC1": { ... 同上 },
    "NPC2": { ... 同上 }
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
可参考主角属性 {{ characters.MAIN.stats }} 
例如若玩家力量大于特定值 可给出“强行破门”选项，魅力高则给“说服”选项。
Return strict JSON with a top-level key "options".
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
严格返回 JSON：{ "title":"...", "ending":"..." }
""".strip())

# ────────── 通用解析器 ──────────
def _safe_json_parse(text: str) -> dict:
    """
    最宽容的 JSON 提取：
    1. 去掉 ```json ``` 包裹、``` 等
    2. 去掉行首 // 或 # 的注释
    3. 把裸回车 \n 替成 空格，\t 替成 空格
    4. 捕获第一个 {...}
    """
    # 1. code fence
    cleaned = re.sub(r"```[\s\S]*?```", "", text, flags=re.I).strip()

    # 2. 行注释
    cleaned = re.sub(r"^\s*(//|#).*$", "", cleaned, flags=re.M)

    # 3. 裸换行、制表
    cleaned = cleaned.replace("\n", " ").replace("\t", " ")

    # 4. 直接尝试
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned)
        if m:
            return json.loads(m.group())
        raise



# ────────── 生成世界观 ──────────
def create_world(tags:List[str], lang="zh", *, need_avatar=False, avatar_style="anime")->WorldState:
    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":STYLE_HINT+lang_hint(lang)},
            {"role":"user","content":WORLD_PROMPT.render(keywords="、".join(tags))},
        ],
        response_format={"type":"json_object"},
        max_tokens=700, temperature=0.7,
    )
    data = _safe_json_parse(rsp.choices[0].message.content)

    characters: Dict[str, Character] = {}
    for code, info in data["characters"].items():
        info["stats"] = fill_stats(info.get("stats", {}))
        char = Character(id=str(uuid4()), **info)
        
        if need_avatar:
            img = client.images.generate(
                prompt=f"{avatar_style} portrait of {char.name} {char.traits[0]}",
                size="512x512", n=1)
            char.avatar_url = img.data[0].url
        characters[code] = char

    return WorldState(
        genre_tags=tags,
        summary   =data["summary"],
        main_plot =data["main_plot"],
        characters=characters,
        timeline  =[],
        flags     ={},
    )

# ---------- 事件 ----------

def generate_event(world:WorldState, lang="zh", retry=1)->dict:
    prompt = EVENT_PROMPT.render(
        summary=world.summary, main_plot=world.main_plot,
        last_event=world.flags.get("current_event_text",""),
        last_choice=world.flags.get("last_choice_text",""),
        characters=world.characters,                       # ★ 传 characters
    )
    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":STYLE_HINT+lang_hint(lang)},
            {"role":"user","content":prompt},
        ],
        response_format={"type":"json_object"},
        max_tokens=500, temperature=0.7,
    )
    raw = _safe_json_parse(rsp.choices[0].message.content)
    if "options" not in raw:
        raw["options"] = raw.get("choices", [])
    return raw


# ────────── 结算选择 ──────────
def apply_choice(
    world: WorldState,
    choice_id: str | None,
    options: list[dict],
    custom_input: str | None = None,
    lang: str = "zh",
) -> tuple[WorldState, str]:

    # ① 生成「即时反馈」+ impact ---------------------------------
    if custom_input:                                  # 自由输入
        prompt = (
            "Player action (between triple quotes):\n"
            f'"""{custom_input}"""\n\n'
            'Return strict JSON: {"narration":"(one line summarizing the choice, dont expand)","impact":(-1|0|1)}'
        )

        resp  = client.chat.completions.create(
            model = MODEL,
            messages=[
                {"role":"system","content":STYLE_HINT + lang_hint(lang)},
                {"role":"user","content":prompt},
            ],
            response_format={"type":"json_object"},
            max_tokens=120,
            temperature=0.7,
        )
        data        = _safe_json_parse(resp.choices[0].message.content)
        instant_fb  = data.get("narration","")
        impact      = data.get("impact",0)
        choice_txt  = custom_input
    else:                                             # 按钮 A/B/C
        opt        = next(o for o in options if o["id"] == choice_id.upper())
        choice_txt = opt["text"]
        impact     = opt.get("impact",0)
        instant_fb = (
            f"你选择了【{choice_txt}】。" if lang=="zh"
            else f'You chose "{choice_txt}".'
        )

    # ② 更新业障 & 时间线 -----------------------------------------
    karma = world.flags.get("karma",0) + impact
    world.flags["karma"] = karma
    world.timeline.append({
        "event" : world.flags.get("current_event_text",""),
        "choice": choice_txt,
        "impact": impact,
        "karma" : karma,
    })
    world.flags["last_choice_text"] = choice_txt

    # ③ 拼最终旁白（根据语言） -----------------------------------
    if lang == "zh":
        narration = f"{instant_fb} 业障变化 {impact:+d}，当前业障 {karma}。"
    else:
        narration = f"{instant_fb} Karma change {impact:+d}, current karma {karma}."

    return world, narration


# ────────── 生成结局 ──────────
def generate_ending(world: WorldState, lang: str = "zh", retry: int = 1) -> dict:
    prompt = ENDING_PROMPT.render(
        summary   = world.summary,
        main_plot = world.main_plot,
        timeline  = world.timeline,
        karma     = world.flags.get("karma",0),
    )
    resp = client.chat.completions.create(
        model   = MODEL,
        messages=[
            {"role":"system","content": STYLE_HINT + lang_hint(lang)},
            {"role":"user","content": prompt},
        ],
        response_format={"type":"json_object"},
        max_tokens=500,
        temperature=0.7,
    )
    try:
        return _safe_json_parse(resp.choices[0].message.content)
    except json.JSONDecodeError:
        if retry:
            time.sleep(0.5)
            return generate_ending(world, lang, retry-1)
        raise
