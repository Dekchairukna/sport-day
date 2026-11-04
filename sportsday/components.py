"""ส่วนหน้าจอที่ใช้ซ้ำ ทั้งหน้ากลางของครู และหน้าของแต่ละสี

ทุกฟังก์ชันรับ color_id ได้: ถ้าใส่ จะแสดงและแก้ได้เฉพาะสีนั้น
"""
from __future__ import annotations

import html
import io
from datetime import datetime

import pandas as pd
import streamlit as st

from . import reports, services as sv, ui
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
        elig = ev[pd.Series([sv.is_eligible(gender, grade, g, lv) for g, lv in zip(ev.gender, ev.level)],
                            index=ev.index, dtype=bool)]
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
    # ใช้ Series ชนิด bool เสมอ: ถ้าเป็นลิสต์ว่าง pandas จะตีความเป็นการเลือกคอลัมน์ (ตอนยังไม่มีนักเรียน)
    elig = studs[pd.Series([sv.is_eligible(g, gr, e.gender, e.level) for g, gr in zip(studs.gender, studs.grade)],
                           index=studs.index, dtype=bool)]
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
        daily_rounds_form(engine, key, color_id)
        st.markdown("#### หรือสร้างรอบเดียว")
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
        if msg := st.session_state.pop(f"{key}_mv_flash", None):
            st.success(msg)
        if ses.empty:
            st.info("ยังไม่มีรอบเช็คชื่อ")
            daily_rounds_form(engine, f"{key}_quick", color_id, compact=True)
        else:
            today = datetime.now().date()
            days = sorted(ses["day"].unique(), reverse=True)
            if today not in days:
                with st.container(border=True):
                    st.caption("วันนี้ยังไม่มีรอบเช็คชื่อ")
                    daily_rounds_form(engine, f"{key}_quick", color_id, compact=True)
            picked = st.session_state.get(pick_key)
            picked_day = ses.set_index("id")["day"].get(picked) if picked in set(ses["id"]) else None
            day_default = picked_day or (today if today in days else days[0])
            day = st.selectbox("วันที่", days, index=days.index(day_default), format_func=thai_date,
                               key=f"{key}_day_{day_default}")
            day_ses = ses[ses["day"] == day]
            ids = day_ses["id"].tolist()
            labels = dict(zip(day_ses["id"], day_ses["title"].str.replace(r"\s*\(สี.*\)$", "", regex=True)
                              + " · " + day_ses["activity"]))
            if picked in ids:
                idx = ids.index(picked)
            elif day == today:  # เดารอบตามเวลาตอนนี้: ก่อน 10 โมง = รอบแรก, ก่อนบ่ายโมง = รอบสอง, หลังจากนั้น = รอบสาม
                h = datetime.now().hour
                idx = min(len(ids) - 1, 0 if h < 10 else 1 if h < 13 else 2)
            else:
                idx = 0
            sid = int(st.radio("รอบ", ids, index=idx, format_func=labels.get, horizontal=True,
                               key=f"{key}_round_{day}_{ids[idx]}"))
            st.session_state[pick_key] = sid
            checklist(engine, key, sid, color_id)

    with tab_sum:
        daily_panel(engine, key, color_id, colors)
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


