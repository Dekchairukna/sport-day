"""กติกาหลักของระบบกีฬาสี: สิทธิ์ลงแข่ง, เวลาชน, นับถ้วย, ย้ายสี, เช็คชื่อ

ทุกฟังก์ชันรับ Engine เพื่อให้เทสต์ใช้ฐานข้อมูลชั่วคราวได้
"""
from __future__ import annotations

import copy
import csv
import functools
import hashlib
import hmac
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import and_, delete, event, func, insert, select, update
from sqlalchemy.engine import Engine

from . import db

# ---------------------------------------------------------------- แคชระหว่างการรันหนึ่งรอบ
# ฐานข้อมูลบนเว็บอยู่ไกล (ทุกคำสั่งใช้เวลาไปกลับ) จึงจำผลการอ่านไว้ใช้ซ้ำภายในการรันหน้าเดียวกัน
# แยกตามเธรด (หนึ่งผู้ใช้ = หนึ่งเธรด) · ล้างทุกครั้งที่เริ่มรันหน้าใหม่ และทุกครั้งที่มีการเขียนข้อมูล (commit)
_local = threading.local()


def clear_cache() -> None:
    _local.d = {}


def _watch(engine: Engine) -> None:
    if not getattr(engine, "_sd_watch", False):
        event.listen(engine, "commit", lambda conn: clear_cache())
        engine._sd_watch = True


def cached(fn):
    @functools.wraps(fn)
    def wrapper(engine, *args, **kwargs):
        _watch(engine)
        key = (fn.__name__, id(engine), args, tuple(sorted(kwargs.items())))
        d = getattr(_local, "d", None)
        if d is None:
            d = _local.d = {}
        if key not in d:
            d[key] = fn(engine, *args, **kwargs)
        v = d[key]
        return v.copy() if isinstance(v, pd.DataFrame) else copy.deepcopy(v)
    return wrapper

GRADES = [1, 2, 3, 4, 5, 6]
GENDERS = ["ชาย", "หญิง"]
EVENT_GENDERS = ["ชาย", "หญิง", "ผสม"]
LEVELS = {"ต้น": "ม.ต้น", "ปลาย": "ม.ปลาย", "รวม": "รวม"}
ATT_STATUSES = ["มา", "สาย", "ลา", "ขาด"]
DEFAULT_ACTIVITIES = ["เช็ครวมสี", "ซ้อมเชียร์", "ซ้อมขบวนพาเหรด", "ซ้อมกีฬา", "ก่อนแข่งขัน", "ประชุมสี"]
# รอบประจำวันช่วงก่อนแข่ง (แก้ได้ที่ ตั้งค่า → กิจกรรมเช็คชื่อ)
DEFAULT_DAILY_ROUNDS = [
    {"slot": "เช้า", "activity": "ประชุมสี"},
    {"slot": "สาย", "activity": "ซ้อมเชียร์"},
    {"slot": "บ่าย", "activity": "ซ้อมเชียร์"},
]
TROPHY_STATUSES = ["รอเตรียม", "ติดสติ๊กเกอร์แล้ว", "ส่งครูฟ้าแล้ว"]
ROLE_GROUPS = {"admin": "ฝ่ายบริหาร / สต๊าฟ", "cheer": "กองเชียร์"}

DEFAULT_COLORS = [("น้ำเงิน", "#1f4fd1"), ("ชมพู", "#e0559b")]
DEFAULT_ROLES = {
    "admin": ["ประธานสี", "รองประธานสี", "เลขานุการ", "เหรัญญิก", "สต๊าฟ", "ฝ่ายพยาบาล"],
    "cheer": ["ลีดเดอร์ (หรีด)", "ขึ้นสแตนด์", "ผู้นำเชียร์", "ดรัมเมเยอร์", "คทากร", "ขบวนพาเหรด"],
}
DEFAULT_SETTINGS = {
    "event_title": "กีฬาสีภายใน ปีการศึกษา 2569",
    "school_name": "โรงเรียนเปรมติณสูลานนท์",
}
SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


# ---------------------------------------------------------------- เบ็ดเตล็ด

def grade_label(grade: int, room: int | None = None) -> str:
    return f"ม.{grade}" + (f"/{room}" if room is not None else "")


def level_of_grade(grade: int) -> str:
    return "ต้น" if grade <= 3 else "ปลาย"


def event_label(gender: str, level: str, detail: str = "") -> str:
    """เช่น 'ชาย ม.ต้น', 'หญิงรวม', 'ชาย ม.ปลาย 100 ม.'"""
    lv = "รวม" if level == "รวม" else LEVELS[level]
    label = f"{gender}{lv}" if level == "รวม" else f"{gender} {lv}"
    return f"{label} {detail}".strip()


def event_name(sport: str, gender: str, level: str, detail: str = "") -> str:
    return f"{sport} {event_label(gender, level, detail)}"


def is_eligible(student_gender: str, student_grade: int, event_gender: str, event_level: str) -> bool:
    if event_gender != "ผสม" and student_gender != event_gender:
        return False
    if event_level == "รวม":
        return True
    return level_of_grade(student_grade) == event_level


def event_window(d: date, start: str, duration_min: int) -> tuple[datetime, datetime]:
    h, m = (int(x) for x in start.split(":"))
    begin = datetime(d.year, d.month, d.day, h, m)
    return begin, begin + timedelta(minutes=int(duration_min))


def overlaps(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def valid_hhmm(text: str) -> bool:
    try:
        h, m = text.split(":")
        return len(h) == 2 and len(m) == 2 and 0 <= int(h) < 24 and 0 <= int(m) < 60
    except ValueError:
        return False


# ---------------------------------------------------------------- ตั้งค่าเริ่มต้น

def seed_defaults(engine: Engine, schedule_csv: Path | None = None) -> None:
    """ใส่สี หน้าที่ ค่าตั้งต้น และตารางแข่ง (ครั้งแรกเท่านั้น)"""
    with engine.begin() as c:
        if not c.execute(select(func.count()).select_from(db.colors)).scalar():
            c.execute(insert(db.colors), [{"name": n, "hex": h} for n, h in DEFAULT_COLORS])
        if not c.execute(select(func.count()).select_from(db.roles)).scalar():
            rows = [
                {"name": n, "grp": g, "sort": i}
                for g, names in DEFAULT_ROLES.items()
                for i, n in enumerate(names)
            ]
            c.execute(insert(db.roles), rows)
        if not c.execute(select(func.count()).select_from(db.activities)).scalar():
            c.execute(insert(db.activities), [{"name": n, "sort": i, "active": True}
                                              for i, n in enumerate(DEFAULT_ACTIVITIES)])
        have = {r.key for r in c.execute(select(db.settings.c.key))}
        for k, v in DEFAULT_SETTINGS.items():
            if k not in have:
                c.execute(insert(db.settings).values(key=k, value=v))
    _tag_old_sessions(engine)
    if count_events(engine) == 0:
        path = schedule_csv or SEED_DIR / "schedule.csv"
        if path.exists():
            import_schedule(engine, path)


@cached
def _all_settings(engine: Engine) -> dict:
    with engine.connect() as c:
        return {r.key: r.value for r in c.execute(select(db.settings))}


def get_setting(engine: Engine, key: str) -> str:
    v = _all_settings(engine).get(key)
    return v if v is not None else DEFAULT_SETTINGS.get(key, "")


def set_setting(engine: Engine, key: str, value: str) -> None:
    with engine.begin() as c:
        if c.execute(select(db.settings.c.key).where(db.settings.c.key == key)).first():
            c.execute(update(db.settings).where(db.settings.c.key == key).values(value=value))
        else:
            c.execute(insert(db.settings).values(key=key, value=value))


# ---------------------------------------------------------------- ผู้ใช้และสิทธิ์

ROLES = {
    "admin": "ผู้ดูแลระบบ",
    "staff": "ครู/กรรมการ",
    "color": "สต๊าฟสี",
}
# สิทธิ์ที่เลือกให้ครู/กรรมการได้ทีละข้อ (ผู้ดูแลระบบได้ทุกข้อ + จัดการผู้ใช้)
PERMS = {
    "results": "บันทึกผลการแข่งขัน",
    "schedule": "จัดตารางแข่งและนักกีฬา",
    "attendance": "เช็คชื่อ",
    "trophies": "ถ้วยรางวัล",
    "members": "ดูและแก้ข้อมูลสมาชิก (รวม Excel ที่มีรายชื่อ)",
    "colors": "จัดการหน้าสีได้ทุกสี",
    "move_color": "ย้ายสี",
    "settings": "ตั้งค่าระบบ",
    "certificates": "เกียรติบัตรและนักกีฬายอดเยี่ยม",
}
DEFAULT_STAFF_PERMS = ["results", "schedule", "attendance", "trophies", "members", "colors"]
# สิทธิ์ที่เปิดให้สต๊าฟสีได้ (เช็คชื่อเฉพาะสมาชิกในสีตัวเอง)
COLOR_PERMS = {
    "results": "บันทึกผลการแข่งขัน (แก้/ลบได้เฉพาะผลที่ตัวเองบันทึก)",
    "attendance": "เช็คชื่อสมาชิกในสี",
}
DEFAULT_COLOR_PERMS = ["results", "attendance"]
MIN_PASSWORD = 6
_PBKDF2_ROUNDS = 200_000


def _hash_pin(pin: str) -> str:
    """แฮชแบบเก่าของ PIN สี (ใช้ตรวจบัญชีที่ย้ายมาจาก PIN เดิมเท่านั้น)"""
    return hashlib.sha256(("sportsday:" + pin.strip()).encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        _, rounds, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(dk.hex(), digest)
    if stored.startswith("sha256$"):
        return hmac.compare_digest(_hash_pin(password), stored.split("$", 1)[1])
    return False


def _norm_username(username: str) -> str:
    return username.strip().lower()


def _clean_perms(role: str, perms: Iterable[str] | None) -> str:
    allowed = PERMS if role == "staff" else COLOR_PERMS if role == "color" else {}
    return ",".join(p for p in allowed if p in set(perms or []))


def user_perms(user: dict | None) -> set[str]:
    """ชุดสิทธิ์ของผู้ใช้ · ผู้ดูแลระบบได้ทุกข้อรวม "users" """
    if not user:
        return set()
    if user["role"] == "admin":
        return set(PERMS) | {"users"}
    allowed = PERMS if user["role"] == "staff" else COLOR_PERMS if user["role"] == "color" else {}
    return {p for p in (user.get("perms") or "").split(",") if p in allowed}


def _validate_user(c, username: str, role: str, color_id: int | None, user_id: int | None = None) -> None:
    if role not in ROLES:
        raise ValueError("บทบาทไม่ถูกต้อง")
    if not (3 <= len(username) <= 50) or any(ch.isspace() for ch in username):
        raise ValueError("ชื่อผู้ใช้ต้องยาว 3–50 ตัวอักษร และไม่มีช่องว่าง")
    q = select(db.users.c.id).where(db.users.c.username == username)
    if user_id is not None:
        q = q.where(db.users.c.id != user_id)
    if c.execute(q).first():
        raise ValueError(f"มีชื่อผู้ใช้ {username} อยู่แล้ว")
    if role == "color" and color_id is None:
        raise ValueError("สต๊าฟสีต้องเลือกสี")


def _check_password_rule(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"รหัสผ่านต้องยาวอย่างน้อย {MIN_PASSWORD} ตัว")


@cached
def users_df(engine: Engine) -> pd.DataFrame:
    q = (select(db.users.c.id, db.users.c.username, db.users.c.display_name, db.users.c.role,
                db.users.c.color_id, db.colors.c.name.label("color"), db.colors.c.hex.label("color_hex"),
                db.users.c.perms, db.users.c.active, db.users.c.created_at, db.users.c.last_login)
         .select_from(db.users.outerjoin(db.colors, db.users.c.color_id == db.colors.c.id))
         .order_by(db.users.c.role, db.users.c.username))
    with engine.connect() as c:
        return pd.DataFrame(c.execute(q).mappings().all(),
                            columns=["id", "username", "display_name", "role", "color_id", "color", "color_hex",
                                     "perms", "active", "created_at", "last_login"])


@cached
def get_user(engine: Engine, user_id: int) -> dict | None:
    with engine.connect() as c:
        r = c.execute(select(db.users).where(db.users.c.id == user_id)).mappings().first()
    return dict(r) if r else None


def create_user(engine: Engine, username: str, password: str, role: str, display_name: str = "",
                color_id: int | None = None, perms: Iterable[str] | None = None) -> int:
    username = _norm_username(username)
    _check_password_rule(password)
    if perms is None:
        perms = DEFAULT_STAFF_PERMS if role == "staff" else DEFAULT_COLOR_PERMS
    with engine.begin() as c:
        _validate_user(c, username, role, color_id)
        return c.execute(insert(db.users).values(
            username=username, display_name=display_name.strip() or username, pw_hash=hash_password(password),
            role=role, color_id=color_id if role == "color" else None, perms=_clean_perms(role, perms),
            active=True, created_at=datetime.now(),
        )).inserted_primary_key[0]


def _active_admins(c, exclude_id: int | None = None) -> int:
    q = select(func.count()).select_from(db.users).where(db.users.c.role == "admin", db.users.c.active.is_(True))
    if exclude_id is not None:
        q = q.where(db.users.c.id != exclude_id)
    return c.execute(q).scalar()


def update_user(engine: Engine, user_id: int, *, username: str, display_name: str, role: str,
                color_id: int | None, perms: Iterable[str] | None, active: bool) -> None:
    username = _norm_username(username)
    with engine.begin() as c:
        _validate_user(c, username, role, color_id, user_id)
        if (role != "admin" or not active) and _active_admins(c, exclude_id=user_id) == 0:
            raise ValueError("ต้องมีผู้ดูแลระบบที่ใช้งานอยู่อย่างน้อย 1 คน")
        c.execute(update(db.users).where(db.users.c.id == user_id).values(
            username=username, display_name=display_name.strip() or username, role=role,
            color_id=color_id if role == "color" else None, perms=_clean_perms(role, perms), active=active,
        ))


def set_password(engine: Engine, user_id: int, password: str) -> None:
    _check_password_rule(password)
    with engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == user_id).values(pw_hash=hash_password(password)))


