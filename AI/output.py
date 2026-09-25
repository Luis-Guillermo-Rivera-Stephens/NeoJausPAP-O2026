from pydantic import BaseModel

class AiResponse(BaseModel):
    response: str
    new_summary: str
    errors: list[str] = []