from olx_bot.db import init_db, is_seen, mark_seen


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
