"""
Illustration Rare Pokémon price tracker.

Run this once to build the card catalog, then run it once a day
(via cron or GitHub Actions — see README.md) to log that day's
TCGPlayer Market Price for every card.

Data source: the Pokémon TCG API (api.pokemontcg.io), which surfaces
TCGPlayer's own pricing data, including "market" price per variant.
Get a free key at https://dev.pokemontcg.io/
"""

import os
import time
import sqlite3
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POKEMONTCG_API_KEY", "")
BASE_URL = "https://api.pokemontcg.io/v2/cards"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pokemon_prices.db")

# Change to "Special Illustration Rare" to track that tier instead,
# or call fetch_all_cards twice (once per rarity) to track both.
TARGET_RARITY = "Illustration Rare"

PAGE_SIZE = 250


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_id TEXT PRIMARY KEY,
            name TEXT,
            set_id TEXT,
            set_name TEXT,
            set_release_date TEXT,
            number TEXT,
            rarity TEXT,
            image_url TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            card_id TEXT,
            variant TEXT,
            date TEXT,
            market_price REAL,
            low_price REAL,
            mid_price REAL,
            high_price REAL,
            PRIMARY KEY (card_id, variant, date)
        )
    """)
    conn.commit()
    return conn


def _get_with_retry(params):
    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    for attempt in range(4):
        resp = requests.get(BASE_URL, headers=headers, params=params, timeout=30)
        if resp.status_code == 429:
            wait = 5 * (attempt + 1)
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def fetch_all_cards(rarity):
    """Fetch every card matching `rarity`, handling pagination via totalCount."""
    page = 1
    all_cards = []
    total_count = None

    while True:
        params = {"q": f'rarity:"{rarity}"', "page": page, "pageSize": PAGE_SIZE}
        payload = _get_with_retry(params)
        batch = payload.get("data", [])

        if total_count is None:
            total_count = payload.get("totalCount", len(batch))

        if not batch:
            break

        all_cards.extend(batch)
        print(f"  fetched page {page}: {len(all_cards)}/{total_count} cards")

        if len(all_cards) >= total_count:
            break

        page += 1
        time.sleep(0.5)  # be polite to the API

    # Defensive filter: a quoted phrase query for "Illustration Rare" can also
    # match "Special Illustration Rare" since it contains the same two words
    # in sequence. Keep only exact matches.
    return [c for c in all_cards if c.get("rarity") == rarity]


def update_database(conn, cards):
    today = date.today().isoformat()
    cur = conn.cursor()
    new_cards = 0
    price_rows = 0

    for card in cards:
        set_info = card.get("set", {}) or {}
        images = card.get("images", {}) or {}

        cur.execute("""
            INSERT INTO cards (card_id, name, set_id, set_name, set_release_date, number, rarity, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                name=excluded.name,
                set_id=excluded.set_id,
                set_name=excluded.set_name,
                set_release_date=excluded.set_release_date,
                number=excluded.number,
                rarity=excluded.rarity,
                image_url=excluded.image_url
        """, (
            card["id"],
            card.get("name"),
            set_info.get("id"),
            set_info.get("name"),
            set_info.get("releaseDate"),
            card.get("number"),
            card.get("rarity"),
            images.get("large") or images.get("small"),
        ))
        if cur.rowcount == 1:
            new_cards += 1

        prices = ((card.get("tcgplayer") or {}).get("prices") or {})
        for variant, p in prices.items():
            market = p.get("market")
            if market is None:
                continue  # TCGPlayer has no market price for this variant yet
            cur.execute("""
                INSERT INTO price_history (card_id, variant, date, market_price, low_price, mid_price, high_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id, variant, date) DO UPDATE SET
                    market_price=excluded.market_price,
                    low_price=excluded.low_price,
                    mid_price=excluded.mid_price,
                    high_price=excluded.high_price
            """, (card["id"], variant, today, market, p.get("low"), p.get("mid"), p.get("high")))
            price_rows += 1

    conn.commit()
    return new_cards, price_rows


def main():
    if not API_KEY:
        print("Warning: no POKEMONTCG_API_KEY set — you'll be limited to a much lower rate limit.")

    print(f"Fetching all '{TARGET_RARITY}' cards...")
    cards = fetch_all_cards(TARGET_RARITY)
    print(f"Found {len(cards)} cards.")

    conn = get_connection()
    new_cards, price_rows = update_database(conn, cards)
    conn.close()

    print(f"Done. {new_cards} new card(s) added to the catalog. "
          f"{price_rows} price point(s) logged for {date.today().isoformat()}.")


if __name__ == "__main__":
    main()
