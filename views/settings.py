"""ตั้งค่า: ชื่องาน, สี, หน้าที่, นำเข้ารายชื่อและตารางแข่ง"""
import csv
import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from sportsday import services as sv, ui
from sportsday.db import colors as colors_tbl

ui.require("settings")
engine = ui.get_engine()
st.title("ตั้งค่า")

tab_gen, tab_import, tab_colors, tab_roles, tab_acts = st.tabs(["ทั่วไป", "นำเข้าข้อมูล", "สี", "หน้าที่", "กิจกรรมเช็คชื่อ"])

with tab_gen:
    with st.form("gen"):
        title = st.text_input("ชื่องาน", sv.get_setting(engine, "event_title"), key="set_title")
        school = st.text_input("ชื่อโรงเรียน", sv.get_setting(engine, "school_name"), key="set_school")
        if st.form_submit_button("บันทึก", type="primary"):
            sv.set_setting(engine, "event_title", title.strip())
            sv.set_setting(engine, "school_name", school.strip())
            st.success("บันทึกแล้ว · ใช้บนกระดานผล รายงาน และสติ๊กเกอร์")

with tab_import:
    st.markdown("#### นำเข้ารายชื่อนักเรียน (CSV)")
    st.caption("คอลัมน์: ชั้น, ห้อง, เลขที่, เลขประจำตัว, คำนำหน้า, ชื่อ, นามสกุล, เพศ, สี, ค่าเสื้อ, หมายเหตุ · "
               "ถ้าเลขประจำตัวซ้ำจะอัปเดตข้อมูลเดิม ไม่สร้างซ้ำ")
    template = "ชั้น,ห้อง,เลขที่,เลขประจำตัว,คำนำหน้า,ชื่อ,นามสกุล,เพศ,สี,ค่าเสื้อ,หมายเหตุ\nม.1,1,1,0000,เด็กชาย,ตัวอย่าง,นามสกุล,ชาย,ชมพู,จ่ายแล้ว,\n"
    st.download_button("ดาวน์โหลดแม่แบบ CSV", ("﻿" + template).encode("utf-8"), "แม่แบบรายชื่อ.csv", "text/csv")
    up = st.file_uploader("เลือกไฟล์ CSV", type=["csv"], key="imp_members")
    if up is not None:
        text = up.getvalue().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        st.dataframe(pd.DataFrame(rows).head(10), hide_index=True, width="stretch")
        st.caption(f"พบ {len(rows)} แถว (แสดง 10 แถวแรก)")
        if st.button("นำเข้ารายชื่อ", type="primary"):
            stats = sv.import_members_csv(engine, rows)
            st.success(f"เพิ่มใหม่ {stats['added']} · อัปเดต {stats['updated']} · ข้าม {stats['skipped']} แถว")

    st.markdown("#### นำเข้าตารางแข่ง (CSV)")
    st.caption("คอลัมน์: ชนิดกีฬา, เพศ (ชาย/หญิง/ผสม), ระดับ (ต้น/ปลาย/รวม), รายละเอียด, วันที่ (ปปปป-ดด-วว), เริ่ม (ชช:นน), นาที, สนาม · "
               "รายการจะถูกเพิ่มต่อจากของเดิม")
    up2 = st.file_uploader("เลือกไฟล์ตารางแข่ง", type=["csv"], key="imp_sched")
    if up2 is not None and st.button("นำเข้าตารางแข่ง"):
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as fh:
            fh.write(up2.getvalue())
        try:
            n = sv.import_schedule(engine, Path(fh.name))
            st.success(f"เพิ่ม {n} รายการ")
        except (ValueError, KeyError) as err:
            st.error(f"นำเข้าไม่สำเร็จ ตรวจรูปแบบไฟล์: {err}")