def delete_user(engine: Engine, user_id: int) -> None:
    with engine.begin() as c:
        if _active_admins(c, exclude_id=user_id) == 0:
            raise ValueError("ลบไม่ได้ ต้องมีผู้ดูแลระบบที่ใช้งานอยู่อย่างน้อย 1 คน")
        c.execute(delete(db.users).where(db.users.c.id == user_id))


def authenticate(engine: Engine, username: str, password: str) -> dict | None:
    """คืนข้อมูลผู้ใช้ถ้าชื่อและรหัสผ่านถูกและบัญชียังใช้งานอยู่ แล้วบันทึกเวลาเข้าล่าสุด"""
    username = _norm_username(username)
    if not username or not password:
        return None
    with engine.begin() as c:
        r = c.execute(select(db.users).where(db.users.c.username == username)).mappings().first()
        if not r or not r["active"] or not verify_password(password, r["pw_hash"]):
            return None
        upd = {"last_login": datetime.now()}
        if r["pw_hash"].startswith("sha256$"):  # อัปเกรดแฮชเก่าเป็นแบบใหม่ตอนเข้าสู่ระบบ
            upd["pw_hash"] = hash_password(password)
        c.execute(update(db.users).where(db.users.c.id == r["id"]).values(**upd))
    return dict(r)


def seed_users(engine: Engine, admin_password: str) -> None:
    """ครั้งแรกที่ยังไม่มีผู้ใช้: สร้างบัญชี admin (รหัสผ่าน = PIN ครูเดิม)
    และย้าย PIN ของแต่ละสีมาเป็นบัญชี color<id> (รหัสผ่าน = PIN สีเดิม)"""
    with engine.begin() as c:
        if c.execute(select(func.count()).select_from(db.users)).scalar():
            return
        now = datetime.now()
        c.execute(insert(db.users).values(
            username="admin", display_name="ผู้ดูแลระบบ", pw_hash=hash_password(admin_password),
            role="admin", perms="", active=True, created_at=now))
        names = {r.id: r.name for r in c.execute(select(db.colors))}
        for r in c.execute(select(db.settings).where(db.settings.c.key.like("pin_color_%"))).all():
            cid = int(r.key.rsplit("_", 1)[1])
            if r.value and cid in names:
                c.execute(insert(db.users).values(
                    username=f"color{cid}", display_name=f"สต๊าฟสี{names[cid]}", pw_hash="sha256$" + r.value,
                    role="color", color_id=cid, perms=",".join(DEFAULT_COLOR_PERMS), active=True, created_at=now))
    migrate_color_perms(engine)


def migrate_color_perms(engine: Engine) -> None:
    """ครั้งเดียว: สต๊าฟสีที่สร้างก่อนมีสิทธิ์บันทึกผล/เช็คชื่อ ได้สิทธิ์ทั้งสองข้อ"""
    if get_setting(engine, "color_perms_v2"):
        return
    with engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.role == "color", db.users.c.perms == "")
                  .values(perms=",".join(DEFAULT_COLOR_PERMS)))
    set_setting(engine, "color_perms_v2", "1")


# ---------------------------------------------------------------- สี

@cached
def list_colors(engine: Engine) -> pd.DataFrame:
    with engine.connect() as c:
        return pd.read_sql(select(db.colors).order_by(db.colors.c.id), c)


def add_color(engine: Engine, name: str, hex_: str) -> int:
    with engine.begin() as c:
        return c.execute(insert(db.colors).values(name=name.strip(), hex=hex_)).inserted_primary_key[0]


def color_id_by_name(engine: Engine, name: str) -> int | None:
    with engine.connect() as c:
        return c.execute(select(db.colors.c.id).where(db.colors.c.name == name)).scalar()


# ---------------------------------------------------------------- สมาชิก

@cached
def students_df(engine: Engine, include_inactive: bool = False) -> pd.DataFrame:
    s, col = db.students, db.colors
    q = (
        select(
            s.c.id, s.c.code, s.c.prefix, s.c.first_name, s.c.last_name, s.c.gender,
            s.c.grade, s.c.room, s.c.color_id, col.c.name.label("color"), col.c.hex.label("color_hex"),
            s.c.note, s.c.shirt_size, s.c.shirt_paid, s.c.active,
        )
        .select_from(s.outerjoin(col, s.c.color_id == col.c.id))
        .order_by(s.c.grade, s.c.room, s.c.id)
    )
    if not include_inactive:
        q = q.where(s.c.active.is_(True))
    with engine.connect() as c:
        df = pd.read_sql(q, c)
        roles = pd.read_sql(
            select(db.student_roles.c.student_id, db.roles.c.name, db.roles.c.sort, db.roles.c.grp)
            .select_from(db.student_roles.join(db.roles))
            .order_by(db.roles.c.grp, db.roles.c.sort),
            c,
        )
        ent = pd.read_sql(
            select(db.entries.c.student_id, db.entries.c.event_id), c
        )
    for col in ("shirt_paid", "active"):  # ตารางว่างทำให้ pandas เดาชนิดผิด ต้องกำหนดเป็น bool ชัด ๆ
        df[col] = df[col].fillna(False).astype(bool)
    df["full_name"] = df["prefix"] + df["first_name"] + " " + df["last_name"]
    df["class"] = "ม." + df["grade"].astype(str) + "/" + df["room"].astype(str)
    role_map = roles.groupby("student_id")["name"].apply(list).to_dict()
    df["roles"] = df["id"].map(lambda i: role_map.get(i, []))
    ev_map = ent.groupby("student_id")["event_id"].apply(list).to_dict()
    df["event_ids"] = df["id"].map(lambda i: ev_map.get(i, []))
    df["color"] = df["color"].fillna("ยังไม่ระบุ")
    return df


