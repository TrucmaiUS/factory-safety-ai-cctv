from pydantic import BaseModel


class SerialLogResponse(BaseModel):
    lines: list[str]
