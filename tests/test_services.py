from datetime import date

import pytest

from sportsday import services as sv
from sportsday.db import make_engine


@pytest.fixture()
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    sv.seed_defaults(eng)
    return eng


def _student(eng, first, gender, grade, color="ชมพู", room=1):
    return sv.add_student(
        eng, code=f"9{first}", prefix="", first_name=first, last_name="ทดสอบ",
        gender=gender, grade=grade, room=room, color_id=sv.color_id_by_name(eng, color),
    )


def _event_id(eng, name):
    ev = sv.events_df(eng)
    return int(ev.loc[ev.name == name, "id"].iloc[0])


def test_seed_loads_schedule_and_trophies(engine):
    ev = sv.events_df(engine)
    assert len(ev) == 27
    assert set(ev.trophy_status) == {"รอเตรียม"}
    assert "กรีฑา ชาย ม.ปลาย 4x400 ม." in set(ev.name)
    assert "ฟุตบอล หญิงรวม" in set(ev.name)


def test_eligibility_rules():
    assert sv.is_eligible("หญิง", 2, "หญิง", "ต้น")
    assert not sv.is_eligible("หญิง", 5, "หญิง", "ต้น")
    assert not sv.is_eligible("ชาย", 2, "หญิง", "รวม")
    assert sv.is_eligible("ชาย", 6, "ชาย", "รวม")
    assert sv.is_eligible("หญิง", 4, "ผสม", "ปลาย")


def test_entries_skip_ineligible(engine):
    girl_m2 = _student(engine, "เอ", "หญิง", 2)
    boy_m5 = _student(engine, "บี", "ชาย", 5)
    eid = _event_id(engine, "วอลเลย์บอล หญิง ม.ต้น")
    skipped = sv.set_event_entries(engine, eid, [girl_m2, boy_m5])
    assert skipped == ["บี ทดสอบ"]
    assert sv.entries_df(engine, eid).student_id.tolist() == [girl_m2]


def test_time_conflict_detected(engine):
    s = _student(engine, "ซี", "ชาย", 5)
    a = _event_id(engine, "กรีฑา ชาย ม.ปลาย 100 ม.")  # 13 พ.ย. 09:12-09:32
    b = _event_id(engine, "ฟุตบอล ชายรวม")  # 13 พ.ย. 13:12
    sv.set_student_events(engine, s, [a, b])
    assert sv.find_conflicts(engine) == []
    sv.update_event(engine, b, start="09:20")
    conflicts = sv.find_conflicts(engine)
    assert len(conflicts) == 1 and conflicts[0].student_id == s


def test_standings_count_trophies(engine):
    blue, pink = sv.color_id_by_name(engine, "น้ำเงิน"), sv.color_id_by_name(engine, "ชมพู")
    ids = sv.events_df(engine).id.tolist()
    sv.set_result(engine, ids[0], pink, "2-1")
    sv.set_result(engine, ids[1], pink)
    sv.set_result(engine, ids[2], blue)
    st = sv.standings(engine)
    assert st.iloc[0]["name"] == "ชมพู" and st.iloc[0]["trophies"] == 2
    assert sv.progress(engine) == {"total": 27, "done": 3, "left": 24}
    sv.set_result(engine, ids[1], blue)  # แก้ผล
    sv.update_event(engine, ids[0], cancelled=True)  # ยกเลิกรายการ ไม่นับถ้วย
    st = sv.standings(engine).set_index("name")
    assert st.loc["น้ำเงิน", "trophies"] == 2 and st.loc["ชมพู", "trophies"] == 0


def test_add_new_sport_creates_trophy(engine):
    eid = sv.add_event(engine, "ชักเย่อ", "ผสม", "รวม", date(2026, 11, 13), "15:00", 30, "สนามฟุตบอล")
    ev = sv.events_df(engine).set_index("id")
    assert ev.loc[eid, "name"] == "ชักเย่อ ผสมรวม"
    assert ev.loc[eid, "trophy_status"] == "รอเตรียม"
    with pytest.raises(ValueError):
        sv.add_event(engine, "ชักเย่อ", "ผสม", "รวม", date(2026, 11, 13), "9.00", 30)


