"""จัดการผู้ใช้: เพิ่ม แก้ไข ลบ ตั้งสิทธิ์ และรีเซ็ตรหัสผ่าน (เฉพาะผู้ดูแลระบบ)"""
import pandas as pd
import streamlit as st

from sportsday import services as sv, ui

ui.require("users")
engine = ui.get_engine()
me = ui.current_user()
st.title("ผู้ใช้")
st.caption("ผู้ดูแลระบบทำได้ทุกอย่าง · ครู/กรรมการเลือกสิทธิ์ได้ทีละข้อ · "
           "สต๊าฟสีจัดการหน้าสีของตัวเอง และบันทึกผล/เช็คชื่อสมาชิกในสีได้ถ้าเปิดสิทธิ์")

colors = sv.list_colors(engine)
color_names = dict(zip(colors["id"], colors["name"]))
SHORT = {"results": "บันทึกผล", "schedule": "ตารางแข่ง", "attendance": "เช็คชื่อ", "trophies": "ถ้วย",
         "members": "สมาชิก", "colors": "ทุกสี", "move_color": "ย้ายสี", "settings": "ตั้งค่า"}


def perm_text(r) -> str:
    if r.role == "admin":
        return "ทุกอย่าง รวมจัดการผู้ใช้"
    if r.role == "color":
        extra = [SHORT[p] for p in (r.perms or "").split(",") if p in sv.COLOR_PERMS]
        return " · ".join([f"หน้าสี{r.color or '?'}"] + extra)
    names = [SHORT[p] for p in (r.perms or "").split(",") if p in SHORT]
    return " · ".join(names) if names else "ดูอย่างเดียว"


def when(v) -> str:
    return "" if pd.isna(v) or v is None else pd.Timestamp(v).strftime("%d/%m/%Y %H:%M")


def role_fields(prefix: str, role: str, color_id=None, perms=None):
    """ช่องที่ขึ้นกับบทบาท: เลือกสี (สต๊าฟสี) หรือเลือกสิทธิ์ (ครู/กรรมการ)"""
    cid, chosen = None, []
    if role == "color":
        ids = list(color_names)
        cid = st.selectbox("สีที่ดูแล", ids, format_func=lambda i: f"สี{color_names[i]}",
                           index=ids.index(color_id) if color_id in ids else 0, key=f"{prefix}_color")
        st.markdown("**สิทธิ์ที่ให้** (นอกจากจัดนักกีฬาและแก้สมาชิกในสีตัวเอง)")
        have = set(perms if perms is not None else sv.DEFAULT_COLOR_PERMS)
        cols = st.columns(2)
        for i, (k, label) in enumerate(sv.COLOR_PERMS.items()):
            if cols[i % 2].checkbox(label, value=k in have, key=f"{prefix}_cp_{k}"):
                chosen.append(k)
    elif role == "staff":
        st.markdown("**สิทธิ์ที่ให้**")
        have = set(perms if perms is not None else sv.DEFAULT_STAFF_PERMS)
        cols = st.columns(2)
        for i, (k, label) in enumerate(sv.PERMS.items()):
            if cols[i % 2].checkbox(label, value=k in have, key=f"{prefix}_p_{k}"):
                chosen.append(k)
    else:
        st.caption("ผู้ดูแลระบบได้ทุกสิทธิ์ รวมถึงเพิ่ม ลบ และแก้ไขผู้ใช้")
    return cid, chosen


users = sv.users_df(engine)
tab_list, tab_add, tab_edit = st.tabs(["รายชื่อผู้ใช้", "เพิ่มผู้ใช้", "แก้ไข / ลบ"])

# ------------------------------------------------------------------ รายชื่อ
with tab_list:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ผู้ใช้ทั้งหมด", len(users))
    c2.metric("ผู้ดูแลระบบ", int((users.role == "admin").sum()))
    c3.metric("ครู/กรรมการ", int((users.role == "staff").sum()))
    c4.metric("สต๊าฟสี", int((users.role == "color").sum()))
    st.dataframe(
        pd.DataFrame({
            "ชื่อผู้ใช้": users["username"],
            "ชื่อที่แสดง": users["display_name"],
            "บทบาท": users["role"].map(sv.ROLES),
            "สิทธิ์": [perm_text(r) for r in users.itertuples()],
            "สถานะ": users["active"].map({True: "ใช้งาน", False: "ปิดใช้งาน"}),
            "เข้าล่าสุด": users["last_login"].map(when),
        }),
        hide_index=True, width="stretch",
    )

