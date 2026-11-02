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
        c.drawString(20 * mm, A4[1] - 30 * mm, "ไม่มีรายการ")
    c.save()
    return buf.getvalue()
