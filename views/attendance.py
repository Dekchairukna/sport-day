"""เช็คชื่อ (ทุกสี): ตามรายการแข่ง ตามหน้าที่ (เช่น ซ้อมเชียร์) หรือทั้งสี"""
import streamlit as st

from sportsday import components as comp, services as sv, ui

ui.require("attendance")
engine = ui.get_engine()
mine = ui.staff_color_id()
if mine is not None:  # สต๊าฟสี: เห็นและเช็คได้เฉพาะสมาชิกในสีตัวเอง
    cname = sv.list_colors(engine).set_index("id").loc[mine, "name"]
    st.title(f"เช็คชื่อสมาชิกสี{cname}")
    st.caption("เห็นเฉพาะรอบเช็คชื่อและสมาชิกของสีตัวเอง")
    comp.attendance_panel(engine, f"c{mine}_att", color_id=mine)
else:
    st.title("เช็คชื่อ")
    st.caption("หน้านี้เห็นทุกรอบของทุกสี · สต๊าฟแต่ละสีเช็คชื่อได้เฉพาะสีตัวเอง")
    comp.attendance_panel(engine, "att")
