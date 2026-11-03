from datetime import date, datetime
import re
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
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
            raise ValueError('Enter a valid email address')
        return value

    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError('Enter your name')
        return value.strip()


class Login(BaseModel):
    email: str
    password: str = Field(max_length=128)


class RecoveryRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    email_valid = field_validator('email')(Registration.email_valid.__func__)


class ProfileUpdate(RecoveryRequest):
    name: str = Field(min_length=1, max_length=120)
    current_password: str = Field(min_length=1, max_length=128)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Enter your name')
        return value.strip()


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordReset(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class Pet(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    species: str = Field(min_length=1, max_length=100)
    breed: str = Field(default='', max_length=120)
    age_months: int = Field(default=0, ge=0, le=1200)
    gender: Literal['male', 'female', 'unknown'] = 'unknown'
    medical_notes: str = Field(default='', max_length=5000)
    weight_kg: float | None = Field(default=None, gt=0, le=2000, allow_inf_nan=False)
    allergies: str = Field(default='', max_length=5000)


class Medication(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=500)
    instructions: str = Field(default='', max_length=2000)
    starts_at: datetime
    ends_at: datetime
    interval_hours: int = Field(ge=1, le=720)

    @model_validator(mode='after')
    def schedule(self):
        from datetime import timedelta, timezone
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError('Use timestamps with UTC offset')
        if self.ends_at < self.starts_at or self.ends_at-self.starts_at > timedelta(days=366):
            raise ValueError('End must follow start and be within 366 days')
        if self.starts_at < datetime.now(timezone.utc)-timedelta(minutes=5):
            raise ValueError('Start must be now or in the future')
        if not self.name.strip() or not self.dosage.strip():
            raise ValueError('Medication and dosage are required')
        return self


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