def add_student(engine: Engine, **fields) -> int:
    with engine.begin() as c:
        return c.execute(insert(db.students).values(**fields)).inserted_primary_key[0]


def update_student(engine: Engine, student_id: int, **fields) -> None:
    with engine.begin() as c:
        c.execute(update(db.students).where(db.students.c.id == student_id).values(**fields))


def set_student_roles(engine: Engine, student_id: int, role_ids: Iterable[int]) -> None:
    with engine.begin() as c:
        c.execute(delete(db.student_roles).where(db.student_roles.c.student_id == student_id))
        rows = [{"student_id": student_id, "role_id": r} for r in set(role_ids)]
        if rows:
            c.execute(insert(db.student_roles), rows)


def set_student_events(engine: Engine, student_id: int, event_ids: Iterable[int]) -> list[str]:
    """กำหนดรายการแข่งของนักเรียน คืนรายการที่ข้ามเพราะไม่ตรงรุ่น"""
    skipped: list[str] = []
    with engine.begin() as c:
        st = c.execute(select(db.students).where(db.students.c.id == student_id)).one()
        evs = {e.id: e for e in c.execute(event_query().where(db.events.c.id.in_(list(event_ids) or [-1])))}
        ok = []
        for eid, e in evs.items():
            if is_eligible(st.gender, st.grade, e.gender, e.level):
                ok.append(eid)
            else:
                skipped.append(event_name(e.sport, e.gender, e.level, e.detail))
        current = {r.event_id for r in c.execute(select(db.entries.c.event_id).where(db.entries.c.student_id == student_id))}
        to_remove = current - set(ok)
        to_add = set(ok) - current
        if to_remove:
            c.execute(delete(db.entries).where(and_(db.entries.c.student_id == student_id, db.entries.c.event_id.in_(to_remove))))
        if to_add:
            c.execute(insert(db.entries), [{"event_id": e, "student_id": student_id, "color_id": st.color_id} for e in to_add])
    return skipped


def import_members_csv(engine: Engine, rows: Iterable[dict]) -> dict:
    """นำเข้าจากไฟล์รูปแบบ members_all.csv อัปเดตถ้าเลขประจำตัวซ้ำ"""
    stats = {"added": 0, "updated": 0, "skipped": 0}
    color_cache: dict[str, int | None] = {}

    def color_for(name: str) -> int | None:
        name = (name or "").strip()
        if not name or name == "ยังไม่ระบุ":
            return None
        if name not in color_cache:
            cid = color_id_by_name(engine, name)
            if cid is None:
                cid = add_color(engine, name, "#888888")
            color_cache[name] = cid
        return color_cache[name]

    with engine.connect() as c:
        by_code = {r.code.lstrip("0"): r.id for r in c.execute(select(db.students.c.id, db.students.c.code)) if r.code}
    for r in rows:
        try:
            grade = int(str(r.get("ชั้น", "")).replace("ม.", "").strip())
            first = (r.get("ชื่อ") or "").strip()
            if not first or grade not in GRADES:
                raise ValueError
        except ValueError:
            stats["skipped"] += 1
            continue
        prefix = (r.get("คำนำหน้า") or "").strip()
        gender = (r.get("เพศ") or "").strip() or ("หญิง" if prefix in ("เด็กหญิง", "นางสาว", "นาง") else "ชาย")
        fields = {
            "code": (r.get("เลขประจำตัว") or "").strip(),
            "prefix": prefix,
            "first_name": first,
            "last_name": (r.get("นามสกุล") or "").strip(),
            "gender": gender,
            "grade": grade,
            "room": int(r.get("ห้อง") or 1),
            "color_id": color_for(r.get("สี", "")),
            "note": "; ".join(x for x in [(r.get("หมายเหตุ") or "").strip(), (r.get("ควรตรวจทาน") or "").strip()] if x),
            "shirt_size": (r.get("ไซซ์เสื้อ") or "").strip(),
            "shirt_paid": (r.get("ค่าเสื้อ") or "").strip() == "จ่ายแล้ว",
        }
        sid = by_code.get(fields["code"].lstrip("0")) if fields["code"] else None
        if sid:
            update_student(engine, sid, **fields)
            stats["updated"] += 1
        else:
            new_id = add_student(engine, **fields)
            if fields["code"]:
                by_code[fields["code"].lstrip("0")] = new_id
            stats["added"] += 1
    return stats


# ---------------------------------------------------------------- หน้าที่

@cached
def roles_df(engine: Engine) -> pd.DataFrame:
    with engine.connect() as c:
        return pd.read_sql(select(db.roles).order_by(db.roles.c.grp, db.roles.c.sort, db.roles.c.id), c)


def add_role(engine: Engine, name: str, grp: str) -> int:
    with engine.begin() as c:
        n = c.execute(select(func.count()).select_from(db.roles).where(db.roles.c.grp == grp)).scalar()
        return c.execute(insert(db.roles).values(name=name.strip(), grp=grp, sort=n)).inserted_primary_key[0]


# ---------------------------------------------------------------- กีฬาและรายการแข่ง

def event_query():
    e, sp = db.events, db.sports
    return select(
        e.c.id, sp.c.name.label("sport"), e.c.sport_id, e.c.gender, e.c.level, e.c.detail,
        e.c.date, e.c.start, e.c.duration_min, e.c.venue, e.c.cancelled,
    ).select_from(e.join(sp, e.c.sport_id == sp.c.id))


def count_events(engine: Engine) -> int:
    with engine.connect() as c:
        return c.execute(select(func.count()).select_from(db.events)).scalar()


def sport_id(engine: Engine, name: str) -> int:
    name = name.strip()
    with engine.begin() as c:
        sid = c.execute(select(db.sports.c.id).where(db.sports.c.name == name)).scalar()
        if sid is None:
            sid = c.execute(insert(db.sports).values(name=name)).inserted_primary_key[0]
        return sid


def add_event(engine: Engine, sport: str, gender: str, level: str, d: date, start: str,
              duration_min: int, venue: str = "", detail: str = "") -> int:
    if gender not in EVENT_GENDERS or level not in LEVELS:
        raise ValueError("เพศหรือระดับไม่ถูกต้อง")
    if not valid_hhmm(start):
        raise ValueError("เวลาเริ่มต้องเป็นรูปแบบ ชช:นน เช่น 09:00")
    sid = sport_id(engine, sport)
    with engine.begin() as c:
        eid = c.execute(
            insert(db.events).values(
                sport_id=sid, gender=gender, level=level, detail=detail.strip(), date=d,
                start=start, duration_min=int(duration_min), venue=venue.strip(),
            )
        ).inserted_primary_key[0]
        c.execute(insert(db.trophies).values(event_id=eid))
    return eid


def update_event(engine: Engine, event_id: int, **fields) -> None:
    if "start" in fields and not valid_hhmm(fields["start"]):
        raise ValueError("เวลาเริ่มต้องเป็นรูปแบบ ชช:นน เช่น 09:00")
    if "sport" in fields:
        fields["sport_id"] = sport_id(engine, fields.pop("sport"))
    with engine.begin() as c:
        c.execute(update(db.events).where(db.events.c.id == event_id).values(**fields))


def delete_event(engine: Engine, event_id: int) -> None:
    with engine.begin() as c:
        c.execute(delete(db.events).where(db.events.c.id == event_id))


def import_schedule(engine: Engine, path: Path) -> int:
    n = 0
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            add_event(
                engine, r["ชนิดกีฬา"], r["เพศ"], r["ระดับ"],
                date.fromisoformat(r["วันที่"]), r["เริ่ม"], int(r["นาที"]),
                r.get("สนาม", ""), r.get("รายละเอียด", ""),
            )
            n += 1
    return n


@cached
def events_df(engine: Engine, include_cancelled: bool = True) -> pd.DataFrame:
    """รายการแข่งทั้งหมด พร้อมผล ถ้วย และจำนวนนักกีฬาแต่ละสี"""
    with engine.connect() as c:
        df = pd.read_sql(event_query().order_by(db.events.c.date, db.events.c.start, db.events.c.id), c)
        res = pd.read_sql(
            select(db.results.c.event_id, db.colors.c.name.label("winner"), db.colors.c.hex.label("winner_hex"),
                   db.results.c.winner_color_id, db.results.c.score, db.results.c.note.label("result_note"),
                   db.results.c.recorded_by, db.results.c.recorded_at)
            .select_from(db.results.join(db.colors, db.results.c.winner_color_id == db.colors.c.id)),
            c,
        )
        tro = pd.read_sql(select(db.trophies.c.event_id, db.trophies.c.status.label("trophy_status"), db.trophies.c.note.label("trophy_note")), c)
        cnt = pd.read_sql(
            select(db.entries.c.event_id, func.count().label("n")).group_by(db.entries.c.event_id), c
        )
    df["cancelled"] = df["cancelled"].fillna(False).astype(bool)
    if df.empty:
        for col in ["name", "label", "winner", "winner_hex", "winner_color_id", "score", "result_note", "recorded_by",
                    "recorded_at", "trophy_status", "trophy_note", "athletes", "end", "status"]:
            df[col] = []
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.merge(res, left_on="id", right_on="event_id", how="left").drop(columns="event_id")
    df = df.merge(tro, left_on="id", right_on="event_id", how="left").drop(columns="event_id")
    df = df.merge(cnt, left_on="id", right_on="event_id", how="left").drop(columns="event_id")
    df["athletes"] = pd.to_numeric(df["n"], errors="coerce").fillna(0).astype(int)
    df = df.drop(columns="n")
    df["trophy_status"] = df["trophy_status"].fillna("รอเตรียม")
    df["label"] = [event_label(g, l, d) for g, l, d in zip(df.gender, df.level, df.detail)]
    df["name"] = df["sport"] + " " + df["label"]
    df["end"] = [event_window(d, s, m)[1].strftime("%H:%M") for d, s, m in zip(df.date, df.start, df.duration_min)]
    df["status"] = [
        "ยกเลิก" if cx else ("จบแล้ว" if isinstance(w, str) else "รอแข่ง")
        for cx, w in zip(df.cancelled, df.winner)
    ]
    if not include_cancelled:
        df = df[~df.cancelled]
    return df.reset_index(drop=True)


