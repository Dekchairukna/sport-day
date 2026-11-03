"""ระบบกีฬาสี — จุดเริ่มโปรแกรม

รัน:  streamlit run app.py
"""
import streamlit as st

from sportsday import color_view, services as sv, ui

st.set_page_config(page_title="ระบบกีฬาสี", page_icon="🏆", layout="wide")
ui.setup_page()
engine = ui.get_engine()  # สร้างฐานข้อมูลและข้อมูลตั้งต้นครั้งแรก
ui.band(engine)


def color_page(color_id: int, name: str, default: bool = False) -> st.Page:
    def run():
        color_view.render(color_id)

    return st.Page(run, title=f"สี{name}", icon=":material/flag:", url_path=f"color-{color_id}", default=default)


colors = sv.list_colors(engine)
staff = ui.staff_color_id()

overview = [
    st.Page("views/board.py", title="กระดานผล", icon=":material/emoji_events:", default=staff is None),
    st.Page("views/schedule.py", title="ตารางแข่ง", icon=":material/calendar_month:"),
    st.Page("views/medals.py", title="สรุปเหรียญ", icon=":material/workspace_premium:"),
    st.Page("views/reports.py", title="รายงาน", icon=":material/description:"),
]
if staff is not None:  # สต๊าฟสี: หน้าสีตัวเอง + บันทึกผล/เช็คชื่อ ถ้าได้รับสิทธิ์
    mine = [color_page(staff, colors.set_index("id").loc[staff, "name"], default=True)]
    if ui.has("results"):
        mine.append(st.Page("views/results.py", title="บันทึกผล", icon=":material/edit_note:"))
    if ui.has("attendance"):
        mine.append(st.Page("views/attendance.py", title="เช็คชื่อสมาชิกในสี", icon=":material/fact_check:"))
    pages = {"สีของฉัน": mine, "ภาพรวม": overview}
else:
    pages = {
        "ภาพรวม": overview,
        "หน้าสี": [color_page(int(r.id), r.name) for r in colors.itertuples()],
    }
    # แสดงเฉพาะเมนูที่บัญชีนี้มีสิทธิ์
    work = [
        ("results", "views/results.py", "บันทึกผล", ":material/edit_note:"),
        ("attendance", "views/attendance.py", "เช็คชื่อ", ":material/fact_check:"),
        ("trophies", "views/trophies.py", "ถ้วยรางวัล", ":material/military_tech:"),
        ("certificates", "views/certificates.py", "เกียรติบัตร", ":material/card_membership:"),
    ]
    registry = [
        ("members", "views/members.py", "สมาชิก", ":material/groups:"),
        ("move_color", "views/move_color.py", "ย้ายสี", ":material/swap_horiz:"),
        ("settings", "views/settings.py", "ตั้งค่า", ":material/settings:"),
        ("users", "views/users.py", "ผู้ใช้", ":material/manage_accounts:"),
    ]
    for section, items in (("งานกรรมการ", work), ("ทะเบียน", registry)):
        allowed = [st.Page(path, title=t, icon=i) for perm, path, t, i in items if ui.has(perm)]
        if allowed:
            pages[section] = allowed

nav = st.navigation(pages, expanded=True)  # แสดงเมนูครบ ไม่ย่อเป็น View more
ui.sidebar_login(engine)
nav.run()
