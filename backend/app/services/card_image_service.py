from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_image(source: str) -> Image.Image:
    if source.startswith("http://") or source.startswith("https://"):
        with urlopen(source) as response:
            data = response.read()
        return Image.open(BytesIO(data)).convert("RGBA")

    path = Path(source)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return Image.open(path).convert("RGBA")


def _resolve_local_asset(source: str) -> str:
    if source.startswith("/static/"):
        relative = source.removeprefix("/static/")
        return str(PROJECT_ROOT / "app" / "static" / relative)
    return source


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for candidate in font_candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, width: int, font: ImageFont.ImageFont, fill: tuple[int, int, int]) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = int((width - text_w) / 2)
    draw.text((x, y), text, font=font, fill=fill)


def _draw_centered_in_region(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    left: int,
    region_width: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = int(left + (region_width - text_w) / 2)
    draw.text((x, y), text, font=font, fill=fill)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    wrapped_lines: list[str] = []
    normalized = " ".join(part.strip() for part in text.splitlines() if part.strip())
    raw_lines = [normalized] if normalized else [text]

    for raw_line in raw_lines:
        words = raw_line.split()
        if not words:
            wrapped_lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            bbox = draw.textbbox((0, 0), candidate, font=font)
            candidate_width = bbox[2] - bbox[0]
            if candidate_width <= max_width:
                current = candidate
            else:
                wrapped_lines.append(current)
                current = word
        wrapped_lines.append(current)

    return wrapped_lines


def generate_card_image(member: dict[str, Any], backend_public_url: str) -> bytes:
    front_url = "https://res.cloudinary.com/dqndhcmu2/image/upload/v1773232516/vanigan/templates/ID_Front.png"
    back_url = "https://res.cloudinary.com/dqndhcmu2/image/upload/v1773232519/vanigan/templates/ID_Back.png"

    front_bg = _load_image(front_url)
    back_target_height = int(round(front_bg.width * 590 / 421))
    back_bg = _load_image(back_url).resize((front_bg.width, back_target_height), Image.Resampling.LANCZOS)

    width, front_h = front_bg.size
    back_h = back_bg.height
    gap = 32

    # Build front side
    front = front_bg.copy()
    draw_front = ImageDraw.Draw(front)

    sx = width / 421.0
    sy = front_h / 573.0

    photo_source = str(member.get("photo_url", ""))
    if photo_source and not photo_source.startswith("http"):
        photo_source = _resolve_local_asset(photo_source)
    photo = _load_image(photo_source).convert("RGB")

    photo_w = int(137 * sx)
    photo_h = int(136 * sy)
    photo_x = int(((421 - 137) / 2) * sx)
    photo_y = int(182 * sy)

    photo = ImageOps.fit(photo, (photo_w, photo_h), Image.Resampling.LANCZOS)
    radius = int(22 * sx)
    mask = Image.new("L", (photo_w, photo_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, photo_w, photo_h), radius=radius, fill=255)

    border_w = max(4, int(5 * sx))
    border_layer = Image.new("RGBA", (photo_w + border_w * 2, photo_h + border_w * 2), (0, 0, 0, 0))
    ImageDraw.Draw(border_layer).rounded_rectangle(
        (0, 0, border_layer.width - 1, border_layer.height - 1),
        radius=radius + border_w,
        fill=(0, 146, 69, 255),
    )
    border_layer.paste(photo.convert("RGBA"), (border_w, border_w), mask)
    front.paste(border_layer, (photo_x - border_w, photo_y - border_w), border_layer)

    front_positions = {
        "name": int(328 * sy),
        "membership": int(362 * sy),
        "assembly": int(388 * sy),
        "district": int(414 * sy),
        "id": int(442 * sy),
    }

    _draw_centered(draw_front, str(member.get("name", "")), front_positions["name"], width, _font(max(26, int(23 * sy)), True), (0, 146, 69))
    _draw_centered(draw_front, str(member.get("membership", "")), front_positions["membership"], width, _font(max(24, int(19 * sy)), True), (0, 0, 0))
    _draw_centered(draw_front, str(member.get("assembly", "")), front_positions["assembly"], width, _font(max(24, int(19 * sy)), True), (0, 0, 0))
    _draw_centered(draw_front, str(member.get("district", "")), front_positions["district"], width, _font(max(24, int(19 * sy)), True), (0, 0, 0))
    _draw_centered(draw_front, str(member.get("unique_id", "")), front_positions["id"], width, _font(max(22, int(18 * sy)), True), (0, 0, 0))

    # Build back side
    back = back_bg.copy()
    draw_back = ImageDraw.Draw(back)

    sy_b = back_h / 590.0
    sx_b = width / 421.0

    labels = ["DATE OF BIRTH", "AGE", "BLOOD GROUP", "ADDRESS", "CONTACT"]
    values = [
        str(member.get("dob", "")),
        str(member.get("age", "")),
        str(member.get("blood_group", "")),
        str(member.get("address", "")),
        str(member.get("contact_number", "")),
    ]

    x_label = int(22 * sx_b)
    x_sep = int(196 * sx_b)
    x_value = int(218 * sx_b)
    value_max_width = width - x_value - int(18 * sx_b)
    y = int(174 * sy_b)

    for idx, (label, value) in enumerate(zip(labels, values)):
        draw_back.text((x_label, y), label, font=_font(max(28, int(14 * sy_b)), True), fill=(0, 0, 0))
        draw_back.text((x_sep, y - int(3 * sy_b)), ":", font=_font(max(34, int(22 * sy_b)), True), fill=(0, 0, 0))

        if idx == 3:
            address_font = _font(max(22, int(14 * sy_b)), True)
            line_h = int(15 * sy_b)
            address_lines = _wrap_text(draw_back, str(value), address_font, value_max_width)
            for line_idx, line in enumerate(address_lines):
                draw_back.text((x_value, y + line_idx * line_h), line, font=address_font, fill=(0, 0, 0))
            y += max(int(52 * sy_b), line_h * len(address_lines) + int(2 * sy_b))
        else:
            draw_back.text((x_value, y), str(value), font=_font(max(28, int(17 * sy_b)), True), fill=(0, 0, 0))
            y += int(32 * sy_b)

    qr_source = str(member.get("qr_url", ""))
    if qr_source and not qr_source.startswith("http"):
        qr_source = _resolve_local_asset(qr_source)
    qr_img = _load_image(qr_source).convert("RGBA")
    qr_w = int(96 * sx_b)
    qr_h = int(88 * sy_b)
    qr_x = int(20 * sx_b)
    qr_y = int(404 * sy_b)
    qr_img = qr_img.resize((qr_w, qr_h), Image.Resampling.NEAREST)
    back.paste(qr_img, (qr_x, qr_y), qr_img)

    signature = _load_image("app/static/assets/signature.png").convert("RGBA")
    sign_w = int(92 * sx_b)
    sign_h = int(34 * sy_b)
    sign_x = int(264 * sx_b)
    sign_y = int(400 * sy_b)
    signature = signature.resize((sign_w, sign_h), Image.Resampling.LANCZOS)
    back.paste(signature, (sign_x, sign_y), signature)

    sign_region_left = int(182 * sx_b)
    sign_region_width = width - sign_region_left - int(12 * sx_b)
    _draw_centered_in_region(
        draw_back,
        "SENTHIL KUMAR N",
        sign_y + sign_h + int(10 * sy_b),
        sign_region_left,
        sign_region_width,
        _font(max(26, int(14 * sy_b)), True),
        (0, 0, 0),
    )
    _draw_centered_in_region(
        draw_back,
        "Founder & State President",
        sign_y + sign_h + int(28 * sy_b),
        sign_region_left,
        sign_region_width,
        _font(max(21, int(12 * sy_b)), True),
        (0, 0, 0),
    )
    _draw_centered_in_region(
        draw_back,
        "Tamilnadu Vanigargalin Sangamam",
        sign_y + sign_h + int(44 * sy_b),
        sign_region_left,
        sign_region_width,
        _font(max(21, int(12 * sy_b)), True),
        (0, 0, 0),
    )

    # Combine front and back into one vertical image
    final = Image.new("RGBA", (width, front_h + gap + back_h), (255, 255, 255, 0))
    final.paste(front, (0, 0), front)
    final.paste(back, (0, front_h + gap), back)

    out = BytesIO()
    final.convert("RGB").save(out, format="PNG", optimize=False, compress_level=0)
    return out.getvalue()