@cached
def entries_df(engine: Engine, event_id: int | None = None) -> pd.DataFrame:
    s, en, col = db.students, db.entries, db.colors
    q = (
        select(en.c.event_id, s.c.id.label("student_id"), s.c.prefix, s.c.first_name, s.c.last_name,
               s.c.grade, s.c.room, s.c.gender, col.c.name.label("color"))
        .select_from(en.join(s, en.c.student_id == s.c.id).outerjoin(col, en.c.color_id == col.c.id))
        .order_by(col.c.name, s.c.grade, s.c.room, s.c.first_name)
    )
    if event_id is not None:
        q = q.where(en.c.event_id == event_id)
    with engine.connect() as c:
        df = pd.read_sql(q, c)
    df["full_name"] = df["prefix"] + df["first_name"] + " " + df["last_name"]
    df["class"] = "ม." + df["grade"].astype(str) + "/" + df["room"].astype(str)
    df["color"] = df["color"].fillna("ยังไม่ระบุ")
    return df


def set_event_entries(engine: Engine, event_id: int, student_ids: Iterable[int]) -> list[str]:
    """กำหนดนักกีฬาของรายการ (ข้ามคนที่ไม่ตรงรุ่น) คืนชื่อคนที่ถูกข้าม"""
    skipped = []
    with engine.begin() as c:
        e = c.execute(event_query().where(db.events.c.id == event_id)).one()
        studs = c.execute(select(db.students).where(db.students.c.id.in_(list(student_ids) or [-1]))).all()
        c.execute(delete(db.entries).where(db.entries.c.event_id == event_id))
        rows = []
        for s in studs:
            if is_eligible(s.gender, s.grade, e.gender, e.level):
                rows.append({"event_id": event_id, "student_id": s.id, "color_id": s.color_id})
            else:
                skipped.append(f"{s.first_name} {s.last_name}")
        if rows:
            c.execute(insert(db.entries), rows)
    return skipped


@dataclass
class Conflict:
    student_id: int
    student: str
    klass: str
    color: str
    event_a: str
    event_b: str
    when: str


def find_conflicts(engine: Engine) -> list[Conflict]:
    """นักกีฬาที่ลงสองรายการซึ่งเวลาซ้อนกัน (ไม่นับรายการที่ยกเลิก)"""
    ev = events_df(engine, include_cancelled=False)
    if ev.empty:
        return []
    win = {r.id: event_window(r.date, r.start, r.duration_min) for r in ev.itertuples()}
    names = dict(zip(ev.id, ev.name))
    ent = entries_df(engine)
    ent = ent[ent.event_id.isin(win)]
    out: list[Conflict] = []
    for sid, grp in ent.groupby("student_id"):
        ids = sorted(grp.event_id.unique(), key=lambda i: win[i][0])
        row = grp.iloc[0]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if overlaps(win[a], win[b]):
                    w = win[a][0]
                    out.append(Conflict(int(sid), row.full_name, row["class"], row.color, names[a], names[b],
                                        f"{w:%d/%m} {win[a][0]:%H:%M}-{win[a][1]:%H:%M} กับ {win[b][0]:%H:%M}-{win[b][1]:%H:%M}"))
    return out


def color_todo(engine: Engine, color_id: int) -> dict:
    """สิ่งที่สต๊าฟสีต้องตามงาน"""
    colors = list_colors(engine).set_index("id")
    cname = colors.loc[color_id, "name"]
    ev = events_df(engine, include_cancelled=False)
    pending = ev[ev.winner.isna()]
    ent = entries_df(engine)
    mine = ent[ent.color == cname]
    have = mine.groupby("event_id").size()
    no_athletes = pending[~pending.id.isin(have.index)]
    st_ = students_df(engine)
    st_ = st_[st_.color_id == color_id]
    roles = roles_df(engine)
    filled = {r for rs in st_.roles for r in rs}
    return {
        "color": cname,
        "members": len(st_),
        "events_without_athletes": no_athletes["name"].tolist(),
        "athlete_counts": {int(k): int(v) for k, v in have.items()},
        "conflicts": [c for c in find_conflicts(engine) if c.color == cname],
        "unpaid": st_[~st_.shirt_paid][["id", "full_name", "class"]].reset_index(drop=True),
        "roles_empty": [r for r in roles["name"] if r not in filled],
        "no_role_no_event": int(((st_.roles.map(len) == 0) & (st_.event_ids.map(len) == 0)).sum()),
    }


# ---------------------------------------------------------------- ผลการแข่งขัน

def set_result(engine: Engine, event_id: int, winner_color_id: int, score: str = "", note: str = "",
               recorded_by: str = "") -> None:
    row = {"winner_color_id": winner_color_id, "score": score.strip(), "note": note.strip(),
           "recorded_by": recorded_by.strip(), "recorded_at": datetime.now()}
    with engine.begin() as c:
        if c.execute(select(db.results.c.event_id).where(db.results.c.event_id == event_id)).first():
            c.execute(update(db.results).where(db.results.c.event_id == event_id).values(**row))
        else:
            c.execute(insert(db.results).values(event_id=event_id, **row))


def clear_result(engine: Engine, event_id: int) -> None:
    with engine.begin() as c:
        c.execute(delete(db.placings).where(db.placings.c.event_id == event_id))
        c.execute(delete(db.results).where(db.results.c.event_id == event_id))


@cached
def standings(engine: Engine) -> pd.DataFrame:
    """จำนวนถ้วยของแต่ละสี เรียงมากไปน้อย"""
    cols = list_colors(engine)
    ev = events_df(engine, include_cancelled=False)
    wins = ev.dropna(subset=["winner"]).groupby("winner_color_id").size() if not ev.empty else pd.Series(dtype=int)
    cols["trophies"] = cols["id"].map(wins).fillna(0).astype(int)
    by_sport = (
        ev.dropna(subset=["winner"]).groupby(["winner_color_id", "sport"]).size().unstack(fill_value=0)
        if not ev.empty and ev["winner"].notna().any() else pd.DataFrame()
    )
    cols["by_sport"] = cols["id"].map(lambda i: by_sport.loc[i].to_dict() if i in by_sport.index else {})
    return cols.sort_values(["trophies", "id"], ascending=[False, True]).reset_index(drop=True)


def progress(engine: Engine) -> dict:
    ev = events_df(engine, include_cancelled=False)
    done = int(ev["winner"].notna().sum()) if not ev.empty else 0
    return {"total": len(ev), "done": done, "left": len(ev) - done}


# ---------------------------------------------------------------- ถ้วยรางวัล

def set_trophy(engine: Engine, event_id: int, status: str, note: str = "") -> None:
    if status not in TROPHY_STATUSES:
        raise ValueError(status)
    with engine.begin() as c:
        if c.execute(select(db.trophies.c.event_id).where(db.trophies.c.event_id == event_id)).first():
            c.execute(update(db.trophies).where(db.trophies.c.event_id == event_id).values(status=status, note=note))
        else:
            c.execute(insert(db.trophies).values(event_id=event_id, status=status, note=note))


# ---------------------------------------------------------------- ย้ายสี

def pending_entries(engine: Engine, student_id: int) -> pd.DataFrame:
    ev = events_df(engine)
    ent = entries_df(engine)
    mine = ent[ent.student_id == student_id][["event_id", "color"]]
    out = mine.merge(ev, left_on="event_id", right_on="id")
    return out[out.status == "รอแข่ง"]


def move_color(engine: Engine, student_id: int, to_color_id: int, reason: str = "", moved_by: str = "",
               remove_pending_entries: bool = True) -> list[str]:
    """ย้ายสี + เก็บประวัติ; ถอดออกจากรายการที่ยังไม่แข่งของสีเดิม (ผลที่จบแล้วไม่เปลี่ยน)"""
    removed: list[str] = []
    pend = pending_entries(engine, student_id)
    with engine.begin() as c:
        cur = c.execute(select(db.students.c.color_id).where(db.students.c.id == student_id)).scalar()
        if cur == to_color_id:
            return removed
        c.execute(update(db.students).where(db.students.c.id == student_id).values(color_id=to_color_id))
        c.execute(insert(db.color_moves).values(
            student_id=student_id, from_color_id=cur, to_color_id=to_color_id,
            reason=reason.strip(), moved_by=moved_by.strip(), moved_at=datetime.now(),
        ))
        c.execute(delete(db.stand_seats).where(db.stand_seats.c.student_id == student_id))  # ที่นั่งสแตนด์สีเดิม
        if remove_pending_entries and not pend.empty:
            c.execute(delete(db.entries).where(and_(
                db.entries.c.student_id == student_id, db.entries.c.event_id.in_(pend.event_id.tolist()))))
            removed = pend["name"].tolist()
    return removed


def color_moves_df(engine: Engine) -> pd.DataFrame:
    m, s = db.color_moves, db.students
    fc, tc = db.colors.alias("fc"), db.colors.alias("tc")
    q = (
        select(m.c.moved_at, s.c.prefix, s.c.first_name, s.c.last_name, s.c.grade, s.c.room,
               fc.c.name.label("from_color"), tc.c.name.label("to_color"), m.c.reason, m.c.moved_by)
        .select_from(m.join(s, m.c.student_id == s.c.id)
                     .outerjoin(fc, m.c.from_color_id == fc.c.id)
                     .join(tc, m.c.to_color_id == tc.c.id))
        .order_by(m.c.moved_at.desc())
    )
    with engine.connect() as c:
        df = pd.read_sql(q, c)
    df["from_color"] = df["from_color"].fillna("ยังไม่ระบุ")
    return df


