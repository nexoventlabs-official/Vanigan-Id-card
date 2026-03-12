from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import cloudinary.uploader

from app.core.config import settings
from app.core.db import get_member_collection, get_whatsapp_session_collection
from app.models.member import member_document
from app.services.id_generator import generate_unique_member_id
from app.services.otp_service import normalize_contact_number
from app.services.qr_service import generate_qr

GRAPH_API_BASE = "https://graph.facebook.com/v22.0"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


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
    await send_text(wa_id, "Step 1/8: Send your NAME")


async def _find_registered_member(wa_id: str) -> dict[str, Any] | None:
    members = get_member_collection()
    contact = normalize_contact_number(wa_id)
    return await members.find_one(
        {
            "contact_number": contact,
            "status": {"$ne": "rejected"},
        },
        {"_id": 0, "unique_id": 1, "name": 1, "membership": 1, "contact_number": 1},
        sort=[("updated_at", -1)],
    )


async def _send_registered_menu(wa_id: str, member: dict[str, Any]) -> None:
    await send_list(
        wa_id,
        (
            f"Welcome back {member.get('name', 'Member')}!\n"
            "Choose an option from menu."
        ),
        "Open Menu",
        [
            ("menu:download", "Download Card"),
            ("menu:edit", "Edit Details"),
            ("menu:refer", "Refer"),
            ("menu:contact", "Contact"),
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
    if action not in {"menu:download", "menu:edit", "menu:refer", "menu:contact"} and not action.startswith("direct_download:"):
        return False

    if action.startswith("direct_download:"):
        unique_id = action.split(":", 1)[1]
        download_url = f"{_public_base_url()}{settings.api_v1_prefix}/public/card-image/{unique_id}"
        await send_text(wa_id, f"Download: {download_url}")
        member = await _find_registered_member(wa_id)
        if member:
            await _send_registered_menu(wa_id, member)
        return True

    member = await _find_registered_member(wa_id)
    if not member:
        await send_text(wa_id, "No existing card found for this number. Send Hi to start a new application.")
        return True

    unique_id = member.get("unique_id", "")
    if action == "menu:download":
        await _send_download_cta(wa_id, member)
        return True

    if action == "menu:edit":
        await send_text(wa_id, "Let us update your details. We will start from beginning and keep your WhatsApp number.")
        await _start_flow(wa_id)
        return True

    if action == "menu:refer":
        refer_text = (
            "Refer Vanigan ID to your contacts:\n"
            "1) Save this number\n"
            "2) Send Hi\n"
            "3) Complete the form to get ID card"
        )
        await send_text(wa_id, refer_text)
        await _send_registered_menu(wa_id, member)
        return True

    if action == "menu:contact":
        await send_text(wa_id, "For support, reply here with your issue and our team will contact you.")
        await _send_registered_menu(wa_id, member)
        return True

    return False


async def _send_next_prompt(wa_id: str, step: str) -> None:
    prompts = {
        "name": "Step 1/8: Send your NAME",
        "assembly": "Step 2/8: Send ASSEMBLY",
        "district": "Step 3/8: Send DISTRICT",
        "dob": "Step 4/8: Send DOB in YYYY-MM-DD (example 2000-10-01)",
        "age": "Step 5/8: Send AGE (number)",
        "blood_group": "Step 6/8: Choose BLOOD GROUP",
        "address": "Step 7/8: Send ADDRESS",
        "photo": "Step 8/8: Upload PHOTO image (jpg/png/webp)",
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
    summary = (
        "Please confirm your details:\n"
        f"Name: {data.get('name', '')}\n"
        f"Membership: {data.get('membership', '')}\n"
        f"Assembly: {data.get('assembly', '')}\n"
        f"District: {data.get('district', '')}\n"
        f"DOB: {data.get('dob', '')}\n"
        f"Age: {data.get('age', '')}\n"
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

    payload = member_document(
        {
            "unique_id": unique_id,
            "name": data["name"],
            "membership": data["membership"],
            "assembly": data["assembly"],
            "district": data["district"],
            "dob": data["dob"],
            "age": int(data["age"]),
            "blood_group": data["blood_group"],
            "address": data["address"],
            "contact_number": data["contact_number"],
            "photo_url": data["photo_url"],
            "qr_url": qr_url,
            "verify_url": verify_url,
            "status": "approved",
        }
    )

    await members.insert_one(payload)

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


async def _download_and_store_whatsapp_image(media_id: str) -> str:
    if not settings.whatsapp_access_token:
        raise ValueError("WhatsApp access token missing")

    media_meta = _json_get(f"{GRAPH_API_BASE}/{media_id}", settings.whatsapp_access_token)
    media_url = media_meta.get("url")
    if not media_url:
        raise ValueError("Media URL not found")

    content = _bytes_get(media_url, settings.whatsapp_access_token)
    uploaded = cloudinary.uploader.upload(content, folder="vanigan/photos")
    return uploaded["secure_url"]


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

    if msg_kind == "action" and content:
        handled = await _handle_registered_menu_action(wa_id, content)
        if handled:
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
        try:
            photo_url = await _download_and_store_whatsapp_image(content)
        except (HTTPError, URLError, ValueError):
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
            datetime.strptime(content, "%Y-%m-%d")
        except ValueError:
            await send_text(wa_id, "Invalid DOB format. Use YYYY-MM-DD.")
            return

    if step == "age":
        if not content.isdigit():
            await send_text(wa_id, "Age must be a number.")
            return

    fields_order = ["name", "assembly", "district", "dob", "age", "blood_group", "address", "photo"]
    if step in {"name", "assembly", "district", "dob", "age", "address"}:
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
