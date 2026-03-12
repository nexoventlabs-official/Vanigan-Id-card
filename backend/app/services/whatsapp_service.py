from __future__ import annotations

import asyncio
import json
from datetime import datetime
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import cloudinary.uploader

from app.core.config import settings
from app.core.db import get_member_collection, get_whatsapp_session_collection, get_poll_collection
from app.models.member import member_document
from app.services.id_generator import generate_unique_member_id
from app.services.otp_service import normalize_contact_number
from app.services.qr_service import generate_qr

GRAPH_API_BASE = "https://graph.facebook.com/v22.0"
ORGANIZER_THRESHOLD = 25


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _title(text: str) -> str:
    return text.strip().title() if text else ""


def _calc_age(dob_str: str) -> int:
    try:
        from datetime import date
        # Support DD/MM/YYYY format
        if '/' in dob_str:
            parts = dob_str.strip().split('/')
            dob = date(int(parts[2]), int(parts[1]), int(parts[0]))
        else:
            dob = date.fromisoformat(dob_str)
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except (ValueError, TypeError, IndexError):
        return 0


def _public_base_url() -> str:
    # WhatsApp users need an internet-reachable URL, not localhost.
    if settings.whatsapp_public_base_url:
        return settings.whatsapp_public_base_url.rstrip("/")
    return settings.backend_public_url.rstrip("/")


def _json_post(url: str, payload: dict[str, Any], access_token: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _json_get(url: str, access_token: str) -> dict[str, Any]:
    req = Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _bytes_get(url: str, access_token: str) -> bytes:
    req = Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def _messages_url() -> str:
    return f"{GRAPH_API_BASE}/{settings.whatsapp_phone_number_id}/messages"


async def send_text(to_wa_id: str, text: str) -> None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": text},
    }
    _json_post(_messages_url(), payload, settings.whatsapp_access_token)


async def send_reply_buttons(to_wa_id: str, body: str, buttons: list[tuple[str, str]]) -> None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": btn_id, "title": title[:20]},
                    }
                    for btn_id, title in buttons[:3]
                ]
            },
        },
    }
    _json_post(_messages_url(), payload, settings.whatsapp_access_token)


async def send_list(to_wa_id: str, body: str, button_text: str, rows: list[tuple[str, str]]) -> None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_text[:20],
                "sections": [
                    {
                        "title": "Options",
                        "rows": [{"id": rid, "title": title[:24]} for rid, title in rows[:10]],
                    }
                ],
            },
        },
    }
    _json_post(_messages_url(), payload, settings.whatsapp_access_token)



async def send_template_url_button(to_wa_id: str, template_name: str, lang: str, url_suffix: str) -> bool:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
            "components": [
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": url_suffix}],
                }
            ],
        },
    }
    try:
        _json_post(_messages_url(), payload, settings.whatsapp_access_token)
        return True
    except (HTTPError, URLError, ValueError):
        return False


async def send_download_template(to_wa_id: str, member: dict[str, Any]) -> bool:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return False
    if not settings.whatsapp_download_template_name:
        return False

    unique_id = member.get("unique_id", "")
    if not unique_id:
        return False

    download_url = f"{_public_base_url()}{settings.api_v1_prefix}/public/card-image/{unique_id}"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": settings.whatsapp_download_template_name,
            "language": {"code": settings.whatsapp_download_template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": member.get("name", "")},
                        {"type": "text", "text": member.get("membership", "")},
                        {"type": "text", "text": member.get("contact_number", "")},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": unique_id}],
                },
            ],
        },
    }
    try:
        _json_post(_messages_url(), payload, settings.whatsapp_access_token)
        return True
    except (HTTPError, URLError, ValueError):
        return False


async def send_view_card_template(to_wa_id: str, member: dict[str, Any]) -> bool:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return False
    if not settings.whatsapp_view_template_name:
        return False

    unique_id = member.get("unique_id", "")
    if not unique_id:
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": settings.whatsapp_view_template_name,
            "language": {"code": settings.whatsapp_view_template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": member.get("name", "")},
                        {"type": "text", "text": member.get("membership", "")},
                        {"type": "text", "text": member.get("contact_number", "")},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": unique_id}],
                },
            ],
        },
    }
    try:
        _json_post(_messages_url(), payload, settings.whatsapp_access_token)
        return True
    except (HTTPError, URLError, ValueError):
        return False