# ---------------------------------------------------------------- เช็คชื่อ

# ---------------------------------------------------------------- กิจกรรมเช็คชื่อ

@cached
def activities_df(engine: Engine, include_inactive: bool = False) -> pd.DataFrame:
    q = select(db.activities).order_by(db.activities.c.sort, db.activities.c.id)
    if not include_inactive:
        q = q.where(db.activities.c.active.is_(True))
    with engine.connect() as c:
        df = pd.read_sql(q, c)
        used = pd.read_sql(select(db.att_sessions.c.activity_id, func.count().label("rounds"))
                           .group_by(db.att_sessions.c.activity_id), c)
    df = df.merge(used, left_on="id", right_on="activity_id", how="left").drop(columns="activity_id")
    df["rounds"] = pd.to_numeric(df["rounds"], errors="coerce").fillna(0).astype(int)
    return df


def add_activity(engine: Engine, name: str) -> int:
    """เพิ่มกิจกรรม ถ้ามีชื่อนี้อยู่แล้ว (แม้ถูกซ่อน) จะเปิดใช้และคืน id เดิม"""
    name = " ".join(name.split())
    if not name:
        raise ValueError("ใส่ชื่อกิจกรรมก่อน")
    with engine.begin() as c:
        r = c.execute(select(db.activities.c.id).where(db.activities.c.name == name)).first()
        if r:
            c.execute(update(db.activities).where(db.activities.c.id == r.id).values(active=True))
            return int(r.id)
        nxt = (c.execute(select(func.max(db.activities.c.sort))).scalar() or 0) + 1
        return c.execute(insert(db.activities).values(name=name, sort=nxt, active=True)).inserted_primary_key[0]


def update_activity(engine: Engine, activity_id: int, name: str, active: bool) -> None:
    name = " ".join(name.split())
    if not name:
        raise ValueError("ชื่อกิจกรรมว่างไม่ได้")
    with engine.begin() as c:
        if c.execute(select(db.activities.c.id).where(db.activities.c.name == name,
                                                      db.activities.c.id != activity_id)).first():
            raise ValueError(f"มีกิจกรรม {name} อยู่แล้ว")
        c.execute(update(db.activities).where(db.activities.c.id == activity_id).values(name=name, active=active))


def delete_activity(engine: Engine, activity_id: int) -> None:
    with engine.begin() as c:
        used = c.execute(select(func.count()).select_from(db.att_sessions)
                         .where(db.att_sessions.c.activity_id == activity_id)).scalar()
        if used:
            raise ValueError(f"กิจกรรมนี้มีรอบเช็คชื่อ {used} รอบ ลบไม่ได้ ให้ซ่อนแทน")
        c.execute(delete(db.activities).where(db.activities.c.id == activity_id))


def _tag_old_sessions(engine: Engine) -> None:
    """รอบเช็คชื่อที่สร้างก่อนมีกิจกรรม: ตามรายการแข่ง = ก่อนแข่งขัน, ทั้งสี = เช็ครวมสี"""
    with engine.begin() as c:
        ids = {r.name: r.id for r in c.execute(select(db.activities))}
        s = db.att_sessions.c
        if "ก่อนแข่งขัน" in ids:
            c.execute(update(db.att_sessions).where(s.activity_id.is_(None), s.event_id.is_not(None))
                      .values(activity_id=ids["ก่อนแข่งขัน"]))
        if "เช็ครวมสี" in ids:
            c.execute(update(db.att_sessions).where(s.activity_id.is_(None), s.event_id.is_(None), s.role_id.is_(None))
                      .values(activity_id=ids["เช็ครวมสี"]))


def create_session(engine: Engine, title: str, d: date, event_id: int | None = None,
                   role_id: int | None = None, color_id: int | None = None,
                   activity_id: int | None = None) -> int:
    with engine.begin() as c:
        return c.execute(insert(db.att_sessions).values(
            title=title.strip(), date=d, event_id=event_id, role_id=role_id, color_id=color_id,
            activity_id=activity_id,
        )).inserted_primary_key[0]


@cached
def sessions_df(engine: Engine) -> pd.DataFrame:
    s = db.att_sessions
    q = (select(s, db.activities.c.name.label("activity"))
         .select_from(s.outerjoin(db.activities, s.c.activity_id == db.activities.c.id))
         .order_by(s.c.date.desc(), s.c.id))
    with engine.connect() as c:
        df = pd.read_sql(q, c)
    df["activity"] = df["activity"].fillna("ไม่ระบุกิจกรรม")
    df["day"] = pd.to_datetime(df["date"]).dt.date
    return df


def delete_session(engine: Engine, session_id: int) -> None:
    with engine.begin() as c:
        c.execute(delete(db.att_sessions).where(db.att_sessions.c.id == session_id))


def session_roster(engine: Engine, session_id: int) -> pd.DataFrame:
    """รายชื่อที่ต้องเช็คในรอบนี้ พร้อมสถานะที่บันทึกไว้"""
    with engine.connect() as c:
        ses = c.execute(select(db.att_sessions).where(db.att_sessions.c.id == session_id)).one()
        saved = pd.read_sql(select(db.attendance).where(db.attendance.c.session_id == session_id), c)
    st = students_df(engine)
    if ses.event_id:
        ids = set(entries_df(engine, ses.event_id).student_id)
        st = st[st.id.isin(ids)]
    if ses.role_id:
        rname = roles_df(engine).set_index("id").loc[ses.role_id, "name"]
        st = st[st.roles.map(lambda rs: rname in rs)]
    if ses.color_id:
        st = st[st.color_id == ses.color_id]
    st = st[["id", "full_name", "class", "color"]].rename(columns={"id": "student_id"})
    st = st.merge(saved[["student_id", "status", "note"]], on="student_id", how="left")
    st["status"] = st["status"].fillna("")
    st["note"] = st["note"].fillna("")
    return st.reset_index(drop=True)


def _log(c, session_id: int, changes: list[tuple[int, str, str]], by: str) -> None:
    """บันทึกประวัติ (student_id, เดิม, ใหม่) เฉพาะที่เปลี่ยนจริง"""
    now = datetime.now()
    rows = [{"session_id": session_id, "student_id": int(sid), "old_status": old or "", "new_status": new or "",
             "by_name": (by or "")[:100], "at": now} for sid, old, new in changes if (old or "") != (new or "")]
    if rows:
        c.execute(insert(db.attendance_log), rows)


def _current_status(c, session_id: int) -> dict[int, str]:
    a = db.attendance.c
    return {r.student_id: r.status for r in c.execute(select(a.student_id, a.status).where(a.session_id == session_id))}


def save_attendance(engine: Engine, session_id: int, rows: Iterable[dict], by: str = "") -> int:
    n = 0
    with engine.begin() as c:
        before = _current_status(c, session_id)
        changes = []
        for r in rows:
            sid = int(r["student_id"])
            c.execute(delete(db.attendance).where(and_(db.attendance.c.session_id == session_id,
                                                       db.attendance.c.student_id == sid)))
            new = r.get("status") if r.get("status") in ATT_STATUSES else ""
            if new:
                c.execute(insert(db.attendance).values(session_id=session_id, student_id=sid,
                                                       status=new, note=(r.get("note") or "").strip()))
                n += 1
            changes.append((sid, before.get(sid, ""), new))
        _log(c, session_id, changes, by)
    return n


def _attendance_rows(engine: Engine, activity_id: int | None = None) -> pd.DataFrame:
    s = db.att_sessions
    q = (select(db.attendance, s.c.activity_id, s.c.color_id.label("session_color"))
         .select_from(db.attendance.join(s, db.attendance.c.session_id == s.c.id)))
    if activity_id is not None:
        q = q.where(s.c.activity_id == activity_id)
    with engine.connect() as c:
        return pd.read_sql(q, c)


def set_attendance_one(engine: Engine, session_id: int, student_id: int, status: str | None, by: str = "") -> None:
    """บันทึกสถานะของนักเรียนคนเดียว (กดปุ่มบนมือถือแล้วบันทึกทันที) · status ว่าง = ยกเลิกการเช็ค
    หมายเหตุเดิมยังเก็บไว้ · เก็บประวัติการเปลี่ยน"""
    a = db.attendance.c
    where = and_(a.session_id == session_id, a.student_id == student_id)
    with engine.begin() as c:
        old = c.execute(select(a.status, a.note).where(where)).first()
        c.execute(delete(db.attendance).where(where))
        new = status if status in ATT_STATUSES else ""
        if new:
            c.execute(insert(db.attendance).values(session_id=session_id, student_id=student_id,
                                                   status=new, note=(old.note if old else "") or ""))
        _log(c, session_id, [(student_id, old.status if old else "", new)], by)


def mark_unchecked(engine: Engine, session_id: int, student_ids: Iterable[int], status: str = "มา", by: str = "") -> int:
    """ใส่สถานะให้คนที่ยังไม่ได้เช็คในรายชื่อที่ส่งมา (ไม่ทับคนที่เช็คแล้ว)"""
    a = db.attendance.c
    with engine.begin() as c:
        done = {r[0] for r in c.execute(select(a.student_id).where(a.session_id == session_id))}
        rows = [{"session_id": session_id, "student_id": int(i), "status": status, "note": ""}
                for i in student_ids if int(i) not in done]
        if rows:
            c.execute(insert(db.attendance), rows)
        _log(c, session_id, [(r["student_id"], "", status) for r in rows], by)
    return len(rows)