def test_move_color_keeps_history_and_finished_results(engine):
    blue, pink = sv.color_id_by_name(engine, "น้ำเงิน"), sv.color_id_by_name(engine, "ชมพู")
    s = _student(engine, "ดี", "หญิง", 1)
    done = _event_id(engine, "วอลเลย์บอล หญิง ม.ต้น")
    todo = _event_id(engine, "เปตอง หญิง ม.ต้น")
    sv.set_student_events(engine, s, [done, todo])
    sv.set_result(engine, done, pink)
    removed = sv.move_color(engine, s, blue, reason="ย้ายตามพี่น้อง", moved_by="ครูรักษ์")
    assert removed == ["เปตอง หญิง ม.ต้น"]
    assert sv.entries_df(engine, done).color.tolist() == ["ชมพู"]  # ผลเดิมยังเป็นของสีเดิม
    assert sv.standings(engine).set_index("name").loc["ชมพู", "trophies"] == 1
    hist = sv.color_moves_df(engine)
    assert hist.iloc[0][["from_color", "to_color", "moved_by"]].tolist() == ["ชมพู", "น้ำเงิน", "ครูรักษ์"]


def test_attendance_summary(engine):
    s1 = _student(engine, "อี", "ชาย", 4)
    s2 = _student(engine, "เอฟ", "ชาย", 4)
    role = int(sv.roles_df(engine).query("name == 'ขึ้นสแตนด์'").id.iloc[0])
    sv.set_student_roles(engine, s1, [role])
    sv.set_student_roles(engine, s2, [role])
    for i, (a, b) in enumerate([("มา", "ขาด"), ("สาย", "ขาด")]):
        sid = sv.create_session(engine, f"ซ้อมเชียร์ {i}", date(2026, 11, 3 + i), role_id=role)
        assert len(sv.session_roster(engine, sid)) == 2
        sv.save_attendance(engine, sid, [{"student_id": s1, "status": a}, {"student_id": s2, "status": b}])
    summ = sv.attendance_summary(engine).set_index("student_id")
    assert summ.loc[s1, "ร้อยละมา"] == 100 and summ.loc[s2, "ขาด"] == 2


def test_import_members_csv_upserts(engine):
    rows = [
        {"ชั้น": "ม.6", "ห้อง": "1", "เลขประจำตัว": "3297", "คำนำหน้า": "นาย", "ชื่อ": "ก", "นามสกุล": "ข",
         "เพศ": "ชาย", "สี": "ชมพู", "ค่าเสื้อ": "จ่ายแล้ว"},
        {"ชั้น": "ม.1", "ห้อง": "1", "เลขประจำตัว": "3667", "คำนำหน้า": "เด็กหญิง", "ชื่อ": "ค", "นามสกุล": "ง",
         "เพศ": "", "สี": "ยังไม่ระบุ"},
        {"ชั้น": "", "ชื่อ": ""},
    ]
    assert sv.import_members_csv(engine, rows) == {"added": 2, "updated": 0, "skipped": 1}
    rows[0]["สี"] = "น้ำเงิน"
    assert sv.import_members_csv(engine, rows[:1])["updated"] == 1
    df = sv.students_df(engine).set_index("code")
    assert df.loc["3297", "color"] == "น้ำเงิน" and bool(df.loc["3297", "shirt_paid"])
    assert df.loc["3667", "gender"] == "หญิง" and df.loc["3667", "color"] == "ยังไม่ระบุ"


def test_users_crud_and_permissions(engine):
    pink = sv.color_id_by_name(engine, "ชมพู")
    sv.seed_users(engine, "9999")
    assert sv.authenticate(engine, "ADMIN ", "9999")["role"] == "admin"  # ชื่อผู้ใช้ไม่สนตัวพิมพ์
    assert sv.authenticate(engine, "admin", "wrong") is None
    sid = sv.create_user(engine, "kru.rak", "secret1", "staff", "ครูรักษ์", perms=["results", "bogus"])
    cid = sv.create_user(engine, "pinkstaff", "secret2", "color", color_id=pink)
    assert sv.user_perms(sv.get_user(engine, sid)) == {"results"}
    assert sv.user_perms(sv.get_user(engine, cid)) == {"results", "attendance"}
    assert "users" in sv.user_perms(sv.authenticate(engine, "admin", "9999"))
    with pytest.raises(ValueError):
        sv.create_user(engine, "Kru.Rak", "secret3", "staff")  # ซ้ำ
    with pytest.raises(ValueError):
        sv.create_user(engine, "short", "123", "staff")  # รหัสสั้น
    with pytest.raises(ValueError):
        sv.create_user(engine, "nocolor", "secret4", "color")  # สต๊าฟสีต้องมีสี
    sv.update_user(engine, sid, username="kru.rak", display_name="ครูรักษ์", role="staff",
                   color_id=None, perms=["attendance", "members"], active=False)
    assert sv.authenticate(engine, "kru.rak", "secret1") is None  # ปิดใช้งานแล้ว
    sv.set_password(engine, cid, "newpass")
    assert sv.authenticate(engine, "pinkstaff", "newpass")["color_id"] == pink
    sv.delete_user(engine, cid)
    assert sv.get_user(engine, cid) is None