def daily_rounds_form(engine, key: str, color_id: int | None, compact: bool = False) -> None:
    """สร้างรอบประจำวัน (เช่น เช้า ประชุมสี · สาย/บ่าย ซ้อมเชียร์) ทีละหลายวันในกดเดียว"""
    rounds = sv.get_daily_rounds(engine)
    text = " · ".join(f"{r['slot']}: {r['activity']}" for r in rounds)
    colors = sv.list_colors(engine)
    today = datetime.now().date()
    if compact:
        if st.button(f"สร้างรอบประจำวันของวันนี้ ({text})", type="primary", key=f"{key}_dq", width="stretch"):
            ids = [color_id] if color_id is not None else colors["id"].tolist()
            sv.create_daily_rounds(engine, today, today, ids)
            st.rerun()
        return
    with st.container(border=True):
        st.markdown("#### รอบประจำวัน")
        st.caption(f"{text} · เช็คทุกคนในสี · แก้ช่วงเวลาและกิจกรรมได้ที่ ตั้งค่า → กิจกรรมเช็คชื่อ")
        rng = st.date_input("ช่วงวันที่ (เลือกวันเดียวหรือหลายวัน เช่น ทั้งช่วงก่อนแข่ง)", value=(today, today),
                            format="DD/MM/YYYY", key=f"{key}_drange")
        if color_id is None:
            opts = dict(zip(colors["id"], "สี" + colors["name"]))
            pick = st.multiselect("สี", list(opts), default=list(opts), format_func=opts.get, key=f"{key}_dcolors")
        else:
            pick = [color_id]
        if st.button("สร้างรอบประจำวัน", type="primary", key=f"{key}_dgo", width="stretch"):
            start, end = (rng + (rng[0],))[:2] if isinstance(rng, tuple) and rng else (rng, rng)
            if not pick:
                st.error("เลือกสีอย่างน้อย 1 สี")
            else:
                try:
                    made, skip = sv.create_daily_rounds(engine, start, end, pick)
                    msg = f"สร้าง {made} รอบ" + (f" · ข้าม {skip} รอบที่มีอยู่แล้ว" if skip else "")
                    st.session_state[f"{key}_dflash"] = msg
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
        if msg := st.session_state.pop(f"{key}_dflash", None):
            st.success(msg + " · ไปเช็คได้ที่แท็บ เช็คชื่อ")


