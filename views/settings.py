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

tab_names = ["ทั่วไป", "นำเข้าข้อมูล", "สี", "หน้าที่", "กิจกรรมเช็คชื่อ"] + (["สำรองข้อมูล"] if ui.is_admin() else [])
tab_gen, tab_import, tab_colors, tab_roles, tab_acts, *tab_backup = st.tabs(tab_names)

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
    st.markdown("#### รอบประจำวัน")
    st.caption("ใช้กับปุ่ม สร้างรอบประจำวัน ในหน้าเช็คชื่อ (เช็คทุกคนในสี) · เพิ่ม/ลบแถวได้ เรียงตามลำดับเวลาในวัน")
    act_names = sv.activities_df(engine)["name"].tolist()
    cur = pd.DataFrame(sv.get_daily_rounds(engine))
    edited = st.data_editor(
        cur, key="daily_rounds_ed", num_rows="dynamic", hide_index=True, width="stretch",
        column_config={
            "slot": st.column_config.TextColumn("ช่วงเวลา", help="เช่น เช้า สาย บ่าย เย็น", required=True),
            "activity": st.column_config.SelectboxColumn("กิจกรรม", options=act_names, required=True),
        },
    )
    if st.button("บันทึกรอบประจำวัน", type="primary", key="daily_rounds_save"):
        try:
            sv.set_daily_rounds(engine, edited.to_dict("records"))
            st.success("บันทึกแล้ว")
        except ValueError as err:
            st.error(str(err))
    st.markdown("#### รายการกิจกรรม")
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

