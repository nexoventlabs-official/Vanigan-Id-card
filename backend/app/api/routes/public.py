from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.db import get_member_collection
from app.models.member import member_document
from app.schemas.member import MemberOut
from app.services.cloudinary_service import save_photo
from app.services.card_image_service import generate_card_image
from app.services.id_generator import generate_unique_member_id
from app.services.otp_service import consume_verified, is_contact_verified, normalize_contact_number
from app.services.qr_service import generate_qr

router = APIRouter(prefix="/public", tags=["public"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/apply", response_model=MemberOut)
async def apply_member(
    name: str = Form(...),
    membership: str = Form(...),
    assembly: str = Form(...),
    district: str = Form(...),
    dob: str = Form(...),
    age: int = Form(...),
    blood_group: str = Form(...),
    address: str = Form(...),
    contact_number: str = Form(...),
    photo: UploadFile = File(...),
):
    contact_number = normalize_contact_number(contact_number)

    if not await is_contact_verified(contact_number):
        raise HTTPException(status_code=403, detail="Contact number is not OTP verified")

    members = get_member_collection()
    already_exists = await members.find_one({"contact_number": contact_number, "status": {"$ne": "rejected"}})
    if already_exists:
        raise HTTPException(status_code=409, detail="Member with this contact already exists")

    if photo.content_type not in {"image/jpeg", "image/png", "image/jpg", "image/webp"}:
        raise HTTPException(status_code=400, detail="Photo must be jpg, png, or webp")

    unique_id = await generate_unique_member_id()
    verify_url = f"{settings.backend_public_url}/verify/{unique_id}"
    photo_url = await save_photo(photo)
    qr_url = generate_qr(unique_id, verify_url)

    payload = member_document(
        {
            "unique_id": unique_id,
            "name": name,
            "membership": membership,
            "assembly": assembly,
            "district": district,
            "dob": dob,
            "age": age,
            "blood_group": blood_group,
            "address": address,
            "contact_number": contact_number,
            "photo_url": photo_url,
            "qr_url": qr_url,
            "verify_url": verify_url,
            "status": "pending",
        }
    )

    await members.insert_one(payload)
    await consume_verified(contact_number)

    return MemberOut(**payload)


@router.get("/member/{unique_id}", response_model=MemberOut)
async def get_member(unique_id: str):
    members = get_member_collection()
    member = await members.find_one({"unique_id": unique_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return MemberOut(**member)


@router.get("/landing-content")
async def landing_content():
    return {
        "heroTitle": "Tamilnadu Vanigargalin Sangamam",
        "heroSubtitle": "Digital membership identity for merchants across Tamil Nadu",
        "stats": [
            {"label": "District Coverage", "value": "38"},
            {"label": "Verified Members", "value": "10,000+"},
            {"label": "Avg Approval Time", "value": "< 24h"},
        ],
    }


@router.get("/verify-card/{unique_id}", response_class=HTMLResponse)
async def verify_card_page(request: Request, unique_id: str):
    members = get_member_collection()
    member = await members.find_one({"unique_id": unique_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Card not found")

    return templates.TemplateResponse(
        request=request,
        name="id_card.html",
        context={
            "member": member,
            "generated_at": datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC"),
            "base_url": settings.backend_public_url,
            "api_v1_prefix": settings.api_v1_prefix,
        },
    )


@router.get("/card-image/{unique_id}")
async def download_card_image(unique_id: str):
    members = get_member_collection()
    member = await members.find_one({"unique_id": unique_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Card not found")

    image_bytes = generate_card_image(member, settings.backend_public_url)
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{unique_id}-id-card.png"'},
    )