@st.fragment
def checklist(engine, key: str, sid: int, color_id: int | None = None) -> None:
    """เช็คชื่อแบบกดปุ่มรายคน ใช้บนมือถือได้ · กดแล้วบันทึกทันที
    เป็น fragment: กดปุ่มแล้วรันใหม่เฉพาะส่วนนี้ ไม่ต้องโหลดทั้งหน้า (เร็วขึ้นมากเมื่อฐานข้อมูลอยู่ไกล)"""
    roster = sv.session_roster(engine, sid)
    if roster.empty:
        st.warning("รอบนี้ยังไม่มีรายชื่อ (เช่น ยังไม่ได้จัดนักกีฬาในรายการ หรือยังไม่มีใครได้หน้าที่นี้)")
        return
    ver_key = f"{key}_ver_{sid}"  # เปลี่ยนเมื่อแก้ทีละหลายคน เพื่อให้ปุ่มทุกแถวอ่านค่าใหม่
    ver = st.session_state.get(ver_key, 0)

    cnt = roster["status"].value_counts()
    done = int((roster["status"] != "").sum())
    st.progress(done / len(roster), text=" · ".join(
        [f"{s} {int(cnt.get(s, 0))}" for s in sv.ATT_STATUSES] + [f"ยังไม่เช็ค {len(roster) - done}"]))

    c1, c2 = st.columns(2)
    q = c1.text_input("ค้นหาชื่อ", placeholder="พิมพ์ชื่อหรือนามสกุล", key=f"{key}_q_{sid}")
    classes = ["ทุกห้อง"] + sorted(roster["class"].unique(), key=lambda c: [int(x) if x.isdigit() else x
                                                                          for x in c.replace("ม.", "").split("/")])
    room = c2.selectbox("ห้อง", classes, key=f"{key}_room_{sid}")
    only_left = st.toggle("แสดงเฉพาะคนที่ยังไม่เช็ค", value=False, key=f"{key}_left_{sid}")

    view = roster
    if room != "ทุกห้อง":
        view = view[view["class"] == room]
    if q.strip():
        view = view[view["full_name"].str.contains(q.strip(), regex=False)]
    if only_left:
        view = view[view["status"] == ""]

    left = view[view["status"] == ""]
    if len(left) and st.button(f"มาทั้งหมด ({len(left)} คนที่ยังไม่เช็คในรายชื่อด้านล่าง)", key=f"{key}_all_{sid}",
                               width="stretch"):
        sv.mark_unchecked(engine, sid, left["student_id"], by=ui.editor_name())
        st.session_state[ver_key] = ver + 1
        st.rerun(scope="fragment")

    def save(student_id: int, wkey: str) -> None:
        sv.set_attendance_one(engine, sid, student_id, st.session_state.get(wkey), by=ui.editor_name())

    if view.empty:
        st.caption("ไม่มีรายชื่อตามที่กรอง")
    for r in view.itertuples():
        wkey = f"{key}_s{sid}_v{ver}_{r.student_id}"
        with st.container(key=f"attrow_{key}_{sid}_{r.student_id}"):
            st.markdown(f"**{html.escape(r.full_name)}** <span class='muted'>{r._3}</span>", unsafe_allow_html=True)
            st.segmented_control("สถานะ", sv.ATT_STATUSES, default=r.status or None, key=wkey,
                                 label_visibility="collapsed", on_change=save, args=(int(r.student_id), wkey))

    with st.expander("แก้แบบตาราง / ใส่หมายเหตุ (สะดวกบนคอมพิวเตอร์)"):
        ed_key = f"{key}_editor_{sid}_v{ver}"
        out = st.data_editor(
            roster, key=ed_key, hide_index=True, width="stretch",
            disabled=["student_id", "full_name", "class", "color"],
            column_config={
                "student_id": None, "full_name": "ชื่อ-สกุล", "class": "ชั้น", "color": "สี",
                "status": st.column_config.SelectboxColumn("สถานะ", options=sv.ATT_STATUSES),
                "note": "หมายเหตุ",
            },
        )
        if st.button("บันทึกตาราง", type="primary", key=f"{key}_save_{sid}"):
            sv.save_attendance(engine, sid, out.to_dict("records"), by=ui.editor_name())
            st.session_state[ver_key] = ver + 1
            st.rerun(scope="fragment")
    with st.expander("ย้ายผลเช็คชื่อรอบนี้ไปรอบอื่น (กรณีกรอกผิดรอบ)"):
        ses = sv.sessions_df(engine)
        if color_id is not None:
            ses = ses[ses.color_id == color_id]
        ses = ses[ses.id != sid]
        if ses.empty:
            st.caption("ไม่มีรอบอื่นให้ย้ายไป")
        else:
            opts = dict(zip(ses["id"], ses["day"].map(lambda d: thai_date(d, False)) + " · " + ses["title"]
                            + " · " + ses["activity"]))
            dst = st.selectbox("ย้ายไปรอบ", list(opts), format_func=opts.get, key=f"{key}_mv_dst_{sid}")
            mode = st.radio("ถ้ารอบปลายทางมีคนเช็คแล้ว", ["เขียนทับด้วยผลจากรอบนี้", "ใส่เฉพาะคนที่ยังไม่ได้เช็ค"],
                            key=f"{key}_mv_mode_{sid}")
            drop = st.checkbox("ลบรอบนี้ทิ้งหลังย้ายเสร็จ", value=True, key=f"{key}_mv_drop_{sid}")
            ok = st.checkbox("ยืนยันการย้าย", key=f"{key}_mv_ok_{sid}")
            if st.button("ย้ายผลเช็คชื่อ", type="primary", disabled=not ok, key=f"{key}_mv_go_{sid}"):
                n = sv.move_attendance(engine, sid, int(dst), overwrite=mode.startswith("เขียนทับ"), delete_src=drop,
                                       by=ui.editor_name())
                st.session_state[f"{key}_session"] = int(dst)
                st.session_state[f"{key}_mv_flash"] = f"ย้ายผลเช็คชื่อแล้ว {n} คน ไปที่รอบ {opts[dst]}"
                st.rerun()
    with st.expander("ประวัติการแก้ไขรอบนี้"):
        h = sv.attendance_history(engine, sid)
        if h.empty:
            st.caption("ยังไม่มีประวัติ (เริ่มเก็บตั้งแต่อัปเดตนี้)")
        else:
            st.dataframe(pd.DataFrame({
                "เวลา": pd.to_datetime(h["at"]).dt.strftime("%d/%m %H:%M"), "ชื่อ-สกุล": h["full_name"],
                "เดิม": h["old_status"].replace("", "-"), "เปลี่ยนเป็น": h["new_status"].replace("", "-"),
                "โดย": h["by_name"]}), hide_index=True, width="stretch", height=300)
    with st.expander("ลบรอบนี้"):
        if st.checkbox("ยืนยันการลบรอบและผลเช็คชื่อทั้งหมดของรอบนี้", key=f"{key}_del_ok_{sid}"):
            if st.button("ลบรอบ", key=f"{key}_del_{sid}"):
                sv.delete_session(engine, sid)
                st.session_state.pop(f"{key}_session", None)
                st.rerun()


