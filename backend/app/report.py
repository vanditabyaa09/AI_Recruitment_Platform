"""CSV and PDF export of screening results."""
from __future__ import annotations

import io
import csv


def candidates_csv(candidates) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Rank", "Name", "Overall", "Skills", "Experience", "Domain",
                "Education", "Soft Skills", "Years", "Recommendation",
                "Hidden Gem", "Matched Skills", "Missing Must-Haves"])
    for c in sorted(candidates, key=lambda x: x.rank or 9999):
        s = c.scores
        w.writerow([
            c.rank, c.parsed.name,
            f"{s.overall:.0f}" if s else "",
            f"{s.skills:.0f}" if s else "",
            f"{s.experience:.0f}" if s else "",
            f"{s.domain:.0f}" if s else "",
            f"{s.education:.0f}" if s else "",
            f"{s.soft_skills:.0f}" if s else "",
            f"{c.parsed.years_of_experience:.0f}",
            c.explanation.recommendation if c.explanation else "",
            "Yes" if c.is_hidden_gem else "",
            "; ".join(c.matched_skills),
            "; ".join(c.missing_skills),
        ])
    return buf.getvalue()


def candidate_pdf(c, jd) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading2"], textColor=colors.HexColor("#1e293b"))
    elements = []

    elements.append(Paragraph(f"Candidate Evaluation — {c.parsed.name}", styles["Title"]))
    if jd:
        elements.append(Paragraph(f"For: {jd.title} ({jd.parsed.seniority})", styles["Normal"]))
    elements.append(Spacer(1, 12))

    s = c.scores
    if s:
        rows = [["Overall", f"{s.overall:.0f}"], ["Skills", f"{s.skills:.0f}"],
                ["Experience", f"{s.experience:.0f}"], ["Semantic fit", f"{s.semantic:.0f}"],
                ["Domain", f"{s.domain:.0f}"], ["Education", f"{s.education:.0f}"]]
        t = Table([["Rank", f"#{c.rank}"]] + rows, colWidths=[2 * inch, 2 * inch])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 12))

    if c.explanation:
        e = c.explanation
        elements.append(Paragraph("Summary", h))
        elements.append(Paragraph(e.summary or "—", styles["Normal"]))
        for title, items in [("Strengths", e.strengths), ("Gaps", e.gaps), ("Flags", e.flags)]:
            if items:
                elements.append(Spacer(1, 8))
                elements.append(Paragraph(title, h))
                for it in items:
                    elements.append(Paragraph(f"• {it}", styles["Normal"]))

    if c.interview_questions:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Tailored Interview Questions", h))
        for q in c.interview_questions:
            elements.append(Paragraph(f"<b>[{q.category}]</b> {q.question}", styles["Normal"]))
            elements.append(Spacer(1, 4))

    doc.build(elements)
    return buf.getvalue()
