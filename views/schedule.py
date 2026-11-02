"""ตารางแข่ง: ดูตามวัน, เพิ่มกีฬา/รายการ, แก้เวลา, จัดนักกีฬา, เตือนเวลาชน"""
from datetime import date

import pandas as pd
import streamlit as st

from sportsday import components as comp, services as sv, ui
from sportsday.reports import thai_date

engine = ui.get_engine()
st.title("ตารางแข่ง")

ev = sv.events_df(engine)
tab_names = ["ตามวัน"] + (["จัดนักกีฬา", "เวลาชน", "เพิ่ม/แก้รายการ"] if ui.has("schedule") else [])
tabs = st.tabs(tab_names)

with tabs[0]:
    if ev.empty:
        st.info("ยังไม่มีรายการแข่ง")
    sports = ["ทุกชนิด"] + list(dict.fromkeys(ev["sport"]))
    pick = st.selectbox("ชนิดกีฬา", sports, key="sch_sport")
    view = ev if pick == "ทุกชนิด" else ev[ev.sport == pick]
    for d, g in view.groupby("date", sort=True):
        st.subheader(thai_date(d))
        st.dataframe(
            pd.DataFrame({
                "เวลา": g["start"] + "–" + g["end"],
                "ชนิดกีฬา": g["sport"],
                "รุ่น/ประเภท": g["label"],
                "สนาม": g["venue"],
                "นักกีฬา": g["athletes"],
                "สถานะ": g["status"],
                "ได้ถ้วย": g["winner"].fillna("").map(lambda w: f"สี{w}" if w else ""),
            }),
            hide_index=True, width="stretch",
        )
    if not ui.has("schedule"):
        st.caption("ครูและกรรมการเข้าสู่ระบบเพื่อจัดนักกีฬา เพิ่มกีฬา หรือแก้เวลา")

if ui.has("schedule"):
    active = ev[~ev.cancelled]
    # ---------------------------------------------------------- จัดนักกีฬา
    with tabs[1]:
        comp.athlete_picker(engine, "ent")

    # ---------------------------------------------------------- เวลาชน
    with tabs[2]:
        comp.conflicts_table(sv.find_conflicts(engine))

    # ---------------------------------------------------------- เพิ่ม/แก้รายการ
    with tabs[3]:
        st.markdown("#### เพิ่มรายการแข่ง หรือกีฬาใหม่")
        with st.form("add_event", clear_on_submit=True):
            existing = list(dict.fromkeys(ev["sport"]))
            c1, c2 = st.columns(2)
            sport_pick = c1.selectbox("ชนิดกีฬา", existing + ["+ กีฬาใหม่"], key="new_sport_pick")
            new_sport = c2.text_input("ชื่อกีฬาใหม่ (ถ้าเลือก + กีฬาใหม่)", key="new_sport_name", placeholder="เช่น ชักเย่อ")
            c1, c2, c3 = st.columns(3)
            gender = c1.selectbox("เพศ", sv.EVENT_GENDERS, key="new_gender")
            level = c2.selectbox("ระดับ", list(sv.LEVELS), format_func=sv.LEVELS.get, key="new_level")
            detail = c3.text_input("รายละเอียด (ถ้ามี)", key="new_detail", placeholder="เช่น 100 ม.")
            c1, c2, c3, c4 = st.columns(4)
            d = c1.date_input("วันที่", value=date(2026, 11, 9), key="new_date", format="DD/MM/YYYY")
            start = c2.text_input("เวลาเริ่ม", value="09:00", key="new_start")
            dur = c3.number_input("นาที", 5, 600, 40, step=5, key="new_dur")
            venue = c4.text_input("สนาม", key="new_venue")
            if st.form_submit_button("เพิ่มรายการ", type="primary"):
                name = new_sport.strip() if sport_pick == "+ กีฬาใหม่" else sport_pick
                if not name:
                    st.error("กรอกชื่อกีฬาใหม่ก่อน")
                else:
                    try:
                        sv.add_event(engine, name, gender, level, d, start.strip(), int(dur), venue, detail)
                        st.success(f"เพิ่ม {sv.event_name(name, gender, level, detail)} แล้ว (สร้างรายการถ้วยให้ด้วย)")
                        st.rerun()
                    except ValueError as err:
                        st.error(str(err))

        st.markdown("#### แก้วัน เวลา สนาม หรือยกเลิกรายการ")
        st.caption("แก้ในตารางแล้วกดบันทึก · รายการที่ยกเลิกจะไม่นับถ้วยและไม่ขึ้นสติ๊กเกอร์")
        if not ev.empty:
            edit = pd.DataFrame({
                "id": ev["id"], "รายการ": ev["name"], "วันที่": ev["date"], "เริ่ม": ev["start"],
                "นาที": ev["duration_min"], "สนาม": ev["venue"], "ยกเลิก": ev["cancelled"],
            })
            out = st.data_editor(
                edit, hide_index=True, width="stretch", key="ev_editor", disabled=["id", "รายการ"],
                column_config={
                    "id": None,
                    "วันที่": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    "นาที": st.column_config.NumberColumn(min_value=5, max_value=600, step=5),
                },
            )
            if st.button("บันทึกการแก้ไขตาราง"):
                errors, n = [], 0
                for old, new in zip(edit.to_dict("records"), out.to_dict("records")):
                    if old != new:
                        try:
                            sv.update_event(engine, int(new["id"]), date=pd.Timestamp(new["วันที่"]).date(),
                                            start=str(new["เริ่ม"]).strip(), duration_min=int(new["นาที"]),
                                            venue=str(new["สนาม"] or ""), cancelled=bool(new["ยกเลิก"]))
                            n += 1
                        except ValueError as err:
                            errors.append(f"{new['รายการ']}: {err}")
                for e_ in errors:
                    st.error(e_)
                if n:
                    st.success(f"บันทึก {n} รายการ")
                    st.rerun()