def move_attendance(engine: Engine, src: int, dst: int, overwrite: bool = True, delete_src: bool = False,
                    by: str = "") -> int:
    """ย้ายผลเช็คชื่อจากรอบ src ไปรอบ dst (เช่น เด็กกรอกผิดรอบ)
    overwrite=True: ทับคนที่รอบปลายทางเช็คแล้ว · False: ใส่เฉพาะคนที่ปลายทางยังว่าง · delete_src: ลบรอบต้นทางทิ้ง"""
    if src == dst:
        raise ValueError("เลือกรอบปลายทางที่ไม่ใช่รอบเดิม")
    a = db.attendance.c
    with engine.begin() as c:
        rows = c.execute(select(db.attendance).where(a.session_id == src)).mappings().all()
        before = {r.student_id: r for r in c.execute(select(db.attendance).where(a.session_id == dst))}
        moved, changes = 0, []
        for r in rows:
            sid = r["student_id"]
            if sid in before and not overwrite:
                continue
            c.execute(delete(db.attendance).where(and_(a.session_id == dst, a.student_id == sid)))
            c.execute(insert(db.attendance).values(session_id=dst, student_id=sid, status=r["status"],
                                                   note=r["note"] or ""))
            changes.append((sid, before[sid].status if sid in before else "", r["status"]))
            moved += 1
        _log(c, dst, changes, by or "ย้ายจากรอบอื่น")
        if delete_src:
            c.execute(delete(db.att_sessions).where(db.att_sessions.c.id == src))
    return moved


def attendance_history(engine: Engine, session_id: int) -> pd.DataFrame:
    """ประวัติการเปลี่ยนผลเช็คชื่อของรอบ ล่าสุดก่อน"""
    with engine.connect() as c:
        log = pd.read_sql(select(db.attendance_log).where(db.attendance_log.c.session_id == session_id)
                          .order_by(db.attendance_log.c.id.desc()), c)
    st = students_df(engine, include_inactive=True)[["id", "full_name", "class"]]
    return log.merge(st, left_on="student_id", right_on="id", how="left", suffixes=("", "_s"))


def round_compare(engine: Engine, other: Engine, other_sid: int, sid: int) -> dict:
    """เทียบผลเช็คชื่อรอบ other_sid (ในอีกฐานข้อมูล เช่น ไฟล์เดิม) กับรอบ sid ตอนนี้"""
    a = db.attendance.c
    with other.connect() as c:
        theirs = {r.student_id: r.status for r in c.execute(select(a.student_id, a.status).where(a.session_id == other_sid))}
    with engine.connect() as c:
        mine = _current_status(c, sid)
    differ = sum(1 for k in set(theirs) | set(mine) if theirs.get(k, "") != mine.get(k, ""))
    return {"in_file": len(theirs), "now": len(mine), "differ": differ}


def restore_round(engine: Engine, other: Engine, other_sid: int, sid: int, by: str = "") -> int:
    """แทนที่ผลเช็คชื่อรอบ sid ด้วยผลของรอบ other_sid จากอีกฐานข้อมูล (เช่น ไฟล์เดิมบนเซิร์ฟเวอร์)"""
    a = db.attendance.c
    with other.connect() as c:
        rows = c.execute(select(db.attendance).where(a.session_id == other_sid)).mappings().all()
    with engine.begin() as c:
        exists = {r[0] for r in c.execute(select(db.students.c.id))}
        before = _current_status(c, sid)
        c.execute(delete(db.attendance).where(a.session_id == sid))
        keep = [r for r in rows if r["student_id"] in exists]
        if keep:
            c.execute(insert(db.attendance), [{"session_id": sid, "student_id": r["student_id"], "status": r["status"],
                                               "note": r["note"] or ""} for r in keep])
        after = {r["student_id"]: r["status"] for r in keep}
        _log(c, sid, [(k, before.get(k, ""), after.get(k, "")) for k in set(before) | set(after)],
             by or "กู้จากไฟล์เดิม")
    return len(keep)


def get_daily_rounds(engine: Engine) -> list[dict]:
    raw = get_setting(engine, "daily_rounds")
    try:
        rows = json.loads(raw) if raw else DEFAULT_DAILY_ROUNDS
    except ValueError:
        rows = DEFAULT_DAILY_ROUNDS
    return [{"slot": str(r["slot"]).strip(), "activity": str(r["activity"]).strip()}
            for r in rows if str(r.get("slot", "")).strip() and str(r.get("activity", "")).strip()]


def set_daily_rounds(engine: Engine, rows: Iterable[dict]) -> list[dict]:
    clean = [{"slot": str(r.get("slot") or "").strip(), "activity": str(r.get("activity") or "").strip()}
             for r in rows]
    clean = [r for r in clean if r["slot"] and r["activity"]]
    if not clean:
        raise ValueError("ต้องมีอย่างน้อย 1 รอบ")
    if len({r["slot"] for r in clean}) != len(clean):
        raise ValueError("ชื่อช่วงเวลาซ้ำกัน")
    set_setting(engine, "daily_rounds", json.dumps(clean, ensure_ascii=False))
    return clean


def create_daily_rounds(engine: Engine, start: date, end: date, color_ids: Iterable[int]) -> tuple[int, int]:
    """สร้างรอบประจำวัน (ทั้งสี) ทุกวันตั้งแต่ start ถึง end ให้แต่ละสี · รอบที่มีอยู่แล้วจะข้าม
    คืน (สร้างใหม่, ข้าม)"""
    if end < start:
        start, end = end, start
    if (end - start).days > 60:
        raise ValueError("สร้างได้ครั้งละไม่เกิน 60 วัน")
    rounds = get_daily_rounds(engine)
    names = list_colors(engine).set_index("id")["name"].to_dict()
    act_ids = {r["activity"]: add_activity(engine, r["activity"]) for r in rounds}
    s = db.att_sessions.c
    made = skipped = 0
    with engine.begin() as c:
        d = start
        while d <= end:
            for cid in color_ids:
                for r in rounds:
                    title = f"{r['slot']} (สี{names.get(cid, '')})"
                    if c.execute(select(s.id).where(s.date == d, s.color_id == cid, s.title == title)).first():
                        skipped += 1
                        continue
                    c.execute(insert(db.att_sessions).values(title=title, date=d, color_id=cid,
                                                             activity_id=act_ids[r["activity"]]))
                    made += 1
            d += timedelta(days=1)
    return made, skipped


def attendance_summary(engine: Engine, activity_id: int | None = None) -> pd.DataFrame:
    """สรุปรายคน: มา/สาย/ลา/ขาด และร้อยละการมา (นับ สาย เป็นมา) · เลือกเฉพาะกิจกรรมได้"""
    att = _attendance_rows(engine, activity_id)
    if att.empty:
        return pd.DataFrame(columns=["student_id", "full_name", "class", "color", *ATT_STATUSES, "รวม", "ร้อยละมา"])
    piv = att[["student_id", "status"]].pivot_table(index="student_id", columns="status", aggfunc="size", fill_value=0)
    for s in ATT_STATUSES:
        if s not in piv:
            piv[s] = 0
    piv = piv[ATT_STATUSES]
    piv["รวม"] = piv.sum(axis=1)
    piv["ร้อยละมา"] = ((piv["มา"] + piv["สาย"]) / piv["รวม"] * 100).round(0).astype(int)
    st = students_df(engine, include_inactive=True)[["id", "full_name", "class", "color"]]
    out = st.merge(piv, left_on="id", right_index=True).rename(columns={"id": "student_id"})
    return out.sort_values(["ร้อยละมา", "ขาด"], ascending=[True, False]).reset_index(drop=True)


def activity_overview(engine: Engine, color_id: int | None = None) -> pd.DataFrame:
    """สรุปแยกกิจกรรม: จำนวนรอบ จำนวนครั้งที่เช็ค และร้อยละการมา"""
    ses = sessions_df(engine)
    if color_id is not None:
        ses = ses[ses.color_id == color_id]
    att = _attendance_rows(engine)
    att = att[att.session_id.isin(ses.id)]
    rows = []
    for name, g in ses.groupby("activity", sort=False):
        a = att[att.session_id.isin(g.id)]
        came = int(a.status.isin(["มา", "สาย"]).sum())
        rows.append({"กิจกรรม": name, "จำนวนรอบ": len(g), "เช็คแล้ว (คน-ครั้ง)": len(a),
                     "ขาด": int((a.status == "ขาด").sum()),
                     "ร้อยละมา": round(came / len(a) * 100) if len(a) else 0})
    return pd.DataFrame(rows, columns=["กิจกรรม", "จำนวนรอบ", "เช็คแล้ว (คน-ครั้ง)", "ขาด", "ร้อยละมา"])


# ---------------------------------------------------------------- เหรียญ อันดับ และรางวัลพิเศษ

MEDALS = {1: "ทอง", 2: "เงิน", 3: "ทองแดง"}
PLACE_TEXT = {1: "ชนะเลิศ", 2: "รองชนะเลิศอันดับ 1", 3: "รองชนะเลิศอันดับ 2"}
# นักกีฬายอดเยี่ยม: ระบบคำนวณเองจากจำนวนเหรียญรวม แยกชาย/หญิง
BEST_TITLES = {"ชาย": "นักกีฬายอดเยี่ยมชาย", "หญิง": "นักกีฬายอดเยี่ยมหญิง"}
# รางวัลพิเศษอื่นที่กรรมการเลือกเอง
AWARD_TITLES = ["นักกีฬาดาวรุ่ง", "นักกีฬาน้ำใจนักกีฬา", "ผู้ฝึกสอนดีเด่น"]


def set_places(engine: Engine, event_id: int, places: dict[int, int]) -> None:
    """ตั้งอันดับ 2-3 ของรายการ {color_id: place} (อันดับ 1 ใช้ set_result)"""
    with engine.begin() as c:
        c.execute(delete(db.placings).where(db.placings.c.event_id == event_id))
        rows = [{"event_id": event_id, "color_id": int(cid), "place": int(p)}
                for cid, p in places.items() if p in (2, 3)]
        if rows:
            c.execute(insert(db.placings), rows)


