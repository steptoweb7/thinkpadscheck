from olx_bot.db import get_price_stats, init_db, is_seen, mark_seen, record_price_observation


def test_dedup_flow(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)

    assert is_seen(conn, "123") is False

    mark_seen(conn, "123", "Laptop Test", 1200, 33.3, "2026-09-02T10:00:00")

    assert is_seen(conn, "123") is True
    assert is_seen(conn, "999") is False

    conn.close()


def test_init_db_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn1 = init_db(db_path)
    mark_seen(conn1, "1", "A", 100, None, "2026-09-02T10:00:00")
    conn1.close()

    conn2 = init_db(db_path)
    assert is_seen(conn2, "1") is True
    conn2.close()


def test_price_stats_empty_when_no_observations(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    median, count = get_price_stats(conn, 1000)
    assert median is None
    assert count == 0
    conn.close()


def test_price_stats_computes_median_and_count(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    for i, price in enumerate([300, 320, 280, 310, 290]):
        record_price_observation(conn, f"ad{i}", 1000, price, "2026-09-12T00:00:00")

    median, count = get_price_stats(conn, 1000)
    assert count == 5
    assert median == 300  # sorted: 280,290,300,310,320 -> middle
    conn.close()


def test_price_stats_ignores_other_capacity_buckets(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    record_price_observation(conn, "ad1", 1000, 300, "2026-09-12T00:00:00")
    record_price_observation(conn, "ad2", 2000, 500, "2026-09-12T00:00:00")

    median, count = get_price_stats(conn, 1000)
    assert count == 1
    assert median == 300
    conn.close()


def test_record_price_observation_is_idempotent_per_listing(tmp_path):
    """Same ad scanned again on a later run must not double-count."""
    conn = init_db(str(tmp_path / "test.db"))
    record_price_observation(conn, "ad1", 1000, 300, "2026-09-12T00:00:00")
    record_price_observation(conn, "ad1", 1000, 300, "2026-09-13T00:00:00")

    median, count = get_price_stats(conn, 1000)
    assert count == 1
    conn.close()
