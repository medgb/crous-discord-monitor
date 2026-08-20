"""SQLite persistence layer and state transition detector."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.crous.models import Accommodation

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class Database:
    """SQLite Database manager for tracking accommodation availability snapshots."""

    def __init__(self, db_path: str = "data/crous_monitor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection with Row factory enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database tables and indices if they do not exist."""
        with self._get_connection() as conn:
            # Check if existing table needs migration to composite primary key
            cursor = conn.execute("PRAGMA table_info(accommodations)")
            rows = cursor.fetchall()
            if rows:
                columns = {row["name"]: row for row in rows}
                # Check if target_name is part of primary key
                pk_count = sum(1 for row in rows if row["pk"] > 0)
                if "target_name" not in columns or pk_count < 2:
                    logger.info("Migrating database schema to multi-target composite primary key...")
                    conn.execute("ALTER TABLE accommodations RENAME TO accommodations_old")
                    conn.execute("""
                        CREATE TABLE accommodations (
                            id INTEGER NOT NULL,
                            target_name TEXT NOT NULL DEFAULT 'default',
                            tool_id INTEGER NOT NULL,
                            residence_name TEXT NOT NULL,
                            accommodation_type TEXT NOT NULL,
                            city TEXT NOT NULL,
                            address TEXT,
                            price_eur REAL,
                            surface_min REAL,
                            surface_max REAL,
                            url TEXT NOT NULL,
                            currently_available INTEGER NOT NULL DEFAULT 1,
                            first_seen_at TEXT NOT NULL,
                            last_seen_at TEXT NOT NULL,
                            last_available_at TEXT,
                            raw_json TEXT,
                            PRIMARY KEY (id, target_name)
                        )
                    """)
                    conn.execute("""
                        INSERT OR IGNORE INTO accommodations (
                            id, target_name, tool_id, residence_name, accommodation_type, city,
                            address, price_eur, surface_min, surface_max, url,
                            currently_available, first_seen_at, last_seen_at, last_available_at, raw_json
                        )
                        SELECT id, 'default', tool_id, residence_name, accommodation_type, city,
                               address, price_eur, surface_min, surface_max, url,
                               currently_available, first_seen_at, last_seen_at, last_available_at, raw_json
                        FROM accommodations_old
                    """)
                    conn.execute("DROP TABLE accommodations_old")
            else:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS accommodations (
                        id INTEGER NOT NULL,
                        target_name TEXT NOT NULL DEFAULT 'default',
                        tool_id INTEGER NOT NULL,
                        residence_name TEXT NOT NULL,
                        accommodation_type TEXT NOT NULL,
                        city TEXT NOT NULL,
                        address TEXT,
                        price_eur REAL,
                        surface_min REAL,
                        surface_max REAL,
                        url TEXT NOT NULL,
                        currently_available INTEGER NOT NULL DEFAULT 1,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        last_available_at TEXT,
                        raw_json TEXT,
                        PRIMARY KEY (id, target_name)
                    )
                """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_accommodations_target_avail 
                ON accommodations (target_name, currently_available)
            """)
            conn.commit()
        logger.debug("Database initialized at %s", self.db_path)

    def is_empty(self, target_name: str = "default") -> bool:
        """Check whether the accommodations table contains any records for the target."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM accommodations WHERE target_name = ?", (target_name,))
            count = cursor.fetchone()[0]
            return count == 0

    def get_currently_available_count(self, target_name: str = "default") -> int:
        """Get the total number of currently available accommodations in DB for target."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM accommodations WHERE target_name = ? AND currently_available = 1",
                (target_name,)
            )
            return cursor.fetchone()[0]

    def get_accommodation(self, room_id: int, target_name: str = "default") -> Optional[dict]:
        """Fetch a single accommodation record by ID and target."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM accommodations WHERE id = ? AND target_name = ?", (room_id, target_name)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def sync_snapshot(
        self,
        current_items: List[Accommodation],
        target_name: str = "default",
        is_baseline: bool = False,
    ) -> Tuple[List[Accommodation], List[Accommodation], int]:
        """
        Synchronize a newly fetched snapshot with the SQLite database for a specific target.
        """
        now = utc_now_iso()
        current_map: Dict[int, Accommodation] = {item.id: item for item in current_items if item.available}
        newly_available: List[Accommodation] = []
        disappeared_items: List[Accommodation] = []
        maintained_count = 0

        with self._get_connection() as conn:
            # Fetch all existing records for this target
            cursor = conn.execute(
                "SELECT * FROM accommodations WHERE target_name = ?", (target_name,)
            )
            existing_rows = cursor.fetchall()
            existing_db_records: Dict[int, int] = {
                row["id"]: row["currently_available"] for row in existing_rows
            }
            existing_db_map: Dict[int, sqlite3.Row] = {
                row["id"]: row for row in existing_rows
            }

            # 1. Process current snapshot items
            for room_id, item in current_map.items():
                raw_json = json.dumps(item.raw_data, ensure_ascii=False)

                if room_id not in existing_db_records:
                    # Brand new room never seen before for this target
                    conn.execute("""
                        INSERT INTO accommodations (
                            id, target_name, tool_id, residence_name, accommodation_type, city,
                            address, price_eur, surface_min, surface_max, url,
                            currently_available, first_seen_at, last_seen_at, last_available_at, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """, (
                        item.id, target_name, item.tool_id, item.residence_name, item.accommodation_type, item.city,
                        item.address, item.price_eur, item.surface_min, item.surface_max, item.url,
                        now, now, now, raw_json
                    ))

                    if not is_baseline:
                        newly_available.append(item)
                        logger.info("STATE TRANSITION [%s]: [NEW ROOM] %s", target_name, item.summary())

                else:
                    was_available = bool(existing_db_records[room_id])
                    if not was_available:
                        # Room was unavailable and has now reappeared!
                        conn.execute("""
                            UPDATE accommodations SET
                                currently_available = 1,
                                last_seen_at = ?,
                                last_available_at = ?,
                                residence_name = ?,
                                accommodation_type = ?,
                                city = ?,
                                address = ?,
                                price_eur = ?,
                                surface_min = ?,
                                surface_max = ?,
                                url = ?,
                                raw_json = ?
                            WHERE id = ? AND target_name = ?
                        """, (
                            now, now, item.residence_name, item.accommodation_type, item.city,
                            item.address, item.price_eur, item.surface_min, item.surface_max, item.url,
                            raw_json, room_id, target_name
                        ))

                        if not is_baseline:
                            newly_available.append(item)
                            logger.info("STATE TRANSITION [%s]: [REAPPEARED ROOM] %s", target_name, item.summary())
                    else:
                        # Maintained available
                        maintained_count += 1
                        conn.execute("""
                            UPDATE accommodations SET
                                last_seen_at = ?,
                                price_eur = ?,
                                surface_min = ?,
                                surface_max = ?,
                                raw_json = ?
                            WHERE id = ? AND target_name = ?
                        """, (now, item.price_eur, item.surface_min, item.surface_max, raw_json, room_id, target_name))

            # 2. Detect disappeared rooms (were available in DB, but not in current snapshot)
            for room_id, was_available in existing_db_records.items():
                if was_available and room_id not in current_map:
                    row = existing_db_map[room_id]
                    disappeared_acc = Accommodation(
                        id=row["id"],
                        tool_id=row["tool_id"],
                        residence_name=row["residence_name"],
                        address=row["address"] or "",
                        city=row["city"] or "",
                        accommodation_type=row["accommodation_type"],
                        surface_min=row["surface_min"],
                        surface_max=row["surface_max"],
                        price_eur=row["price_eur"] or 0.0,
                        url=row["url"],
                        available=False,
                    )
                    disappeared_items.append(disappeared_acc)
                    conn.execute("""
                        UPDATE accommodations SET
                            currently_available = 0,
                            last_seen_at = ?
                        WHERE id = ? AND target_name = ?
                    """, (now, room_id, target_name))
                    logger.info("STATE TRANSITION [%s]: [DISAPPEARED ROOM] ID %d (%s) is no longer listed.", target_name, room_id, row["residence_name"])

            conn.commit()

        return newly_available, disappeared_items, maintained_count
