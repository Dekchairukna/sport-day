"""เกียรติบัตร: พิมพ์ตามผลการแข่งขัน / เข้าร่วม / นักกีฬายอดเยี่ยม / ผู้ปฏิบัติหน้าที่ + เลือกนักกีฬายอดเยี่ยม"""
import base64
from datetime import date

import pandas as pd
import streamlit as st

from sportsday import reports as rp, services as sv, ui

ui.require("certificates")
engine = ui.get_engine()
st.title("เกียรติบัตร")

tab_print, tab_best, tab_cfg = st.tabs(["พิมพ์เกียรติบัตร", "นักกีฬายอดเยี่ยม", "ตั้งค่าเกียรติบัตร"])
colors = sv.list_colors(engine)

# ------------------------------------------------------------------ พิมพ์
with tab_print:
    kind = st.radio("ประเภท", list(rp.CERT_KINDS), format_func=rp.CERT_KINDS.get, key="ct_kind")
    c1, c2 = st.columns(2)
    color_opts = ["ทุกสี"] + colors["name"].tolist()
    color = c1.selectbox("สี", color_opts, format_func=lambda c: c if c == "ทุกสี" else f"สี{c}", key="ct_color")
    event_ids = role_names = None
    places = (1, 2, 3)
    if kind in ("medal", "join"):
        ev = sv.events_df(engine, include_cancelled=False)
        ev = ev[ev.winner.notna()]
        names = dict(zip(ev["id"], ev["name"]))
        event_ids = st.multiselect("รายการแข่ง (ไม่เลือก = ทุกรายการที่มีผลแล้ว)", list(names), format_func=names.get,
                                   key="ct_events") or None
        if kind == "medal":
            pick = c2.multiselect("อันดับ", [1, 2, 3], default=[1, 2, 3], format_func={1: "ชนะเลิศ", 2: "รองฯ อันดับ 1", 3: "รองฯ อันดับ 2"}.get,
                               key="ct_places")
            places = tuple(pick) or (1, 2, 3)
    elif kind == "role":
        role_names = st.multiselect("หน้าที่ (ไม่เลือก = ทุกหน้าที่)", sv.roles_df(engine)["name"].tolist(),
                                    key="ct_roles") or None
    issue = c2.date_input("วันที่ออกเกียรติบัตร", value=date.today(), format="DD/MM/YYYY", key="ct_date")

    items = rp.certificate_items(engine, kind, event_ids, None if color == "ทุกสี" else color, places, role_names)
    if items.empty:
        hint = {"medal": "ยังไม่มีผลการแข่งขัน หรือรายการที่มีผลยังไม่ได้จัดนักกีฬา",
                "join": "ยังไม่มีผลการแข่งขัน หรือรายการที่มีผลยังไม่ได้จัดนักกีฬา",
                "award": "ยังไม่ได้เลือกนักกีฬายอดเยี่ยม เลือกได้ที่แท็บ นักกีฬายอดเยี่ยม",
                "role": "ยังไม่มีนักเรียนที่ได้รับหน้าที่"}[kind]
        st.info(hint)
    else:
        st.markdown(f"**{len(items)} ใบ**")
        st.dataframe(items.rename(columns={"name": "ชื่อ-สกุล", "klass": "ชั้น", "color": "สี", "achievement": "รางวัล",
                                           "detail": "รายการ"}).drop(columns="student_id"),
                     hide_index=True, width="stretch", height=min(400, 38 + 35 * len(items)))
        prefix = sv.cert_settings(engine)["prefix"]
        if len(items) > 300:
            st.warning("เกิน 300 ใบ แนะนำให้แยกพิมพ์ทีละสีหรือทีละรายการ ไฟล์จะได้ไม่ใหญ่เกินไป")
        c1, c2 = st.columns(2)
        if c1.button(f"สร้างไฟล์ PDF ({len(items)} ใบ)", type="primary", key="ct_make", width="stretch"):
            with st.spinner("กำลังสร้างเกียรติบัตร…"):
                st.session_state["ct_pdf"] = rp.certificate_pdf(engine, items, issue)
                st.session_state["ct_reg"] = rp.certificate_register(items, prefix)
                st.session_state["ct_sig"] = (kind, tuple(items["student_id"]), tuple(items["detail"]))
        ready = st.session_state.get("ct_sig") == (kind, tuple(items["student_id"]), tuple(items["detail"]))
        if ready:
            c2.download_button("ดาวน์โหลดเกียรติบัตร PDF", st.session_state["ct_pdf"], "เกียรติบัตร.pdf",
                               "application/pdf", width="stretch", key="ct_dl")
            st.download_button("ดาวน์โหลดทะเบียนคุมเกียรติบัตร (Excel)", st.session_state["ct_reg"],
                               "ทะเบียนเกียรติบัตร.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ct_dlr")
        st.caption("A4 แนวนอน หน้าละ 1 ใบ · เลขที่เกียรติบัตรเรียงตามไฟล์ที่สร้าง ทะเบียนคุมใช้เลขชุดเดียวกัน")