with tab_colors:
    cols = sv.list_colors(engine)
    st.caption("แก้สีที่แสดงบนกระดานผลได้ · ถ้าจะเพิ่มสีที่สาม ให้เพิ่มด้านล่าง")
    for c in cols.itertuples():
        c1, c2 = st.columns([3, 1])
        new_hex = c2.color_picker(f"สี{c.name}", c.hex, key=f"hex_{c.id}")
        c1.markdown(ui.chip(f"สี{c.name}", new_hex), unsafe_allow_html=True)
        if new_hex != c.hex:
            with engine.begin() as conn:
                conn.execute(colors_tbl.update().where(colors_tbl.c.id == c.id).values(hex=new_hex))
            st.rerun()
    with st.form("add_color", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        name = c1.text_input("ชื่อสีใหม่", key="nc_name")
        hx = c2.color_picker("รหัสสี", "#2a9d55", key="nc_hex")
        if st.form_submit_button("เพิ่มสี") and name.strip():
            sv.add_color(engine, name.strip().removeprefix("สี"), hx)
            st.rerun()

    st.caption("บัญชีสต๊าฟของแต่ละสี เพิ่มและตั้งรหัสผ่านได้ที่หน้า ผู้ใช้ (เลือกบทบาท สต๊าฟสี)")

with tab_roles:
    roles = sv.roles_df(engine)
    for grp, label in sv.ROLE_GROUPS.items():
        st.markdown(f"**{label}**")
        st.markdown(ui.tags(roles[roles.grp == grp]["name"].tolist()), unsafe_allow_html=True)
    with st.form("add_role", clear_on_submit=True):
        c1, c2 = st.columns([3, 2])
        name = c1.text_input("ชื่อหน้าที่ใหม่", placeholder="เช่น ฝ่ายสวัสดิการ", key="nr_name")
        grp = c2.selectbox("กลุ่ม", list(sv.ROLE_GROUPS), format_func=sv.ROLE_GROUPS.get, key="nr_grp")
        if st.form_submit_button("เพิ่มหน้าที่") and name.strip():
            if name.strip() in roles["name"].tolist():
                st.error("มีหน้าที่นี้อยู่แล้ว")
            else:
                sv.add_role(engine, name, grp)
                st.rerun()
    st.caption("นักกีฬาไม่ต้องเพิ่มเป็นหน้าที่ ระบบใช้รายการแข่งในตารางแข่งแทน")

with tab_acts:
    st.caption("กิจกรรมที่ใช้ตอนสร้างรอบเช็คชื่อ เช่น เช็ครวมสี ซ้อมเชียร์ · ครูและสต๊าฟสีเพิ่มกิจกรรมใหม่ได้ตอนสร้างรอบ "
               "· กิจกรรมที่มีรอบเช็คชื่อแล้วลบไม่ได้ ให้ซ่อนแทน (ข้อมูลเดิมยังอยู่)")
    acts = sv.activities_df(engine, include_inactive=True)
    for a in acts.itertuples():
        c1, c2, c3, c4 = st.columns([4, 2, 1.3, 1])
        name = c1.text_input("ชื่อ", a.name, key=f"act_name_{a.id}", label_visibility="collapsed")
        c2.caption(f"{a.rounds} รอบ")
        on = c3.toggle("ใช้งาน", value=bool(a.active), key=f"act_on_{a.id}")
        if name.strip() != a.name or on != bool(a.active):
            try:
                sv.update_activity(engine, int(a.id), name, on)
                st.rerun()
            except ValueError as err:
                st.error(str(err))
        if c4.button("ลบ", key=f"act_del_{a.id}", disabled=a.rounds > 0):
            sv.delete_activity(engine, int(a.id))
            st.rerun()
    with st.form("add_act", clear_on_submit=True):
        c1, c2 = st.columns([4, 1])
        nm = c1.text_input("กิจกรรมใหม่", placeholder="เช่น ซ้อมแปรอักษร", key="act_new", label_visibility="collapsed")
        if c2.form_submit_button("เพิ่ม") and nm.strip():
            sv.add_activity(engine, nm)
            st.rerun()
