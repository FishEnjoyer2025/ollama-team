import aiosqlite
import json
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "ollama_team.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id TEXT PRIMARY KEY,
    started_at DATETIME,
    completed_at DATETIME,
    status TEXT CHECK(status IN ('running', 'success', 'failed', 'rolled_back', 'abandoned')),
    proposal TEXT,
    branch_name TEXT,
    diff TEXT,
    test_output TEXT,
    deploy_log TEXT,
    rollback_reason TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL REFERENCES cycles(id),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    rating TEXT CHECK(rating IN ('up', 'down')),
    change_summary TEXT,
    files_changed TEXT,
    agent_prompts_version TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS agent_stats (
    agent_name TEXT PRIMARY KEY,
    total_invocations INTEGER DEFAULT 0,
    total_successes INTEGER DEFAULT 0,
    total_failures INTEGER DEFAULT 0,
    avg_duration_seconds REAL DEFAULT 0.0,
    last_invoked_at DATETIME
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "cycle_cooldown_seconds": "60",
    "max_retries_per_step": "3",
    "process_timeout_seconds": "600",
    "health_check_timeout_seconds": "60",
    "paused": "false",
    "stopped": "false",
}


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# --- Cycles ---

async def create_cycle(cycle_id: str, proposal: dict) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO cycles (id, started_at, status, proposal)
               VALUES (?, datetime('now'), 'running', ?)""",
            (cycle_id, json.dumps(proposal)),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,))
        row = await cursor.fetchone()
        return dict(row)


async def update_cycle(cycle_id: str, **kwargs) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [cycle_id]
        await db.execute(f"UPDATE cycles SET {sets} WHERE id = ?", vals)
        await db.commit()
        cursor = await db.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,))
        row = await cursor.fetchone()
        return dict(row)


async def complete_cycle(cycle_id: str, status: str, **kwargs):
    kwargs["status"] = status
    kwargs["completed_at"] = "datetime('now')"
    async with aiosqlite.connect(DB_PATH) as db:
        # Handle the datetime specially
        sets = []
        vals = []
        for k, v in kwargs.items():
            if v == "datetime('now')":
                sets.append(f"{k} = datetime('now')")
            else:
                sets.append(f"{k} = ?")
                vals.append(v)
        vals.append(cycle_id)
        await db.execute(f"UPDATE cycles SET {', '.join(sets)} WHERE id = ?", vals)
        await db.commit()


async def get_cycle(cycle_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_cycles(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM cycles"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# --- Feedback ---

async def add_feedback(cycle_id: str, rating: str, note: Optional[str] = None) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get cycle info for context
        cursor = await db.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,))
        cycle = await cursor.fetchone()
        change_summary = None
        files_changed = None
        if cycle:
            proposal = json.loads(cycle["proposal"]) if cycle["proposal"] else {}
            change_summary = proposal.get("description", "")
            files_changed = json.dumps(proposal.get("files", []))

        await db.execute(
            """INSERT INTO feedback (cycle_id, rating, change_summary, files_changed, note)
               VALUES (?, ?, ?, ?, ?)""",
            (cycle_id, rating, change_summary, files_changed, note),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM feedback WHERE cycle_id = ? ORDER BY id DESC LIMIT 1",
            (cycle_id,),
        )
        row = await cursor.fetchone()
        return dict(row)


async def get_feedback(cycle_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if cycle_id:
            cursor = await db.execute(
                "SELECT * FROM feedback WHERE cycle_id = ? ORDER BY timestamp DESC LIMIT ?",
                (cycle_id, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM feedback ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_feedback_summary() -> dict:
    """Get aggregate feedback stats for the Planner to reference."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT rating, COUNT(*) as count FROM feedback GROUP BY rating"
        )
        rows = await cursor.fetchall()
        counts = {row["rating"]: row["count"] for row in rows}

        # Recent thumbs-down with notes (most useful for improvement)
        cursor = await db.execute(
            """SELECT f.*, c.proposal FROM feedback f
               JOIN cycles c ON f.cycle_id = c.id
               WHERE f.rating = 'down' AND f.note IS NOT NULL
               ORDER BY f.timestamp DESC LIMIT 10"""
        )
        recent_downs = [dict(r) for r in await cursor.fetchall()]

        # Recent thumbs-up patterns
        cursor = await db.execute(
            """SELECT f.*, c.proposal FROM feedback f
               JOIN cycles c ON f.cycle_id = c.id
               WHERE f.rating = 'up'
               ORDER BY f.timestamp DESC LIMIT 10"""
        )
        recent_ups = [dict(r) for r in await cursor.fetchall()]

        return {
            "total_up": counts.get("up", 0),
            "total_down": counts.get("down", 0),
            "recent_negative_feedback": recent_downs,
            "recent_positive_feedback": recent_ups,
        }


# --- Settings ---

async def get_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}


async def update_settings(updates: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in updates.items():
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        await db.commit()


# --- Agent Stats ---

async def record_agent_invocation(agent_name: str, success: bool, duration: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO agent_stats (agent_name, total_invocations, total_successes, total_failures, avg_duration_seconds, last_invoked_at)
               VALUES (?, 1, ?, ?, ?, datetime('now'))
               ON CONFLICT(agent_name) DO UPDATE SET
                   total_invocations = total_invocations + 1,
                   total_successes = total_successes + ?,
                   total_failures = total_failures + ?,
                   avg_duration_seconds = (avg_duration_seconds * (total_invocations - 1) + ?) / total_invocations,
                   last_invoked_at = datetime('now')""",
            (
                agent_name,
                1 if success else 0,
                0 if success else 1,
                duration,
                1 if success else 0,
                0 if success else 1,
                duration,
            ),
        )
        await db.commit()


async def get_agent_stats(agent_name: Optional[str] = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if agent_name:
            cursor = await db.execute(
                "SELECT * FROM agent_stats WHERE agent_name = ?", (agent_name,)
            )
        else:
            cursor = await db.execute("SELECT * FROM agent_stats")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
