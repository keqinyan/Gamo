from pydantic import BaseModel
from typing import List, Dict, Any

class Character(BaseModel):
    id: str
    name: str
    role: str
    traits: List[str]

class WorldState(BaseModel):
    genre_tags: list[str]
    summary: str
    main_plot: str                     
    characters: dict[str, Character]
    timeline: list[dict] = []
    flags: dict = {}

