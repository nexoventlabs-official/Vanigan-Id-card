import random
import time
from importlib import import_module

from app.core.config import settings
from app.core.db import redis_client


_memory_store: dict[str, tuple[str, float]] = {}


def normalize_contact_number(contact_number: str) -> str:
    cleaned = "".join(char for char in contact_number.strip() if char.isdigit() or char == "+")

    if cleaned.startswith("+"):
        return cleaned

    digits = "".join(char for char in cleaned if char.isdigit())
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"

    return cleaned


def _otp_key(contact_number: str) -> str:
    return f"otp:{contact_number}"


def _verified_key(contact_number: str) -> str:
    return f"verified:{contact_number}"


def _purge_expired() -> None:
    now = time.time()
    expired_keys = [key for key, (_, expires_at) in _memory_store.items() if expires_at <= now]
    for key in expired_keys:
        del _memory_store[key]


async def _set_value(key: str, ttl_seconds: int, value: str) -> None:
    try:
        await redis_client.setex(key, ttl_seconds, value)
        return
    except Exception:
        pass

    _purge_expired()
    _memory_store[key] = (value, time.time() + ttl_seconds)


async def _get_value(key: str) -> str | None:
    try:
        return await redis_client.get(key)
    except Exception:
        pass

    _purge_expired()
    record = _memory_store.get(key)
    return record[0] if record else None


async def _delete_value(key: str) -> None:
    try:
        await redis_client.delete(key)
    except Exception:
        pass

    _memory_store.pop(key, None)


async def request_otp(contact_number: str) -> str | None:
    contact_number = normalize_contact_number(contact_number)
    otp_code = "".join(str(random.randint(0, 9)) for _ in range(6))
    await _set_value(_otp_key(contact_number), settings.otp_ttl_seconds, otp_code)

    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_verify_service_sid:
        try:
            twilio_exceptions = import_module("twilio.base.exceptions")
            twilio_rest = import_module("twilio.rest")
            TwilioException = getattr(twilio_exceptions, "TwilioException")
            Client = getattr(twilio_rest, "Client")
        except ImportError:
            return otp_code

        try:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            client.verify.v2.services(settings.twilio_verify_service_sid).verifications.create(
                to=contact_number,
                channel="sms",
            )
            return None
        except TwilioException:
            # Fall back to dev OTP mode if Twilio setup is incomplete.
            return otp_code

    return otp_code


async def verify_otp(contact_number: str, otp: str) -> bool:
    contact_number = normalize_contact_number(contact_number)
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_verify_service_sid:
        try:
            twilio_exceptions = import_module("twilio.base.exceptions")
            twilio_rest = import_module("twilio.rest")
            TwilioException = getattr(twilio_exceptions, "TwilioException")
            Client = getattr(twilio_rest, "Client")
        except ImportError:
            return False

        try:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            check = client.verify.v2.services(settings.twilio_verify_service_sid).verification_checks.create(
                to=contact_number,
                code=otp,
            )
            if check.status == "approved":
                await _set_value(_verified_key(contact_number), settings.verify_ttl_seconds, "1")
                return True
            return False
        except TwilioException:
            pass

    saved_otp = await _get_value(_otp_key(contact_number))
    if not saved_otp or saved_otp != otp:
        return False

    await _delete_value(_otp_key(contact_number))
    await _set_value(_verified_key(contact_number), settings.verify_ttl_seconds, "1")
    return True


async def is_contact_verified(contact_number: str) -> bool:
    contact_number = normalize_contact_number(contact_number)
    return (await _get_value(_verified_key(contact_number))) == "1"


async def consume_verified(contact_number: str) -> None:
    contact_number = normalize_contact_number(contact_number)
    await _delete_value(_verified_key(contact_number))