if tab_backup:
    from datetime import datetime

    from sqlalchemy import create_engine

    from sportsday.db import local_db_path

    TABLE_TH = {"students": "นักเรียน", "events": "รายการแข่ง", "results": "ผลแข่ง", "entries": "นักกีฬา",
                "attendance": "เช็คชื่อ (คน-ครั้ง)", "att_sessions": "รอบเช็คชื่อ", "users": "ผู้ใช้", "awards": "รางวัลพิเศษ"}

    def show_counts(counts: dict) -> str:
        return " · ".join(f"{v} {counts.get(k, 0)}" for k, v in TABLE_TH.items())

    with tab_backup[0]:
        temp = ui.storage_is_temporary(engine)
        if engine.dialect.name == "postgresql":
            st.success("ข้อมูลเก็บในฐานข้อมูลถาวร (PostgreSQL) · อัปเดตโค้ดหรือรีบูตแอปแล้วข้อมูลไม่หาย")
        elif temp:
            st.error("ข้อมูลบนเว็บนี้เก็บในไฟล์ชั่วคราวบนเซิร์ฟเวอร์ Streamlit และจะหายเมื่อแอปเริ่มใหม่ "
                     "(เช่น แอปหลับแล้วถูกปลุก หรือกด Reboot) · ดาวน์โหลดสำรองไว้ แล้วตั้ง db_url ตามขั้นตอนด้านล่าง")
        else:
            st.info("ข้อมูลเก็บในไฟล์บนคอมพิวเตอร์เครื่องนี้ (data/sportsday.db)")
        st.caption("ข้อมูลตอนนี้: " + show_counts(sv.data_counts(engine)))

        st.markdown("#### ดาวน์โหลดสำรองข้อมูล")
        st.caption("ไฟล์เดียวมีทุกอย่าง: นักเรียน ตารางแข่ง ผลแข่ง เช็คชื่อ ผู้ใช้ ตั้งค่า · เก็บไว้ในที่ปลอดภัย "
                   "เพราะมีข้อมูลนักเรียนและรหัสผ่านแบบเข้ารหัส")
        st.download_button("ดาวน์โหลดไฟล์สำรอง", sv.export_backup(engine),
                           f"สำรองกีฬาสี_{datetime.now():%Y-%m-%d_%H%M}.json", "application/json",
                           type="primary", key="bk_dl")

        legacy = local_db_path()
        if engine.dialect.name == "postgresql" and legacy.exists():
            st.markdown("#### ย้ายข้อมูลจากไฟล์เดิมบนเซิร์ฟเวอร์")
            try:
                from sportsday.db import make_engine as _open
                old = _open(f"sqlite:///{legacy}")  # เปิดแบบเติมตาราง/คอลัมน์ที่ขาด (ไฟล์เดิมอาจเป็นโครงสร้างรุ่นเก่า)
                old_counts = sv.data_counts(old)
            except Exception:  # ไฟล์เดิมเปิดไม่ได้หรือโครงสร้างเก่าเกินไป
                old, old_counts = None, {}
            if old is not None and old_counts.get("students", 0):
                st.caption("พบข้อมูลในไฟล์เดิม: " + show_counts(old_counts))
                already = sv.data_counts(engine).get("students", 0) > 0
                box = st.expander("ย้ายซ้ำทั้งหมด (ระวัง: ทับข้อมูลที่กรอกหลังย้ายแล้ว)") if already else st.container()
                with box:
                    if already:
                        st.error("ฐานข้อมูลถาวรมีข้อมูลแล้ว ถ้าย้ายซ้ำ ข้อมูลที่กรอกหลังจากย้ายครั้งก่อนจะหายทั้งหมด "
                                 "ถ้าต้องการแก้เฉพาะบางรอบ ใช้ ดึงผลเช็คชื่อรอบเดียว ด้านล่างแทน")
                    else:
                        st.warning("ข้อมูลในฐานข้อมูลถาวรตอนนี้จะถูกแทนที่ด้วยข้อมูลจากไฟล์เดิมทั้งหมด")
                    ok = st.checkbox("ยืนยันการย้ายข้อมูล", key="bk_mig_ok")
                    if st.button("ย้ายข้อมูลจากไฟล์เดิมเข้าฐานข้อมูลถาวร", type="primary", disabled=not ok, key="bk_mig"):
                        counts = sv.import_backup(engine, sv.export_backup(old))
                        st.session_state.clear()  # ผู้ใช้ชุดใหม่: เข้าสู่ระบบใหม่ด้วยบัญชีเดิมบนเว็บ
                        st.session_state["bk_flash"] = "ย้ายแล้ว: " + show_counts(counts)
                        st.rerun()
            else:
                st.caption("ไม่พบข้อมูลในไฟล์เดิม (ไฟล์อาจหายไปแล้วเพราะแอปเริ่มใหม่) ใช้การกู้คืนจากไฟล์สำรองด้านล่างแทน")

            if old is not None and old_counts.get("att_sessions", 0):
                st.markdown("#### ดึงผลเช็คชื่อรอบเดียวจากไฟล์เดิม")
                st.caption("ใช้เมื่อผลเช็คชื่อรอบใดรอบหนึ่งถูกกดทับหรือหาย · แทนที่เฉพาะรอบที่เลือก รอบอื่นไม่เปลี่ยน")
                old_eng = old
                sv.clear_cache()
                old_ses = sv.sessions_df(old_eng)
                sv.clear_cache()
                cur_ses = sv.sessions_df(engine)
                with old_eng.connect() as _c:
                    from sqlalchemy import func as _f, select as _s
                    from sportsday import db as _db
                    cnt = dict(_c.execute(_s(_db.attendance.c.session_id, _f.count()).group_by(_db.attendance.c.session_id)).all())
                lab = lambda df: df["day"].map(lambda d: d.strftime("%d/%m")) + " · " + df["title"] + " · " + df["activity"]
                o_opts = dict(zip(old_ses["id"], lab(old_ses) + old_ses["id"].map(lambda i: f"  ({cnt.get(i, 0)} คน)")))
                c_opts = dict(zip(cur_ses["id"], lab(cur_ses)))
                if not c_opts:
                    st.caption("ฐานข้อมูลตอนนี้ยังไม่มีรอบเช็คชื่อ ย้ายข้อมูลทั้งหมดก่อน")
                else:
                    osid = st.selectbox("รอบในไฟล์เดิม", list(o_opts), format_func=o_opts.get, key="rr_old")
                    o = old_ses.set_index("id").loc[osid]
                    match = cur_ses[(cur_ses["day"] == o["day"]) & (cur_ses["title"] == o["title"])
                                    & (cur_ses["color_id"].fillna(0) == (o["color_id"] if pd.notna(o["color_id"]) else 0))]
                    ids = list(c_opts)
                    default = ids.index(int(match.iloc[0]["id"])) if not match.empty else 0
                    csid = st.selectbox("ใส่ลงรอบตอนนี้", ids, index=default, format_func=c_opts.get, key=f"rr_cur_{osid}")
                    cmp_ = sv.round_compare(engine, old_eng, int(osid), int(csid))
                    st.caption(f"ในไฟล์เดิม {cmp_['in_file']} คน · ตอนนี้ {cmp_['now']} คน · ต่างกัน {cmp_['differ']} คน")
                    ok = st.checkbox("ยืนยันแทนที่ผลเช็คชื่อรอบนี้ด้วยข้อมูลจากไฟล์เดิม", key="rr_ok")
                    if st.button("ดึงผลรอบนี้กลับมา", type="primary", disabled=not ok or cmp_["differ"] == 0, key="rr_go"):
                        n = sv.restore_round(engine, old_eng, int(osid), int(csid), by=ui.editor_name())
                        st.success(f"ดึงกลับมาแล้ว {n} คน")

        st.markdown("#### กู้คืนจากไฟล์สำรอง")
        up = st.file_uploader("เลือกไฟล์สำรอง (.json)", type=["json"], key="bk_up")
        if up is not None:
            try:
                st.caption("ในไฟล์มี: " + show_counts(sv.backup_summary(up.getvalue())))
                st.warning("ข้อมูลทั้งหมดตอนนี้จะถูกแทนที่ด้วยข้อมูลในไฟล์ แล้วต้องเข้าสู่ระบบใหม่")
                ok = st.checkbox("ยืนยันการกู้คืน", key="bk_rs_ok")
                if st.button("กู้คืนข้อมูล", type="primary", disabled=not ok, key="bk_rs"):
                    counts = sv.import_backup(engine, up.getvalue())
                    st.session_state.clear()
                    st.session_state["bk_flash"] = "กู้คืนแล้ว: " + show_counts(counts)
                    st.rerun()
            except (ValueError, KeyError) as err:
                st.error(f"อ่านไฟล์ไม่ได้: {err}")