# ------------------------------------------------------------------ นักกีฬายอดเยี่ยม
with tab_best:
    st.caption("ระบบเลือกให้อัตโนมัติ: คนที่ได้เหรียญรวม (ทอง + เงิน + ทองแดง) มากที่สุดของแต่ละเพศ · "
               "เท่ากันตัดสินด้วยทอง แล้วเงิน แล้วทองแดง · ถ้ายังเท่ากันได้รางวัลร่วม · อัปเดตเองทุกครั้งที่บันทึกผล")
    best = sv.best_athletes(engine)
    cols = st.columns(len(sv.BEST_TITLES))
    for col, (gender, title) in zip(cols, sv.BEST_TITLES.items()):
        with col.container(border=True):
            st.markdown(f"#### 🏅 {title}")
            win = best[best.title == title]
            if win.empty:
                st.caption("ยังไม่มีนักกีฬาที่ได้เหรียญ")
            for r in win.to_dict("records"):
                st.markdown(f"**{r['full_name']}**  \n<span class='muted'>{r['class']} · สี{r['color']}</span>",
                            unsafe_allow_html=True)
                st.markdown(f"<div class='medals'><span class='m g'>{r['ทอง']}</span><span class='m s'>{r['เงิน']}</span>"
                            f"<span class='m b'>{r['ทองแดง']}</span></div>"
                            f"<span class='muted'>รวม {r['รวมเหรียญ']} เหรียญ · ลงแข่ง {r['รายการที่ลง']} รายการ</span>",
                            unsafe_allow_html=True)
            if len(win) > 1:
                st.caption(f"คะแนนเท่ากัน {len(win)} คน ได้รางวัลร่วม")

    st.markdown("#### อันดับนักกีฬา")
    lb = sv.athlete_leaderboard(engine)
    c1, c2 = st.columns(2)
    g = c1.selectbox("เพศ", ["ทั้งหมด", "ชาย", "หญิง"], key="bt_g")
    lv = c2.selectbox("ระดับ", ["ทั้งหมด", "ม.ต้น", "ม.ปลาย"], key="bt_lv")
    view = lb
    if g != "ทั้งหมด":
        view = view[view.gender == g]
    if lv != "ทั้งหมด":
        view = view[view.grade <= 3] if lv == "ม.ต้น" else view[view.grade >= 4]
    view = view.reset_index(drop=True)
    if view.empty:
        st.info("ยังไม่มีนักกีฬาที่ลงแข่งในรายการที่มีผลแล้ว")
    else:
        top = view.head(20).copy()
        top.insert(0, "อันดับ", range(1, len(top) + 1))
        st.dataframe(top.drop(columns=["student_id", "gender", "grade"]).rename(
            columns={"full_name": "ชื่อ-สกุล", "class": "ชั้น", "color": "สี"}), hide_index=True, width="stretch")

    with st.expander("รางวัลพิเศษอื่น (กรรมการเลือกเอง เช่น ดาวรุ่ง น้ำใจนักกีฬา)"):
        c1, c2 = st.columns(2)
        title_opt = c1.selectbox("รางวัล", sv.AWARD_TITLES + ["อื่น ๆ (พิมพ์เอง)"], key="bt_title")
        title = c2.text_input("ชื่อรางวัล", key="bt_title_custom") if title_opt.startswith("อื่น") else title_opt
        pool = view if not view.empty else sv.students_df(engine).rename(columns={"id": "student_id"})
        opts = dict(zip(pool["student_id"], pool["full_name"] + " · " + pool["class"] + " · สี" + pool["color"]))
        sid = st.selectbox("นักเรียน", list(opts), format_func=opts.get, key="bt_student")
        note = st.text_input("หมายเหตุบนเกียรติบัตร (ไม่ใส่ก็ได้)", key="bt_note")
        if st.button("มอบรางวัล", type="primary", key="bt_add"):
            if (title or "").strip() in sv.BEST_TITLES.values():
                st.error("นักกีฬายอดเยี่ยมชาย/หญิง ระบบเลือกให้อัตโนมัติแล้ว")
            else:
                try:
                    sv.add_award(engine, title or "", int(sid), note)
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
        aw = sv.awards_df(engine)
        aw = aw[~aw["title"].isin(sv.BEST_TITLES.values())]
        for a in aw.to_dict("records"):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"🏅 **{a['title']}** — {a['full_name']} <span class='muted'>{a['class']} · สี{a['color']}</span>",
                        unsafe_allow_html=True)
            if c2.button("ลบ", key=f"bt_del_{a['id']}"):
                sv.delete_award(engine, int(a["id"]))
                st.rerun()
    st.caption("พิมพ์เกียรติบัตรได้ที่แท็บ พิมพ์เกียรติบัตร → นักกีฬายอดเยี่ยมและรางวัลพิเศษ")

