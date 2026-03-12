from fastapi import APIRouter, HTTPException

from app.schemas.member import OtpResponse, RequestOtpIn, VerifyOtpIn
from app.services.otp_service import request_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp", response_model=OtpResponse)
async def request_otp_endpoint(payload: RequestOtpIn):
    dev_otp = await request_otp(payload.contact_number)
    return OtpResponse(message="OTP sent successfully", dev_otp=dev_otp)


@router.post("/verify-otp")
async def verify_otp_endpoint(payload: VerifyOtpIn):
    ok = await verify_otp(payload.contact_number, payload.otp)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    return {"message": "OTP verified"}
