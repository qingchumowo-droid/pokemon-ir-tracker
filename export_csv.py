"""
Exports the full card + price history to a CSV file, sorted by card then date.
Run this any time after tracker.py has logged at least one day of prices.
"""

import csv
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pokemon_prices.db")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "illustration_rare_price_history.csv")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT c.name, c.set_name, c.number, c.rarity, p.variant, p.date, p.market_price
        FROM price_history p
        JOIN cards c ON c.card_id = p.card_id
        ORDER BY c.name, p.variant, p.date
    """)
    rows = cur.fetchall()
    conn.close()

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "set", "number", "rarity", "variant", "date", "market_price"])
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