@cached
def event_places(engine: Engine) -> pd.DataFrame:
    """อันดับของแต่ละสีในแต่ละรายการที่มีผลแล้ว: event_id, color_id, place
    อันดับ 1 = สีที่ได้ถ้วย · อันดับ 2-3 ตามที่บันทึก · ถ้ามี 2 สี สีที่แพ้ได้อันดับ 2 อัตโนมัติ"""
    with engine.connect() as c:
        res = pd.read_sql(select(db.results.c.event_id, db.results.c.winner_color_id), c)
        pl = pd.read_sql(select(db.placings), c)
        ev = pd.read_sql(select(db.events.c.id).where(db.events.c.cancelled.is_(False)), c)
    color_ids = list_colors(engine)["id"].tolist()
    res = res[res.event_id.isin(ev.id)]
    rows = []
    for r in res.itertuples():
        rows.append((r.event_id, r.winner_color_id, 1))
        mine = pl[(pl.event_id == r.event_id) & (pl.color_id != r.winner_color_id)]
        if not mine.empty:
            rows += [(r.event_id, p.color_id, p.place) for p in mine.itertuples()]
        elif len(color_ids) == 2:
            rows += [(r.event_id, cid, 2) for cid in color_ids if cid != r.winner_color_id]
    return pd.DataFrame(rows, columns=["event_id", "color_id", "place"]).astype(int)


def medal_table(engine: Engine) -> pd.DataFrame:
    """ตารางเหรียญรายสี เรียงแบบโอลิมปิก (ทอง > เงิน > ทองแดง)"""
    cols = list_colors(engine)
    pl = event_places(engine)
    out = cols[["id", "name", "hex"]].copy()
    for p, m in MEDALS.items():
        out[m] = out["id"].map(pl[pl.place == p].groupby("color_id").size()).fillna(0).astype(int)
    out["รวม"] = out[list(MEDALS.values())].sum(axis=1)
    out = out.sort_values(["ทอง", "เงิน", "ทองแดง", "name"], ascending=[False, False, False, True]).reset_index(drop=True)
    out.insert(0, "อันดับ", range(1, len(out) + 1))
    return out


def medal_by_sport(engine: Engine) -> pd.DataFrame:
    ev = events_df(engine, include_cancelled=False)[["id", "sport"]]
    pl = event_places(engine).merge(ev, left_on="event_id", right_on="id")
    names = list_colors(engine).set_index("id")["name"]
    rows = []
    for sport in dict.fromkeys(ev["sport"]):
        g = pl[pl.sport == sport]
        row = {"ชนิดกีฬา": sport}
        for cid, cname in names.items():
            mine = g[g.color_id == cid]
            row[f"สี{cname}"] = " ".join(f"{m} {int((mine.place == p).sum())}"
                                        for p, m in MEDALS.items() if (mine.place == p).any()) or "-"
        rows.append(row)
    return pd.DataFrame(rows)


@cached
def athlete_results(engine: Engine) -> pd.DataFrame:
    """ผลรายนักกีฬารายรายการ: นักกีฬา + รายการ + สีที่ลงแข่ง + อันดับ (ว่าง = เข้าร่วม/ยังไม่มีผล)"""
    en = entries_df(engine)
    if en.empty:
        return pd.DataFrame(columns=["event_id", "student_id", "full_name", "class", "gender", "grade", "color",
                                     "color_id", "event", "sport", "label", "date", "place"])
    with engine.connect() as c:
        ec = pd.read_sql(select(db.entries.c.event_id, db.entries.c.student_id, db.entries.c.color_id), c)
    en = en.merge(ec, on=["event_id", "student_id"])
    ev = events_df(engine, include_cancelled=False)[["id", "name", "sport", "label", "date", "winner"]]
    df = en.merge(ev, left_on="event_id", right_on="id").drop(columns="id").rename(columns={"name": "event"})
    pl = event_places(engine)
    df = df.merge(pl, on=["event_id", "color_id"], how="left")
    df["done"] = df["winner"].notna()
    return df


@cached
def athlete_leaderboard(engine: Engine) -> pd.DataFrame:
    """จัดอันดับนักกีฬา: เหรียญรวมมากสุด > ทอง > เงิน > ทองแดง > จำนวนรายการที่ลง"""
    ar = athlete_results(engine)
    cols = ["student_id", "full_name", "class", "gender", "grade", "color", "รวมเหรียญ", "ทอง", "เงิน", "ทองแดง",
            "รายการที่ลง", "รายการที่ชนะ"]
    if ar.empty:
        return pd.DataFrame(columns=cols)
    g = ar.groupby("student_id")
    out = g[["full_name", "class", "gender", "grade", "color"]].first()
    for p, m in MEDALS.items():
        out[m] = g["place"].apply(lambda s, p=p: int((s == p).sum()))
    out["รวมเหรียญ"] = out["ทอง"] + out["เงิน"] + out["ทองแดง"]
    out["รายการที่ลง"] = g.size()
    out["รายการที่ชนะ"] = g.apply(lambda d: ", ".join(d.loc[d.place == 1, "event"]), include_groups=False)
    out = out.reset_index().sort_values(["รวมเหรียญ", "ทอง", "เงิน", "ทองแดง", "รายการที่ลง", "full_name"],
                                        ascending=[False, False, False, False, False, True])
    return out[cols].reset_index(drop=True)


def best_athletes(engine: Engine) -> pd.DataFrame:
    """นักกีฬายอดเยี่ยมชาย/หญิง = เหรียญรวมมากที่สุดของแต่ละเพศ
    เท่ากันตัดสินด้วย ทอง > เงิน > ทองแดง · ถ้ายังเท่ากันทุกอย่าง ได้รางวัลร่วม"""
    lb = athlete_leaderboard(engine)
    key = ["รวมเหรียญ", "ทอง", "เงิน", "ทองแดง"]
    rows = []
    for gender, title in BEST_TITLES.items():
        g = lb[(lb.gender == gender) & (lb["รวมเหรียญ"] > 0)]
        if g.empty:
            continue
        top = tuple(g.iloc[0][key])
        win = g[g[key].apply(tuple, axis=1) == top].copy()
        win.insert(0, "title", title)
        win["tie"] = len(win) > 1
        rows.append(win)
    cols = ["title"] + list(lb.columns) + ["tie"]
    return pd.concat(rows, ignore_index=True)[cols] if rows else pd.DataFrame(columns=cols)


@cached
def awards_df(engine: Engine) -> pd.DataFrame:
    with engine.connect() as c:
        a = pd.read_sql(select(db.awards).order_by(db.awards.c.id), c)
    st = students_df(engine, include_inactive=True)[["id", "full_name", "class", "color"]]
    return a.merge(st, left_on="student_id", right_on="id", how="left", suffixes=("", "_s")).drop(columns="id_s")


def add_award(engine: Engine, title: str, student_id: int, note: str = "") -> int:
    title = " ".join(title.split())
    if not title:
        raise ValueError("ใส่ชื่อรางวัลก่อน")
    with engine.begin() as c:
        if c.execute(select(db.awards.c.id).where(db.awards.c.title == title,
                                                   db.awards.c.student_id == student_id)).first():
            raise ValueError("นักเรียนคนนี้ได้รางวัลนี้แล้ว")
        return c.execute(insert(db.awards).values(title=title, student_id=student_id, note=note.strip(),
                                                  created_at=datetime.now())).inserted_primary_key[0]


def delete_award(engine: Engine, award_id: int) -> None:
    with engine.begin() as c:
        c.execute(delete(db.awards).where(db.awards.c.id == award_id))


# ---------------------------------------------------------------- ตั้งค่าเกียรติบัตร

DEFAULT_SIGNERS = [{"name": "", "position": "ผู้อำนวยการโรงเรียน"}]


def cert_settings(engine: Engine) -> dict:
    try:
        signers = json.loads(get_setting(engine, "cert_signers") or "null") or DEFAULT_SIGNERS
    except ValueError:
        signers = DEFAULT_SIGNERS
    return {
        "signers": signers,
        "date_text": get_setting(engine, "cert_date_text"),
        "prefix": get_setting(engine, "cert_prefix"),
        "logo": get_setting(engine, "cert_logo"),  # base64
    }


def save_cert_settings(engine: Engine, signers: list[dict], date_text: str, prefix: str) -> None:
    clean = [{"name": str(s.get("name") or "").strip(), "position": str(s.get("position") or "").strip()}
             for s in signers]
    clean = [s for s in clean if s["name"] or s["position"]][:3]
    set_setting(engine, "cert_signers", json.dumps(clean, ensure_ascii=False))
    set_setting(engine, "cert_date_text", date_text.strip())
    set_setting(engine, "cert_prefix", prefix.strip())


# ---------------------------------------------------------------- สำรองและย้ายข้อมูล

BACKUP_VERSION = 1


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def export_backup(engine: Engine) -> bytes:
    """สำรองข้อมูลทุกตาราง (รวมผู้ใช้และรหัสผ่านแบบเข้ารหัส) เป็น JSON"""
    out = {"app": "sportsday", "version": BACKUP_VERSION, "created_at": datetime.now().isoformat(), "tables": {}}
    with engine.connect() as c:
        for t in db.metadata.sorted_tables:
            rows = c.execute(select(t)).mappings().all()
            out["tables"][t.name] = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
    return json.dumps(out, ensure_ascii=False).encode("utf-8")


def backup_summary(data: bytes) -> dict[str, int]:
    """จำนวนแถวของแต่ละตารางในไฟล์สำรอง (ใช้แสดงก่อนกู้คืน)"""
    obj = json.loads(data.decode("utf-8"))
    if obj.get("app") != "sportsday":
        raise ValueError("ไม่ใช่ไฟล์สำรองของระบบกีฬาสี")
    return {k: len(v) for k, v in obj["tables"].items()}


def _convert(table, row: dict) -> dict:
    from sqlalchemy import Date, DateTime
    out = {}
    for k, v in row.items():
        if k not in table.c:
            continue  # คอลัมน์ที่เลิกใช้แล้ว
        col = table.c[k]
        if isinstance(v, str) and isinstance(col.type, DateTime):
            v = datetime.fromisoformat(v)
        elif isinstance(v, str) and isinstance(col.type, Date):
            v = date.fromisoformat(v[:10])
        out[k] = v
    return out


