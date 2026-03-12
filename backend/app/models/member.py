from datetime import datetime
from typing import Any


def member_document(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "unique_id": data["unique_id"],
        "name": data["name"],
        "membership": data["membership"],
        "assembly": data["assembly"],
        "district": data["district"],
        "dob": data["dob"],
        "age": data["age"],
        "blood_group": data["blood_group"],
        "address": data["address"],
        "contact_number": data["contact_number"],
        "photo_url": data["photo_url"],
        "qr_url": data["qr_url"],
        "verify_url": data["verify_url"],
        "status": data.get("status", "pending"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "approved_at": None,
    }
