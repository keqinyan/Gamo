from pydantic import BaseModel
from typing import List, Dict, Any

class Character(BaseModel):
    id: str
    name: str
    role: str
    traits: list[str]
    backstory: str
    goal: str
    stats: dict[str, int]               # ★ 六维属性
    avatar_url: str | None = None

class WorldState(BaseModel):
    genre_tags: list[str]
    summary: str
    main_plot: str                     
    characters: dict[str, Character]
    timeline: list[dict] = []
    flags: dict = {}

