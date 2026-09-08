import sqlite3


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_listings (
            id TEXT PRIMARY KEY,
            title TEXT,
            price INTEGER,
            score_pct REAL,
            seen_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def is_seen(conn: sqlite3.Connection, listing_id: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM seen_listings WHERE id = ?", (listing_id,)
    )
    return cursor.fetchone() is not None


def mark_seen(
    conn: sqlite3.Connection,
    listing_id: str,
    title: str,
    price: int,
    score_pct,
    seen_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO seen_listings (id, title, price, score_pct, seen_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (listing_id, title, price, score_pct, seen_at),
    )
    conn.commit()