def test_last_admin_is_protected(engine):
    sv.seed_users(engine, "9999")
    admin = sv.authenticate(engine, "admin", "9999")["id"]
    with pytest.raises(ValueError):
        sv.delete_user(engine, admin)
    with pytest.raises(ValueError):
        sv.update_user(engine, admin, username="admin", display_name="", role="staff",
                       color_id=None, perms=[], active=True)
    other = sv.create_user(engine, "boss2", "secret9", "admin")
    sv.delete_user(engine, admin)  # มีแอดมินอีกคนแล้ว ลบได้
    assert sv.get_user(engine, other)["role"] == "admin"


def test_old_color_pins_become_accounts(engine):
    blue = sv.color_id_by_name(engine, "น้ำเงิน")
    sv.set_setting(engine, f"pin_color_{blue}", sv._hash_pin("3333"))  # PIN แบบเก่า
    sv.seed_users(engine, "9999")
    u = sv.authenticate(engine, f"color{blue}", "3333")
    assert u and u["role"] == "color" and u["color_id"] == blue
    assert sv.get_user(engine, u["id"])["pw_hash"].startswith("pbkdf2$")  # อัปเกรดแฮชแล้ว
    sv.seed_users(engine, "other")  # เรียกซ้ำไม่สร้างเพิ่ม
    assert len(sv.users_df(engine)) == 2

def test_color_todo(engine):
    pink = sv.color_id_by_name(engine, "ชมพู")
    s = _student(engine, "จี", "หญิง", 2)
    _student(engine, "เอช", "ชาย", 2, color="น้ำเงิน")
    sv.set_student_events(engine, s, [_event_id(engine, "วอลเลย์บอล หญิง ม.ต้น")])
    role = int(sv.roles_df(engine).query("name == 'ประธานสี'").id.iloc[0])
    sv.set_student_roles(engine, s, [role])
    todo = sv.color_todo(engine, pink)
    assert todo["members"] == 1
    assert "วอลเลย์บอล หญิง ม.ต้น" not in todo["events_without_athletes"]
    assert len(todo["events_without_athletes"]) == 26
    assert "ประธานสี" not in todo["roles_empty"] and "สต๊าฟ" in todo["roles_empty"]
    assert len(todo["unpaid"]) == 1


def test_color_staff_permissions(engine):
    sv.seed_users(engine, "9999")
    pink = sv.color_id_by_name(engine, "ชมพู")
    uid = sv.create_user(engine, "pink1", "secret1", "color", color_id=pink)
    assert sv.user_perms(sv.get_user(engine, uid)) == {"results", "attendance"}  # ค่าตั้งต้น
    sv.update_user(engine, uid, username="pink1", display_name="", role="color", color_id=pink,
                   perms=["attendance", "settings", "members"], active=True)  # สิทธิ์ครูใช้กับสต๊าฟสีไม่ได้
    assert sv.user_perms(sv.get_user(engine, uid)) == {"attendance"}


def test_migrate_color_perms_once(engine):
    sv.create_user(engine, "admin", "secret0", "admin")  # ฐานข้อมูลเดิมที่มีผู้ใช้อยู่แล้ว
    pink = sv.color_id_by_name(engine, "ชมพู")
    uid = sv.create_user(engine, "pink2", "secret1", "color", color_id=pink, perms=[])
    sv.migrate_color_perms(engine)  # บัญชีเก่าที่ยังไม่มีสิทธิ์ ได้ทั้งสองข้อ
    assert sv.user_perms(sv.get_user(engine, uid)) == {"results", "attendance"}
    sv.update_user(engine, uid, username="pink2", display_name="", role="color", color_id=pink,
                   perms=[], active=True)
    sv.migrate_color_perms(engine)  # ครั้งที่สองไม่ทับค่าที่แอดมินปิดไว้
    assert sv.user_perms(sv.get_user(engine, uid)) == set()


