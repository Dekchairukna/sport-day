"""รายงานการแข่งขัน: สรุปถ้วย แยกชนิดกีฬา ผลรายวัน + ดาวน์โหลด PDF / Excel"""
from datetime import datetime

import streamlit as st

from sportsday import reports as rp, services as sv, ui

engine = ui.get_engine()
st.title("รายงานการแข่งขัน")

prog = sv.progress(engine)
st.caption(f"แข่งจบแล้ว {prog['done']} จาก {prog['total']} รายการ · ข้อมูล ณ {datetime.now():%d/%m/%Y %H:%M} น.")

st.subheader("สรุปถ้วย")
st.dataframe(rp.standings_table(engine), hide_index=True, width="stretch")

st.subheader("แยกชนิดกีฬา")
st.dataframe(rp.by_sport_table(engine), hide_index=True, width="stretch")

st.subheader("ผลรายวัน")
res = rp.results_table(engine)
if res.empty:
    st.info("ยังไม่มีรายการแข่ง")
else:
    days = sorted(res["_date"].unique())
    today = datetime.now().date()
    day = st.selectbox("วันที่", days, index=days.index(today) if today in days else 0,
                       format_func=rp.thai_date, key="rp_day")
    st.dataframe(res[res["_date"] == day].drop(columns=["_date", "วันที่"]), hide_index=True, width="stretch")

    st.subheader("ดาวน์โหลด")
    c1, c2, c3 = st.columns(3)
    c1.download_button("PDF สรุปทั้งงาน", rp.pdf_report(engine), "รายงานผลการแข่งขัน.pdf",
                       "application/pdf", type="primary", width="stretch")
    c2.download_button(f"PDF เฉพาะ {rp.thai_date(day, False)}", rp.pdf_report(engine, day),
                       f"รายงานผล_{day:%Y-%m-%d}.pdf", "application/pdf", width="stretch")
    if ui.has("members"):
        c3.download_button("Excel ครบทุกตาราง (มีรายชื่อนักเรียน)", rp.excel_report(engine), "รายงานกีฬาสี.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    else:
        c3.caption("Excel ที่มีรายชื่อนักเรียน ดาวน์โหลดได้หลังเข้าสู่ระบบ")
