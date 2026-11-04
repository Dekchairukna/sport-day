"""รายงานผลการแข่งขัน (Excel / PDF) และสติ๊กเกอร์ติดถ้วย"""
from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors as rl_colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.engine import Engine

from . import services as sv

FONT_DIR = Path(__file__).resolve().parent / "fonts"
# จัดรูปอักษรไทยด้วย HarfBuzz (uharfbuzz) ให้วรรณยุกต์ซ้อนสระบนถูกตำแหน่ง เช่น ที่ เพื่อ นี้
ParagraphStyle.defaults["shaping"] = 1
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]


def thai_date(d: date, with_day: bool = True) -> str:
    s = f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"
    return f"{THAI_DAYS[d.weekday()]} {s}" if with_day else s


def _register_fonts() -> None:
    if "Sarabun" in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont("Sarabun", str(FONT_DIR / "Sarabun-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Sarabun-Bold", str(FONT_DIR / "Sarabun-Bold.ttf")))
    pdfmetrics.registerFontFamily("Sarabun", normal="Sarabun", bold="Sarabun-Bold",
                                  italic="Sarabun", boldItalic="Sarabun-Bold")


def _styles():
    _register_fonts()
    base = dict(fontName="Sarabun", fontSize=12, leading=17)
    return {
        "title": ParagraphStyle("title", fontName="Sarabun-Bold", fontSize=18, leading=24, alignment=TA_CENTER),
        "sub": ParagraphStyle("sub", alignment=TA_CENTER, textColor=rl_colors.HexColor("#555555"), **base),
        "h2": ParagraphStyle("h2", fontName="Sarabun-Bold", fontSize=14, leading=20, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", **base),
        "cell": ParagraphStyle("cell", fontName="Sarabun", fontSize=11, leading=15),
        "cellb": ParagraphStyle("cellb", fontName="Sarabun-Bold", fontSize=11, leading=15),
    }


# ---------------------------------------------------------------- ตารางข้อมูลสำหรับรายงาน

def results_table(engine: Engine) -> pd.DataFrame:
    ev = sv.events_df(engine)
    if ev.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "วันที่": ev["date"].map(lambda d: thai_date(d)),
        "เวลา": ev["start"] + "-" + ev["end"],
        "ชนิดกีฬา": ev["sport"],
        "รุ่น/ประเภท": ev["label"],
        "สนาม": ev["venue"],
        "สถานะ": ev["status"],
        "สีที่ได้ถ้วย": ev["winner"].fillna(""),
        "สกอร์": ev["score"].fillna(""),
        "หมายเหตุ": ev["result_note"].fillna(""),
        "นักกีฬา (คน)": ev["athletes"],
    })
    out.insert(0, "_date", ev["date"])
    return out


def standings_table(engine: Engine) -> pd.DataFrame:
    st = sv.standings(engine)
    sports = sorted({s for d in st["by_sport"] for s in d})
    rows = []
    for i, r in enumerate(st.itertuples(), 1):
        row = {"อันดับ": i, "สี": r.name, "ถ้วยรวม": r.trophies}
        row.update({s: r.by_sport.get(s, 0) for s in sports})
        rows.append(row)
    return pd.DataFrame(rows)