def daily_panel(engine, key: str, color_id: int | None, colors: pd.DataFrame) -> None:
    """สรุปเช็คชื่อรายวันของแต่ละสี + รายชื่อคนที่ขาด/ลา/สาย"""
    st.markdown("#### สรุปรายวัน")
    pick = color_id
    if color_id is None:
        opts = {0: "ทุกสี", **dict(zip(colors["id"], "สี" + colors["name"]))}
        pick = st.selectbox("สี", list(opts), format_func=opts.get, key=f"{key}_dcolor") or None
    ds = sv.daily_summary(engine, pick)
    if ds.empty:
        st.caption("ยังไม่มีรอบเช็คชื่อ")
        return
    days = sorted(ds["day"].unique(), reverse=True)
    today = datetime.now().date()
    day = st.selectbox("วันที่", days, index=days.index(today) if today in days else 0, format_func=thai_date,
                       key=f"{key}_dday")
    one = ds[ds["day"] == day]
    pct = st.column_config.ProgressColumn("ร้อยละมา", min_value=0, max_value=100, format="%d%%")
    show = one.drop(columns=["session_id", "day"]).rename(columns={"color": "สี"})
    if pick is not None:
        show = show.drop(columns="สี")
    st.dataframe(show, hide_index=True, width="stretch", column_config={"ร้อยละมา": pct})

    ab = sv.absent_list(engine, one["session_id"])
    if pick is not None and not ab.empty:
        ab = ab[ab["color"] == colors.set_index("id").loc[pick, "name"]]
    label = f"รายชื่อคนที่ ขาด / ลา / สาย วันนี้ ({len(ab)} รายการ)" if day == today else \
        f"รายชื่อคนที่ ขาด / ลา / สาย ({len(ab)} รายการ)"
    with st.expander(label, expanded=False):
        if ab.empty:
            st.caption("ไม่มี")
        else:
            st.dataframe(ab.rename(columns={"status": "สถานะ", "full_name": "ชื่อ-สกุล", "class": "ชั้น", "color": "สี",
                                            "note": "หมายเหตุ"}), hide_index=True, width="stretch")

    with st.expander("ภาพรวมทุกวัน"):
        grid = ds.assign(ช่อง=ds["color"] + " · " + ds["รอบ"]) if pick is None else ds.assign(ช่อง=ds["รอบ"])
        piv = grid.pivot_table(index="day", columns="ช่อง", values="ร้อยละมา", aggfunc="first")
        piv = piv[list(dict.fromkeys(grid["ช่อง"]))].sort_index(ascending=False)  # เรียงรอบตามเวลา เช้า→บ่าย
        piv.index = [thai_date(d) for d in piv.index]
        st.caption("ร้อยละการมา (นับสายเป็นมา) ของแต่ละรอบ")
        st.dataframe(piv.map(lambda v: "" if pd.isna(v) else f"{int(v)}%"), width="stretch")
        buf = io.BytesIO()
        ds.drop(columns="session_id").rename(columns={"day": "วันที่", "color": "สี"}).to_excel(buf, index=False)
        st.download_button("ดาวน์โหลดสรุปรายวัน (Excel)", buf.getvalue(), "สรุปเช็คชื่อรายวัน.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key}_dxl")


