"""ทะเบียนสมาชิก (ทุกสี): ชื่อ ชั้น ห้อง สี + หน้าที่และรายการแข่ง (เลือกได้หลายอย่าง)"""
import streamlit as st

from sportsday import components as comp, services as sv, ui

ui.require("members")
engine = ui.get_engine()
st.title("สมาชิก")

st_df = sv.students_df(engine)
colors = sv.list_colors(engine)

m = st.columns(len(colors) + 2)
m[0].metric("สมาชิกทั้งหมด", len(st_df))
for col, c in zip(m[1:], colors.itertuples()):
    col.metric(f"สี{c.name}", int((st_df.color_id == c.id).sum()))
m[-1].metric("ยังไม่ระบุสี", int(st_df.color_id.isna().sum()))

tab_list, tab_edit, tab_add = st.tabs(["รายชื่อ", "แก้ไข / กำหนดหน้าที่", "เพิ่มสมาชิก"])

with tab_list:
    comp.member_list(engine, st_df, "mf")

with tab_edit:
    comp.member_editor(engine, st_df, "me")

with tab_add:
    with st.form("me_add", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
        prefix = c1.selectbox("คำนำหน้า", ["เด็กชาย", "เด็กหญิง", "นาย", "นางสาว"], key="ma_pre")
        first = c2.text_input("ชื่อ", key="ma_first")
        last = c3.text_input("นามสกุล", key="ma_last")
        code = c4.text_input("เลขประจำตัว", key="ma_code")
        c1, c2, c3 = st.columns(3)
        grade = c1.selectbox("ชั้น ม.", sv.GRADES, key="ma_grade")
        room = c2.number_input("ห้อง", 1, 20, 1, key="ma_room")
        cmap = {0: "ยังไม่ระบุ", **dict(zip(colors.id, colors.name))}
        color = c3.selectbox("สี", list(cmap), format_func=cmap.get, key="ma_color")
        if st.form_submit_button("เพิ่มสมาชิก", type="primary"):
            if not first.strip():
                st.error("กรอกชื่อก่อน")
            else:
                sv.add_student(engine, code=code.strip(), prefix=prefix, first_name=first.strip(), last_name=last.strip(),
                               gender="หญิง" if prefix in ("เด็กหญิง", "นางสาว") else "ชาย",
                               grade=int(grade), room=int(room), color_id=color or None)
                st.success(f"เพิ่ม {prefix}{first} แล้ว · กำหนดหน้าที่ต่อได้ที่แท็บ แก้ไข")
