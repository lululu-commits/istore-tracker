"""
iStore price tracker (daily).
Each run: fetch price -> append to prices.csv -> email you if the price changed.

Install:  pip install requests beautifulsoup4
Env vars: GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO (comma-separated for several people)
"""
import csv
import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://www.istore.co.za/apple-tv-4k-3rd-gen"
PRODUCT_ID = "1562721"       # from span id="product-price-1562721"
PRODUCT_NAME = "Apple TV 4K (3rd Gen)"
ALERT_ON_INCREASE = True     # False = only email when the price drops
CSV_FILE = Path("prices.csv")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-ZA,en;q=0.9",
}


def fetch_price() -> int:
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # The page has several prices (related products), so target the main product by ID
    el = soup.select_one(f"#product-price-{PRODUCT_ID}[data-price-amount]")
    if el is None:
        raise RuntimeError("Price element not found - layout may have changed")
    return int(float(el["data-price-amount"]))


def last_price():
    if not CSV_FILE.exists():
        return None
    with CSV_FILE.open() as f:
        rows = list(csv.reader(f))
    return int(rows[-1][1]) if len(rows) > 1 else None


def save_price(price: int):
    new_file = not CSV_FILE.exists()
    with CSV_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "price"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), price])


def send_email(subject: str, text: str, html: str):
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipients = [e.strip() for e in os.getenv("EMAIL_TO", user or "").split(",") if e.strip()]
    if not user or not password or not recipients:
        print("EMAIL (not configured):", subject, "|", text)
        return
    msg = EmailMessage()
    msg["From"] = f"iStore Price Alerts <{user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)


def build_html(headline: str, prev: int, price: int) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px">
      <h2 style="margin:0 0 8px">{headline}</h2>
      <p style="font-size:16px;margin:0 0 16px">{PRODUCT_NAME}</p>
      <p style="font-size:28px;margin:0 0 4px"><b>R{price:,}</b></p>
      <p style="color:#777;margin:0 0 24px">was R{prev:,}</p>
      <a href="{URL}" style="background:#0071e3;color:#fff;padding:12px 24px;
         text-decoration:none;border-radius:8px;display:inline-block">View on iStore</a>
    </div>"""


def main():
    try:
        price = fetch_price()
    except Exception as e:
        print("Error:", e)
        sys.exit(1)

    prev = last_price()
    save_price(price)
    print(f"Current price: R{price:,} (previous: {prev})")

    if prev is None or price == prev:
        return  # first run or no change: stay quiet

    if price < prev:
        send_email(
            f"Price drop: {PRODUCT_NAME} now R{price:,}",
            f"{PRODUCT_NAME} dropped from R{prev:,} to R{price:,}. {URL}",
            build_html("Price drop!", prev, price),
        )
    elif ALERT_ON_INCREASE:
        send_email(
            f"Price increase: {PRODUCT_NAME} now R{price:,}",
            f"{PRODUCT_NAME} went up from R{prev:,} to R{price:,}. {URL}",
            build_html("Price increase", prev, price),
        )


if __name__ == "__main__":
    main()
