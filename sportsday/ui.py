"""ส่วนกลางของหน้าจอ Streamlit: ฐานข้อมูล, ผู้ใช้และสิทธิ์, สไตล์"""
from __future__ import annotations

import html
import os
import time

import streamlit as st

from . import services as sv
from .db import local_db_path, make_engine, on_streamlit_cloud, schema_signature

CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@500;600;700&family=IBM+Plex+Sans+Thai:wght@400;500;600&family=Sarabun:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#fbf8f3; --surface:#ffffff; --surface-2:#f7f3ec; --ink:#2e2b36; --muted:#6e6a78; --line:#ece4d8;
  --mint:#cdeee4; --mint-ink:#2f7a6b; --peach:#ffd9c7; --butter:#fff1c1; --rose:#fbd3df; --sky:#d4e8fb;
  --coral:#f4a58a; --accent:#6fbfae; --accent-soft:#e3f4ef;
  --f-display:"Kanit","IBM Plex Sans Thai",system-ui,sans-serif;
  --f-body:"IBM Plex Sans Thai","Sarabun",system-ui,sans-serif;
}
html, body, p, li, label, input, textarea, select, td, th, button, .stMarkdown { font-family: var(--f-body); }
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
h1, h2, h3, h4, .big-num { font-family: var(--f-display) !important; letter-spacing: 0 !important; color: var(--ink); }
h1 { font-weight: 700 !important; } h2, h3, h4 { font-weight: 600 !important; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; }
/* แถบหัวพาสเทล */
.band { background: linear-gradient(115deg, var(--peach) 0%, var(--butter) 50%, var(--mint) 100%); color: var(--ink);
        border-radius: 16px; padding: 18px 22px 21px; margin: 0 0 18px; position: relative; overflow: hidden; }