# ---------------------------------------------------------------- แผนผังสแตนด์

def stand_grid_html(engine, color_id: int) -> str:
    """ภาพแผนผัง: แถวหลังอยู่บน แถวหน้า (A) อยู่ล่างติดสนาม · สีฟ้า = ชาย ชมพู = หญิง"""
    rows, cols = sv.stand_size(engine)
    seats = sv.stand_seats(engine, color_id)
    at = {(int(r["row"]), int(r["col"])): r for r in seats.to_dict("records")}
    cells = [f'<div class="sg-h"></div>'] + [f'<div class="sg-h">{k}</div>' for k in range(1, cols + 1)]
    for r in range(rows, 0, -1):
        cells.append(f'<div class="sg-h">{sv.ROW_LABELS[r - 1]}</div>')
        for k in range(1, cols + 1):
            s = at.get((r, k))
            if s is None:
                cells.append(f'<div class="sg-c empty"><span>{sv.seat_label(r, k)}</span></div>')
            else:
                g = "m" if s["gender"] == "ชาย" else "f"
                cells.append(f'<div class="sg-c {g}" title="{html.escape(str(s["full_name"]))}">'
                             f'<span>{sv.seat_label(r, k)}</span><b>{html.escape(str(s["first_name"]))}</b>'
                             f'<i>{html.escape(str(s["class"]))}</i></div>')
    return (f'<div class="sg-wrap"><div class="sg" style="grid-template-columns: 28px repeat({cols}, minmax(72px, 1fr))">'
            + "".join(cells) + f'</div><div class="sg-field" style="margin-left:32px">ด้านหน้า · สนาม</div></div>')