def test_attendance_activities(engine):
    pink = sv.color_id_by_name(engine, "ชมพู")
    a = _student(engine, "ก", "ชาย", 1)
    b = _student(engine, "ข", "หญิง", 2)
    acts = sv.activities_df(engine)
    assert "เช็ครวมสี" in acts.name.tolist()
    whole = int(acts.set_index("name").loc["เช็ครวมสี", "id"])
    new = sv.add_activity(engine, "  ซ้อม  แปรอักษร ")
    assert sv.add_activity(engine, "ซ้อม แปรอักษร") == new  # ชื่อซ้ำได้ id เดิม
    s1 = sv.create_session(engine, "รวมสี", date(2026, 11, 3), color_id=pink, activity_id=whole)
    s2 = sv.create_session(engine, "แปรอักษร", date(2026, 11, 4), color_id=pink, activity_id=new)
    sv.save_attendance(engine, s1, [{"student_id": a, "status": "มา"}, {"student_id": b, "status": "ขาด"}])
    sv.save_attendance(engine, s2, [{"student_id": a, "status": "สาย"}, {"student_id": b, "status": "มา"}])
    assert set(sv.sessions_df(engine).activity) == {"เช็ครวมสี", "ซ้อม แปรอักษร"}
    only = sv.attendance_summary(engine, whole).set_index("student_id")
    assert only.loc[b, "ร้อยละมา"] == 0 and only.loc[a, "รวม"] == 1
    assert sv.attendance_summary(engine).set_index("student_id").loc[b, "ร้อยละมา"] == 50
    ov = sv.activity_overview(engine, pink).set_index("กิจกรรม")
    assert ov.loc["เช็ครวมสี", "ร้อยละมา"] == 50 and ov.loc["ซ้อม แปรอักษร", "ร้อยละมา"] == 100
    with pytest.raises(ValueError):
        sv.delete_activity(engine, new)  # มีรอบแล้วลบไม่ได้
    sv.update_activity(engine, new, "ซ้อมแปรอักษร", active=False)
    assert "ซ้อมแปรอักษร" not in sv.activities_df(engine).name.tolist()
    spare = sv.add_activity(engine, "ไม่ได้ใช้")
    sv.delete_activity(engine, spare)


def test_old_database_gets_activity_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    eng = make_engine(f"sqlite:///{path}")
    sv.seed_defaults(eng)
    eng.dispose()
    con = sqlite3.connect(path)  # จำลองฐานข้อมูลรุ่นก่อน: ไม่มีคอลัมน์ activity_id
    con.executescript("DROP TABLE att_sessions;"
                      "CREATE TABLE att_sessions (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL,"
                      " date DATE NOT NULL, event_id INTEGER, role_id INTEGER, color_id INTEGER);"
                      "INSERT INTO att_sessions (title, date) VALUES ('เก่า', '2026-11-01');")
    con.commit(); con.close()
    eng = make_engine(f"sqlite:///{path}")
    sv.seed_defaults(eng)
    assert sv.sessions_df(eng).set_index("title").loc["เก่า", "activity"] == "เช็ครวมสี"


