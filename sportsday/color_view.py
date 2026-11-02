"""หน้าของแต่ละสี — สต๊าฟสีใช้ทำงานของสีตัวเองในที่เดียว"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from . import components as comp, services as sv, ui
from .reports import thai_date


def render(color_id: int) -> None:
    engine = ui.get_engine()
    colors = sv.list_colors(engine).set_index("id")
    if color_id not in colors.index:
        st.error("ไม่พบสีนี้")
        return
    c = colors.loc[color_id]
    stand = sv.standings(engine)
    rank = int(stand.index[stand.id == color_id][0]) + 1
    trophies = int(stand.loc[stand.id == color_id, "trophies"].iloc[0])
    st_df = sv.students_df(engine)
    mine = st_df[st_df.color_id == color_id]
    ev = sv.events_df(engine, include_cancelled=False)

    st.markdown(
        f'<div class="score-card" style="--c:{c["hex"]};margin-bottom:12px">'
        f'<div class="lbl">หน้าสต๊าฟ</div><div class="big-num">สี{c["name"]}</div>'
        f'<div class="lbl">{trophies} ถ้วย · อันดับ {rank} จาก {len(stand)} สี · สมาชิก {len(mine)} คน</div></div>',
        unsafe_allow_html=True,
    )

    if not ui.can_manage_color(color_id):
        wins = ev[ev.winner == c["name"]]
        st.subheader("ถ้วยที่ได้แล้ว")
        if wins.empty:
            st.caption("ยังไม่มี")
        for r in wins.itertuples():
            st.markdown(f"🏆 **{r.sport}** {r.label}" + (f" <span class='muted'>({r.score})</span>" if r.score else ""),
                        unsafe_allow_html=True)
        st.info(f"สต๊าฟสี{c['name']} เข้าสู่ระบบที่แถบด้านซ้าย เพื่อจัดนักกีฬา บันทึกผล เช็คชื่อ และดูงานที่ต้องทำ")
        return

    key = f"c{color_id}"
    todo = sv.color_todo(engine, color_id)
    tabs = st.tabs(["งานที่ต้องทำ", "จัดนักกีฬา", "รายชื่อสี", "แก้ไขสมาชิก", "เช็คชื่อ", "เสื้อสี"])

    # ------------------------------------------------------------ งานที่ต้องทำ
    with tabs[0]:
        m = st.columns(4)
        m[0].metric("รายการที่ยังไม่มีนักกีฬา", len(todo["events_without_athletes"]))
        m[1].metric("นักกีฬาเวลาชน", len(todo["conflicts"]))
        m[2].metric("หน้าที่ที่ยังไม่มีคน", len(todo["roles_empty"]))
        m[3].metric("ยังไม่จ่ายค่าเสื้อ", len(todo["unpaid"]))

        today = datetime.now().date()
        days = sorted(ev["date"].unique()) if not ev.empty else []
        nxt = next((d for d in days if d >= today), None)
        if nxt is not None:
            st.subheader(("วันนี้" if nxt == today else "วันแข่งถัดไป") + f" · {thai_date(nxt)}")
            ent = sv.entries_df(engine)
            ent = ent[ent.color == c["name"]]
            for r in ev[ev["date"] == nxt].itertuples():
                names = ent[ent.event_id == r.id]
                head = f"**{r.start}–{r.end}** {r.sport} · {r.label} <span class='muted'>{r.venue}</span>"
                if isinstance(r.winner, str):
                    head += " " + ui.chip(f"สี{r.winner} ได้ถ้วย", r.winner_hex)
                st.markdown(head, unsafe_allow_html=True)
                if names.empty:
                    st.markdown("<span style='color:#c42b2b'>ยังไม่มีนักกีฬาของสีเรา</span>", unsafe_allow_html=True)
                else:
                    st.markdown(ui.tags([f"{n} ({k})" for n, k in zip(names.full_name, names["class"])]),
                                unsafe_allow_html=True)

        if todo["events_without_athletes"]:
            with st.expander(f"รายการที่ยังไม่มีนักกีฬาสี{c['name']} ({len(todo['events_without_athletes'])})", expanded=True):
                st.markdown(ui.tags(todo["events_without_athletes"]), unsafe_allow_html=True)
                st.caption("จัดได้ที่แท็บ จัดนักกีฬา")
        if todo["conflicts"]:
            with st.expander(f"นักกีฬาเวลาชน ({len(todo['conflicts'])})", expanded=True):
                comp.conflicts_table(todo["conflicts"])
        if todo["roles_empty"]:
            with st.expander(f"หน้าที่ที่ยังไม่มีคนรับ ({len(todo['roles_empty'])})"):
                st.markdown(ui.tags(todo["roles_empty"]), unsafe_allow_html=True)
                st.caption("มอบหมายได้ที่แท็บ แก้ไขสมาชิก")
        st.caption(f"สมาชิกที่ยังไม่มีหน้าที่และไม่ได้ลงแข่ง {todo['no_role_no_event']} คน · ดูรายชื่อได้ที่แท็บ รายชื่อสี")

    with tabs[1]:
        comp.athlete_picker(engine, f"{key}_ath", color_id=color_id)
        st.markdown("#### เวลาชนของสีเรา")
        comp.conflicts_table(todo["conflicts"])

    with tabs[2]:
        comp.member_list(engine, mine, f"{key}_list", show_color_filter=False)

    with tabs[3]:
        comp.member_editor(engine, mine, f"{key}_edit")

    with tabs[4]:
        if ui.role() == "color" and not ui.has("attendance"):
            st.info("บัญชีนี้ยังไม่ได้รับสิทธิ์เช็คชื่อ ติดต่อผู้ดูแลระบบ")
        else:
            comp.attendance_panel(engine, f"{key}_att", color_id=color_id)

    with tabs[5]:
        comp.shirt_panel(mine)
