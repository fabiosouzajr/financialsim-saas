from typing import Literal
from pydantic import BaseModel


class SettingItem(BaseModel):
    value: str
    source: Literal["db", "env"]


class SettingUpdateIn(BaseModel):
    value: str