def test_daily_rounds_and_quick_check(engine):
    pink = sv.color_id_by_name(engine, "ชมพู")
    blue = sv.color_id_by_name(engine, "น้ำเงิน")
    a = _student(engine, "ก", "ชาย", 1)
    b = _student(engine, "ข", "หญิง", 2)
    assert [r["slot"] for r in sv.get_daily_rounds(engine)] == ["เช้า", "สาย", "บ่าย"]
    made, skip = sv.create_daily_rounds(engine, date(2026, 11, 4), date(2026, 11, 5), [pink, blue])
    assert (made, skip) == (12, 0)  # 2 วัน x 2 สี x 3 รอบ
    assert sv.create_daily_rounds(engine, date(2026, 11, 5), date(2026, 11, 5), [pink]) == (0, 3)  # ไม่สร้างซ้ำ
    ses = sv.sessions_df(engine)
    day = ses[(ses["day"] == date(2026, 11, 4)) & (ses.color_id == pink)]
    assert day["title"].tolist() == ["เช้า (สีชมพู)", "สาย (สีชมพู)", "บ่าย (สีชมพู)"]  # เรียงตามเวลา
    assert day["activity"].tolist() == ["ประชุมสี", "ซ้อมเชียร์", "ซ้อมเชียร์"]
    sid = int(day.iloc[0]["id"])
    sv.set_attendance_one(engine, sid, a, "สาย")
    assert sv.mark_unchecked(engine, sid, [a, b]) == 1  # ไม่ทับ a ที่เช็คแล้ว
    roster = sv.session_roster(engine, sid).set_index("student_id")
    assert roster.loc[a, "status"] == "สาย" and roster.loc[b, "status"] == "มา"
    sv.set_attendance_one(engine, sid, b, None)  # กดซ้ำเพื่อยกเลิก
    assert sv.session_roster(engine, sid).set_index("student_id").loc[b, "status"] == ""
    sv.set_daily_rounds(engine, [{"slot": "เย็น", "activity": "ซ้อมแปรอักษร"}, {"slot": "", "activity": "x"}])
    assert sv.get_daily_rounds(engine) == [{"slot": "เย็น", "activity": "ซ้อมแปรอักษร"}]
    with pytest.raises(ValueError):
        sv.set_daily_rounds(engine, [{"slot": "เช้า", "activity": "ก"}, {"slot": "เช้า", "activity": "ข"}])


def _event_with(engine, sport, gender, level, ids):
    eid = sv.add_event(engine, sport, gender, level, date(2026, 11, 20), "09:00", 30, "สนาม")
    sv.set_event_entries(engine, eid, ids)
    return eid


def test_medals_two_colors(engine):
    pink = sv.color_id_by_name(engine, "ชมพู")
    blue = sv.color_id_by_name(engine, "น้ำเงิน")
    p1 = _student(engine, "ชมพู1", "ชาย", 1, "ชมพู")
    b1 = _student(engine, "ฟ้า1", "ชาย", 1, "น้ำเงิน")
    e1 = _event_with(engine, "แบดมินตัน", "ชาย", "ต้น", [p1, b1])
    e2 = _event_with(engine, "ปิงปอง", "ชาย", "ต้น", [p1, b1])
    sv.set_result(engine, e1, pink)
    sv.set_result(engine, e2, pink)
    mt = sv.medal_table(engine).set_index("name")
    assert (mt.loc["ชมพู", "ทอง"], mt.loc["ชมพู", "เงิน"]) == (2, 0)
    assert (mt.loc["น้ำเงิน", "ทอง"], mt.loc["น้ำเงิน", "เงิน"]) == (0, 2)  # 2 สี: สีที่แพ้ได้เงินอัตโนมัติ
    assert sv.medal_table(engine).iloc[0]["name"] == "ชมพู"
    lb = sv.athlete_leaderboard(engine).set_index("student_id")
    assert lb.loc[p1, "ทอง"] == 2 and lb.loc[b1, "เงิน"] == 2
    assert sv.athlete_leaderboard(engine).iloc[0]["student_id"] == p1
    sv.clear_result(engine, e2)
    assert sv.medal_table(engine).set_index("name").loc["ชมพู", "ทอง"] == 1


