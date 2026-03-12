from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from app.core.config import settings


mongo_client = AsyncIOMotorClient(settings.mongo_url)
mongo_db = mongo_client[settings.mongo_db_name]
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def get_member_collection():
    return mongo_db["members"]


def get_whatsapp_session_collection():
    return mongo_db["whatsapp_sessions"]
