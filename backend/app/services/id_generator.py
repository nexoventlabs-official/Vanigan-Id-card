import random

from app.core.db import get_member_collection


async def generate_unique_member_id(prefix: str = "TVSM") -> str:
    members = get_member_collection()
    while True:
        random_digits = "".join(str(random.randint(0, 9)) for _ in range(9))
        unique_id = f"{prefix}{random_digits}"
        exists = await members.find_one({"unique_id": unique_id}, {"_id": 1})
        if not exists:
            return unique_id