def test_medals_three_colors_and_certificates(engine):
    from sportsday import reports as rp
    green = sv.add_color(engine, "เขียว", "#2a9d55")
    pink = sv.color_id_by_name(engine, "ชมพู")
    blue = sv.color_id_by_name(engine, "น้ำเงิน")
    p1 = _student(engine, "ชมพู1", "หญิง", 2, "ชมพู")
    b1 = _student(engine, "ฟ้า1", "หญิง", 2, "น้ำเงิน")
    g1 = _student(engine, "เขียว1", "หญิง", 2, "เขียว")
    e1 = _event_with(engine, "แชร์บอล", "หญิง", "ต้น", [p1, b1, g1])
    sv.set_result(engine, e1, green)
    assert sv.medal_table(engine).set_index("name").loc["ชมพู", "รวม"] == 0  # 3 สี: ยังไม่ระบุรองชนะเลิศ
    sv.set_places(engine, e1, {blue: 2, pink: 3})
    mt = sv.medal_table(engine).set_index("name")
    assert (mt.loc["เขียว", "ทอง"], mt.loc["น้ำเงิน", "เงิน"], mt.loc["ชมพู", "ทองแดง"]) == (1, 1, 1)
    medal = rp.certificate_items(engine, "medal")
    assert dict(zip(medal.student_id, medal.achievement)) == {
        g1: "ได้รับรางวัลชนะเลิศ", b1: "ได้รับรางวัลรองชนะเลิศอันดับ 1", p1: "ได้รับรางวัลรองชนะเลิศอันดับ 2"}
    assert list(rp.certificate_items(engine, "medal", places=(1,)).student_id) == [g1]
    assert len(rp.certificate_items(engine, "join", color="ชมพู")) == 1
    sv.seed_users(engine, "9999")
    aid = sv.add_award(engine, "นักกีฬายอดเยี่ยมหญิง", g1)
    with pytest.raises(ValueError):
        sv.add_award(engine, "นักกีฬายอดเยี่ยมหญิง", g1)
    aw = rp.certificate_items(engine, "award")
    assert aw.iloc[0]["achievement"] == "ได้รับรางวัลนักกีฬายอดเยี่ยมหญิง"
    sv.save_cert_settings(engine, [{"name": "นายก", "position": "ผู้อำนวยการ"}, {"name": "", "position": ""}], "", "กส./")
    assert sv.cert_settings(engine)["signers"] == [{"name": "นายก", "position": "ผู้อำนวยการ"}]
    pdf = rp.certificate_pdf(engine, medal)
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page>") >= 1
    assert rp.certificate_register(medal, "กส./")[:2] == b"PK"
    sv.delete_award(engine, aid)
    assert sv.awards_df(engine).empty


def test_best_athletes_by_total_medals(engine):
    from sportsday import reports as rp
    pink = sv.color_id_by_name(engine, "ชมพู")
    blue = sv.color_id_by_name(engine, "น้ำเงิน")
    gold1 = _student(engine, "ทองเดียว", "ชาย", 1, "ชมพู")
    many = _student(engine, "เหรียญเยอะ", "ชาย", 1, "น้ำเงิน")
    girl1 = _student(engine, "หญิงหนึ่ง", "หญิง", 1, "ชมพู")
    girl2 = _student(engine, "หญิงสอง", "หญิง", 1, "ชมพู")
    e1 = _event_with(engine, "วิ่ง", "ชาย", "ต้น", [gold1, many])
    sv.set_result(engine, e1, pink)  # gold1 ทอง 1, many เงิน 1
    for sport in ("กระโดดไกล", "ทุ่มน้ำหนัก"):
        e = _event_with(engine, sport, "ชาย", "ต้น", [many])
        sv.set_result(engine, e, pink)  # many ลงคนเดียว สีน้ำเงินแพ้ = เงิน
    e4 = _event_with(engine, "แบดมินตัน", "หญิง", "ต้น", [girl1, girl2])
    sv.set_result(engine, e4, pink)  # ทั้งคู่ได้ทอง 1 เท่ากัน
    best = sv.best_athletes(engine)
    men = best[best.title == "นักกีฬายอดเยี่ยมชาย"]
    assert men["student_id"].tolist() == [many]  # เงิน 3 เหรียญ ชนะ ทอง 1 เหรียญ เพราะนับเหรียญรวม
    women = best[best.title == "นักกีฬายอดเยี่ยมหญิง"]
    assert set(women["student_id"]) == {girl1, girl2} and women["tie"].all()  # เท่ากันทุกอย่าง = รางวัลร่วม
    assert sv.athlete_leaderboard(engine).iloc[0]["student_id"] == many
    certs = rp.certificate_items(engine, "award")
    assert len(certs) == 3 and "เหรียญรวม 3" in certs.set_index("student_id").loc[many, "detail"]


