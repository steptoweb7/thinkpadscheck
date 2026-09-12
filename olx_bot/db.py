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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ssd_price_observations (
            listing_id TEXT PRIMARY KEY,
            capacity_bucket INTEGER,
            price INTEGER,
            recorded_at TEXT
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


def record_price_observation(
    conn: sqlite3.Connection,
    listing_id: str,
    capacity_bucket: int,
    price: int,
    recorded_at: str,
) -> None:
    """Records one ad's (capacity, price) once, forever — a listing scanned
    again on a later run must not be counted twice toward the market
    average, since it would still be the same ad still for sale."""
    conn.execute(
        """
        INSERT OR IGNORE INTO ssd_price_observations
            (listing_id, capacity_bucket, price, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        (listing_id, capacity_bucket, price, recorded_at),
    )
    conn.commit()


def get_price_stats(conn: sqlite3.Connection, capacity_bucket: int):
    """Returns (median_price, sample_count) for all observations recorded
    at this capacity bucket. (None, 0) if nothing has been observed yet."""
    cursor = conn.execute(
        "SELECT price FROM ssd_price_observations WHERE capacity_bucket = ? ORDER BY price",
        (capacity_bucket,),
    )
    prices = [row[0] for row in cursor.fetchall()]
    if not prices:
        return None, 0

    n = len(prices)
    mid = n // 2
    median = prices[mid] if n % 2 == 1 else (prices[mid - 1] + prices[mid]) / 2
    return median, n