def by_sport_table(engine: Engine) -> pd.DataFrame:
    ev = sv.events_df(engine, include_cancelled=False)
    cols = sv.list_colors(engine)["name"].tolist()
    rows = []
    for sport, g in ev.groupby("sport", sort=False):
        row = {"ชนิดกีฬา": sport, "จำนวนรายการ": len(g), "แข่งจบ": int(g["winner"].notna().sum())}
        for c in cols:
            row[c] = int((g["winner"] == c).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def athletes_table(engine: Engine) -> pd.DataFrame:
    ev = sv.events_df(engine)[["id", "name", "date", "start"]]
    en = sv.entries_df(engine)
    if en.empty:
        return pd.DataFrame(columns=["รายการ", "สี", "ชื่อ-สกุล", "ชั้น"])
    df = en.merge(ev, left_on="event_id", right_on="id").sort_values(["date", "start", "name", "color", "grade", "room"])
    return pd.DataFrame({"รายการ": df["name"], "สี": df["color"], "ชื่อ-สกุล": df["full_name"], "ชั้น": df["class"]})


def members_table(engine: Engine) -> pd.DataFrame:
    st = sv.students_df(engine)
    ev_names = dict(zip(*sv.events_df(engine)[["id", "name"]].T.values))
    return pd.DataFrame({
        "ชั้น": st["class"], "เลขประจำตัว": st["code"], "ชื่อ-สกุล": st["full_name"], "เพศ": st["gender"],
        "สี": st["color"], "หน้าที่": st["roles"].map(", ".join),
        "รายการแข่ง": st["event_ids"].map(lambda ids: ", ".join(ev_names.get(i, "") for i in ids)),
        "ไซซ์เสื้อ": st["shirt_size"], "ค่าเสื้อ": st["shirt_paid"].map({True: "จ่ายแล้ว", False: "ยังไม่จ่าย"}),
        "หมายเหตุ": st["note"],
    })


# ---------------------------------------------------------------- Excel

def excel_report(engine: Engine) -> bytes:
    buf = io.BytesIO()
    res = results_table(engine)
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        standings_table(engine).to_excel(xw, sheet_name="สรุปถ้วย", index=False)
        by_sport_table(engine).to_excel(xw, sheet_name="แยกชนิดกีฬา", index=False)
        (res.drop(columns="_date") if not res.empty else res).to_excel(xw, sheet_name="ผลทุกรายการ", index=False)
        athletes_table(engine).to_excel(xw, sheet_name="รายชื่อนักกีฬา", index=False)
        members_table(engine).to_excel(xw, sheet_name="สมาชิก", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(8, width * 1.1 + 2), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()


# ---------------------------------------------------------------- PDF

def _table(df: pd.DataFrame, styles, col_widths=None, header_bg="#1d2433") -> Table:
    hdr = ParagraphStyle("hdr", parent=styles["cellb"], textColor=rl_colors.white)
    data = [[Paragraph(str(c), hdr) for c in df.columns]]
    for row in df.itertuples(index=False):
        data.append([Paragraph(str(v), styles["cell"]) for v in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(header_bg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#c8ccd6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f3f5f9")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def pdf_report(engine: Engine, day: date | None = None) -> bytes:
    """รายงานสรุปผล: ทั้งงาน หรือเฉพาะวันที่ระบุ"""
    s = _styles()
    title = sv.get_setting(engine, "event_title")
    school = sv.get_setting(engine, "school_name")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"รายงานผลการแข่งขัน {title}")
    story = [
        Paragraph("รายงานผลการแข่งขัน" + (f" ประจำวันที่ {thai_date(day)}" if day else ""), s["title"]),
        Paragraph(f"{title} · {school}", s["sub"]),
        Paragraph(f"ข้อมูล ณ {thai_date(datetime.now().date())} เวลา {datetime.now():%H:%M} น.", s["sub"]),
        Spacer(1, 6 * mm),
    ]
    st = sv.standings(engine)
    prog = sv.progress(engine)
    score_line = " · ".join(f"<b>สี{r.name} {r.trophies} ถ้วย</b>" for r in st.itertuples())
    story.append(Paragraph(f"คะแนนรวม (นับจำนวนถ้วย): {score_line}", s["body"]))
    story.append(Paragraph(f"แข่งจบแล้ว {prog['done']} จาก {prog['total']} รายการ เหลือ {prog['left']} รายการ", s["body"]))

    bs = by_sport_table(engine)
    if not bs.empty:
        story += [Paragraph("สรุปแยกชนิดกีฬา", s["h2"]), _table(bs, s)]

    res = results_table(engine)
    if not res.empty:
        if day:
            res = res[res["_date"] == day]
        story.append(Paragraph("ผลรายการ" if day else "ผลทุกรายการ", s["h2"]))
        for d, g in res.groupby("_date", sort=True):
            tbl = g[["เวลา", "ชนิดกีฬา", "รุ่น/ประเภท", "สถานะ", "สีที่ได้ถ้วย", "สกอร์"]]
            story.append(KeepTogether([
                Paragraph(thai_date(d), s["cellb"]), Spacer(1, 1 * mm),
                _table(tbl, s, [29 * mm, 30 * mm, 45 * mm, 20 * mm, 29 * mm, 27 * mm]), Spacer(1, 3 * mm),
            ]))
    story += [Spacer(1, 10 * mm),
              Paragraph("ลงชื่อ ........................................ ผู้จัดเก็บข้อมูล", s["body"]),
              Paragraph("(........................................)", s["body"])]
    doc.build(story)
    return buf.getvalue()


def sticker_pdf(engine: Engine, event_ids: list[int] | None = None, copies: int = 1) -> bytes:
    """สติ๊กเกอร์ติดถ้วย A4 แผ่นละ 10 ดวง (2 x 5) ขนาด 90 x 50 มม."""
    s = _styles()
    title = sv.get_setting(engine, "event_title")
    school = sv.get_setting(engine, "school_name")
    ev = sv.events_df(engine, include_cancelled=False)
    if event_ids:
        ev = ev[ev.id.isin(event_ids)]
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("สติ๊กเกอร์ถ้วยรางวัล")
    w, h = 90 * mm, 50 * mm
    cols, rows = 2, 5
    left = (A4[0] - cols * w) / 2
    top = A4[1] - (A4[1] - rows * h) / 2
    st_school = ParagraphStyle("ss", fontName="Sarabun", fontSize=10, leading=13, alignment=TA_CENTER,
                               textColor=rl_colors.HexColor("#444444"))
    st_title = ParagraphStyle("st", fontName="Sarabun", fontSize=10.5, leading=14, alignment=TA_CENTER)
    st_sport = ParagraphStyle("sp", fontName="Sarabun-Bold", fontSize=17, leading=22, alignment=TA_CENTER)
    st_label = ParagraphStyle("sl", fontName="Sarabun", fontSize=13, leading=17, alignment=TA_CENTER)
    st_win = ParagraphStyle("sw", fontName="Sarabun-Bold", fontSize=15, leading=20, alignment=TA_CENTER)
    labels = [r for r in ev.itertuples() for _ in range(copies)]
    for i, r in enumerate(labels):
        slot = i % (cols * rows)
        if i and slot == 0:
            c.showPage()
        x = left + (slot % cols) * w
        y = top - (slot // cols + 1) * h
        c.setStrokeColor(rl_colors.HexColor("#bbbbbb"))
        c.setDash(2, 2)
        c.rect(x, y, w, h)
        c.setDash()
        parts = [
            (Paragraph(school, st_school), 13),
            (Paragraph(title, st_title), 14),
            (Paragraph(r.sport, st_sport), 22),
            (Paragraph(r.label, st_label), 17),
            (Paragraph("ชนะเลิศ", st_win), 20),
        ]
        total = sum(p[1] for p in parts)
        cy = y + h / 2 + total / 2
        for p, lead in parts:
            pw, ph = p.wrap(w - 8 * mm, lead * 2)
            cy -= ph
            p.drawOn(c, x + 4 * mm, cy)
    if not labels:
        c.setFont("Sarabun", 14)
        c.drawString(20 * mm, A4[1] - 30 * mm, "ไม่มีรายการ", shaping=True)
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------- เกียรติบัตร

THAI_MONTHS_FULL = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
                    "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
CERT_KINDS = {
    "medal": "ผู้ได้รับเหรียญ (ชนะเลิศ / รองชนะเลิศ)",
    "join": "เข้าร่วมการแข่งขัน",
    "award": "นักกีฬายอดเยี่ยมและรางวัลพิเศษ",
    "role": "ผู้ปฏิบัติหน้าที่ (ประธานสี ลีดเดอร์ ฯลฯ)",
}


def thai_full_date(d: date) -> str:
    return f"{d.day} {THAI_MONTHS_FULL[d.month - 1]} พ.ศ. {d.year + 543}"


def certificate_items(engine: Engine, kind: str, event_ids: list[int] | None = None, color: str | None = None,
                      places: tuple[int, ...] = (1, 2, 3), role_names: list[str] | None = None) -> pd.DataFrame:
    """รายชื่อที่จะได้เกียรติบัตร: name, klass, color, achievement, detail, student_id"""
    cols = ["student_id", "name", "klass", "color", "achievement", "detail"]
    if kind in ("medal", "join"):
        ar = sv.athlete_results(engine)
        ar = ar[ar["done"]] if not ar.empty else ar
        if event_ids:
            ar = ar[ar.event_id.isin(event_ids)]
        if kind == "medal":
            ar = ar[ar.place.isin(places)]
            ach = ar["place"].map(lambda p: "ได้รับรางวัล" + sv.PLACE_TEXT[int(p)])
        else:
            ach = pd.Series("ได้เข้าร่วมการแข่งขัน", index=ar.index)
        out = pd.DataFrame({"student_id": ar["student_id"], "name": ar["full_name"], "klass": ar["class"],
                            "color": ar["color"], "achievement": ach,
                            "detail": "ประเภท " + ar["event"].astype(str), "_d": ar["date"], "_p": ar.get("place")})
        out = out.sort_values(["_d", "detail", "_p", "color", "klass", "name"]).drop(columns=["_d", "_p"])
    elif kind == "award":
        best = sv.best_athletes(engine)
        a = sv.awards_df(engine)
        a = a[~a["title"].isin(sv.BEST_TITLES.values())]  # นักกีฬายอดเยี่ยมใช้ผลที่ระบบคำนวณ
        out = pd.concat([
            pd.DataFrame({"student_id": best["student_id"], "name": best["full_name"], "klass": best["class"],
                          "color": best["color"], "achievement": "ได้รับรางวัล" + best["title"],
                          "detail": [f"ได้เหรียญรวม {r['รวมเหรียญ']} เหรียญ (ทอง {r['ทอง']} · เงิน {r['เงิน']} · ทองแดง {r['ทองแดง']})"
                                     for r in best.to_dict("records")]}),
            pd.DataFrame({"student_id": a["student_id"], "name": a["full_name"], "klass": a["class"],
                          "color": a["color"], "achievement": "ได้รับรางวัล" + a["title"],
                          "detail": a["note"].fillna("")}),
        ], ignore_index=True)
    elif kind == "role":
        st = sv.students_df(engine)
        rows = []
        for r in st.to_dict("records"):
            for role in r["roles"]:
                if not role_names or role in role_names:
                    rows.append((r["id"], r["full_name"], r["class"], r["color"], f"ได้ปฏิบัติหน้าที่{role}", ""))
        out = pd.DataFrame(rows, columns=cols)
    else:
        raise ValueError(kind)
    if color:
        out = out[out["color"] == color]
    return out[cols].reset_index(drop=True)


def certificate_pdf(engine: Engine, items: pd.DataFrame, issue_date: date | None = None) -> bytes:
    """เกียรติบัตร A4 แนวนอน หน้าละ 1 ใบ"""
    import base64
    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    _register_fonts()
    cfg = sv.cert_settings(engine)
    title = sv.get_setting(engine, "event_title")
    school = sv.get_setting(engine, "school_name")
    date_text = cfg["date_text"] or f"ให้ไว้ ณ วันที่ {thai_full_date(issue_date or date.today())}"
    logo = None
    if cfg["logo"]:
        try:
            logo = ImageReader(io.BytesIO(base64.b64decode(cfg["logo"])))
        except Exception:  # รูปเสีย ข้ามไป
            logo = None
    signers = [s for s in cfg["signers"] if s.get("name") or s.get("position")]

    W, H = landscape(A4)
    gold, ink, soft = rl_colors.HexColor("#b8902b"), rl_colors.HexColor("#2b2a33"), rl_colors.HexColor("#6e6a78")
    teal = rl_colors.HexColor("#2f7a6b")

    def para(text, size, bold=False, color=ink, leading=None):
        return Paragraph(text, ParagraphStyle("c", fontName="Sarabun-Bold" if bold else "Sarabun", fontSize=size,
                                              leading=leading or size * 1.45, alignment=TA_CENTER, textColor=color))

    def center(c, p, y, width=W - 60 * mm):
        _, h = p.wrap(width, 200)
        p.drawOn(c, (W - width) / 2, y - h)
        return y - h

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"เกียรติบัตร {title}")
    for n, r in enumerate(items.itertuples(), 1):
        # กรอบ
        c.setStrokeColor(gold)
        c.setLineWidth(3)
        c.rect(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm)
        c.setLineWidth(0.8)
        c.rect(14 * mm, 14 * mm, W - 28 * mm, H - 28 * mm)
        for x, y in [(14, 14), (W / mm - 14, 14), (14, H / mm - 14), (W / mm - 14, H / mm - 14)]:
            c.setFillColor(gold)
            c.circle(x * mm, y * mm, 2.2 * mm, stroke=0, fill=1)
        if cfg["prefix"]:
            c.setFont("Sarabun", 11)
            c.setFillColor(soft)
            c.drawRightString(W - 22 * mm, H - 22 * mm, f"เลขที่ {cfg['prefix']}{n}", shaping=True)

        top = H - 18 * mm
        if logo:
            lh = 24 * mm
            iw, ih = logo.getSize()
            lw = lh * iw / ih
            c.drawImage(logo, (W - lw) / 2, top - lh, lw, lh, mask="auto")
            top -= lh + 2 * mm
        sub = " · ".join(x for x in [f"ชั้น {r.klass}" if r.klass else "", f"สี{r.color}" if r.color else ""] if x)
        block = [  # (ย่อหน้า, ระยะห่างก่อนหน้า มม.)
            (para(school, 20, True), 0),
            (para("เกียรติบัตร", 40, True, color=gold, leading=52), 0),
            (para("ฉบับนี้ให้ไว้เพื่อแสดงว่า", 17, color=soft), 1),
            (para(r.name, 32, True, leading=46), 3),
            (para(sub, 16, color=soft), 0) if sub else None,
            (para(r.achievement, 24, True, color=teal), 4),
            (para(r.detail, 18), 0) if r.detail else None,
            (para(f"ในการแข่งขัน{title}", 17), 2),
            (para("ขอให้มีความสุข ความเจริญ และเป็นแบบอย่างที่ดีตลอดไป", 15, color=soft), 0),
            (para(date_text, 15), 3),
        ]
        block = [b for b in block if b]
        width = W - 60 * mm
        sizes = [p.wrap(width, 300)[1] + gap * mm for p, gap in block]
        bottom = (58 if signers else 24) * mm
        y = top - max(0, (top - bottom - sum(sizes)) / 2)
        for (p, gap), h in zip(block, sizes):
            y -= h
            p.drawOn(c, (W - width) / 2, y)

        if signers:
            slot = (W - 40 * mm) / len(signers)
            base = 26 * mm
            for i, s in enumerate(signers):
                cx = 20 * mm + slot * i + slot / 2
                c.setStrokeColor(soft)
                c.setLineWidth(0.5)
                c.setDash(1, 2)
                c.line(cx - 32 * mm, base + 14 * mm, cx + 32 * mm, base + 14 * mm)
                c.setDash()
                for text, dy, size in [(f"({s['name']})" if s.get("name") else "", 8, 14),
                                       (s.get("position", ""), 1, 13)]:
                    if text:
                        p = Paragraph(text, ParagraphStyle("s", fontName="Sarabun", fontSize=size, leading=size * 1.4,
                                                           alignment=TA_CENTER, textColor=ink))
                        _, h = p.wrap(80 * mm, 40)
                        p.drawOn(c, cx - 40 * mm, base + dy * mm - h + size * 0.4)
        c.showPage()
    if items.empty:
        c.setFont("Sarabun", 16)
        c.drawString(30 * mm, H - 40 * mm, "ไม่มีรายชื่อตามที่เลือก", shaping=True)
        c.showPage()
    c.save()
    return buf.getvalue()


def certificate_register(items: pd.DataFrame, prefix: str = "") -> bytes:
    """ทะเบียนคุมเกียรติบัตร (Excel) เลขที่ตรงกับไฟล์ PDF ชุดเดียวกัน"""
    df = pd.DataFrame({
        "เลขที่": [f"{prefix}{i}" for i in range(1, len(items) + 1)],
        "ชื่อ-สกุล": items["name"], "ชั้น": items["klass"], "สี": items["color"],
        "รางวัล": items["achievement"], "รายการ": items["detail"],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="ทะเบียนเกียรติบัตร")
        ws = xw.sheets["ทะเบียนเกียรติบัตร"]
        for col, w in zip("ABCDEF", [14, 32, 10, 10, 34, 40]):
            ws.column_dimensions[col].width = w
    return buf.getvalue()


# ---------------------------------------------------------------- แผนผังสแตนด์

def stand_pdf(engine: Engine, color_ids: list[int]) -> bytes:
    """แผนผังนั่งสแตนด์ A4 แนวนอน สีละ 1 หน้า · แถวหลังอยู่บน แถวหน้า (A) อยู่ล่างติดสนาม"""
    from reportlab.lib.pagesizes import landscape
    _register_fonts()
    rows, cols = sv.stand_size(engine)
    colors_df = sv.list_colors(engine).set_index("id")
    title = sv.get_setting(engine, "event_title")
    school = sv.get_setting(engine, "school_name")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm, title="แผนผังนั่งสแตนด์")
    head = ParagraphStyle("h", fontName="Sarabun-Bold", fontSize=18, leading=24, alignment=TA_CENTER)
    sub = ParagraphStyle("s", fontName="Sarabun", fontSize=11, leading=15, alignment=TA_CENTER,
                         textColor=rl_colors.HexColor("#555555"))
    cell = ParagraphStyle("c", fontName="Sarabun", fontSize=8.5, leading=11, alignment=TA_CENTER)
    story = []
    W = landscape(A4)[0] - 20 * mm
    for n, cid in enumerate(color_ids):
        if n:
            story.append(PageBreak())
        seats = sv.stand_seats(engine, cid)
        at = {(int(r.row), int(r.col)): r for r in seats.rename(columns={"class": "klass"}).itertuples()}
        story += [Paragraph(f"แผนผังนั่งสแตนด์ สี{colors_df.loc[cid, 'name']}", head),
                  Paragraph(f"{school} · {title} · จัดแล้ว {len(seats)} จาก {rows * cols} ที่", sub), Spacer(1, 4 * mm)]
        data = [[""] + [Paragraph(f"<b>{k}</b>", cell) for k in range(1, cols + 1)]]
        for r in range(rows, 0, -1):
            line = [Paragraph(f"<b>{sv.ROW_LABELS[r - 1]}</b>", cell)]
            for k in range(1, cols + 1):
                s = at.get((r, k))
                line.append(Paragraph(f"<font size=7 color='#888888'>{sv.seat_label(r, k)}</font><br/>"
                                      f"<b>{s.first_name}</b><br/><font size=7.5>{s.klass}</font>"
                                      if s is not None else f"<font size=7 color='#bbbbbb'>{sv.seat_label(r, k)}</font>",
                                      cell))
            data.append(line)
        cw = (W - 10 * mm) / cols
        t = Table(data, colWidths=[10 * mm] + [cw] * cols, rowHeights=[7 * mm] + [24 * mm] * rows)
        style = [("GRID", (1, 1), (-1, -1), 0.6, rl_colors.HexColor("#999999")),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        for r_i in range(rows):
            for k in range(cols):
                s = at.get((rows - r_i, k + 1))
                if s is not None:
                    bg = "#e3effd" if s.gender == "ชาย" else "#fde7ee"
                    style.append(("BACKGROUND", (k + 1, r_i + 1), (k + 1, r_i + 1), rl_colors.HexColor(bg)))
        t.setStyle(TableStyle(style))
        story.append(t)
        field = Table([[Paragraph("<b>ด้านหน้า · สนาม</b>", ParagraphStyle("f", parent=cell, fontSize=11, leading=15))]],
                      colWidths=[W - 10 * mm], rowHeights=[9 * mm])
        field.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor("#cdeee4")),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [Spacer(1, 2 * mm), Table([[None, field]], colWidths=[10 * mm, W - 10 * mm])]
    doc.build(story)
    return buf.getvalue()