def _fill_some(engine):
    sv.seed_users(engine, "9999")
    pink = sv.color_id_by_name(engine, "ชมพู")
    a = _student(engine, "สำรอง", "ชาย", 1, "ชมพู")
    eid = _event_with(engine, "วิ่งผลัด", "ชาย", "ต้น", [a])
    sv.set_result(engine, eid, pink, "1-0", recorded_by="ครู")
    sid = sv.create_session(engine, "เช้า", date(2026, 11, 4), color_id=pink)
    sv.set_attendance_one(engine, sid, a, "สาย")
    sv.create_user(engine, "kru1", "secret1", "staff", "ครูหนึ่ง", perms=["results"])
    return a, eid, sid


def test_backup_roundtrip_sqlite(engine, tmp_path):
    a, eid, sid = _fill_some(engine)
    data = sv.export_backup(engine)
    assert sv.backup_summary(data)["students"] == 1
    other = make_engine(f"sqlite:///{tmp_path / 'new.db'}")
    sv.seed_defaults(other)
    sv.seed_users(other, "1234")  # ฐานข้อมูลใหม่มีค่าเริ่มต้นอยู่แล้ว ต้องถูกแทนที่ทั้งหมด
    sv.import_backup(other, data)
    assert sv.data_counts(other) == sv.data_counts(engine)
    assert sv.authenticate(other, "kru1", "secret1")["display_name"] == "ครูหนึ่ง"
    assert sv.authenticate(other, "admin", "9999") and sv.authenticate(other, "admin", "1234") is None
    assert sv.session_roster(other, sid).set_index("student_id").loc[a, "status"] == "สาย"
    ev = sv.events_df(other).set_index("id")
    assert ev.loc[eid, "winner"] == "ชมพู" and ev.loc[eid, "recorded_by"] == "ครู"
    new_id = sv.add_student(other, code="x", prefix="", first_name="ใหม่", last_name="", gender="ชาย", grade=1, room=1)
    assert new_id > a  # เลข id ต่อจากข้อมูลเดิม
    with pytest.raises(ValueError):
        sv.import_backup(other, b'{"app": "other", "tables": {}}')


@pytest.mark.skipif(not __import__("os").environ.get("SPORTSDAY_TEST_PG"), reason="ตั้ง SPORTSDAY_TEST_PG เพื่อทดสอบกับ PostgreSQL")
def test_backup_into_postgres(engine):
    import os
    from sqlalchemy import text
    a, eid, sid = _fill_some(engine)
    pg = make_engine(os.environ["SPORTSDAY_TEST_PG"])
    with pg.begin() as c:  # เริ่มจากฐานข้อมูลว่าง
        for t in reversed(__import__("sportsday.db", fromlist=["metadata"]).metadata.sorted_tables):
            c.execute(text(f"DELETE FROM {t.name}"))
    sv.seed_defaults(pg)
    sv.seed_users(pg, "1234")
    sv.import_backup(pg, sv.export_backup(engine))
    assert sv.data_counts(pg) == sv.data_counts(engine)
    assert sv.authenticate(pg, "kru1", "secret1")
    new_id = sv.add_student(pg, code="x", prefix="", first_name="ใหม่", last_name="", gender="ชาย", grade=1, room=1)
    assert new_id > a  # sequence ถูกตั้งต่อจากข้อมูลที่กู้คืน
    sv.create_user(pg, "kru2", "secret2", "staff")
    sv.create_daily_rounds(pg, date(2026, 11, 5), date(2026, 11, 5), [sv.color_id_by_name(pg, "ชมพู")])


def test_empty_database_does_not_crash(tmp_path):
    from sportsday import reports as rp
    eng = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    sv.seed_defaults(eng, schedule_csv=tmp_path / "none.csv")  # ไม่มีนักเรียน ไม่มีรายการแข่ง
    pink = sv.color_id_by_name(eng, "ชมพู")
    todo = sv.color_todo(eng, pink)
    assert todo["unpaid"].empty and todo["events_without_athletes"] == []
    assert sv.standings(eng)["trophies"].sum() == 0
    assert sv.medal_table(eng)["รวม"].sum() == 0 and sv.athlete_leaderboard(eng).empty
    assert sv.best_athletes(eng).empty and sv.events_df(eng, include_cancelled=False).empty
    for kind in rp.CERT_KINDS:
        assert rp.certificate_items(eng, kind).empty
    assert rp.pdf_report(eng).startswith(b"%PDF") and rp.excel_report(eng)[:2] == b"PK"
