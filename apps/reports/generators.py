import csv
import io
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.ingestion.models import Event


def report_window(frequency, now=None):
    """daily and weekly are rolling windows. monthly is the previous calendar month.

    The monthly job runs on the 1st. A rolling 30 days would mix two months.
    """
    now = now or timezone.now()
    if frequency == "monthly":
        first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous = first_this_month - timedelta(days=1)
        start = previous.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, first_this_month
    days = 7 if frequency == "weekly" else 1
    return now - timedelta(days=days), now


def _rows(frequency):
    start, end = report_window(frequency)
    qs = Event.objects.filter(timestamp__gte=start)
    if frequency == "monthly":
        qs = qs.filter(timestamp__lt=end)
    return list(qs.values("name").annotate(total=Sum("value"), count=Count("id")).order_by("-total"))


def csv_safe(value) -> str:
    # A cell that starts with =, +, - or @ is a formula in Excel.
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def make_csv(frequency) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "total_value", "event_count"])
    for row in _rows(frequency):
        writer.writerow([csv_safe(row["name"]), row["total"], row["count"]])
    return buf.getvalue().encode()


def make_pdf(frequency, title="Report") -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = 800
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, f"{title} ({frequency})")
    pdf.setFont("Helvetica", 11)
    y -= 30
    for row in _rows(frequency):
        pdf.drawString(50, y, f"{row['name']}   total={row['total']}   count={row['count']}")
        y -= 18
        if y < 60:
            pdf.showPage()
            y = 800
    pdf.save()
    return buf.getvalue()
