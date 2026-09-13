from pydantic import BaseModel


class AuthRequest(BaseModel):
    password: str
