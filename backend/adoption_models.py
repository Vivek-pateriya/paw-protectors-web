from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Listing(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    species: str = Field(min_length=1, max_length=100)
    breed: str = Field(default='', max_length=120)
    age_months: int = Field(default=0, ge=0, le=1200)
    gender: Literal['male', 'female', 'unknown'] = 'unknown'
    location: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    health_summary: str = Field(default='', max_length=5000)
    weight_kg: float | None = Field(default=None, ge=0.001, le=2000, allow_inf_nan=False)
    allergies: str = Field(default='', max_length=5000)

    @field_validator('name', 'species', 'location', 'description')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('This field cannot be blank')
        return value.strip()


class ListingEdit(Listing):
    version: int = Field(gt=0)


class Review(BaseModel):
    version: int = Field(gt=0)
    action: Literal['approve', 'reject', 'archive']
    reason: str = Field(default='', max_length=2000)


class Application(BaseModel):
    motivation: str = Field(min_length=10, max_length=2000)
    housing: Literal['house', 'apartment', 'farm', 'other']
    has_other_pets: bool = False
    experience: str = Field(default='', max_length=2000)
    contact_phone: str = Field(default='', max_length=30)

    @field_validator('motivation')
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10:
            raise ValueError('Explain your adoption interest in at least 10 characters')
        return value.strip()


class Decision(BaseModel):
    action: Literal['approve', 'reject', 'complete', 'withdraw']
    reason: str = Field(default='', max_length=2000)
