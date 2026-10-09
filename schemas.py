import re
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    phone_number: str = Field(..., pattern=r"^09\d{9}$")
    password: str

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long.')
        if not re.search(r"[a-z]", v) or not re.search(r"[A-Z]", v):
            raise ValueError('Password must contain both uppercase and lowercase letters.')
        return v

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    phone_number: str
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TaskBase(BaseModel):
    title: str
    description: str | None = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(TaskBase):
    pass

class TaskResponse(TaskBase):
    id: int
    user_id: int
    attachment_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True