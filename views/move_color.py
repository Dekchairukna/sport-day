"""ย้ายสี: เปลี่ยนสีพร้อมเหตุผล เก็บประวัติ และจัดการรายการแข่งที่ยังไม่แข่ง"""
import pandas as pd
import streamlit as st

from sportsday import services as sv, ui

ui.require("move_color")
engine = ui.get_engine()
st.title("ย้ายสี")
st.caption("ผลการแข่งขันที่จบไปแล้วไม่เปลี่ยน ถ้วยยังนับให้สีเดิม")

st_df = sv.students_df(engine)
colors = sv.list_colors(engine)
if st_df.empty:
    st.info("ยังไม่มีสมาชิก")
    st.stop()

labels = dict(zip(st_df.id, st_df["class"] + "  " + st_df.full_name + " · สี" + st_df.color))
sid = st.selectbox("นักเรียน (พิมพ์ค้นหาได้)", list(labels), format_func=labels.get, key="mv_pick")
s = st_df.set_index("id").loc[sid]
st.markdown("สีปัจจุบัน " + ui.chip(f"สี{s['color']}", s["color_hex"] if isinstance(s["color_hex"], str) else None),
            unsafe_allow_html=True)

pend = sv.pending_entries(engine, int(sid))
if not pend.empty:
    st.warning("นักเรียนคนนี้ลงแข่งรายการที่ยังไม่แข่งอยู่ในทีมสีเดิม: " + ", ".join(pend["name"]))

targets = colors[colors.id != s["color_id"]]
cmap = dict(zip(targets.id, "สี" + targets.name))
with st.form(f"mv_form_{sid}"):
    to = st.radio("ย้ายไป", list(cmap), format_func=cmap.get, horizontal=True, key=f"mv_to_{sid}")
    reason = st.text_input("เหตุผล", placeholder="เช่น ปรับจำนวนให้สมดุล / ย้ายตามพี่น้อง", key=f"mv_reason_{sid}")
    remove = st.checkbox("ถอดออกจากรายการที่ยังไม่แข่งของสีเดิม", value=True, disabled=pend.empty, key=f"mv_rm_{sid}")
    if st.form_submit_button("ยืนยันการย้ายสี", type="primary"):
        if not reason.strip():
            st.error("ใส่เหตุผลการย้ายก่อน เพื่อเก็บเป็นประวัติ")
        else:
            removed = sv.move_color(engine, int(sid), int(to), reason, ui.editor_name(), remove_pending_entries=remove)
            st.success(f"ย้าย {s['full_name']} ไป{cmap[to]} แล้ว")
            if removed:
                st.info("ถอดออกจาก: " + ", ".join(removed) + " · จัดนักกีฬาแทนได้ที่หน้าตารางแข่ง")

st.markdown("#### ประวัติการย้ายสี")
hist = sv.color_moves_df(engine)
if hist.empty:
    st.caption("ยังไม่มีการย้ายสี")
else:
    st.dataframe(pd.DataFrame({
        "เวลา": pd.to_datetime(hist["moved_at"]).dt.strftime("%d/%m/%Y %H:%M"),
        "ชื่อ-สกุล": hist["prefix"] + hist["first_name"] + " " + hist["last_name"],
        "ชั้น": "ม." + hist["grade"].astype(str) + "/" + hist["room"].astype(str),
        "จากสี": hist["from_color"], "ไปสี": hist["to_color"], "เหตุผล": hist["reason"], "ผู้ดำเนินการ": hist["moved_by"],
    }), hide_index=True, width="stretch")