async def send_referral_template(to_wa_id: str, member: dict[str, Any]) -> bool:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return False
    if not settings.whatsapp_referral_template_name:
        return False

    referral_code = member.get("referral_code", member.get("unique_id", ""))
    referral_link = f"https://wa.me/{settings.whatsapp_phone_number_id}?text=REF_{referral_code}"
    count = member.get("referral_count", 0)

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": settings.whatsapp_referral_template_name,
            "language": {"code": settings.whatsapp_referral_template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": member.get("name", "")},
                        {"type": "text", "text": str(count)},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "copy_code",
                    "index": "0",
                    "parameters": [{"type": "coupon_code", "coupon_code": referral_link}],
                },
            ],
        },
    }
    try:
        _json_post(_messages_url(), payload, settings.whatsapp_access_token)
        return True
    except (HTTPError, URLError, ValueError):
        return False


async def send_organizer_template(to_wa_id: str, member: dict[str, Any]) -> bool:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return False
    if not settings.whatsapp_organizer_template_name:
        return False

    referral_code = member.get("referral_code", member.get("unique_id", ""))
    referral_link = f"https://wa.me/{settings.whatsapp_phone_number_id}?text=REF_{referral_code}"
    count = member.get("referral_count", 0)
    remaining = max(0, ORGANIZER_THRESHOLD - count)

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": settings.whatsapp_organizer_template_name,
            "language": {"code": settings.whatsapp_organizer_template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": member.get("name", "")},
                        {"type": "text", "text": str(count)},
                        {"type": "text", "text": str(remaining)},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "copy_code",
                    "index": "0",
                    "parameters": [{"type": "coupon_code", "coupon_code": referral_link}],
                },
            ],
        },
    }
    try:
        _json_post(_messages_url(), payload, settings.whatsapp_access_token)
        return True
    except (HTTPError, URLError, ValueError):
        return False


