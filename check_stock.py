import json
import os
import re
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

import requests

PRODUCT_URL = os.getenv(
    "PRODUCT_URL",
    "https://uk.twiceofficial.store/products/online-exclusive-varsity-jacket",
).rstrip("/")
TARGET_SIZES = [s.strip().upper() for s in os.getenv("TARGET_SIZES", "S,M,L").split(",") if s.strip()]
STATE_FILE = Path(os.getenv("STATE_FILE", "stock_state.json"))
TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def origin():
    p = urlsplit(PRODUCT_URL)
    return f"{p.scheme}://{p.netloc}"

def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def get_product(s):
    r = s.get(PRODUCT_URL + ".js", headers={"Accept": "application/json"},
              params={"_": os.urandom(8).hex()}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def get_page(s):
    r = s.get(PRODUCT_URL, headers={"Accept": "text/html"},
              params={"_": os.urandom(8).hex()}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def size_of(v):
    for key in ("option1", "option2", "title"):
        value = str(v.get(key) or "").strip().upper()
        if value in TARGET_SIZES:
            return value
    return ""

def variants_of(product):
    found = {}
    for v in product.get("variants", []):
        size = size_of(v)
        if size:
            found[size] = {
                "id": str(v["id"]),
                "available_json": bool(v.get("available")),
            }
    missing = [s for s in TARGET_SIZES if s not in found]
    if missing:
        raise RuntimeError("対象サイズが見つかりません: " + ", ".join(missing))
    return found

def page_sold_out(html):
    """
    商品ページ内には、画像のalt属性などにも商品名が複数回登場する。
    そのため「価格表示を伴う実際の商品販売欄」を特定して判定する。
    """
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    title_pattern = (
        r"\[Online Exclusive\]\s*VARSITY JACKET"
    )

    matches = list(
        re.finditer(
            title_pattern,
            text,
            flags=re.I,
        )
    )

    if not matches:
        raise RuntimeError(
            "商品ページ上で商品名を確認できませんでした。"
        )

    product_block = None

    for index, match in enumerate(matches):
        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = min(len(text), start + 3000)

        candidate = text[start:end]

        has_price = bool(
            re.search(
                r"(Regular price|Sale price|£\s*150|150\.00)",
                candidate,
                flags=re.I,
            )
        )

        if has_price:
            product_block = candidate
            break

    if product_block is None:
        raise RuntimeError(
            "VARSITY JACKETの販売欄を特定できませんでした。"
        )

    sold_out_count = len(
        re.findall(
            r"\bSold out\b",
            product_block,
            flags=re.I,
        )
    )

    print(
        "Product sales block Sold out count:",
        sold_out_count,
    )

    return sold_out_count > 0

def cart_add_check(variant_id):
    s = session()
    get_page(s)
    r = s.post(
        origin() + "/cart/add.js",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": origin(),
            "Referer": PRODUCT_URL,
        },
        json={"items": [{"id": int(variant_id), "quantity": 1}]},
        timeout=TIMEOUT,
    )
    if r.status_code not in (200, 201):
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    try:
        data = r.json()
    except ValueError:
        return False, "JSON応答ではありません。"
    items = data.get("items", []) if isinstance(data, dict) else []
    if not items and isinstance(data, dict) and data.get("id"):
        items = [data]
    ok = any(
        str(i.get("variant_id") or i.get("id")) == str(variant_id)
        and int(i.get("quantity", 0)) >= 1
        for i in items if isinstance(i, dict)
    )
    return ok, "cart/add.js success" if ok else "対象商品を応答内で確認できません。"

def load_state():
    default = {s: False for s in TARGET_SIZES}
    if not STATE_FILE.exists():
        return default
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {s: bool(data.get(s, False)) for s in TARGET_SIZES}
    except Exception:
        return default

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def cart_url(variant_id):
    return f"{origin()}/cart/{variant_id}:1"

def send_email(subject, body):
    user = os.environ["SMTP_USERNAME"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT) as smtp:
        smtp.login(user, os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)

def send_line(body):
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": "Bearer " + os.environ["LINE_CHANNEL_ACCESS_TOKEN"],
            "Content-Type": "application/json",
        },
        json={"to": os.environ["LINE_USER_ID"],
              "messages": [{"type": "text", "text": body[:5000]}]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()

def set_github_output(key, value):
    """GitHub Actions の GITHUB_OUTPUT へ値を書き出す。"""
    output_file = os.getenv("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")

def notify(subject, body):
    errors = []
    try:
        send_email(subject, body)
        print("Email notification sent.")
    except Exception as e:
        errors.append("Email: " + str(e))
    try:
        send_line(body)
        print("LINE notification sent.")
    except Exception as e:
        errors.append("LINE: " + str(e))
    if errors:
        raise RuntimeError(" / ".join(errors))
    # 通知成功 → workflow 自動停止のフラグをセット
    set_github_output("notified", "true")

def main():
    s = session()
    product = get_product(s)
    html = get_page(s)
    variants = variants_of(product)
    sold_out = page_sold_out(html)
    previous = load_state()
    current = {}
    details = {}

    for size in TARGET_SIZES:
        v = variants[size]
        cart_ok, cart_detail = (False, "JSON unavailable")
        if v["available_json"]:
            cart_ok, cart_detail = cart_add_check(v["id"])
        purchasable = bool(v["available_json"] and cart_ok and not sold_out)
        current[size] = purchasable
        details[size] = {
            "json_available": v["available_json"],
            "page_sold_out": sold_out,
            "cart_add_ok": cart_ok,
            "cart_detail": cart_detail,
            "purchasable": purchasable,
        }

    print(json.dumps(details, ensure_ascii=False, indent=2))
    print("Previous:", previous)
    print("Current:", current)

    newly = [s for s in TARGET_SIZES if current[s] and not previous.get(s, False)]
    if newly:
        links = [f"{s}サイズ（1着）: {cart_url(variants[s]['id'])}" for s in newly]
        size_text = "・".join(newly)
        notify(
            f"【TWICE入荷】VARSITY JACKET {size_text}サイズが購入可能です",
            "購入可能状態への変化を検知しました。\n\n"
            f"入荷サイズ: {size_text}\n\n" + "\n".join(links) +
            "\n\n商品JSON、商品ページ表示、カート追加APIの3条件を確認しています。"
            "\n在庫は決済完了まで確保されません。\n\n" + PRODUCT_URL
        )
    else:
        print("新たに購入可能になったサイズはありません。")

    if current != previous:
        save_state(current)
        print("State file updated.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