.band::before { content:""; position:absolute; left:0; right:0; bottom:0; height:5px; background: var(--accent); }
.band::after { content:""; position:absolute; right:0; bottom:0; width:22%; height:5px; background: var(--coral); }
.band .eyebrow { font-size: 12.5px; letter-spacing: .06em; color: var(--muted); }
.band .games { font-family: var(--f-display); color: var(--mint-ink); font-weight: 600; font-size: 14px; }
.band .ttl { font-family: var(--f-display); font-weight: 700; font-size: clamp(22px, 4vw, 30px); line-height: 1.25; color: var(--ink); margin-top: 2px; }
/* แถบข้าง */
[data-testid="stSidebar"] { border-right: 1px solid #d6ebe3; }
[data-testid="stSidebarNav"] [data-testid="stNavSectionHeader"] { color: var(--muted) !important; letter-spacing: .05em; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: var(--mint) !important; }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--mint-ink) !important; font-weight: 600; }
[data-testid="stSidebar"] [data-testid="stForm"] { background: #ffffffaa; border-color: #d6ebe3; }
/* ปุ่มหลักพื้นพาสเทล ตัวหนังสือเข้ม อ่านง่าย */
.stButton button[kind="primary"], .stFormSubmitButton button, [data-testid="stSidebar"] .stButton button {
  background: var(--accent) !important; border-color: var(--accent) !important; color: #173b34 !important; font-weight: 600; }
.stButton button[kind="primary"]:hover, .stFormSubmitButton button:hover { background: #5fb2a0 !important; }
.stButton button[kind="secondary"]:hover, .stDownloadButton button:hover { border-color: var(--accent); color: var(--mint-ink); }
/* การ์ด แท็บ */
[data-testid="stMain"] [data-testid="stExpander"] details { background: var(--surface); border-color: var(--line); border-radius: 12px; }
[data-testid="stExpander"] summary p { font-family: var(--f-display); font-weight: 500; }
[data-testid="stMain"] [data-testid="stForm"] { background: var(--surface); border-color: var(--line); border-radius: 12px; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; background: var(--surface-2); border: 1px solid var(--line); border-radius: 12px; padding: 4px; }
.stTabs [data-baseweb="tab"] { border-radius: 9px; padding: 6px 14px; height: auto; }
.stTabs [data-baseweb="tab"] p { font-family: var(--f-display); font-weight: 600; font-size: 15px; }
.stTabs [aria-selected="true"] { background: var(--mint); }
.stTabs [aria-selected="true"] p { color: var(--mint-ink); }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
[data-testid="stMetricValue"] { font-family: var(--f-display); font-variant-numeric: tabular-nums; }
[data-testid="stProgress"] [role="progressbar"] > div > div { background: var(--surface-2) !important; }
[data-testid="stProgress"] [role="progressbar"] > div > div > div { background: linear-gradient(90deg, var(--accent), var(--coral)) !important; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
/* ชิ้นส่วนของระบบ: สีประจำทีมแสดงเป็นโทนพาสเทล */
.chip { display:inline-flex; align-items:center; gap:6px; padding:2px 10px; border-radius:999px; font-size:0.85rem; font-weight:600; white-space:nowrap;
        background: color-mix(in srgb, var(--c, #888) 18%, white); color: color-mix(in srgb, var(--c, #888) 75%, black); }
.chip::before { content:""; width:8px; height:8px; border-radius:50%; background: var(--c, #888); }
.tag { display:inline-block; padding:1px 9px; margin:0 4px 4px 0; border-radius:8px; font-size:0.8rem; background: var(--accent-soft); color: var(--mint-ink); }
.score-card { border-radius:16px; padding:14px 18px; position:relative; overflow:hidden;
              background: color-mix(in srgb, var(--c, #888) 20%, white); color: color-mix(in srgb, var(--c, #888) 70%, black);
              border: 1px solid color-mix(in srgb, var(--c, #888) 30%, white); box-shadow: inset 0 -5px 0 color-mix(in srgb, var(--c, #888) 45%, white); }
.score-card .big-num { font-size:3.4rem; line-height:1.2; font-weight:700; font-variant-numeric: tabular-nums; color: inherit; }
.score-card .lbl { font-size:1.05rem; font-family: var(--f-display); font-weight: 500; }
.muted { color: var(--muted); font-size:.9rem }
/* แผนผังสแตนด์ */
.sg-wrap { overflow-x: auto; padding-bottom: 6px; }
.sg { display: grid; gap: 4px; min-width: max-content; }
.sg-h { font-family: var(--f-display); font-weight: 600; color: var(--muted); text-align: center; align-self: center; font-size: 13px; }
.sg-c { border-radius: 8px; padding: 4px 4px 5px; min-height: 58px; display: flex; flex-direction: column; align-items: center;
        justify-content: center; text-align: center; line-height: 1.25; border: 1px solid var(--line); background: var(--surface); }
.sg-c span { font-size: 10px; color: var(--muted); }
.sg-c b { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.sg-c i { font-style: normal; font-size: 11px; color: var(--muted); }
.sg-c.m { background: #e3effd; border-color: #b9d4f5; } .sg-c.f { background: #fde7ee; border-color: #f4bfd0; }
.sg-c.empty { border-style: dashed; background: transparent; }
.sg-field { margin-top: 6px; background: var(--mint); color: var(--mint-ink); border-radius: 8px; text-align: center;
            padding: 6px; font-family: var(--f-display); font-weight: 600; min-width: max-content; }
.medals { display:flex; gap:8px; margin:8px 0 6px; flex-wrap:wrap; }
.medals .m { font-family: var(--f-display); font-size: 2.2rem; font-weight: 700; line-height: 1.25; min-width: 3.4rem;
             text-align: center; border-radius: 12px; padding: 2px 10px; font-variant-numeric: tabular-nums; }
.medals .g { background: #fff1c1; color: #8a6206; } .medals .s { background: #eef0f4; color: #4b5563; }
.medals .b { background: #fde2cf; color: #9a4a1c; }
/* เช็คชื่อบนมือถือ: ปุ่มใหญ่กดง่าย สีตามสถานะ */
[class*="st-key-attrow"] { gap: 4px; padding: 8px 0 10px; border-bottom: 1px solid var(--line); }
[class*="st-key-attrow"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[class*="st-key-attrow"] p { margin: 0 !important; line-height: 1.7; }
[class*="st-key-attrow"] [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]),
[class*="st-key-attrow"] [data-testid="stButtonGroup"] { width: 100% !important; }
[class*="st-key-attrow"] [data-testid="stButtonGroup"] [role="radiogroup"] { display: grid !important; grid-template-columns: repeat(4, 1fr); width: 100%; max-width: 460px; }
[class*="st-key-attrow"] [data-testid="stButtonGroup"] button { min-height: 44px; font-size: 16px; font-weight: 600; justify-content: center; }
[class*="st-key-attrow"] [data-testid="stButtonGroup"] button:nth-of-type(1)[kind$="Active"] { background: #cdeee4 !important; color: #1f6b5c !important; border-color: #6fbfae !important; }
[class*="st-key-attrow"] [data-testid="stButtonGroup"] button:nth-of-type(2)[kind$="Active"] { background: #fff1c1 !important; color: #8a6206 !important; border-color: #e9c46a !important; }
[class*="st-key-attrow"] [data-testid="stButtonGroup"] button:nth-of-type(3)[kind$="Active"] { background: #d4e8fb !important; color: #24578f !important; border-color: #8fbbe8 !important; }
[class*="st-key-attrow"] [data-testid="stButtonGroup"] button:nth-of-type(4)[kind$="Active"] { background: #fbd3df !important; color: #a3324f !important; border-color: #ee9ab3 !important; }
</style>
"""


def _secret(key: str, default: str | None = None) -> str | None:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # ไม่มีไฟล์ secrets.toml
        pass
    return os.environ.get("SPORTSDAY_" + key.upper(), default)


@st.cache_resource
def _engine(url: str | None, schema: tuple):
    """schema เป็นส่วนหนึ่งของ key แคช: เมื่อโค้ดเพิ่มตารางหรือคอลัมน์ใหม่ (เช่น แก้ไฟล์ขณะแอปรันอยู่)
    จะสร้าง engine ใหม่ ซึ่งสร้างตาราง/คอลัมน์ที่ขาดและใส่ข้อมูลตั้งต้นให้เอง"""
    eng = make_engine(url)
    sv.seed_defaults(eng)
    sv.seed_users(eng, editor_pin())
    sv.migrate_color_perms(eng)
    return eng


def get_engine():
    return _engine(_secret("db_url"), schema_signature())


def setup_page() -> None:
    # ตัดบรรทัดว่างออก ไม่งั้น markdown จะปิดบล็อก <style> กลางทาง
    st.markdown("\n".join(ln for ln in CSS.splitlines() if ln.strip()), unsafe_allow_html=True)


def band(engine) -> None:
    """แถบหัวสีม่วงเข้ม เส้นทอง-ส้มด้านล่าง แสดงบนทุกหน้า"""
    title = html.escape(sv.get_setting(engine, "event_title") or "ระบบกีฬาสี")
    school = html.escape(sv.get_setting(engine, "school_name") or "")
    st.markdown(
        f'<div class="band"><div class="eyebrow">{school}</div>'
        f'<div class="ttl">{title}</div>'
        f'<div class="games">ระบบจัดการกีฬาสี · 1 รายการ = 1 ถ้วย</div></div>',
        unsafe_allow_html=True,
    )


def editor_pin() -> str:
    """รหัสผ่านเริ่มต้นของบัญชี admin ตอนสร้างครั้งแรก (จาก secrets เดิม)"""
    return _secret("edit_pin", "1234") or "1234"


def _logout() -> None:
    for k in ("user_id", "weak_pw"):
        st.session_state.pop(k, None)


def current_user() -> dict | None:
    """ผู้ใช้ที่เข้าสู่ระบบอยู่ อ่านจากฐานข้อมูลทุกครั้ง สิทธิ์ที่แก้จึงมีผลทันที"""
    uid = st.session_state.get("user_id")
    if uid is None:
        return None
    u = sv.get_user(get_engine(), uid)
    if not u or not u["active"]:  # ถูกลบหรือปิดบัญชีระหว่างใช้งาน
        _logout()
        return None
    return u


def role() -> str | None:
    """None = ผู้ชมทั่วไป, "admin" / "staff" / "color" ตามบัญชีที่เข้าสู่ระบบ"""
    u = current_user()
    return u["role"] if u else None


def has(perm: str) -> bool:
    return perm in sv.user_perms(current_user())


def is_admin() -> bool:
    return role() == "admin"


def staff_color_id() -> int | None:
    u = current_user()
    return u["color_id"] if u and u["role"] == "color" else None


def can_manage_color(color_id: int) -> bool:
    return has("colors") or staff_color_id() == color_id


def editor_name() -> str:
    u = current_user()
    return (u["display_name"] or u["username"]) if u else ""


def require(perm: str) -> None:
    if has(perm):
        return
    if role() == "color":
        msg = "หน้านี้ไม่ได้อยู่ในสิทธิ์ของบัญชีสต๊าฟสีนี้ ติดต่อผู้ดูแลระบบ หรือใช้หน้าของสีตัวเองที่เมนูด้านซ้าย"
    elif role():
        msg = f"บัญชีของคุณยังไม่มีสิทธิ์ \"{sv.PERMS.get(perm, 'จัดการผู้ใช้')}\" ติดต่อผู้ดูแลระบบ"
    else:
        msg = "หน้านี้มีข้อมูลนักเรียนหรือใช้แก้ไขข้อมูล กรุณาเข้าสู่ระบบที่แถบด้านซ้าย"
    st.info(msg)
    st.stop()


def _role_text(engine, u: dict) -> str:
    if u["role"] == "color":
        cname = sv.list_colors(engine).set_index("id")["name"].get(u["color_id"], "")
        return f"สต๊าฟสี{cname}"
    return sv.ROLES[u["role"]]


def storage_is_temporary(engine) -> bool:
    """ใช้ไฟล์ SQLite บน Streamlit Cloud = ข้อมูลหายเมื่อแอปเริ่มใหม่"""
    return engine.dialect.name == "sqlite" and on_streamlit_cloud()


def sidebar_login(engine) -> None:
    with st.sidebar:
        if msg := st.session_state.pop("bk_flash", None):  # หลังย้าย/กู้คืนข้อมูล ผู้ใช้ต้องเข้าสู่ระบบใหม่
            st.success(msg + " · เข้าสู่ระบบใหม่ด้วยบัญชีเดิม")
        u = current_user()
        if u and u["role"] == "admin" and storage_is_temporary(engine):
            st.error("ข้อมูลบนเว็บนี้เก็บในไฟล์ชั่วคราว อาจหายเมื่อแอปเริ่มใหม่ "
                     "ย้ายเข้าฐานข้อมูลถาวรได้ที่ ตั้งค่า → สำรองข้อมูล")
        if u:
            st.success(f"**{u['display_name'] or u['username']}**\n\n{_role_text(engine, u)} · {u['username']}")
            if st.session_state.get("weak_pw"):
                st.warning(f"ยังใช้รหัสผ่านเริ่มต้นหรือสั้นเกินไป เปลี่ยนให้ยาวอย่างน้อย {sv.MIN_PASSWORD} ตัว")
            with st.expander("เปลี่ยนรหัสผ่าน", expanded=bool(st.session_state.get("weak_pw"))):
                with st.form("my_pw", clear_on_submit=True):
                    old = st.text_input("รหัสผ่านเดิม", type="password", key="pw_old")
                    new = st.text_input("รหัสผ่านใหม่", type="password", key="pw_new")
                    new2 = st.text_input("พิมพ์รหัสผ่านใหม่อีกครั้ง", type="password", key="pw_new2")
                    if st.form_submit_button("บันทึกรหัสผ่าน", width="stretch"):
                        if not sv.verify_password(old, u["pw_hash"]):
                            st.error("รหัสผ่านเดิมไม่ถูกต้อง")
                        elif new != new2:
                            st.error("รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน")
                        else:
                            try:
                                sv.set_password(engine, u["id"], new)
                                st.session_state.pop("weak_pw", None)
                                st.success("เปลี่ยนรหัสผ่านแล้ว")
                            except ValueError as err:
                                st.error(str(err))
            if st.button("ออกจากระบบ", width="stretch"):
                _logout()
                st.rerun()
            return

        locked = st.session_state.get("login_locked_until", 0) - time.time()
        with st.form("login", clear_on_submit=True):
            st.markdown("**สำหรับครู กรรมการ และสต๊าฟสี**")
            name = st.text_input("ชื่อผู้ใช้", key="login_name", placeholder="เช่น admin")
            pw = st.text_input("รหัสผ่าน", type="password", key="login_pw")
            if st.form_submit_button("เข้าสู่ระบบ", width="stretch"):
                if locked > 0:
                    st.error(f"ใส่ผิดหลายครั้ง รออีก {int(locked) + 1} วินาที")
                else:
                    found = sv.authenticate(engine, name, pw)
                    if found:
                        st.session_state["user_id"] = found["id"]
                        st.session_state["login_fails"] = 0
                        st.session_state["weak_pw"] = len(pw) < sv.MIN_PASSWORD or pw == "1234"
                        st.rerun()
                    fails = st.session_state.get("login_fails", 0) + 1
                    st.session_state["login_fails"] = fails
                    if fails >= 5:
                        st.session_state["login_locked_until"] = time.time() + 60
                        st.session_state["login_fails"] = 0
                        st.error("ใส่ผิด 5 ครั้ง ลองใหม่ได้ใน 1 นาที")
                    else:
                        st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
        st.caption("ยังไม่มีบัญชี ขอให้ผู้ดูแลระบบสร้างให้ที่หน้า ผู้ใช้")


def chip(name: str, hex_: str | None) -> str:
    return f'<span class="chip" style="--c:{html.escape(hex_ or "#888")}">{html.escape(name)}</span>'


def tags(items: list[str]) -> str:
    return "".join(f'<span class="tag">{html.escape(t)}</span>' for t in items)


def color_hex_map(engine) -> dict[str, str]:
    c = sv.list_colors(engine)
    m = dict(zip(c["name"], c["hex"]))
    m["ยังไม่ระบุ"] = "#8a8f98"
    return m
