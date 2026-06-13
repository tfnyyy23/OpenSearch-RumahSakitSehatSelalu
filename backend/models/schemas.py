from pydantic import BaseModel
from typing import Optional


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    question: str
    answer: str
    data: Optional[dict] = None
    query_type: Optional[str] = None