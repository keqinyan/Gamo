from pydantic import BaseModel
from typing import List, Dict, Any

class Character(BaseModel):
    id: str
    name: str
    role: str
    traits: List[str]

class WorldState(BaseModel):
    genre_tags: List[str]
    summary: str
    characters: Dict[str, Character]
    timeline: List[Dict[str, Any]]
    flags: Dict[str, Any] = {}