def import_backup(engine: Engine, data: bytes) -> dict[str, int]:
    """แทนที่ข้อมูลทั้งหมดด้วยไฟล์สำรอง (ทำในทรานแซกชันเดียว ถ้าพังกลางทางข้อมูลเดิมไม่เปลี่ยน)"""
    from sqlalchemy import text
    obj = json.loads(data.decode("utf-8"))
    if obj.get("app") != "sportsday":
        raise ValueError("ไม่ใช่ไฟล์สำรองของระบบกีฬาสี")
    tables = obj["tables"]
    counts = {}
    with engine.begin() as c:
        for t in reversed(db.metadata.sorted_tables):
            c.execute(delete(t))
        for t in db.metadata.sorted_tables:
            rows = [_convert(t, r) for r in tables.get(t.name, [])]
            if rows:
                c.execute(insert(t), rows)
            counts[t.name] = len(rows)
        if engine.dialect.name == "postgresql":  # ให้เลข id ถัดไปต่อจากข้อมูลที่ใส่
            for t in db.metadata.sorted_tables:
                if "id" in t.c and t.c["id"].primary_key:
                    c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                                   f"COALESCE((SELECT MAX(id) FROM {t.name}), 0) + 1, false)"))
    return counts


def storage_kind(engine: Engine) -> str:
    """postgresql = ฐานข้อมูลถาวร · sqlite = ไฟล์"""
    return engine.dialect.name


def data_counts(engine: Engine) -> dict[str, int]:
    from sqlalchemy import inspect
    have = set(inspect(engine).get_table_names())
    with engine.connect() as c:
        return {t.name: c.execute(select(func.count()).select_from(t)).scalar() if t.name in have else 0
                for t in db.metadata.sorted_tables}


# ---------------------------------------------------------------- สรุปเช็คชื่อรายวัน

def daily_summary(engine: Engine, color_id: int | None = None) -> pd.DataFrame:
    """สรุปทุกวันทุกรอบ: ทั้งหมด / มา / สาย / ลา / ขาด / ยังไม่เช็ค / ร้อยละมา (นับสายเป็นมา)
    คำนวณครั้งเดียวจากข้อมูลทั้งหมด (ไม่ query ทีละรอบ)"""
    cols = ["session_id", "day", "color", "รอบ", "กิจกรรม", "ทั้งหมด", *ATT_STATUSES, "ยังไม่เช็ค", "ร้อยละมา"]
    ses = sessions_df(engine)
    if color_id is not None:
        ses = ses[ses.color_id == color_id]
    if ses.empty:
        return pd.DataFrame(columns=cols)
    st = students_df(engine)
    att = _attendance_rows(engine)
    en = entries_df(engine)
    roles = roles_df(engine).set_index("id")["name"].to_dict()
    names = list_colors(engine).set_index("id")["name"].to_dict()
    rows = []
    for s in ses.itertuples():
        pool = st
        if pd.notna(s.event_id):
            pool = pool[pool.id.isin(en.loc[en.event_id == s.event_id, "student_id"])]
        if pd.notna(s.role_id):
            rname = roles.get(int(s.role_id))
            pool = pool[pool.roles.map(lambda rs, r=rname: r in rs)]
        if pd.notna(s.color_id):
            pool = pool[pool.color_id == s.color_id]
        mine = att[(att.session_id == s.id) & att.student_id.isin(pool.id)]
        cnt = mine["status"].value_counts()
        total = len(pool)
        came = int(cnt.get("มา", 0) + cnt.get("สาย", 0))
        rows.append({
            "session_id": int(s.id), "day": s.day,
            "color": f"สี{names[int(s.color_id)]}" if pd.notna(s.color_id) and int(s.color_id) in names else "ทุกสี",
            "รอบ": str(s.title).split(" (สี")[0], "กิจกรรม": s.activity, "ทั้งหมด": total,
            **{k: int(cnt.get(k, 0)) for k in ATT_STATUSES},
            "ยังไม่เช็ค": total - len(mine), "ร้อยละมา": round(came / total * 100) if total else 0,
        })
    out = pd.DataFrame(rows, columns=cols)
    order = {sid: i for i, sid in enumerate(ses.sort_values(["day", "id"])["id"])}
    out["_o"] = out["session_id"].map(order)
    return out.sort_values(["day", "color", "_o"], ascending=[False, True, True]).drop(columns="_o").reset_index(drop=True)


def absent_list(engine: Engine, session_ids: Iterable[int], statuses=("ขาด", "ลา", "สาย")) -> pd.DataFrame:
    """รายชื่อคนที่ ขาด/ลา/สาย ในรอบที่เลือก"""
    att = _attendance_rows(engine)
    att = att[att.session_id.isin(list(session_ids)) & att.status.isin(statuses)]
    st = students_df(engine, include_inactive=True)[["id", "full_name", "class", "color"]]
    ses = sessions_df(engine)[["id", "title"]]
    df = att.merge(st, left_on="student_id", right_on="id").merge(ses, left_on="session_id", right_on="id",
                                                                 suffixes=("", "_ses"))
    df["รอบ"] = df["title"].str.split(" (สี", regex=False).str[0]
    return df[["รอบ", "status", "full_name", "class", "color", "note"]].sort_values(["status", "รอบ", "class", "full_name"])


# ---------------------------------------------------------------- แผนผังนั่งสแตนด์

STAND_ROLE = "ขึ้นสแตนด์"
ROW_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def stand_size(engine: Engine) -> tuple[int, int]:
    """(จำนวนแถว, ที่นั่งต่อแถว) ค่าเริ่มต้น 5 x 10"""
    try:
        return int(get_setting(engine, "stand_rows") or 5), int(get_setting(engine, "stand_cols") or 10)
    except ValueError:
        return 5, 10


def set_stand_size(engine: Engine, rows: int, cols: int) -> None:
    if not (1 <= rows <= 26 and 1 <= cols <= 40):
        raise ValueError("แถว 1–26 และที่นั่งต่อแถว 1–40")
    set_setting(engine, "stand_rows", str(int(rows)))
    set_setting(engine, "stand_cols", str(int(cols)))


def seat_label(row: int, col: int) -> str:
    return f"{ROW_LABELS[row - 1]}{col}"


@cached
def stand_seats(engine: Engine, color_id: int) -> pd.DataFrame:
    """ที่นั่งที่จัดแล้วของสี: row, col, student_id, full_name, first_name, class, gender"""
    s = db.stand_seats.c
    with engine.connect() as c:
        df = pd.read_sql(select(s.row, s.col, s.student_id).where(s.color_id == color_id), c)
    st = students_df(engine, include_inactive=True)[["id", "full_name", "first_name", "class", "gender", "color_id"]]
    return df.merge(st, left_on="student_id", right_on="id", how="left").drop(columns="id")


def save_stand(engine: Engine, color_id: int, seats: dict[tuple[int, int], int]) -> int:
    """บันทึกแผนผังทั้งสีแทนของเดิม {(แถว, ที่): student_id} · คนหนึ่งนั่งได้ที่เดียว"""
    rows, cols = stand_size(engine)
    ids = [int(v) for v in seats.values() if v]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        names = students_df(engine, include_inactive=True).set_index("id")["full_name"]
        raise ValueError("มีชื่อซ้ำมากกว่า 1 ที่: " + ", ".join(names.get(i, str(i)) for i in dup))
    with engine.begin() as c:
        c.execute(delete(db.stand_seats).where(db.stand_seats.c.color_id == color_id))
        data = [{"color_id": color_id, "row": int(r), "col": int(k), "student_id": int(v)}
                for (r, k), v in seats.items() if v and 1 <= r <= rows and 1 <= k <= cols]
        if data:
            c.execute(insert(db.stand_seats), data)
    return len(ids)


def stand_candidates(engine: Engine, color_id: int, only_role: bool = True) -> pd.DataFrame:
    """นักเรียนของสีที่จัดลงสแตนด์ได้ (ค่าเริ่มต้น: เฉพาะคนที่มีหน้าที่ ขึ้นสแตนด์) เรียงตามชั้น/ห้อง/ชื่อ"""
    st = students_df(engine)
    st = st[st.color_id == color_id]
    if only_role:
        st = st[st.roles.map(lambda rs: STAND_ROLE in rs)]
    return st.sort_values(["grade", "room", "first_name"])


def auto_fill_stand(engine: Engine, color_id: int, mode: str = "ชั้น", keep_existing: bool = True,
                    only_role: bool = True) -> tuple[int, int]:
    """จัดที่นั่งอัตโนมัติ เติมจากแถวหน้า (A) ซ้ายไปขวา · mode: ชั้น = เรียงตามชั้น/ห้อง · สลับชายหญิง = ชายหญิงสลับกัน
    คืน (จำนวนที่จัด, จำนวนคนที่ไม่มีที่นั่ง)"""
    rows, cols = stand_size(engine)
    cur = stand_seats(engine, color_id)
    seats = {(int(r.row), int(r.col)): int(r.student_id) for r in cur.itertuples()} if keep_existing else {}
    seated = set(seats.values())
    pool = stand_candidates(engine, color_id, only_role)
    pool = pool[~pool.id.isin(seated)]
    if mode == "สลับชายหญิง":
        m, f = pool[pool.gender == "ชาย"]["id"].tolist(), pool[pool.gender != "ชาย"]["id"].tolist()
        order = [x for pair in zip(m, f) for x in pair] + m[len(f):] + f[len(m):]
    else:
        order = pool["id"].tolist()
    free = [(r, k) for r in range(1, rows + 1) for k in range(1, cols + 1) if (r, k) not in seats]
    for spot, sid in zip(free, order):
        seats[spot] = int(sid)
    save_stand(engine, color_id, seats)
    return min(len(free), len(order)), max(0, len(order) - len(free))