# ------------------------------------------------------------------ เพิ่ม
with tab_add:
    n = st.session_state.get("add_user_n", 0)  # เปลี่ยน key เพื่อล้างช่องหลังเพิ่มสำเร็จ
    p = f"au{n}"
    role = st.radio("บทบาท", list(sv.ROLES), format_func=sv.ROLES.get, horizontal=True, index=1, key=f"{p}_role")
    c1, c2 = st.columns(2)
    username = c1.text_input("ชื่อผู้ใช้ (ใช้ตอนเข้าสู่ระบบ)", placeholder="เช่น kru.rak", key=f"{p}_user")
    display = c2.text_input("ชื่อที่แสดง", placeholder="เช่น ครูรักษ์ ใจดี", key=f"{p}_name")
    c1, c2 = st.columns(2)
    pw = c1.text_input(f"รหัสผ่าน (อย่างน้อย {sv.MIN_PASSWORD} ตัว)", type="password", key=f"{p}_pw")
    pw2 = c2.text_input("พิมพ์รหัสผ่านอีกครั้ง", type="password", key=f"{p}_pw2")
    cid, perms = role_fields(p, role)
    if st.button("เพิ่มผู้ใช้", type="primary", key=f"{p}_go"):
        if pw != pw2:
            st.error("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
        else:
            try:
                sv.create_user(engine, username, pw, role, display, cid, perms)
                st.session_state["add_user_n"] = n + 1
                st.session_state["users_flash"] = f"เพิ่มผู้ใช้ {username.strip().lower()} แล้ว"
                st.rerun()
            except ValueError as err:
                st.error(str(err))
    if msg := st.session_state.pop("users_flash", None):
        st.success(msg)

# ------------------------------------------------------------------ แก้ไข / ลบ
with tab_edit:
    if users.empty:
        st.info("ยังไม่มีผู้ใช้")
        st.stop()
    labels = {int(r.id): f"{r.username} · {r.display_name} · {sv.ROLES[r.role]}"
                         + ("" if r.active else " (ปิดใช้งาน)") for r in users.itertuples()}
    uid = st.selectbox("เลือกผู้ใช้", list(labels), format_func=labels.get, key="eu_pick")
    u = sv.get_user(engine, uid)
    is_me = me is not None and uid == me["id"]
    p = f"eu{uid}"

    with st.container(border=True):
        st.markdown("#### ข้อมูลและสิทธิ์")
        if is_me:
            st.caption("นี่คือบัญชีของคุณ เปลี่ยนบทบาทหรือปิดบัญชีตัวเองไม่ได้ เพื่อกันล็อกตัวเองออกจากระบบ")
        c1, c2 = st.columns(2)
        new_user = c1.text_input("ชื่อผู้ใช้", u["username"], key=f"{p}_user")
        new_name = c2.text_input("ชื่อที่แสดง", u["display_name"], key=f"{p}_name")
        roles = list(sv.ROLES)
        new_role = st.radio("บทบาท", roles, format_func=sv.ROLES.get, horizontal=True,
                            index=roles.index(u["role"]), key=f"{p}_role", disabled=is_me)
        cur_perms = [x for x in (u["perms"] or "").split(",") if x]
        # เปลี่ยนบทบาทแล้วใช้สิทธิ์ตั้งต้นของบทบาทใหม่
        cid, perms = role_fields(p, new_role, u["color_id"], cur_perms if new_role == u["role"] else None)
        active = st.toggle("เปิดใช้งานบัญชีนี้", value=bool(u["active"]), key=f"{p}_active", disabled=is_me)
        if st.button("บันทึกการแก้ไข", type="primary", key=f"{p}_save"):
            try:
                sv.update_user(engine, uid, username=new_user, display_name=new_name, role=new_role,
                               color_id=cid, perms=perms, active=active)
                st.success("บันทึกแล้ว · สิทธิ์ใหม่มีผลทันทีกับผู้ใช้คนนี้")
            except ValueError as err:
                st.error(str(err))

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("#### รีเซ็ตรหัสผ่าน")
        with st.form(f"{p}_pwf", clear_on_submit=True):
            npw = st.text_input("รหัสผ่านใหม่", type="password", key=f"{p}_npw")
            npw2 = st.text_input("พิมพ์อีกครั้ง", type="password", key=f"{p}_npw2")
            if st.form_submit_button("ตั้งรหัสผ่านใหม่"):
                if npw != npw2:
                    st.error("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
                else:
                    try:
                        sv.set_password(engine, uid, npw)
                        st.success(f"ตั้งรหัสผ่านใหม่ให้ {u['username']} แล้ว แจ้งผู้ใช้ให้เปลี่ยนเองอีกครั้งหลังเข้าสู่ระบบ")
                    except ValueError as err:
                        st.error(str(err))
    with c2, st.container(border=True):
        st.markdown("#### ลบผู้ใช้")
        if is_me:
            st.caption("ลบบัญชีของตัวเองไม่ได้")
        else:
            st.caption("ลบแล้วกู้คืนไม่ได้ ถ้าแค่ไม่ให้ใช้ชั่วคราว ให้ปิดใช้งานแทน · ผลที่เคยบันทึกยังเก็บชื่อผู้บันทึกไว้")
            ok = st.checkbox(f"ยืนยันลบ {u['username']}", key=f"{p}_delok")
            if st.button("ลบผู้ใช้", key=f"{p}_del", disabled=not ok):
                try:
                    sv.delete_user(engine, uid)
                    st.session_state.pop("eu_pick", None)
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
