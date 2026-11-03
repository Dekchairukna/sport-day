"""สรุปเหรียญรายสี แยกชนิดกีฬา และอันดับนักกีฬา (อันดับนักกีฬาเห็นเมื่อเข้าสู่ระบบ)"""
import html

import streamlit as st

from sportsday import services as sv, ui

engine = ui.get_engine()
st.title("สรุปเหรียญ")
st.caption("ชนะเลิศ = ทอง · รองชนะเลิศอันดับ 1 = เงิน · รองชนะเลิศอันดับ 2 = ทองแดง · เรียงอันดับตามเหรียญทองก่อน")

mt = sv.medal_table(engine)
cols = st.columns(len(mt) or 1)
for col, r in zip(cols, mt.itertuples()):
    col.markdown(
        f'<div class="score-card" style="--c:{html.escape(r.hex)}">'
        f'<div class="lbl">อันดับ {r.อันดับ} · สี{html.escape(r.name)}</div>'
        f'<div class="medals"><span class="m g">{r.ทอง}</span><span class="m s">{r.เงิน}</span>'
        f'<span class="m b">{r.ทองแดง}</span></div>'
        f'<div class="lbl">ทอง · เงิน · ทองแดง · รวม {r.รวม} เหรียญ</div></div>',
        unsafe_allow_html=True,
    )

st.subheader("แยกตามชนิดกีฬา")
by = sv.medal_by_sport(engine)
if by.empty:
    st.caption("ยังไม่มีรายการแข่ง")
else:
    st.dataframe(by, hide_index=True, width="stretch")

can_see_names = ui.has("members") or ui.has("certificates")
st.subheader("อันดับนักกีฬา")
if not can_see_names:
    st.caption("รายชื่อนักกีฬาเห็นได้หลังเข้าสู่ระบบ (ครูที่มีสิทธิ์สมาชิกหรือเกียรติบัตร)")
    awards = sv.awards_df(engine)
else:
    lb = sv.athlete_leaderboard(engine)
    c1, c2, c3 = st.columns(3)
    g = c1.selectbox("เพศ", ["ทั้งหมด", "ชาย", "หญิง"], key="md_g")
    lv = c2.selectbox("ระดับ", ["ทั้งหมด", "ม.ต้น", "ม.ปลาย"], key="md_lv")
    only = c3.toggle("เฉพาะคนที่ได้เหรียญ", value=True, key="md_only")
    view = lb
    if g != "ทั้งหมด":
        view = view[view.gender == g]
    if lv != "ทั้งหมด":
        view = view[view.grade <= 3] if lv == "ม.ต้น" else view[view.grade >= 4]
    if only:
        view = view[(view["ทอง"] + view["เงิน"] + view["ทองแดง"]) > 0]
    if view.empty:
        st.caption("ยังไม่มีนักกีฬาตามที่เลือก")
    else:
        view = view.reset_index(drop=True)
        view.insert(0, "อันดับ", range(1, len(view) + 1))
        st.dataframe(
            view.drop(columns=["student_id", "gender", "grade"]).rename(
                columns={"full_name": "ชื่อ-สกุล", "class": "ชั้น", "color": "สี"}),
            hide_index=True, width="stretch",
        )
    awards = sv.awards_df(engine)

if can_see_names:
    best = sv.best_athletes(engine)
    awards = awards[~awards["title"].isin(sv.BEST_TITLES.values())]
    if not best.empty or not awards.empty:
        st.subheader("นักกีฬายอดเยี่ยมและรางวัลพิเศษ")
    for b in best.to_dict("records"):
        st.markdown(f"🏅 **{html.escape(b['title'])}** — {html.escape(b['full_name'])} "
                    f"<span class='muted'>{b['class']} · สี{html.escape(str(b['color']))} · "
                    f"เหรียญรวม {b['รวมเหรียญ']} (ทอง {b['ทอง']} เงิน {b['เงิน']} ทองแดง {b['ทองแดง']})</span>",
                    unsafe_allow_html=True)
    for a in awards.to_dict("records"):
        st.markdown(f"🏅 **{html.escape(a['title'])}** — {html.escape(str(a['full_name']))} "
                    f"<span class='muted'>{a['class']} · สี{html.escape(str(a['color']))}</span>",
                    unsafe_allow_html=True)
