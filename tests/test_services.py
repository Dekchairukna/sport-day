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
