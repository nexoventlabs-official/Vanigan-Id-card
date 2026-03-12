import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pymongo import ReturnDocument

import cloudinary
import cloudinary.api
import cloudinary.uploader

from app.core.config import settings
from app.core.db import get_member_collection, get_whatsapp_session_collection, get_poll_collection
from app.schemas.member import AdminStatusUpdateOut

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin_key(x_admin_key: str = Header(default="")):
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.get("/members", dependencies=[Depends(require_admin_key)])
async def list_members(status: str | None = None):
    members = get_member_collection()
    query = {"status": status} if status else {}
    items = await members.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"items": items, "count": len(items)}


@router.post("/members/{unique_id}/approve", response_model=AdminStatusUpdateOut, dependencies=[Depends(require_admin_key)])
async def approve_member(unique_id: str):
    members = get_member_collection()
    updated = await members.find_one_and_update(
        {"unique_id": unique_id},
        {
            "$set": {
                "status": "approved",
                "approved_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Member not found")

    return AdminStatusUpdateOut(message="Member approved", unique_id=unique_id, status="approved")


@router.post("/members/{unique_id}/reject", response_model=AdminStatusUpdateOut, dependencies=[Depends(require_admin_key)])
async def reject_member(unique_id: str):
    members = get_member_collection()
    updated = await members.find_one_and_update(
        {"unique_id": unique_id},
        {"$set": {"status": "rejected", "updated_at": datetime.utcnow()}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Member not found")

    return AdminStatusUpdateOut(message="Member rejected", unique_id=unique_id, status="rejected")


def _destroy_cloudinary_photo(public_id: str) -> None:
    try:
        cloudinary.uploader.destroy(public_id)
    except Exception:
        pass


def _extract_cloudinary_public_id(url: str) -> str | None:
    """Extract public_id from a Cloudinary URL like .../upload/v123/vanigan/photos/abc123.jpg"""
    if not url or "cloudinary" not in url:
        return None
    try:
        parts = url.split("/upload/")
        if len(parts) < 2:
            return None
        after_upload = parts[1]  # e.g. v123/vanigan/photos/abc123.jpg
        segments = after_upload.split("/", 1)
        if len(segments) < 2:
            return None
        path_with_ext = segments[1]  # vanigan/photos/abc123.jpg
        public_id = path_with_ext.rsplit(".", 1)[0]  # vanigan/photos/abc123
        return public_id
    except Exception:
        return None


@router.delete("/members/{unique_id}", dependencies=[Depends(require_admin_key)])
async def delete_member(unique_id: str):
    members = get_member_collection()
    member = await members.find_one({"unique_id": unique_id})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Delete photo from Cloudinary
    photo_url = member.get("photo_url", "")
    public_id = _extract_cloudinary_public_id(photo_url)
    if public_id:
        await asyncio.to_thread(_destroy_cloudinary_photo, public_id)

    await members.delete_one({"unique_id": unique_id})
    return {"message": f"Member {unique_id} deleted", "photo_removed": bool(public_id)}


@router.delete("/reset-all", dependencies=[Depends(require_admin_key)])
async def reset_all():
    members = get_member_collection()
    sessions = get_whatsapp_session_collection()
    polls = get_poll_collection()

    # Collect all photo URLs before deleting
    all_members = await members.find({}, {"photo_url": 1}).to_list(10000)
    photo_ids = []
    for m in all_members:
        pid = _extract_cloudinary_public_id(m.get("photo_url", ""))
        if pid:
            photo_ids.append(pid)

    # Delete photos from Cloudinary
    for pid in photo_ids:
        await asyncio.to_thread(_destroy_cloudinary_photo, pid)

    # Clear all collections
    del_members = await members.delete_many({})
    del_sessions = await sessions.delete_many({})
    del_polls = await polls.delete_many({})

    return {
        "message": "All data reset",
        "deleted_members": del_members.deleted_count,
        "deleted_sessions": del_sessions.deleted_count,
        "deleted_polls": del_polls.deleted_count,
        "deleted_photos": len(photo_ids),
    }
