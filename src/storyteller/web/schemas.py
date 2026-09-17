from pydantic import BaseModel


class AuthRequest(BaseModel):
    password: str


class SetupRequest(BaseModel):
    code: str
    password: str
