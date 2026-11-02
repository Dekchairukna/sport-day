"""ส่วนหน้าจอที่ใช้ซ้ำ ทั้งหน้ากลางของครู และหน้าของแต่ละสี

ทุกฟังก์ชันรับ color_id ได้: ถ้าใส่ จะแสดงและแก้ได้เฉพาะสีนั้น
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from . import services as sv, ui
from .reports import thai_date

SHIRT_SIZES = ["", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]


# ---------------------------------------------------------------- รายชื่อ

def member_list(engine, st_df: pd.DataFrame, key: str, show_color_filter: bool = True) -> None:
    ev = sv.events_df(engine, include_cancelled=False)
    roles = sv.roles_df(engine)
    colors = sv.list_colors(engine)
    ev_names = dict(zip(ev["id"], ev["name"]))
    cols = st.columns(4 if show_color_filter else 3)
    i = 0
    f_color = "ทุกสี"
    if show_color_filter:
        f_color = cols[0].selectbox("สี", ["ทุกสี"] + colors["name"].tolist() + ["ยังไม่ระบุ"], key=f"{key}_color")
        i = 1
    f_grade = cols[i].selectbox("ชั้น", ["ทุกชั้น"] + [f"ม.{g}" for g in sv.GRADES], key=f"{key}_grade")
    f_role = cols[i + 1].selectbox("หน้าที่ / รายการแข่ง",
                                   ["ทั้งหมด", "ยังไม่มีหน้าที่และไม่ได้ลงแข่ง"] + roles["name"].tolist() + list(ev_names.values()),
                                   key=f"{key}_role")
    q = cols[i + 2].text_input("ค้นหาชื่อ", key=f"{key}_q")
    v = st_df
    if f_color != "ทุกสี":
        v = v[v.color == f_color]
    if f_grade != "ทุกชั้น":
        v = v[v.grade == int(f_grade[2:])]
    if f_role == "ยังไม่มีหน้าที่และไม่ได้ลงแข่ง":
        v = v[(v.roles.map(len) == 0) & (v.event_ids.map(len) == 0)]
    elif f_role != "ทั้งหมด":
        ids_for = [k for k, n in ev_names.items() if n == f_role]
        v = v[v.roles.map(lambda rs: f_role in rs) | v.event_ids.map(lambda es: any(k in es for k in ids_for))]
    if q:
        v = v[v.full_name.str.contains(q.strip(), case=False, regex=False)]
    st.caption(f"แสดง {len(v)} คน")
    data = {"ชั้น": v["class"], "ชื่อ-สกุล": v["full_name"], "เพศ": v["gender"]}
    if show_color_filter:
        data["สี"] = v["color"]
    data.update({
        "หน้าที่": v["roles"].map(", ".join),
        "รายการแข่ง": v["event_ids"].map(lambda es: ", ".join(ev_names.get(k, "") for k in es)),
        "เสื้อ": v["shirt_size"] + v["shirt_paid"].map({True: " ✓จ่ายแล้ว", False: ""}),
        "หมายเหตุ": v["note"],
    })
    st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch", height=520)


# ---------------------------------------------------------------- แก้ไขสมาชิก

def member_editor(engine, st_df: pd.DataFrame, key: str) -> None:
    if st_df.empty:
        st.info("ยังไม่มีสมาชิก")
        return
    ev = sv.events_df(engine, include_cancelled=False)
    roles = sv.roles_df(engine)
    ev_names = dict(zip(ev["id"], ev["name"]))
    labels = dict(zip(st_df.id, st_df["class"] + "  " + st_df.full_name + " · สี" + st_df.color))
    sid = st.selectbox("เลือกนักเรียน (พิมพ์ค้นหาได้)", list(labels), format_func=labels.get, key=f"{key}_pick")
    s = st_df.set_index("id").loc[sid]
    st.markdown(ui.chip(f"สี{s['color']}", s["color_hex"] if isinstance(s["color_hex"], str) else None)
                + "  " + ui.tags(s["roles"] + [ev_names.get(k, "") for k in s["event_ids"]]),
                unsafe_allow_html=True)
    with st.form(f"{key}_form_{sid}"):
        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
        prefix = c1.text_input("คำนำหน้า", s["prefix"], key=f"{key}_pre_{sid}")
        first = c2.text_input("ชื่อ", s["first_name"], key=f"{key}_first_{sid}")
        last = c3.text_input("นามสกุล", s["last_name"], key=f"{key}_last_{sid}")
        gender = c4.selectbox("เพศ", sv.GENDERS, index=sv.GENDERS.index(s["gender"]), key=f"{key}_gender_{sid}")
        c1, c2, c3, c4 = st.columns(4)
        grade = c1.selectbox("ชั้น ม.", sv.GRADES, index=sv.GRADES.index(int(s["grade"])), key=f"{key}_grade_{sid}")
        room = c2.number_input("ห้อง", 1, 20, int(s["room"]), key=f"{key}_room_{sid}")
        shirt = c3.selectbox("ไซซ์เสื้อ", SHIRT_SIZES,
                             index=SHIRT_SIZES.index(s["shirt_size"]) if s["shirt_size"] in SHIRT_SIZES else 0,
                             key=f"{key}_shirt_{sid}")
        paid = c4.checkbox("จ่ายค่าเสื้อแล้ว", bool(s["shirt_paid"]), key=f"{key}_paid_{sid}")
        st.caption("การเปลี่ยนสีทำที่หน้า ย้ายสี (ครู) เพื่อเก็บประวัติ")
        sel_roles: list[int] = []
        for grp, glabel in sv.ROLE_GROUPS.items():
            r = roles[roles.grp == grp]
            rmap = dict(zip(r.id, r.name))
            sel_roles += st.multiselect(glabel, list(rmap), default=[k for k, n in rmap.items() if n in s["roles"]],
                                        format_func=rmap.get, key=f"{key}_roles_{grp}_{sid}")
        elig = ev[[sv.is_eligible(gender, grade, g, lv) for g, lv in zip(ev.gender, ev.level)]]
        emap = dict(zip(elig.id, elig.name + " (" + elig["date"].map(lambda d: f"{d:%d/%m}") + " " + elig.start + ")"))
        sel_events = st.multiselect(
            "นักกีฬา: รายการที่ลงแข่ง (แสดงเฉพาะรุ่นที่ตรงกับเพศและชั้น)", list(emap),
            default=[k for k in s["event_ids"] if k in emap], format_func=emap.get, key=f"{key}_events_{sid}",
        )
        note = st.text_input("หมายเหตุ", s["note"], key=f"{key}_note_{sid}")
        active = st.checkbox("ยังร่วมกิจกรรม (เอาออกถ้าย้ายโรงเรียน/ลาออก)", bool(s["active"]), key=f"{key}_active_{sid}")
        if st.form_submit_button("บันทึก", type="primary"):
            sv.update_student(engine, int(sid), prefix=prefix.strip(), first_name=first.strip(), last_name=last.strip(),
                              gender=gender, grade=int(grade), room=int(room), shirt_size=shirt, shirt_paid=paid,
                              note=note.strip(), active=active)
            sv.set_student_roles(engine, int(sid), sel_roles)
            for n in sv.set_student_events(engine, int(sid), sel_events):
                st.warning(f"ไม่ได้ลง {n} เพราะไม่ตรงรุ่น")
            for c in [c for c in sv.find_conflicts(engine) if c.student_id == int(sid)]:
                st.warning(f"เวลาชน: {c.event_a} กับ {c.event_b} · {c.when}")
            st.success("บันทึกแล้ว")


# ---------------------------------------------------------------- จัดนักกีฬา

def athlete_picker(engine, key: str, color_id: int | None = None) -> None:
    ev = sv.events_df(engine, include_cancelled=False)
    if ev.empty:
        st.info("ยังไม่มีรายการแข่ง")
        return
    colors = sv.list_colors(engine)
    if color_id is not None:
        colors = colors[colors.id == color_id]
    ent = sv.entries_df(engine)
    counts = ent.groupby(["event_id", "color"]).size()

    def count_for(eid) -> str:
        parts = [f"{c}:{int(counts.get((eid, c), 0))}" for c in colors["name"]]
        return " · ".join(parts)

    opts = dict(zip(ev["id"], ev["name"] + " · " + ev["date"].map(lambda d: thai_date(d, False)) + " " + ev["start"]
                    + ev["id"].map(lambda i: f"  [{count_for(i)} คน]") + ev["status"].map(lambda s: "  ✓จบแล้ว" if s == "จบแล้ว" else "")))
    eid = st.selectbox("รายการ", list(opts), format_func=opts.get, key=f"{key}_event")
    e = ev.set_index("id").loc[eid]
    st.caption(f"รับเฉพาะ: {sv.event_label(e.gender, e.level)} · แสดงเฉพาะนักเรียนที่ตรงรุ่น")
    studs = sv.students_df(engine)
    elig = studs[[sv.is_eligible(g, gr, e.gender, e.level) for g, gr in zip(studs.gender, studs.grade)]]
    current = sv.entries_df(engine, eid)
    current_ids = set(current.student_id)
    chosen: list[int] = []
    cols = st.columns(len(colors))
    for col, c in zip(cols, colors.itertuples()):
        pool = elig[elig.color_id == c.id]
        labels = dict(zip(pool.id, pool.full_name + " (" + pool["class"] + ")"))
        with col:
            st.markdown(ui.chip(f"สี{c.name}", c.hex) + f" <span class='muted'>มีสิทธิ์ {len(pool)} คน</span>",
                        unsafe_allow_html=True)
            chosen += st.multiselect(
                f"นักกีฬาสี{c.name}", list(labels), default=[i for i in labels if i in current_ids],
                format_func=labels.get, key=f"{key}_{eid}_{c.id}", label_visibility="collapsed",
            )
    if st.button("บันทึกรายชื่อนักกีฬา", type="primary", key=f"{key}_save"):
        if color_id is not None:  # สต๊าฟสีแก้ได้เฉพาะสีตัวเอง เก็บของสีอื่นไว้เหมือนเดิม
            cname = colors.iloc[0]["name"]
            chosen += current[current.color != cname].student_id.tolist()
        sv.set_event_entries(engine, int(eid), chosen)
        st.success("บันทึกรายชื่อนักกีฬาแล้ว")
        conf = [c for c in sv.find_conflicts(engine) if e["name"] in (c.event_a, c.event_b)]
        if color_id is not None:
            conf = [c for c in conf if c.color == colors.iloc[0]["name"]]
        for c in conf:
            st.warning(f"เวลาชน: {c.student} ({c.klass}) ลง {c.event_a} และ {c.event_b} · {c.when}")


def conflicts_table(conf: list) -> None:
    if not conf:
        st.success("ไม่พบนักกีฬาที่ลงแข่งเวลาซ้อนกัน")
        return
    st.warning(f"พบ {len(conf)} กรณี นักกีฬาคนเดียวลงสองรายการที่เวลาซ้อนกัน")
    st.dataframe(pd.DataFrame([{
        "นักกีฬา": c.student, "ชั้น": c.klass, "สี": c.color, "รายการที่ 1": c.event_a,
        "รายการที่ 2": c.event_b, "เวลา": c.when} for c in conf]), hide_index=True, width="stretch")


# ---------------------------------------------------------------- เช็คชื่อ

NEW_ACTIVITY = -1


def attendance_panel(engine, key: str, color_id: int | None = None) -> None:
    tab_check, tab_new, tab_sum = st.tabs(["เช็คชื่อ", "สร้างรอบใหม่", "สรุปการมา"])
    ses = sv.sessions_df(engine)
    if color_id is not None:
        ses = ses[ses.color_id == color_id]
    ev = sv.events_df(engine, include_cancelled=False)
    roles = sv.roles_df(engine)
    colors = sv.list_colors(engine)
    acts = sv.activities_df(engine)
    pick_key = f"{key}_session"

    with tab_new:
        # ไม่ใช้ st.form เพื่อให้ช่องเปลี่ยนตามตัวเลือกทันที · n เปลี่ยน key เพื่อล้างช่องหลังสร้างเสร็จ
        n = st.session_state.get(f"{key}_new_n", 0)
        k = f"{key}_n{n}"
        act_opts = {**dict(zip(acts["id"], acts["name"])), NEW_ACTIVITY: "+ เพิ่มกิจกรรมใหม่…"}
        c1, c2 = st.columns(2)
        act = c1.selectbox("กิจกรรม", list(act_opts), format_func=act_opts.get, key=f"{k}_act")
        new_act = ""
        if act == NEW_ACTIVITY:
            new_act = c2.text_input("ชื่อกิจกรรมใหม่", placeholder="เช่น ซ้อมแปรอักษร, ทำความสะอาดสแตนด์", key=f"{k}_actname")
        d = (c1 if act == NEW_ACTIVITY else c2).date_input("วันที่", value=datetime.now().date(),
                                                          format="DD/MM/YYYY", key=f"{k}_date")

        act_name = new_act.strip() if act == NEW_ACTIVITY else act_opts[act]
        default_scope = 2 if act_name == "ก่อนแข่งขัน" else 0
        scope = st.radio("เช็คใคร", ["ทุกคนในสี", "ตามหน้าที่", "นักกีฬาตามรายการแข่ง"],
                         index=default_scope, horizontal=True, key=f"{k}_scope_{default_scope}")
        c1, c2 = st.columns(2)
        event_id = role_id = None
        ev_opts = dict(zip(ev["id"], ev["name"]))
        role_opts = dict(zip(roles["id"], roles["name"]))
        if scope == "ตามหน้าที่":
            role_id = c1.selectbox("หน้าที่", list(role_opts), format_func=role_opts.get, key=f"{k}_role")
        elif scope == "นักกีฬาตามรายการแข่ง":
            event_id = c1.selectbox("รายการแข่ง", list(ev_opts), format_func=ev_opts.get, key=f"{k}_ev")
        if color_id is None:
            col_opts = {0: "ทุกสี", **dict(zip(colors["id"], "สี" + colors["name"]))}
            pick_color = c2.selectbox("สี", list(col_opts), format_func=col_opts.get, key=f"{k}_color")
        else:
            col_opts = dict(zip(colors["id"], "สี" + colors["name"]))
            pick_color = color_id
        title = st.text_input("ชื่อรอบ (ไม่ใส่ก็ได้ ระบบตั้งให้)", placeholder="เช่น ซ้อมเชียร์รอบเย็น", key=f"{k}_title")

        if st.button("สร้างรอบเช็คชื่อ", type="primary", key=f"{k}_go"):
            if not act_name:
                st.error("ใส่ชื่อกิจกรรมใหม่ก่อน")
            elif scope == "นักกีฬาตามรายการแข่ง" and event_id is None:
                st.error("ยังไม่มีรายการแข่งให้เลือก")
            elif scope == "ตามหน้าที่" and role_id is None:
                st.error("ยังไม่มีหน้าที่ให้เลือก")
            else:
                aid = sv.add_activity(engine, act_name) if act == NEW_ACTIVITY else int(act)
                # ชื่อกิจกรรมแสดงในวงเล็บเหลี่ยมหน้าชื่อรอบอยู่แล้ว ชื่ออัตโนมัติจึงบอกแค่ว่าเช็คใคร
                if event_id is not None:
                    auto = ev_opts[event_id]
                elif role_id is not None:
                    auto = role_opts[role_id]
                else:
                    auto = "ทั้งสี"
                if pick_color:
                    auto += f" ({col_opts[pick_color]})"
                st.session_state[pick_key] = sv.create_session(
                    engine, title.strip() or auto, d, event_id=event_id, role_id=role_id,
                    color_id=pick_color or None, activity_id=aid)
                st.session_state[f"{key}_new_n"] = n + 1
                st.session_state[f"{key}_flash"] = f"สร้างรอบ \"{title.strip() or auto}\" แล้ว ไปที่แท็บ เช็คชื่อ"
                st.rerun()
        if msg := st.session_state.pop(f"{key}_flash", None):
            st.success(msg)

    with tab_check:
        if ses.empty:
            st.info("ยังไม่มีรอบเช็คชื่อ สร้างได้ที่แท็บ สร้างรอบใหม่")
        else:
            act_list = ["ทุกกิจกรรม"] + list(dict.fromkeys(ses["activity"]))
            f_act = st.selectbox("กิจกรรม", act_list, key=f"{key}_fact")
            if f_act != "ทุกกิจกรรม":
                ses = ses[ses.activity == f_act]
            opts = dict(zip(ses["id"], "[" + ses["activity"] + "] " + ses["title"] + " · "
                            + pd.to_datetime(ses["date"]).dt.date.map(thai_date)))
            ids = list(opts)
            default = st.session_state.get(pick_key)
            sid = st.selectbox("รอบ", ids, index=ids.index(default) if default in ids else 0,
                               format_func=opts.get, key=f"{key}_pick")
            roster = sv.session_roster(engine, int(sid))
            if roster.empty:
                st.warning("รอบนี้ยังไม่มีรายชื่อ (เช่น ยังไม่ได้จัดนักกีฬาในรายการ หรือยังไม่มีใครได้หน้าที่นี้)")
            else:
                cnt = roster["status"].value_counts()
                m = st.columns(5)
                for col, s in zip(m, sv.ATT_STATUSES + [""]):
                    col.metric(s or "ยังไม่เช็ค", int(cnt.get(s, 0)))
                ed_key = f"{key}_editor_{sid}"
                if st.button("ทำเครื่องหมาย มา ทุกคนที่ยังไม่เช็ค", key=f"{key}_allin"):
                    roster.loc[roster["status"] == "", "status"] = "มา"
                    sv.save_attendance(engine, int(sid), roster.to_dict("records"))
                    st.session_state.pop(ed_key, None)
                    st.rerun()
                out = st.data_editor(
                    roster, key=ed_key, hide_index=True, width="stretch",
                    disabled=["student_id", "full_name", "class", "color"],
                    column_config={
                        "student_id": None, "full_name": "ชื่อ-สกุล", "class": "ชั้น", "color": "สี",
                        "status": st.column_config.SelectboxColumn("สถานะ", options=sv.ATT_STATUSES),
                        "note": "หมายเหตุ",
                    },
                )
                c1, c2 = st.columns([1, 3])
                if c1.button("บันทึกการเช็คชื่อ", type="primary", key=f"{key}_save"):
                    st.success(f"บันทึกแล้ว {sv.save_attendance(engine, int(sid), out.to_dict('records'))} คน")
                with c2.expander("ลบรอบนี้"):
                    if st.checkbox("ยืนยันการลบรอบและผลเช็คชื่อทั้งหมดของรอบนี้", key=f"{key}_del_ok_{sid}"):
                        if st.button("ลบรอบ", key=f"{key}_del_{sid}"):
                            sv.delete_session(engine, int(sid))
                            st.session_state.pop(pick_key, None)
                            st.rerun()

    with tab_sum:
        st.markdown("#### แยกตามกิจกรรม")
        ov = sv.activity_overview(engine, color_id)
        if ov.empty:
            st.caption("ยังไม่มีรอบเช็คชื่อ")
        else:
            st.dataframe(ov, hide_index=True, width="stretch",
                         column_config={"ร้อยละมา": st.column_config.ProgressColumn("ร้อยละมา", min_value=0, max_value=100, format="%d%%")})
        st.markdown("#### รายคน")
        sum_opts = {0: "ทุกกิจกรรม", **dict(zip(acts["id"], acts["name"]))}
        sum_act = st.selectbox("ดูเฉพาะกิจกรรม", list(sum_opts), format_func=sum_opts.get, key=f"{key}_sumact")
        summ = sv.attendance_summary(engine, sum_act or None)
        if color_id is not None and not summ.empty:
            cname = colors.set_index("id").loc[color_id, "name"]
            summ = summ[summ.color == cname]
        if summ.empty:
            st.info("ยังไม่มีข้อมูลการเช็คชื่อ")
        else:
            th = st.slider("แสดงคนที่มาน้อยกว่า (%)", 0, 100, 100, step=5, key=f"{key}_th")
            view = summ[summ["ร้อยละมา"] <= th].drop(columns="student_id")
            view = view.rename(columns={"full_name": "ชื่อ-สกุล", "class": "ชั้น", "color": "สี"})
            st.dataframe(view, hide_index=True, width="stretch",
                         column_config={"ร้อยละมา": st.column_config.ProgressColumn("ร้อยละมา", min_value=0, max_value=100, format="%d%%")})
            st.caption("นับ สาย เป็นการมา · ใช้ดูว่าใครขาดบ่อยเพื่อติดตามตัว")


# ---------------------------------------------------------------- เสื้อสี

def shirt_panel(st_df: pd.DataFrame) -> None:
    sizes = st_df["shirt_size"].replace("", "ยังไม่ระบุ")
    order = [s for s in SHIRT_SIZES[1:] + ["ยังไม่ระบุ"] if s in set(sizes)]
    cnt = sizes.value_counts().reindex(order, fill_value=0)
    paid = int(st_df.shirt_paid.sum())
    c = st.columns(3)
    c[0].metric("สมาชิก", len(st_df))
    c[1].metric("จ่ายแล้ว", paid)
    c[2].metric("ยังไม่จ่าย", len(st_df) - paid)
    if len(cnt):
        st.markdown("**ยอดสั่งแต่ละไซซ์**")
        st.dataframe(pd.DataFrame([cnt.to_dict()]), hide_index=True, width="stretch")
    unpaid = st_df[~st_df.shirt_paid]
    if len(unpaid):
        st.markdown("**ยังไม่จ่ายค่าเสื้อ**")
        st.dataframe(pd.DataFrame({"ชั้น": unpaid["class"], "ชื่อ-สกุล": unpaid["full_name"], "ไซซ์": unpaid["shirt_size"]}),
                     hide_index=True, width="stretch")
    st.caption("แก้ไซซ์และสถานะจ่ายเงินได้ที่แท็บ แก้ไขสมาชิก")
