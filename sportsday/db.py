"""ตารางฐานข้อมูลของระบบกีฬาสี (SQLAlchemy Core)

ใช้ SQLite ในเครื่องเป็นค่าเริ่มต้น หรือกำหนด SPORTSDAY_DB_URL / secrets["db_url"]
เป็น PostgreSQL เมื่อเปิดใช้ออนไลน์ (ข้อมูลจะไม่หายเมื่อเซิร์ฟเวอร์รีสตาร์ต)
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

settings = Table(
    "settings",
    metadata,
    Column("key", String(50), primary_key=True),
    Column("value", Text, nullable=False, default=""),
)

colors = Table(
    "colors",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50), unique=True, nullable=False),
    Column("hex", String(9), nullable=False, default="#888888"),
)

students = Table(
    "students",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(20), nullable=False, default=""),
    Column("prefix", String(20), nullable=False, default=""),
    Column("first_name", String(100), nullable=False),
    Column("last_name", String(100), nullable=False, default=""),
    Column("gender", String(10), nullable=False),  # ชาย / หญิง
    Column("grade", Integer, nullable=False),  # 1-6
    Column("room", Integer, nullable=False, default=1),
    Column("color_id", Integer, ForeignKey("colors.id"), nullable=True),
    Column("note", Text, nullable=False, default=""),
    Column("shirt_size", String(10), nullable=False, default=""),
    Column("shirt_paid", Boolean, nullable=False, default=False),
    Column("active", Boolean, nullable=False, default=True),
)

roles = Table(
    "roles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), unique=True, nullable=False),
    Column("grp", String(20), nullable=False),  # admin / cheer
    Column("sort", Integer, nullable=False, default=0),
)

student_roles = Table(
    "student_roles",
    metadata,
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

sports = Table(
    "sports",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), unique=True, nullable=False),
)

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("sport_id", Integer, ForeignKey("sports.id"), nullable=False),
    Column("gender", String(10), nullable=False),  # ชาย / หญิง / ผสม
    Column("level", String(10), nullable=False),  # ต้น / ปลาย / รวม
    Column("detail", String(100), nullable=False, default=""),  # เช่น 100 ม.
    Column("date", Date, nullable=False),
    Column("start", String(5), nullable=False),  # HH:MM
    Column("duration_min", Integer, nullable=False, default=30),
    Column("venue", String(100), nullable=False, default=""),
    Column("cancelled", Boolean, nullable=False, default=False),
)

entries = Table(
    "entries",
    metadata,
    Column("event_id", Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    Column("color_id", Integer, ForeignKey("colors.id"), nullable=True),
)

results = Table(
    "results",
    metadata,
    Column("event_id", Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("winner_color_id", Integer, ForeignKey("colors.id"), nullable=False),
    Column("score", String(50), nullable=False, default=""),
    Column("note", Text, nullable=False, default=""),
    Column("recorded_by", String(100), nullable=False, default=""),
    Column("recorded_at", DateTime, nullable=False),
)

placings = Table(  # อันดับ 2-3 (อันดับ 1 อยู่ในตาราง results) ใช้เมื่อมีมากกว่า 2 สี
    "placings",
    metadata,
    Column("event_id", Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("color_id", Integer, ForeignKey("colors.id"), primary_key=True),
    Column("place", Integer, nullable=False),
)

awards = Table(  # รางวัลพิเศษ เช่น นักกีฬายอดเยี่ยมชาย/หญิง
    "awards",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(200), nullable=False),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
    Column("note", Text, nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
)

trophies = Table(
    "trophies",
    metadata,
    Column("event_id", Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("status", String(30), nullable=False, default="รอเตรียม"),
    Column("note", Text, nullable=False, default=""),
)

activities = Table(
    "activities",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), unique=True, nullable=False),  # เช่น เช็ครวมสี ซ้อมเชียร์
    Column("sort", Integer, nullable=False, default=0),
    Column("active", Boolean, nullable=False, default=True),
)

att_sessions = Table(
    "att_sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(200), nullable=False),
    Column("date", Date, nullable=False),
    Column("event_id", Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
    Column("color_id", Integer, ForeignKey("colors.id"), nullable=True),
    Column("activity_id", Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True),
)

attendance = Table(
    "attendance",
    metadata,
    Column("session_id", Integer, ForeignKey("att_sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    Column("status", String(10), nullable=False),  # มา / สาย / ลา / ขาด
    Column("note", Text, nullable=False, default=""),
)

color_moves = Table(
    "color_moves",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
    Column("from_color_id", Integer, ForeignKey("colors.id"), nullable=True),
    Column("to_color_id", Integer, ForeignKey("colors.id"), nullable=False),
    Column("reason", Text, nullable=False, default=""),
    Column("moved_by", String(100), nullable=False, default=""),
    Column("moved_at", DateTime, nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(50), unique=True, nullable=False),  # เก็บตัวพิมพ์เล็ก
    Column("display_name", String(100), nullable=False, default=""),
    Column("pw_hash", String(255), nullable=False),
    Column("role", String(20), nullable=False),  # admin / staff / color
    Column("color_id", Integer, ForeignKey("colors.id"), nullable=True),  # ใช้กับ role = color
    Column("perms", Text, nullable=False, default=""),  # คั่นด้วยจุลภาค ใช้กับ role = staff
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=True),
    Column("last_login", DateTime, nullable=True),
)


def schema_signature() -> tuple:
    """ชื่อตารางและคอลัมน์ทั้งหมด ใช้ตรวจว่าโครงสร้างฐานข้อมูลในโค้ดเปลี่ยนไปหรือไม่"""
    return tuple((t.name, tuple(c.name for c in t.columns)) for t in metadata.sorted_tables)


def local_db_path() -> Path:
    """ไฟล์ฐานข้อมูลในเครื่อง (ใช้เมื่อไม่ได้ตั้ง db_url)"""
    return Path(__file__).resolve().parent.parent / "data" / "sportsday.db"


def on_streamlit_cloud() -> bool:
    """Streamlit Community Cloud วางโค้ดไว้ที่ /mount/src · ไฟล์ในเครื่องที่นั่นหายเมื่อแอปเริ่มใหม่"""
    return Path("/mount/src").exists()


def default_url() -> str:
    url = os.environ.get("SPORTSDAY_DB_URL")
    if url:
        return url
    local_db_path().parent.mkdir(exist_ok=True)
    return f"sqlite:///{local_db_path()}"


def make_engine(url: str | None = None) -> Engine:
    url = url or default_url()
    if url.startswith("postgres://"):  # รูปแบบที่ผู้ให้บริการบางเจ้าให้มา
        url = "postgresql://" + url[len("postgres://"):]
    engine = create_engine(url, future=True, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine: Engine) -> None:
    """เพิ่มคอลัมน์ใหม่ให้ฐานข้อมูลเดิม (create_all สร้างแค่ตารางที่ยังไม่มี)"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    for table in metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have and col.nullable:
                ctype = col.type.compile(dialect=engine.dialect)
                with engine.begin() as c:
                    c.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ctype}'))