async def _start_flow(wa_id: str) -> None:
    sessions = get_whatsapp_session_collection()
    await sessions.update_one(
        {"wa_id": wa_id},
        {
            "$set": {
                "wa_id": wa_id,
                "step": "name",
                "data": {
                    "contact_number": normalize_contact_number(wa_id),
                    "membership": "Member",
                },
                "in_progress": True,
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    await send_text(
        wa_id,
        (
            "Welcome to Vanigan ID WhatsApp Bot.\n"
            f"Detected number: {normalize_contact_number(wa_id)}\n"
            "We will collect details step-by-step."
        ),
    )
    await send_text(wa_id, "Step 1/7: Send your NAME")


async def _find_registered_member(wa_id: str) -> dict[str, Any] | None:
    members = get_member_collection()
    contact = normalize_contact_number(wa_id)
    return await members.find_one(
        {
            "contact_number": contact,
            "status": {"$ne": "rejected"},
        },
        {"_id": 0, "unique_id": 1, "name": 1, "membership": 1, "contact_number": 1,
         "referral_code": 1, "referral_count": 1},
        sort=[("updated_at", -1)],
    )


async def _send_registered_menu(wa_id: str, member: dict[str, Any]) -> None:
    await send_list(
        wa_id,
        (
            f"Welcome back {_title(member.get('name', 'Member'))}!\n"
            "Choose an option from menu."
        ),
        "Open Menu",
        [
            ("menu:download", "Download Card"),
            ("menu:viewcard", "View Card"),
            ("menu:organizer", "Become a Organizer"),
            ("menu:poll", "Poll"),
            ("menu:referral", "Referral Link"),
            ("menu:pvtltd", "Pvt Ltd Company?"),
        ],
    )


async def _send_download_cta(wa_id: str, member: dict[str, Any]) -> None:
    unique_id = member.get("unique_id", "")
    if not unique_id:
        await send_text(wa_id, "Card ID not found for this account.")
        return

    if settings.whatsapp_download_template_name:
        sent = await send_download_template(wa_id, member)
        if sent:
            return

    details = (
        f"Name: {member.get('name', '')}\n"
        f"Membership: {member.get('membership', '')}\n"
        f"Phone: {member.get('contact_number', '')}"
    )
    await send_text(wa_id, details)
    await send_reply_buttons(wa_id, "Tap below to download your card", [(f"direct_download:{unique_id}", "Download Card")])


async def _handle_registered_menu_action(wa_id: str, action: str) -> bool:
    registered_actions = {"menu:download", "menu:viewcard", "menu:organizer", "menu:poll", "menu:referral", "menu:pvtltd", "pvtltd:yes", "pvtltd:no", "pvtltd:edit", "pvtltd:remove", "pvtltd:back"}
    if action not in registered_actions and not action.startswith("direct_download:") and not action.startswith("poll:"):
        return False

    if action.startswith("direct_download:"):
        unique_id = action.split(":", 1)[1]
        download_url = f"{_public_base_url()}{settings.api_v1_prefix}/public/card-image/{unique_id}"
        await send_text(wa_id, f"Download: {download_url}")
        member = await _find_registered_member(wa_id)
        if member:
            await _send_registered_menu(wa_id, member)
        return True

    if action.startswith("poll:"):
        await _handle_poll_vote(wa_id, action)
        return True

    member = await _find_registered_member(wa_id)
    if not member:
        await send_text(wa_id, "No existing card found for this number. Send Hi to start a new application.")
        return True

    unique_id = member.get("unique_id", "")

    if action == "menu:download":
        await _send_download_cta(wa_id, member)
        return True

    if action == "menu:viewcard":
        if settings.whatsapp_view_template_name:
            sent = await send_view_card_template(wa_id, member)
            if sent:
                await _send_registered_menu(wa_id, member)
                return True
        view_url = f"{_public_base_url()}/verify/{unique_id}"
        await send_text(wa_id, f"View your card here:\n{view_url}")
        await _send_registered_menu(wa_id, member)
        return True

    if action == "menu:organizer":
        await _handle_organizer(wa_id, member)
        return True

    if action == "menu:poll":
        await _send_poll(wa_id)
        return True

    if action == "menu:referral":
        await _send_referral_link(wa_id, member)
        return True

    if action == "menu:pvtltd":
        # Check if user already has a company name
        members = get_member_collection()
        contact = normalize_contact_number(wa_id)
        full_member = await members.find_one(
            {"contact_number": contact, "status": {"$ne": "rejected"}},
            {"company_name": 1},
        )
        company = (full_member or {}).get("company_name", "") if full_member else ""
        if company:
            await send_reply_buttons(
                wa_id,
                f"Your Business Name: *{company}*",
                [("pvtltd:edit", "Edit"), ("pvtltd:remove", "Remove"), ("pvtltd:back", "Back")],
            )
        else:
            await send_reply_buttons(wa_id, "Do you have a Pvt Ltd Company?", [("pvtltd:yes", "Yes"), ("pvtltd:no", "No")])
        return True

    if action == "pvtltd:yes":
        sessions = get_whatsapp_session_collection()
        await sessions.update_one(
            {"wa_id": wa_id},
            {"$set": {"pvtltd_step": "company_name", "updated_at": _now_iso()}},
        )
        await send_text(wa_id, "Please send your Company Name.")
        return True

    if action == "pvtltd:no":
        await send_text(wa_id, "Thank you!")
        if member:
            await _send_registered_menu(wa_id, member)
        return True

    if action == "pvtltd:edit":
        sessions = get_whatsapp_session_collection()
        await sessions.update_one(
            {"wa_id": wa_id},
            {"$set": {"pvtltd_step": "company_name", "updated_at": _now_iso()}},
        )
        await send_text(wa_id, "Please send your new Company Name.")
        return True

    if action == "pvtltd:remove":
        members = get_member_collection()
        contact = normalize_contact_number(wa_id)
        await members.update_one(
            {"contact_number": contact, "status": {"$ne": "rejected"}},
            {"$unset": {"company_name": ""}, "$set": {"updated_at": _now_iso()}},
        )
        await send_text(wa_id, "Your company name has been removed.")
        if member:
            await _send_registered_menu(wa_id, member)
        return True

    if action == "pvtltd:back":
        if member:
            await _send_registered_menu(wa_id, member)
        return True

    return False


async def _send_referral_link(wa_id: str, member: dict[str, Any]) -> None:
    if settings.whatsapp_referral_template_name:
        sent = await send_referral_template(wa_id, member)
        if sent:
            await _send_registered_menu(wa_id, member)
            return

    referral_code = member.get("referral_code", member.get("unique_id", ""))
    referral_link = f"https://wa.me/{settings.whatsapp_phone_number_id}?text=REF_{referral_code}"
    count = member.get("referral_count", 0)
    await send_text(
        wa_id,
        (
            f"Your Referral Link:\n{referral_link}\n\n"
            f"Total Referrals: {count}\n"
            "Share this link with your friends. When they register using your link, it counts as your referral."
        ),
    )
    await _send_registered_menu(wa_id, member)


async def _handle_organizer(wa_id: str, member: dict[str, Any]) -> None:
    count = member.get("referral_count", 0)
    remaining = max(0, ORGANIZER_THRESHOLD - count)
    referral_code = member.get("referral_code", member.get("unique_id", ""))
    referral_link = f"https://wa.me/{settings.whatsapp_phone_number_id}?text=REF_{referral_code}"

    if remaining == 0:
        await send_text(
            wa_id,
            f"Congratulations! You have {count} referrals and are eligible to become an Organizer.\n"
            "Our team will contact you shortly."
        )
        await _send_registered_menu(wa_id, member)
        return

    if settings.whatsapp_organizer_template_name:
        sent = await send_organizer_template(wa_id, member)
        if sent:
            await _send_registered_menu(wa_id, member)
            return

    await send_text(
        wa_id,
        (
            f"To become an Organizer, you need at least {ORGANIZER_THRESHOLD} referrals.\n\n"
            f"Your referral count: {count}\n"
            f"Remaining: {remaining}\n\n"
            "Share your referral link to invite more members!"
        ),
    )
    await send_reply_buttons(wa_id, f"Your Referral Link:\n{referral_link}", [("menu:referral", "Copy Link")])


async def _send_poll(wa_id: str) -> None:
    polls = get_poll_collection()
    existing = await polls.find_one({"wa_id": wa_id})
    if existing:
        await send_text(wa_id, f"You have already voted for *{existing.get('party', 'a party')}*. Only one vote per member is allowed.")
        member = await _find_registered_member(wa_id)
        if member:
            await _send_registered_menu(wa_id, member)
        return

    await send_list(
        wa_id,
        "Cast your vote in the Poll.\nChoose your preferred party:",
        "Vote Now",
        [
            ("poll:DMK", "1. DMK"),
            ("poll:AIADMK", "2. AIADMK"),
            ("poll:NTK", "3. NTK"),
            ("poll:TVK", "4. TVK"),
        ],
    )


async def _handle_poll_vote(wa_id: str, action: str) -> None:
    party = action.split(":", 1)[1]
    polls = get_poll_collection()

    existing = await polls.find_one({"wa_id": wa_id})
    if existing:
        await send_text(wa_id, f"You have already voted for {existing.get('party', 'a party')}. Only one vote per member is allowed.")
        member = await _find_registered_member(wa_id)
        if member:
            await _send_registered_menu(wa_id, member)
        return

    await polls.insert_one({
        "wa_id": wa_id,
        "party": party,
        "voted_at": _now_iso(),
    })
    await send_text(wa_id, f"Your vote for *{party}* has been recorded. Thank you!")
    member = await _find_registered_member(wa_id)
    if member:
        await _send_registered_menu(wa_id, member)


async def _send_next_prompt(wa_id: str, step: str) -> None:
    prompts = {
        "name": "Step 1/7: Send your NAME",
        "assembly": "Step 2/7: Send ASSEMBLY",
        "district": "Step 3/7: Send DISTRICT",
        "dob": "Step 4/7: Send DOB in DD/MM/YYYY (example 01/10/2000)",
        "blood_group": "Step 5/7: Choose BLOOD GROUP",
        "address": "Step 6/7: Send ADDRESS (max 80 characters)",
        "photo": "Step 7/7: Upload PHOTO image (jpg/png/webp)",
    }

    if step == "blood_group":
        await send_list(
            wa_id,
            "Select Blood Group",
            "Choose",
            [
                ("bg:A+", "A+"),
                ("bg:A-", "A-"),
                ("bg:B+", "B+"),
                ("bg:B-", "B-"),
                ("bg:AB+", "AB+"),
                ("bg:AB-", "AB-"),
                ("bg:O+", "O+"),
                ("bg:O-", "O-"),
            ],
        )
        return

    await send_text(wa_id, prompts[step])


async def _send_confirmation(wa_id: str, data: dict[str, Any]) -> None:
    age = _calc_age(data.get("dob", ""))
    summary = (
        "Please confirm your details:\n"
        f"Name: {_title(data.get('name', ''))}\n"
        f"Membership: {_title(data.get('membership', ''))}\n"
        f"Assembly: {_title(data.get('assembly', ''))}\n"
        f"District: {_title(data.get('district', ''))}\n"
        f"DOB: {data.get('dob', '')}\n"
        f"Age: {age}\n"
        f"Blood Group: {data.get('blood_group', '')}\n"
        f"Address: {data.get('address', '')}\n"
        f"WhatsApp Number: {data.get('contact_number', '')}"
    )
    await send_reply_buttons(wa_id, summary, [("confirm_submit", "Confirm"), ("restart_form", "Restart")])


async def _save_member_and_send_card(wa_id: str, data: dict[str, Any]) -> str | None:
    members = get_member_collection()

    existing = await members.find_one({"contact_number": data["contact_number"], "status": {"$ne": "rejected"}}, {"_id": 1})
    if existing:
        await send_text(wa_id, "A member with this WhatsApp number already exists.")
        return None

    unique_id = await generate_unique_member_id()
    public_base = _public_base_url()
    verify_url = f"{public_base}/verify/{unique_id}"
    qr_url = generate_qr(unique_id, verify_url)

    age = _calc_age(data.get("dob", ""))

    payload = member_document(
        {
            "unique_id": unique_id,
            "name": _title(data["name"]),
            "membership": _title(data["membership"]),
            "assembly": _title(data["assembly"]),
            "district": _title(data["district"]),
            "dob": data["dob"],
            "age": age,
            "blood_group": data["blood_group"],
            "address": data["address"],
            "contact_number": data["contact_number"],
            "photo_url": data["photo_url"],
            "qr_url": qr_url,
            "verify_url": verify_url,
            "referral_code": unique_id,
            "referred_by": data.get("referred_by"),
            "status": "approved",
        }
    )

    await members.insert_one(payload)

    # If referred by someone, increment their referral count
    referred_by = data.get("referred_by")
    if referred_by:
        await members.update_one(
            {"unique_id": referred_by},
            {"$inc": {"referral_count": 1}},
        )

    image_url = f"{public_base}{settings.api_v1_prefix}/public/card-image/{unique_id}"
    verify_page = f"{public_base}/verify/{unique_id}"

    await send_text(
        wa_id,
        (
            "Your card is generated successfully.\n"
            f"Member ID: {unique_id}\n"
            f"Download Card Image: {image_url}\n"
            f"View Card Page: {verify_page}"
        ),
    )
    await _send_registered_menu(
        wa_id,
        {
            "unique_id": unique_id,
            "name": data.get("name", "Member"),
            "membership": data.get("membership", ""),
            "contact_number": data.get("contact_number", ""),
        },
    )
    return unique_id


def _extract_message(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None, None
        msg = messages[0]
        wa_id = msg.get("from")
        return wa_id, msg
    except Exception:
        return None, None


def _extract_text_or_action(msg: dict[str, Any]) -> tuple[str, str | None]:
    msg_type = msg.get("type", "")

    if msg_type == "text":
        return "text", (msg.get("text", {}) or {}).get("body", "").strip()

    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            return "action", interactive.get("button_reply", {}).get("id")
        if interactive.get("type") == "list_reply":
            return "action", interactive.get("list_reply", {}).get("id")

    if msg_type == "image":
        return "image", (msg.get("image", {}) or {}).get("id")

    return msg_type, None


def _download_and_store_whatsapp_image_sync(media_id: str) -> str:
    if not settings.whatsapp_access_token:
        raise ValueError("WhatsApp access token missing")

    media_meta = _json_get(f"{GRAPH_API_BASE}/{media_id}", settings.whatsapp_access_token)
    media_url = media_meta.get("url")
    if not media_url:
        raise ValueError("Media URL not found")

    content = _bytes_get(media_url, settings.whatsapp_access_token)
    uploaded = cloudinary.uploader.upload(content, folder="vanigan/photos")
    return uploaded["secure_url"]


async def _download_and_store_whatsapp_image(media_id: str) -> str:
    return await asyncio.to_thread(_download_and_store_whatsapp_image_sync, media_id)


def _is_greeting(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered in {"hi", "hello", "hii", "hey", "start", "menu"}


async def process_whatsapp_payload(payload: dict[str, Any]) -> None:
    wa_id, msg = _extract_message(payload)
    if not wa_id or not msg:
        return

    sessions = get_whatsapp_session_collection()
    session = await sessions.find_one({"wa_id": wa_id})

    msg_kind, content = _extract_text_or_action(msg)

    # For registered users, greeting should always open menu (even if stale in-progress session exists).
    if msg_kind == "text" and content and _is_greeting(content):
        existing_member = await _find_registered_member(wa_id)
        if existing_member:
            await sessions.update_one(
                {"wa_id": wa_id},
                {
                    "$set": {
                        "wa_id": wa_id,
                        "step": "done",
                        "in_progress": False,
                        "data": {
                            "contact_number": normalize_contact_number(wa_id),
                            "last_unique_id": existing_member.get("unique_id", ""),
                        },
                        "updated_at": _now_iso(),
                    }
                },
                upsert=True,
            )
            await _send_registered_menu(wa_id, existing_member)
            return

    # Handle referral link: REF_<unique_id>
    if msg_kind == "text" and content and content.upper().startswith("REF_"):
        referral_code = content[4:].strip()
        # Check if referrer exists
        members = get_member_collection()
        referrer = await members.find_one({"unique_id": referral_code}, {"_id": 1, "unique_id": 1})
        if referrer:
            # Check if already registered
            existing_member = await _find_registered_member(wa_id)
            if existing_member:
                await send_text(wa_id, "You are already registered. Referral link is for new members only.")
                await _send_registered_menu(wa_id, existing_member)
                return
            # Start flow with referred_by set
            await sessions.update_one(
                {"wa_id": wa_id},
                {
                    "$set": {
                        "wa_id": wa_id,
                        "step": "name",
                        "data": {
                            "contact_number": normalize_contact_number(wa_id),
                            "membership": "Member",
                            "referred_by": referral_code,
                        },
                        "in_progress": True,
                        "updated_at": _now_iso(),
                    }
                },
                upsert=True,
            )
            await send_text(wa_id, "Welcome! You were referred by a Vanigan member.\nLet's get your ID card.")
            await send_text(wa_id, "Step 1/7: Send your NAME")
            return
        else:
            await send_text(wa_id, "Invalid referral link. Send Hi to start a new application.")
            return

    if msg_kind == "action" and content:
        handled = await _handle_registered_menu_action(wa_id, content)
        if handled:
            return

    # Handle company name input for Pvt Ltd flow
    if session and session.get("pvtltd_step") == "company_name" and msg_kind == "text" and content:
        members = get_member_collection()
        contact = normalize_contact_number(wa_id)
        await members.update_one(
            {"contact_number": contact, "status": {"$ne": "rejected"}},
            {"$set": {"company_name": content, "updated_at": _now_iso()}},
        )
        await sessions.update_one({"wa_id": wa_id}, {"$unset": {"pvtltd_step": ""}})
        await send_text(wa_id, f"Thanks for sharing! Your company *{content}* has been recorded.")
        member = await _find_registered_member(wa_id)
        if member:
            await _send_registered_menu(wa_id, member)
        return

    # Allow post-completion actions even when not in-progress.
    if msg_kind == "action" and content == "download_card" and session:
        member = await _find_registered_member(wa_id)
        last_uid = (session.get("data") or {}).get("last_unique_id", "")
        if member and member.get("unique_id"):
            last_uid = member.get("unique_id", "")
        if last_uid:
            await send_text(wa_id, f"Download: {_public_base_url()}{settings.api_v1_prefix}/public/card-image/{last_uid}")
            if member:
                await _send_registered_menu(wa_id, member)
        else:
            await send_text(wa_id, "No recent generated card found. Send Hi to start a new form.")
        return

    if msg_kind == "action" and content == "new_apply":
        await _start_flow(wa_id)
        return

    if not session or not session.get("in_progress"):
        if msg_kind == "text" and content and _is_greeting(content):
            await _start_flow(wa_id)
        else:
            await send_text(wa_id, "Send Hi to start ID application.")
        return

    step = session.get("step", "name")
    data = session.get("data", {})

    if msg_kind == "text" and content and _is_greeting(content):
        await send_text(wa_id, f"You are currently in step: {step}. Please complete this step.")
        await _send_next_prompt(wa_id, step)
        return

    if msg_kind == "action" and content == "restart_form":
        await _start_flow(wa_id)
        return

    if msg_kind == "action" and content and content.startswith("direct_download:"):
        unique_id = content.split(":", 1)[1]
        download_url = f"{_public_base_url()}{settings.api_v1_prefix}/public/card-image/{unique_id}"
        await send_text(wa_id, download_url)
        return

    if msg_kind == "action" and content == "download_card":
        member = await _find_registered_member(wa_id)
        last_uid = data.get("last_unique_id", "")
        if member and member.get("unique_id"):
            last_uid = member.get("unique_id", "")
        if last_uid:
            await send_text(wa_id, f"Download: {_public_base_url()}{settings.api_v1_prefix}/public/card-image/{last_uid}")
            if member:
                await _send_registered_menu(wa_id, member)
        else:
            await send_text(wa_id, "No card found in this session yet.")
        return

    if step == "confirm":
        if msg_kind == "action" and content == "confirm_submit":
            saved_uid = await _save_member_and_send_card(wa_id, data)
            if saved_uid:
                data["last_unique_id"] = saved_uid
            await sessions.update_one(
                {"wa_id": wa_id},
                {"$set": {"in_progress": False, "step": "done", "data": data, "updated_at": _now_iso()}},
            )
        else:
            await send_reply_buttons(wa_id, "Please use confirm or restart.", [("confirm_submit", "Confirm"), ("restart_form", "Restart")])
        return

    if step == "photo":
        if msg_kind != "image" or not content:
            await send_text(wa_id, "Please upload a photo image to continue.")
            return
        await send_text(wa_id, "Generating your card... please wait.")
        try:
            photo_url = await _download_and_store_whatsapp_image(content)
        except (HTTPError, URLError, ValueError, Exception):
            await send_text(wa_id, "Unable to process this image. Please upload again.")
            return

        data["photo_url"] = photo_url
        await sessions.update_one({"wa_id": wa_id}, {"$set": {"step": "confirm", "data": data, "updated_at": _now_iso()}})
        await _send_confirmation(wa_id, data)
        return

    if step == "blood_group":
        if msg_kind != "action" or not content or not content.startswith("bg:"):
            await _send_next_prompt(wa_id, "blood_group")
            return
        data["blood_group"] = content.split(":", 1)[1]
        next_step = "address"
        await sessions.update_one({"wa_id": wa_id}, {"$set": {"step": next_step, "data": data, "updated_at": _now_iso()}})
        await _send_next_prompt(wa_id, next_step)
        return

    if msg_kind != "text" or not content:
        await send_text(wa_id, "Please reply with text for this step.")
        await _send_next_prompt(wa_id, step)
        return

    if step == "dob":
        try:
            parts = content.strip().split('/')
            if len(parts) != 3:
                raise ValueError
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            from datetime import date
            date(year, month, day)  # validate
        except (ValueError, IndexError):
            await send_text(wa_id, "Invalid DOB format. Use DD/MM/YYYY (example 01/10/2000).")
            return

    if step == "address":
        if len(content) > 80:
            await send_text(wa_id, f"Address is too long ({len(content)} chars). Please keep it under 80 characters.")
            return

    fields_order = ["name", "assembly", "district", "dob", "blood_group", "address", "photo"]
    if step in {"name", "assembly", "district", "dob", "address"}:
        data[step] = content

    current_index = fields_order.index(step)
    next_step = fields_order[current_index + 1]

    await sessions.update_one(
        {"wa_id": wa_id},
        {
            "$set": {
                "data": data,
                "step": next_step,
                "in_progress": True,
                "updated_at": _now_iso(),
            }
        },
    )

    await _send_next_prompt(wa_id, next_step)
