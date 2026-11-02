"""ถ้วยรางวัล: เช็คลิสต์การเตรียม + พิมพ์สติ๊กเกอร์ (ประสานครูฟ้า)"""
import pandas as pd
import streamlit as st

from sportsday import reports, services as sv, ui

ui.require("trophies")
engine = ui.get_engine()
st.title("ถ้วยรางวัล")
st.caption("ถ้วยละ 1 ใบต่อรายการ · เพิ่มรายการแข่งใหม่ที่หน้าตารางแข่ง ระบบจะเพิ่มถ้วยให้อัตโนมัติ")

ev = sv.events_df(engine, include_cancelled=False)
if ev.empty:
    st.info("ยังไม่มีรายการแข่ง")
    st.stop()

counts = ev["trophy_status"].value_counts()
cols = st.columns(len(sv.TROPHY_STATUSES) + 1)
cols[0].metric("ถ้วยทั้งหมด", len(ev))
for col, s in zip(cols[1:], sv.TROPHY_STATUSES):
    col.metric(s, int(counts.get(s, 0)))

st.markdown("#### เช็คลิสต์")
table = pd.DataFrame({
    "id": ev["id"], "ชนิดกีฬา": ev["sport"], "รุ่น/ประเภท": ev["label"],
    "แข่งวันที่": ev["date"].map(lambda d: reports.thai_date(d, False)),
    "สถานะ": ev["trophy_status"], "หมายเหตุ": ev["trophy_note"].fillna(""),
})
out = st.data_editor(
    table, hide_index=True, width="stretch", key="trophy_editor",
    disabled=["id", "ชนิดกีฬา", "รุ่น/ประเภท", "แข่งวันที่"],
    column_config={"id": None, "สถานะ": st.column_config.SelectboxColumn(options=sv.TROPHY_STATUSES, required=True)},
)
if st.button("บันทึกสถานะถ้วย", type="primary"):
    n = 0
    for old, new in zip(table.to_dict("records"), out.to_dict("records")):
        if old != new:
            sv.set_trophy(engine, int(new["id"]), new["สถานะ"], str(new["หมายเหตุ"] or ""))
            n += 1
    st.success(f"บันทึก {n} รายการ")
    st.rerun()

st.markdown("#### พิมพ์สติ๊กเกอร์ติดถ้วย")
st.caption("A4 แผ่นละ 10 ดวง ขนาด 9 x 5 ซม. มีเส้นประไว้ตัด · ข้อความ: ชื่อโรงเรียน, ชื่องาน, ชนิดกีฬา, รุ่น, ชนะเลิศ")
c1, c2 = st.columns([3, 1])
which = c1.radio("เลือกรายการ", ["ทุกรายการ", "เฉพาะที่ยังไม่ติดสติ๊กเกอร์", "เลือกเอง"], horizontal=True, key="stk_which")
copies = c2.number_input("ชุดละกี่ดวง", 1, 5, 1, key="stk_copies")
if which == "ทุกรายการ":
    ids = ev["id"].tolist()
elif which == "เฉพาะที่ยังไม่ติดสติ๊กเกอร์":
    ids = ev.loc[ev.trophy_status == "รอเตรียม", "id"].tolist()
else:
    names = dict(zip(ev["id"], ev["name"]))
    ids = st.multiselect("รายการ", list(names), format_func=names.get, key="stk_pick")
st.download_button(
    f"ดาวน์โหลดสติ๊กเกอร์ PDF ({len(ids) * copies} ดวง)",
    data=reports.sticker_pdf(engine, [int(i) for i in ids] or [-1], int(copies)),
    file_name="สติ๊กเกอร์ถ้วยรางวัล.pdf", mime="application/pdf", disabled=not ids, type="primary",
)
