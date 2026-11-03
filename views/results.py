"""บันทึกผลการแข่งขัน — ครูรักษ์และคณะกรรมการ"""
from datetime import datetime

import streamlit as st

from sportsday import services as sv, ui
from sportsday.reports import thai_date

ui.require("results")
engine = ui.get_engine()
st.title("บันทึกผลการแข่งขัน")

ev = sv.events_df(engine, include_cancelled=False)
if ev.empty:
    st.info("ยังไม่มีรายการแข่ง")
    st.stop()

colors = sv.list_colors(engine)
days = sorted(ev["date"].unique())
today = datetime.now().date()
day_idx = days.index(today) if today in days else 0
c1, c2 = st.columns([1, 2])
day = c1.selectbox("วันที่", days, index=day_idx, format_func=thai_date, key="res_day")
only_pending = c1.toggle("แสดงเฉพาะที่ยังไม่มีผล", value=False, key="res_pending")
g = ev[ev["date"] == day]
if only_pending:
    g = g[g.winner.isna()]
if g.empty:
    c2.success("ทุกรายการของวันนี้มีผลแล้ว")
    st.stop()

opts = dict(zip(g["id"], g["start"] + "  " + g["name"] + g["winner"].map(lambda w: f"  ✓ สี{w}" if isinstance(w, str) else "")))
eid = c2.selectbox("รายการ", list(opts), format_func=opts.get, key="res_event")
e = ev.set_index("id").loc[eid]

st.markdown(f"### {e['name']}")
st.caption(f"{thai_date(e['date'])} · {e['start']}–{e['end']} · {e['venue']} · นักกีฬาในระบบ {e['athletes']} คน")
if isinstance(e["winner"], str):
    st.markdown(
        f"ผลปัจจุบัน: {ui.chip('สี' + e['winner'] + ' ได้ถ้วย', e['winner_hex'])} "
        f"<span class='muted'>{e['score'] or ''} · บันทึกโดย {e['recorded_by'] or '-'} "
        f"{e['recorded_at']:%d/%m %H:%M} น.</span>",
        unsafe_allow_html=True,
    )

# สต๊าฟสีบันทึกผลใหม่ได้ แต่แก้หรือลบได้เฉพาะผลที่ตัวเองบันทึก กันแก้ผลของคนอื่น
locked = (ui.role() == "color" and isinstance(e["winner"], str)
          and (e["recorded_by"] or "") != ui.editor_name())
if locked:
    st.info("รายการนี้มีผลแล้วโดยผู้บันทึกคนอื่น ถ้าผลผิดให้แจ้งครูหรือกรรมการแก้ไข")
    st.stop()

with st.form(f"res_form_{eid}"):
    names = colors["name"].tolist()
    cur = names.index(e["winner"]) if isinstance(e["winner"], str) else None
    winner = st.radio("สีที่ชนะ (ได้ถ้วย)", names, index=cur, horizontal=True, key=f"res_win_{eid}")
    c1, c2 = st.columns(2)
    score = c1.text_input("สกอร์ (ถ้ามี)", value=e["score"] if isinstance(e["score"], str) else "",
                          placeholder="เช่น 2-1 เซต", key=f"res_score_{eid}")
    note = c2.text_input("หมายเหตุ", value=e["result_note"] if isinstance(e["result_note"], str) else "",
                         key=f"res_note_{eid}")
    second = third = None
    if len(names) > 2:  # มีมากกว่า 2 สี: ระบุรองชนะเลิศเพื่อนับเหรียญเงิน/ทองแดง
        cur_pl = sv.event_places(engine)
        cur_pl = dict(zip(cur_pl[cur_pl.event_id == eid].place, cur_pl[cur_pl.event_id == eid].color_id))
        id2name = dict(zip(colors["id"], colors["name"]))
        opts = ["-"] + names
        c1, c2 = st.columns(2)
        second = c1.selectbox("รองชนะเลิศอันดับ 1 (เหรียญเงิน)", opts, key=f"res_2_{eid}",
                              index=opts.index(id2name.get(cur_pl.get(2), "-")))
        third = c2.selectbox("รองชนะเลิศอันดับ 2 (เหรียญทองแดง)", opts, key=f"res_3_{eid}",
                             index=opts.index(id2name.get(cur_pl.get(3), "-")))
        second, third = (None if second == "-" else second), (None if third == "-" else third)
    else:
        st.caption("มี 2 สี: สีที่ชนะได้เหรียญทอง อีกสีได้เหรียญเงินอัตโนมัติ")
    if st.form_submit_button("บันทึกผล", type="primary"):
        if winner is None:
            st.error("เลือกสีที่ชนะก่อนบันทึก")
        else:
            cid = int(colors.set_index("name").loc[winner, "id"])
            sv.set_result(engine, int(eid), cid, score, note, ui.editor_name())
            places = {int(colors.set_index("name").loc[n, "id"]): p
                      for p, n in ((2, second), (3, third)) if n and n != winner}
            sv.set_places(engine, int(eid), places)
            st.success(f"บันทึกแล้ว: สี{winner} ได้ถ้วย {e['name']} · กระดานผลอัปเดตภายใน 30 วินาที")

if isinstance(e["winner"], str):
    with st.expander("ลบผลรายการนี้ (กรณีบันทึกผิดรายการ)"):
        confirm = st.checkbox("ยืนยันว่าต้องการลบผล", key=f"res_del_ok_{eid}")
        if st.button("ลบผล", disabled=not confirm, key=f"res_del_{eid}"):
            sv.clear_result(engine, int(eid))
            st.success("ลบผลแล้ว")
            st.rerun()
