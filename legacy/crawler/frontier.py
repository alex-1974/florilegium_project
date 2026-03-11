from __future__ import annotations

import sqlite3
import time
from urllib.parse import urlparse


class Frontier:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS frontier(
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            domain TEXT,
            depth INTEGER,
            score REAL,
            source_url TEXT,
            anchor_text TEXT,
            status TEXT,
            discovered_at REAL,
            visited_at REAL
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_status ON frontier(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_score ON frontier(score)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_domain ON frontier(domain)")

        self.conn.commit()

    def reset(self) -> None:
        self.conn.execute("DELETE FROM frontier")
        self.conn.commit()

    def add_url(self, url, depth=0, score=0.0, source_url=None, anchor=None):
        domain = urlparse(url).netloc
        try:
            self.conn.execute(
                """
                INSERT INTO frontier
                (url, domain, depth, score, source_url, anchor_text,
                 status, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    url,
                    domain,
                    depth,
                    score,
                    source_url,
                    anchor,
                    time.time(),
                ),
            )
            self.conn.commit()
            return "inserted"
        except sqlite3.IntegrityError:
            return "exists"

    def add_or_requeue_url(self, url, depth=0, score=0.0, source_url=None, anchor=None):
        domain = urlparse(url).netloc
        now = time.time()

        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, depth, score, status
            FROM frontier
            WHERE url=?
            """,
            (url,),
        )
        row = cur.fetchone()

        if row is None:
            self.conn.execute(
                """
                INSERT INTO frontier
                (url, domain, depth, score, source_url, anchor_text,
                 status, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    url,
                    domain,
                    depth,
                    score,
                    source_url,
                    anchor,
                    now,
                ),
            )
            self.conn.commit()
            return "inserted"

        new_depth = min(int(row["depth"]), int(depth))
        new_score = max(float(row["score"]), float(score))

        self.conn.execute(
            """
            UPDATE frontier
            SET domain=?,
                depth=?,
                score=?,
                source_url=?,
                anchor_text=?,
                status='pending'
            WHERE url=?
            """,
            (
                domain,
                new_depth,
                new_score,
                source_url,
                anchor,
                url,
            ),
        )
        self.conn.commit()
        return "requeued"

    def claim_next(self):
        cur = self.conn.cursor()

        cur.execute("""
        SELECT id, url
        FROM frontier
        WHERE status='pending'
        ORDER BY score DESC
        LIMIT 1
        """)
        row = cur.fetchone()

        if row is None:
            return None

        cur.execute("""
        UPDATE frontier
        SET status='in_progress'
        WHERE id=? AND status='pending'
        """, (row["id"],))

        if cur.rowcount == 0:
            return None

        self.conn.commit()

        cur.execute("SELECT * FROM frontier WHERE id=?", (row["id"],))
        claimed = cur.fetchone()
        return dict(claimed) if claimed else None

    def claim_batch(self, size=4):
        batch = []
        for _ in range(size):
            item = self.claim_next()
            if item is None:
                break
            batch.append(item)
        return batch

    def mark_visited(self, url):
        self.conn.execute(
            """
            UPDATE frontier
            SET status='visited', visited_at=?
            WHERE url=?
            """,
            (time.time(), url),
        )
        self.conn.commit()

    def mark_pdf(self, url):
        self.conn.execute(
            """
            UPDATE frontier
            SET status='pdf', visited_at=?
            WHERE url=?
            """,
            (time.time(), url),
        )
        self.conn.commit()

    def mark_error(self, url):
        self.conn.execute(
            """
            UPDATE frontier
            SET status='error', visited_at=?
            WHERE url=?
            """,
            (time.time(), url),
        )
        self.conn.commit()

    def count_pending(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM frontier WHERE status='pending'")
        return cur.fetchone()[0]

    def count_domain(self, domain):
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM frontier
            WHERE domain=? AND status='visited'
            """,
            (domain,),
        )
        return cur.fetchone()[0]

    def close(self):
        self.conn.close()
