# db.py — persistencia SQLite de los leads.
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "leads.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                telefono TEXT,
                correo TEXT,
                ramo TEXT,
                detalles TEXT,
                origen TEXT,
                estado TEXT DEFAULT 'nuevo',
                creado_en TEXT
            )
            """
        )


def insertar_lead(
    nombre: str,
    telefono: str,
    correo: str,
    ramo: str,
    detalles: str,
    origen: str,
) -> int:
    init_db()
    creado_en = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO leads (nombre, telefono, correo, ramo, detalles, origen, estado, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, 'nuevo', ?)
            """,
            (nombre, telefono, correo, ramo, detalles, origen, creado_en),
        )
        return int(cur.lastrowid)


def listar_leads() -> list[dict]:
    init_db()
    with _conn() as conn:
        filas = conn.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    return [dict(f) for f in filas]


def actualizar_estado(lead_id: int, estado: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE leads SET estado = ? WHERE id = ?", (estado, lead_id)
        )
        return cur.rowcount > 0
