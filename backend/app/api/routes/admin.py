from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pymongo import ReturnDocument

from app.core.config import settings
from app.core.db import get_member_collection
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
