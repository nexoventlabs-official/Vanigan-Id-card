import os
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from fastapi import UploadFile

from app.core.config import settings

if settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret:
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


async def save_photo(file: UploadFile) -> str:
    content = await file.read()

    if settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret:
        uploaded = cloudinary.uploader.upload(content, folder="vanigan/photos")
        return uploaded["secure_url"]

    photos_dir = os.path.join("app", "static", "generated", "photos")
    os.makedirs(photos_dir, exist_ok=True)
    filename = f"{uuid4().hex}_{file.filename}"
    filepath = os.path.join(photos_dir, filename)
    with open(filepath, "wb") as out:
        out.write(content)
    return f"/static/generated/photos/{filename}"
