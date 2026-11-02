"""กระดานผลเรียลไทม์ — เปิดขึ้นจอใหญ่ได้ รีเฟรชเองทุก 30 วินาที"""
from datetime import datetime

import streamlit as st

from sportsday import services as sv, ui
from sportsday.reports import thai_date

engine = ui.get_engine()
st.title("กระดานผล")
st.caption("นับคะแนนจากจำนวนถ้วย (1 รายการ = 1 ถ้วย) · รีเฟรชอัตโนมัติทุก 30 วินาที")


@st.fragment(run_every="30s")
def board():
    stand = sv.standings(engine)
    prog = sv.progress(engine)
    ev = sv.events_df(engine, include_cancelled=False)

    cols = st.columns(len(stand) or 1)
    lead = stand.iloc[0]["trophies"] if not stand.empty else 0
    tie = (stand["trophies"] == lead).sum() > 1
    for col, r in zip(cols, stand.itertuples()):
        flag = "นำอยู่" if (r.trophies == lead and lead > 0 and not tie) else ("เสมอ" if tie and lead > 0 else "")
        col.markdown(
            f'<div class="score-card" style="--c:{r.hex}">'
            f'<div class="lbl">สี{r.name} {("· " + flag) if flag else ""}</div>'
            f'<div class="big-num">{r.trophies}</div><div class="lbl">ถ้วย</div></div>',
            unsafe_allow_html=True,
        )

    st.progress(prog["done"] / prog["total"] if prog["total"] else 0.0,
                text=f"แข่งจบแล้ว {prog['done']} จาก {prog['total']} รายการ · เหลือ {prog['left']} รายการ")

    if ev.empty:
        st.info("ยังไม่มีรายการแข่ง เพิ่มได้ที่หน้า ตารางแข่ง")
        return

    hexmap = ui.color_hex_map(engine)
    today = datetime.now().date()
    days = sorted(ev["date"].unique())
    show_day = today if today in days else next((d for d in days if d >= today), days[-1])

    left, right = st.columns([3, 2], gap="large")
    with left:
        head = "วันนี้" if show_day == today else "วันแข่งถัดไป"
        st.subheader(f"{head} · {thai_date(show_day)}")
        for r in ev[ev["date"] == show_day].itertuples():
            if isinstance(r.winner, str):
                badge = ui.chip(f"สี{r.winner} ได้ถ้วย", r.winner_hex) + (f" <span class='muted'>{r.score}</span>" if r.score else "")
            else:
                badge = "<span class='muted'>รอแข่ง</span>"
            st.markdown(
                f"**{r.start}–{r.end}** &nbsp; {r.sport} · {r.label} &nbsp; <span class='muted'>{r.venue}</span><br>{badge}",
                unsafe_allow_html=True,
            )
    with right:
        st.subheader("ผลล่าสุด")
        done = ev.dropna(subset=["winner"]).sort_values("recorded_at", ascending=False).head(6)
        if done.empty:
            st.caption("ยังไม่มีผลการแข่งขัน")
        for r in done.itertuples():
            st.markdown(
                f"{ui.chip(r.winner, hexmap.get(r.winner))} &nbsp; **{r.sport}** {r.label}"
                + (f" <span class='muted'>({r.score})</span>" if r.score else ""),
                unsafe_allow_html=True,
            )

    with st.expander("ถ้วยแยกตามชนิดกีฬา"):
        sports = list(dict.fromkeys(ev["sport"]))
        rows = []
        for sport in sports:
            g = ev[ev.sport == sport]
            row = {"ชนิดกีฬา": sport, "รายการ": len(g)}
            for r in stand.itertuples():
                row[f"สี{r.name}"] = int((g.winner == r.name).sum())
            row["รอแข่ง"] = int(g.winner.isna().sum())
            rows.append(row)
        st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(f"อัปเดตล่าสุด {datetime.now():%H:%M:%S} น. · รีเฟรชอัตโนมัติทุก 30 วินาที")


board()
