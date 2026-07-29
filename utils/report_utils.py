"""
PDF report generation using ReportLab — cover page, dataset overview,
cleaning summary, AI recommendations, model performance, and conclusion.
"""
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_conclusion(ctx):
    profile = ctx.get("profile", {})
    health = ctx.get("health_score", 0)
    best_model = ctx.get("best_model", "N/A")
    task = ctx.get("task", "unknown")
    best_metrics = ctx.get("best_metrics", {})

    lines = []
    lines.append(
        f"The dataset '{ctx.get('dataset_name','dataset')}' contains "
        f"{profile.get('shape', {}).get('rows','?')} rows and {profile.get('shape', {}).get('columns','?')} columns, "
        f"with an overall health score of {health}/100."
    )
    if health >= 80:
        lines.append("Overall data quality is strong, with limited missing values, duplicates, or structural issues.")
    elif health >= 50:
        lines.append("Data quality is moderate — some cleaning steps (missing values, duplicates, or constant/ID columns) meaningfully improved usability.")
    else:
        lines.append("Data quality was initially weak; the cleaning pipeline addressed a substantial share of missing data and structural issues, but results should be interpreted with caution.")

    if best_model and best_model != "N/A":
        lines.append(f"For this {task} task, '{best_model}' was selected as the best-performing model on the held-out test set.")
        if best_metrics:
            metric_str = ", ".join(f"{k}: {v}" for k, v in best_metrics.items() if v is not None)
            lines.append(f"Key metrics: {metric_str}.")

    lines.append(
        "Limitations: results are based on a single train/test split and default hyperparameters unless tuning was applied; "
        "performance may vary with more data, feature engineering, or cross-validation. "
        "For production deployment, monitor for data drift and retrain periodically."
    )
    return " ".join(lines)


def build_report(path, ctx):
    """
    ctx keys: project_name, dataset_name, target_column, task, health_score,
    profile (dict), recommendations (list), warnings (list),
    leaderboard (list of dicts), best_model, best_metrics (dict)
    """
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleBig", parent=styles["Title"], fontSize=26, spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=8,
                         textColor=colors.HexColor("#4338ca"))
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=9, textColor=colors.grey)

    elements = []

    # Cover page
    elements.append(Spacer(1, 4 * cm))
    elements.append(Paragraph(ctx.get("project_name", "AutoML Report"), title_style))
    elements.append(HRFlowable(width="100%", color=colors.HexColor("#4338ca"), thickness=2))
    elements.append(Spacer(1, 0.6 * cm))
    cover_rows = [
        ["Dataset", ctx.get("dataset_name", "-")],
        ["Date", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Selected Model", ctx.get("best_model", "-")],
        ["Dataset Health Score", f"{ctx.get('health_score', '-')}/100"],
        ["Target Column", ctx.get("target_column", "-")],
        ["Task Type", str(ctx.get("task", "-")).title()],
    ]
    t = Table(cover_rows, colWidths=[5 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4338ca")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    elements.append(t)
    elements.append(PageBreak())

    # Dataset overview
    profile = ctx.get("profile", {})
    elements.append(Paragraph("Dataset Overview", h2))
    shape = profile.get("shape", {})
    overview_rows = [
        ["Rows", shape.get("rows", "-")],
        ["Columns", shape.get("columns", "-")],
        ["Duplicate Rows", profile.get("duplicate_rows", "-")],
        ["Total Missing Cells", sum(profile.get("missing_counts", {}).values()) if profile.get("missing_counts") else "-"],
    ]
    ot = Table(overview_rows, colWidths=[5 * cm, 9 * cm])
    ot.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(ot)
    elements.append(Spacer(1, 0.4 * cm))

    missing_pct = profile.get("missing_pct", {})
    top_missing = sorted(missing_pct.items(), key=lambda x: x[1], reverse=True)[:8]
    if any(v > 0 for _, v in top_missing):
        elements.append(Paragraph("Columns with most missing values:", body))
        rows = [["Column", "Missing %"]] + [[c, f"{v}%"] for c, v in top_missing if v > 0]
        mt = Table(rows, colWidths=[8 * cm, 4 * cm])
        mt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ]))
        elements.append(mt)

    # AI Recommendations
    elements.append(Paragraph("AI Recommendations", h2))
    for rec in ctx.get("recommendations", [])[:15]:
        elements.append(Paragraph(f"\u2022 {rec}", body))
    warnings = ctx.get("warnings", [])
    if warnings:
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(Paragraph("Warnings", ParagraphStyle("w", parent=h2, textColor=colors.HexColor("#b91c1c"))))
        for w in warnings[:10]:
            elements.append(Paragraph(f"\u26a0 {w}", body))

    elements.append(PageBreak())

    # Model performance
    elements.append(Paragraph("Model Performance / Leaderboard", h2))
    lb = ctx.get("leaderboard", [])
    if lb:
        cols = list(lb[0].keys())
        rows = [cols] + [[str(row.get(c, "")) for c in cols] for row in lb]
        lt = Table(rows, repeatRows=1)
        lt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4338ca")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        elements.append(lt)
    else:
        elements.append(Paragraph("No models trained yet.", body))

    elements.append(Spacer(1, 0.4 * cm))
    best_metrics = ctx.get("best_metrics", {})
    if best_metrics:
        elements.append(Paragraph(f"Best Model: {ctx.get('best_model','-')}", body))
        for k, v in best_metrics.items():
            elements.append(Paragraph(f"\u2014 {k}: {v}", body))

    elements.append(PageBreak())

    # Conclusion
    elements.append(Paragraph("Final Conclusion", h2))
    elements.append(Paragraph(ctx.get("conclusion", "No conclusion generated."), body))
    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph("Generated by Flask AutoML Studio", small))

    doc.build(elements)
    return path
