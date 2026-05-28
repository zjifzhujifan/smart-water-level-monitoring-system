from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class LocalCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY,
                device_code TEXT,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS water_levels (
                id INTEGER PRIMARY KEY,
                device_id INTEGER,
                device_code TEXT,
                collect_time TEXT,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY,
                device_id INTEGER,
                alarm_time TEXT,
                is_resolved INTEGER,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS alarm_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                operator TEXT,
                remark TEXT,
                is_synced INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                payload TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def save_devices(self, devices: list[dict[str, Any]]) -> None:
        with self.conn:
            for device in devices:
                self.conn.execute(
                    """
                    INSERT INTO devices(id, device_code, payload, updated_at)
                    VALUES(?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        device_code=excluded.device_code,
                        payload=excluded.payload,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (device.get("id"), device.get("deviceCode"), json.dumps(device, ensure_ascii=False)),
                )

    def save_water_levels(self, records: list[dict[str, Any]]) -> None:
        with self.conn:
            for record in records:
                record_id = record.get("id")
                if record_id is None:
                    continue
                self.conn.execute(
                    """
                    INSERT INTO water_levels(id, device_id, device_code, collect_time, payload)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        device_id=excluded.device_id,
                        device_code=excluded.device_code,
                        collect_time=excluded.collect_time,
                        payload=excluded.payload
                    """,
                    (
                        record_id,
                        record.get("deviceId"),
                        record.get("deviceCode"),
                        record.get("collectTime"),
                        json.dumps(record, ensure_ascii=False),
                    ),
                )

    def save_alarms(self, alarms: list[dict[str, Any]]) -> None:
        with self.conn:
            for alarm in alarms:
                alarm_id = alarm.get("id")
                if alarm_id is None:
                    continue
                self.conn.execute(
                    """
                    INSERT INTO alarms(id, device_id, alarm_time, is_resolved, payload)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        device_id=excluded.device_id,
                        alarm_time=excluded.alarm_time,
                        is_resolved=excluded.is_resolved,
                        payload=excluded.payload
                    """,
                    (
                        alarm_id,
                        alarm.get("deviceId"),
                        alarm.get("alarmTime"),
                        alarm.get("isResolved"),
                        json.dumps(alarm, ensure_ascii=False),
                    ),
                )

    def get_devices(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT payload FROM devices ORDER BY id").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_water_levels(self, device_id: int | None = None, limit: int = 300) -> list[dict[str, Any]]:
        if device_id:
            rows = self.conn.execute(
                """
                SELECT payload FROM water_levels
                WHERE device_id=?
                ORDER BY collect_time DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT payload FROM water_levels ORDER BY collect_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_alarms(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload FROM alarms ORDER BY alarm_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def log(self, level: str, message: str) -> None:
        recent = self.conn.execute(
            "SELECT level, message FROM app_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if recent and recent["level"] == level.upper() and recent["message"] == message:
            return
        with self.conn:
            self.conn.execute(
                "INSERT INTO app_logs(level, message) VALUES(?, ?)",
                (level.upper(), message),
            )

    def logs(self, limit: int = 300, level: str | None = None) -> list[dict[str, Any]]:
        if level and level != "全部":
            rows = self.conn.execute(
                "SELECT level, message, created_at FROM app_logs WHERE level=? ORDER BY id DESC LIMIT ?",
                (level.upper(), limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT level, message, created_at FROM app_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_logs(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM app_logs")

    def save_alarm_action(
        self,
        alarm_id: int,
        action: str,
        operator: str = "",
        remark: str = "",
        is_synced: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO alarm_actions(alarm_id, action, operator, remark, is_synced, payload)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    alarm_id,
                    action,
                    operator,
                    remark,
                    is_synced,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )

    def pending_alarm_actions(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, alarm_id, action, operator, remark, is_synced, created_at, payload
            FROM alarm_actions
            WHERE is_synced=0
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except Exception:
                item["payload"] = {}
            items.append(item)
        return items

    def alarm_actions(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, alarm_id, action, operator, remark, is_synced, created_at, payload
            FROM alarm_actions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except Exception:
                item["payload"] = {}
            items.append(item)
        return items

    def mark_alarm_action_synced(self, action_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE alarm_actions SET is_synced=1 WHERE id=?", (action_id,))

    def clear_alarm_actions(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM alarm_actions")

    def table_counts(self) -> dict[str, int]:
        tables = ["devices", "water_levels", "alarms", "app_logs", "alarm_actions"]
        result: dict[str, int] = {}
        for table in tables:
            row = self.conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
            result[table] = int(row["total"] if row else 0)
        return result

    def database_size_bytes(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def cleanup_water_levels(self, keep: int = 1000) -> int:
        before = self.table_counts().get("water_levels", 0)
        with self.conn:
            self.conn.execute(
                """
                DELETE FROM water_levels
                WHERE id NOT IN (
                    SELECT id FROM water_levels ORDER BY collect_time DESC LIMIT ?
                )
                """,
                (keep,),
            )
        after = self.table_counts().get("water_levels", 0)
        return max(before - after, 0)

    def cleanup_logs(self, keep: int = 500) -> int:
        before = self.table_counts().get("app_logs", 0)
        with self.conn:
            self.conn.execute(
                """
                DELETE FROM app_logs
                WHERE id NOT IN (
                    SELECT id FROM app_logs ORDER BY id DESC LIMIT ?
                )
                """,
                (keep,),
            )
        after = self.table_counts().get("app_logs", 0)
        return max(before - after, 0)

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")
