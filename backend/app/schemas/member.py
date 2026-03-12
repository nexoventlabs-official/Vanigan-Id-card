from datetime import datetime

from pydantic import BaseModel, Field


class RequestOtpIn(BaseModel):
    contact_number: str = Field(min_length=10, max_length=15)


class VerifyOtpIn(BaseModel):
    contact_number: str = Field(min_length=10, max_length=15)
    otp: str = Field(min_length=4, max_length=8)


class OtpResponse(BaseModel):
    message: str
    dev_otp: str | None = None


class MemberOut(BaseModel):
    unique_id: str
    name: str
    membership: str
    assembly: str
    district: str
    dob: str
    age: int
    blood_group: str
    address: str
    contact_number: str
    photo_url: str
    qr_url: str
    verify_url: str
    status: str
    created_at: datetime


class AdminStatusUpdateOut(BaseModel):
    message: str
    unique_id: str
    status: str