def stand_panel(engine, key: str, color_id: int) -> None:
    rows, cols = sv.stand_size(engine)
    seats = sv.stand_seats(engine, color_id)
    cand = sv.stand_candidates(engine, color_id)
    seated = set(seats["student_id"])
    waiting = cand[~cand.id.isin(seated)]
    st.markdown(ui.tags([f"จัดแล้ว {len(seats)} / {rows * cols} ที่", f"มีหน้าที่{sv.STAND_ROLE} {len(cand)} คน",
                         f"ยังไม่มีที่นั่ง {len(waiting)} คน"]), unsafe_allow_html=True)
    st.markdown(stand_grid_html(engine, color_id), unsafe_allow_html=True)
    st.caption(f"{rows} แถว แถวละ {cols} ที่ · แถว A อยู่หน้าสุดติดสนาม · ฟ้า = ชาย ชมพู = หญิง · "
               f"เลือกคนจากสมาชิกที่มีหน้าที่ \"{sv.STAND_ROLE}\" (ตั้งได้ที่แท็บ แก้ไขสมาชิก)")
    if msg := st.session_state.pop(f"{key}_flash", None):
        st.success(msg)
    st.download_button("ดาวน์โหลดแผนผัง PDF (A4 แนวนอน)", reports.stand_pdf(engine, [color_id]),
                       "แผนผังสแตนด์.pdf", "application/pdf", key=f"{key}_pdf")

    with st.expander("จัดที่นั่งอัตโนมัติ", expanded=seats.empty):
        mode = st.radio("วิธีเรียง", ["ชั้น", "สลับชายหญิง"], horizontal=True, key=f"{key}_mode",
                        format_func={"ชั้น": "เรียงตามชั้น/ห้อง", "สลับชายหญิง": "สลับชาย-หญิง"}.get)
        only = st.checkbox(f"เฉพาะคนที่มีหน้าที่ {sv.STAND_ROLE}", value=True, key=f"{key}_only")
        keep = st.checkbox("เก็บที่นั่งที่จัดไว้แล้ว เติมเฉพาะที่ว่าง", value=True, key=f"{key}_keep")
        if st.button("จัดที่นั่ง", type="primary", key=f"{key}_auto"):
            n, left = sv.auto_fill_stand(engine, color_id, mode, keep, only)
            st.session_state[f"{key}_flash"] = f"จัดที่นั่งเพิ่ม {n} คน" + (f" · ที่นั่งไม่พอ {left} คน" if left else "")
            st.rerun()

    with st.expander("สลับที่นั่ง 2 คน (สะดวกบนมือถือ)"):
        labels = {(int(r["row"]), int(r["col"])): f"{sv.seat_label(int(r['row']), int(r['col']))} · {r['full_name']}"
                  for r in seats.to_dict("records")}
        allspots = {(r, k): labels.get((r, k), f"{sv.seat_label(r, k)} · (ว่าง)")
                    for r in range(1, rows + 1) for k in range(1, cols + 1)}
        c1, c2 = st.columns(2)
        a = c1.selectbox("ที่นั่งที่ 1", list(allspots), format_func=allspots.get, key=f"{key}_sw_a")
        b = c2.selectbox("ที่นั่งที่ 2", list(allspots), format_func=allspots.get, index=1, key=f"{key}_sw_b")
        if st.button("สลับ", key=f"{key}_swap", disabled=a == b):
            cur = {(int(r["row"]), int(r["col"])): int(r["student_id"]) for r in seats.to_dict("records")}
            va, vb = cur.pop(a, None), cur.pop(b, None)
            if va:
                cur[b] = va
            if vb:
                cur[a] = vb
            sv.save_stand(engine, color_id, cur)
            st.session_state[f"{key}_flash"] = f"สลับ {sv.seat_label(*a)} กับ {sv.seat_label(*b)} แล้ว"
            st.rerun()

    with st.expander("แก้ทั้งแผนผังแบบตาราง (สะดวกบนคอมพิวเตอร์)"):
        members = sv.students_df(engine)
        members = members[members.color_id == color_id].sort_values(["grade", "room", "first_name"])
        name_of = dict(zip(members["id"], members["full_name"] + " (" + members["class"] + ")"))
        id_of = {v: k for k, v in name_of.items()}
        grid = pd.DataFrame("", index=[sv.ROW_LABELS[r - 1] for r in range(1, rows + 1)],
                            columns=[str(k) for k in range(1, cols + 1)])
        for r in seats.to_dict("records"):
            if int(r["student_id"]) in name_of:
                grid.iloc[int(r["row"]) - 1, int(r["col"]) - 1] = name_of[int(r["student_id"])]
        opts = [""] + list(name_of.values())
        out = st.data_editor(grid, key=f"{key}_grid_{len(seats)}", width="stretch",
                             column_config={c: st.column_config.SelectboxColumn(c, options=opts, width="small")
                                            for c in grid.columns})
        st.caption("แถว A = หน้าสุด · เลือกชื่อในช่อง หรือเลือกช่องว่างเพื่อเอาออก แล้วกดบันทึก")
        if st.button("บันทึกแผนผัง", type="primary", key=f"{key}_save"):
            new = {(i + 1, int(c)): id_of[v] for i, (_, row) in enumerate(out.iterrows())
                   for c, v in row.items() if v and v in id_of}
            try:
                n = sv.save_stand(engine, color_id, new)
                st.session_state[f"{key}_flash"] = f"บันทึกแผนผังแล้ว {n} คน"
                st.rerun()
            except ValueError as err:
                st.error(str(err))

    if not waiting.empty:
        with st.expander(f"ยังไม่มีที่นั่ง ({len(waiting)} คน)"):
            st.markdown(ui.tags([f"{n} ({k})" for n, k in zip(waiting.full_name, waiting["class"])]),
                        unsafe_allow_html=True)
    with st.expander("ล้างแผนผังทั้งหมด"):
        if st.checkbox("ยืนยันล้างที่นั่งทุกที่ของสีนี้", key=f"{key}_clr_ok") and \
                st.button("ล้างแผนผัง", key=f"{key}_clr"):
            sv.save_stand(engine, color_id, {})
            st.rerun()


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
