import json
import os
import smtplib
import sys
from email.message import EmailMessage

import requests

PRODUCT_URL = os.getenv(
    "PRODUCT_URL",
    "https://uk.twiceofficial.store/products/online-exclusive-varsity-jacket",
).rstrip("/")
TARGET_SIZES = [s.strip().upper() for s in os.getenv("TARGET_SIZES", "S,M,L").split(",") if s.strip()]
TIMEOUT = 30
UA = "Mozilla/5.0 (compatible; TWICEStockWatcher/1.1; personal-use)"


def get_product() -> dict:
    response = requests.get(
        PRODUCT_URL + ".js",
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def normalize_size(variant: dict) -> str:
    for candidate in (variant.get("option1"), variant.get("title")):
        if candidate:
            return str(candidate).strip().upper()
    return ""


def find_target_variants(product: dict) -> tuple[dict, list[str]]:
    found = {}
    for variant in product.get("variants", []):
        size = normalize_size(variant)
        if size in TARGET_SIZES:
            found[size] = {
                "id": str(variant["id"]),
                "available": bool(variant.get("available")),
                "title": variant.get("title", size),
            }
    missing = [size for size in TARGET_SIZES if size not in found]
    return found, missing


def make_cart_url(variant_id: str) -> str:
    """指定した1サイズを1着だけ入れるShopifyカートリンクを作る。"""
    origin = PRODUCT_URL.split("/products/", 1)[0]
    return f"{origin}/cart/{variant_id}:1"


def send_email(subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    to_addr = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)


def send_line(body: str) -> None:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    user_id = os.environ["LINE_USER_ID"]
    response = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"to": user_id, "messages": [{"type": "text", "text": body[:5000]}]},
        timeout=TIMEOUT,
    )
    response.raise_for_status()


def notify(subject: str, body: str) -> None:
    errors = []
    try:
        send_email(subject, body)
        print("Email notification sent.")
    except Exception as exc:
        errors.append(f"Email: {exc}")

    try:
        send_line(body)
        print("LINE notification sent.")
    except Exception as exc:
        errors.append(f"LINE: {exc}")

    if errors:
        raise RuntimeError(" / ".join(errors))


def write_output(name: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(f"{name}={value}\n")


def main() -> int:
    product = get_product()
    found, missing = find_target_variants(product)

    print("Product:", product.get("title"))
    print(json.dumps(found, ensure_ascii=False, indent=2))

    if missing:
        raise RuntimeError(f"Target variants were not found: {', '.join(missing)}")

    available_sizes = [size for size in TARGET_SIZES if found[size]["available"]]
    if not available_sizes:
        print("S, M, L are still sold out.")
        write_output("restocked", "false")
        return 0

    link_lines = [
        f"{size}サイズ（1着）: {make_cart_url(found[size]['id'])}"
        for size in available_sizes
    ]
    sizes_text = "・".join(available_sizes)
    subject = f"【TWICE入荷】VARSITY JACKET {sizes_text}サイズが購入可能です"
    body = (
        "TWICE UKのVARSITY JACKETで、次のサイズが購入可能になりました。\n\n"
        f"入荷サイズ: {sizes_text}\n\n"
        "購入したいサイズのリンクを開くと、そのサイズ1着を入れたカートへ進みます。\n"
        + "\n".join(link_lines)
        + "\n\n在庫はカート投入だけでは確保されません。できるだけ早く決済してください。\n"
        + f"商品ページ: {PRODUCT_URL}"
    )

    notify(subject, body)
    write_output("restocked", "true")
    write_output("available_sizes", ",".join(available_sizes))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
