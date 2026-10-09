from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Registration(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if '@' not in value or '.' not in value.split('@')[-1] or ' ' in value:
            raise ValueError('Enter a valid email address')
        return value


class Login(BaseModel):
    email: str
    password: str = Field(max_length=128)


class Pet(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    species: str = Field(min_length=1, max_length=100)
    breed: str = Field(default='', max_length=120)
    age_months: int = Field(default=0, ge=0, le=1200)
    gender: Literal['male', 'female', 'unknown'] = 'unknown'
    medical_notes: str = Field(default='', max_length=5000)


class Booking(BaseModel):
    slot_id: int = Field(gt=0)
    pet_id: int = Field(gt=0)
    reason: str = Field(default='', max_length=1000)


class Slot(BaseModel):
    veterinarian_id: int = Field(gt=0)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode='after')
    def interval(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError('Use ISO timestamps with UTC offset')
        if self.ends_at <= self.starts_at:
            raise ValueError('End must be after start')
        return self


class Vet(BaseModel):
    user_id: int = Field(gt=0)
    specialization: str = Field(default='General care', max_length=200)
    clinic: str = Field(default='', max_length=200)
    available: bool = True


class UserUpdate(BaseModel):
    role: Literal['owner', 'vet', 'admin']
    active: bool = True


class Vaccination(BaseModel):
    vaccine: str = Field(min_length=1, max_length=200)
    administered_on: date
    next_due: date | None = None

    @model_validator(mode='after')
    def order(self):
        if self.next_due and self.next_due < self.administered_on:
            raise ValueError('Next due date must follow administered date')
        return self


class Medical(BaseModel):
    diagnosis: str = Field(min_length=1, max_length=5000)
    treatment: str = Field(default='', max_length=5000)
