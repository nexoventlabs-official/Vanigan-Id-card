import os
from importlib import import_module


def generate_qr(unique_id: str, verify_url: str) -> str:
    qrcode = import_module("qrcode")

    qr_dir = os.path.join("app", "static", "generated", "qr")
    os.makedirs(qr_dir, exist_ok=True)
    filename = f"{unique_id}.png"
    filepath = os.path.join(qr_dir, filename)

    img = qrcode.make(verify_url)
    img.save(filepath)
    return f"/static/generated/qr/{filename}"
