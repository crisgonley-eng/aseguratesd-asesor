# db.py — persistencia SQLite de leads y conversaciones.
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                text TEXT,
                creado_en TEXT
            )
            """
        )


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Conversaciones
# ---------------------------------------------------------------------------
def insertar_mensaje(session_id: str, role: str, text: str) -> None:
    init_db()
    creado_en = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO mensajes (session_id, role, text, creado_en) VALUES (?, ?, ?, ?)",
            (session_id, role, text, creado_en),
        )


def listar_conversaciones() -> list[dict]:
    """Devuelve una fila por sesión, con conteo y vista previa."""
    init_db()
    with _conn() as conn:
        filas = conn.execute(
            """
            SELECT session_id, COUNT(*) AS n_mensajes, MAX(creado_en) AS ultimo
            FROM mensajes
            GROUP BY session_id
            ORDER BY ultimo DESC
            """
        ).fetchall()
    resultado = []
    with _conn() as conn:
        for f in filas:
            primer = conn.execute(
                "SELECT text FROM mensajes WHERE session_id = ? AND role = 'user' ORDER BY id ASC LIMIT 1",
                (f["session_id"],),
            ).fetchone()
            resultado.append(
                {
                    "session_id": f["session_id"],
                    "n_mensajes": f["n_mensajes"],
                    "ultimo": f["ultimo"],
                    "preview": primer["text"] if primer else "",
                }
            )
    return resultado


def listar_mensajes(session_id: str) -> list[dict]:
    init_db()
    with _conn() as conn:
        filas = conn.execute(
            "SELECT role, text, creado_en FROM mensajes WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    return [dict(f) for f in filas]
