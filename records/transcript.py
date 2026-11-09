"""PDF transcript generation with ReportLab."""
import io

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from academics.models import Institution

NAVY = colors.HexColor("#1f3a5f")


def _image(field, width, height):
    """ReportLab image from an uploaded file, or None if missing/unreadable."""
    if not field:
        return None
    try:
        return Image(field.path, width=width, height=height, kind="proportional")
    except Exception:  # noqa: BLE001 - a broken image must never stop a transcript
        return None


def build_transcript_pdf(student):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Transcript - {student.matric_no}",
    )
    styles = getSampleStyleSheet()
    h_center = ParagraphStyle("hc", parent=styles["Title"], fontSize=15, textColor=NAVY, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], alignment=1, fontSize=10)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    sem_title = ParagraphStyle("sem", parent=styles["Heading4"], textColor=NAVY, spaceBefore=8, spaceAfter=3)

    institution = Institution.load()
    inst_name = institution.name if institution else "Student Academic Records"
    heading = [
        Paragraph(inst_name.upper(), h_center),
        Paragraph(f"{student.department.faculty}<br/>Department of {student.department.name}", sub),
    ]
    if institution and institution.address:
        heading.append(Paragraph(institution.address, ParagraphStyle("addr", parent=sub, fontSize=8)))
    heading += [Spacer(1, 2 * mm), Paragraph("<b>STUDENT ACADEMIC TRANSCRIPT</b>", sub)]
    logo = _image(institution.logo if institution else None, 22 * mm, 22 * mm)
    photo = _image(student.photo, 25 * mm, 30 * mm)
    header = Table([[logo or "", heading, photo or ""]], colWidths=[28 * mm, 124 * mm, 28 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "RIGHT")]))
    story = [header, Spacer(1, 5 * mm)]

    info = [
        ["Name:", f"{student.user.last_name.upper()}, {student.user.first_name}",
         "Matric No:", student.matric_no],
        ["Department:", str(student.department), "Level:", student.get_level_display()],
        ["Gender:", student.get_gender_display(), "Entry Session:", str(student.entry_session)],
        ["Status:", student.get_status_display(), "Date Issued:", timezone.localdate().strftime("%d %b %Y")],
    ]
    info_table = Table(info, colWidths=[25 * mm, 70 * mm, 28 * mm, 57 * mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [info_table, Spacer(1, 4 * mm)]

    semesters = student.semester_breakdown()
    if not semesters:
        story.append(Paragraph("No approved results on record.", styles["Normal"]))

    for sem in semesters:
        story.append(Paragraph(f"{sem['session']} Session - {sem['semester']}", sem_title))
        data = [["Code", "Course Title", "Units", "Score", "Grade", "GP", "Points"]]
        for r in sem["results"]:
            c = r.registration.course
            data.append([c.code, Paragraph(c.title, styles["Normal"]), c.units, f"{r.total:.0f}",
                         r.grade, r.grade_point, c.units * r.grade_point])
        data.append(["", "Semester totals", sem["units"], "", "", "", sem["points"]])
        t = Table(data, colWidths=[22 * mm, 82 * mm, 14 * mm, 15 * mm, 14 * mm, 12 * mm, 18 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b8c4")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f3f6fa")]),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e4eaf2")),
        ]))
        story.append(t)
        story.append(Paragraph(f"<b>GPA:</b> {sem['gpa']} &nbsp;&nbsp;&nbsp; <b>CGPA:</b> {sem['cgpa']}", styles["Normal"]))

    story += [
        Spacer(1, 6 * mm),
        Table(
            [["Cumulative GPA", f"{student.cgpa()}"],
             ["Total units passed", f"{student.total_units_passed()}"],
             ["Class of degree (current standing)", student.degree_class()]],
            colWidths=[70 * mm, 70 * mm],
            style=TableStyle([
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b8c4")),
            ]),
        ),
        Spacer(1, 6 * mm),
        Paragraph(
            "Grading: " + ", ".join(f"{g} ({m}+) = {p}" for m, g, p in settings.GRADING_SCALE)
            + ". Only results approved by the administrator appear on this transcript.",
            small,
        ),
        Spacer(1, 14 * mm),
        Paragraph("______________________________<br/>"
                  + (f"{institution.registrar_name}<br/>" if institution and institution.registrar_name else "")
                  + "Registrar", styles["Normal"]),
    ]

    doc.build(story)
    return buffer.getvalue()