# ------------------------------------------------------------------ ตั้งค่า
with tab_cfg:
    cfg = sv.cert_settings(engine)
    st.markdown("#### ผู้ลงนาม (สูงสุด 3 คน เรียงจากซ้ายไปขวา)")
    signers = st.data_editor(
        pd.DataFrame(cfg["signers"] or sv.DEFAULT_SIGNERS, columns=["name", "position"]),
        num_rows="dynamic", hide_index=True, width="stretch", key="cfg_signers",
        column_config={"name": st.column_config.TextColumn("ชื่อ-สกุล", help="เช่น นายสมชาย ใจดี"),
                       "position": st.column_config.TextColumn("ตำแหน่ง", help="เช่น ผู้อำนวยการโรงเรียน")},
    )
    date_text = st.text_input("ข้อความวันที่ (เว้นว่าง = ใช้วันที่ที่เลือกตอนพิมพ์)", cfg["date_text"],
                              placeholder="เช่น ให้ไว้ ณ วันที่ 15 พฤศจิกายน พ.ศ. 2569", key="cfg_date")
    prefix = st.text_input("คำนำหน้าเลขที่เกียรติบัตร (เว้นว่าง = ไม่พิมพ์เลขที่)", cfg["prefix"],
                           placeholder="เช่น กส.69/  → เลขที่ กส.69/1, กส.69/2 …", key="cfg_prefix")
    if st.button("บันทึกตั้งค่า", type="primary", key="cfg_save"):
        sv.save_cert_settings(engine, signers.to_dict("records"), date_text, prefix)
        st.success("บันทึกแล้ว")

    st.markdown("#### ตราโรงเรียน")
    if cfg["logo"]:
        st.image(base64.b64decode(cfg["logo"]), width=110)
    up = st.file_uploader("อัปโหลดตรา (PNG หรือ JPG ไม่เกิน 1 MB · PNG พื้นใสสวยที่สุด)", type=["png", "jpg", "jpeg"],
                          key="cfg_logo")
    c1, c2 = st.columns(2)
    if up is not None and c1.button("ใช้รูปนี้", key="cfg_logo_save"):
        data = up.getvalue()
        if len(data) > 1_000_000:
            st.error("ไฟล์ใหญ่เกิน 1 MB")
        else:
            sv.set_setting(engine, "cert_logo", base64.b64encode(data).decode())
            st.rerun()
    if cfg["logo"] and c2.button("ลบตรา", key="cfg_logo_del"):
        sv.set_setting(engine, "cert_logo", "")
        st.rerun()

    st.markdown("#### ตัวอย่าง")
    sample = pd.DataFrame([{"student_id": 0, "name": "เด็กหญิงตัวอย่าง ใจดี", "klass": "ม.2/1", "color": "ชมพู",
                            "achievement": "ได้รับรางวัลชนะเลิศ", "detail": "ประเภท วอลเลย์บอล หญิง ม.ต้น"}])
    st.download_button("ดาวน์โหลดตัวอย่าง PDF", rp.certificate_pdf(engine, sample), "ตัวอย่างเกียรติบัตร.pdf",
                       "application/pdf", key="cfg_sample")
