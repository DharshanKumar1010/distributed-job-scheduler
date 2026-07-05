"""Generates docs/submission.pdf - an 8-page portfolio-style summary of the
Distributed Job Scheduler project. Run with the backend venv (reportlab is
listed in backend/requirements.txt):

    backend/.venv/Scripts/python.exe scripts/generate_submission_pdf.py
"""

import math
import os

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------- palette --
NAVY = HexColor("#0B1120")
BLUE = HexColor("#3B82F6")
DARK = HexColor("#1E293B")
MUTED = HexColor("#64748B")
WHITE = HexColor("#FFFFFF")
LIGHT_BG = HexColor("#F8FAFC")
SUCCESS = HexColor("#10B981")
WARNING = HexColor("#F59E0B")

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 1 * cm
FOOTER_Y = 1 * cm

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "docs", "submission.pdf")


# ------------------------------------------------------------- primitives --
def fit_text(text, font, size, max_width):
    """Truncates with an ellipsis using real glyph widths, instead of a
    rough char-count guess that either cuts words mid-way or wastes space.
    """
    text = str(text)
    if stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    while text and stringWidth(text + ellipsis, font, size) > max_width:
        text = text[:-1]
    return (text + ellipsis) if text else ellipsis


def wrap_text(text, font, size, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if stringWidth(trial, font, size) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_paragraph(c, x, y, text, font="Helvetica", size=10, color=DARK, leading=14, max_width=None):
    max_width = max_width if max_width is not None else CONTENT_W
    c.setFont(font, size)
    c.setFillColor(color)
    for line in wrap_text(text, font, size, max_width):
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_header_footer(c, page_num):
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN, PAGE_H - HEADER_H + 0.32 * cm, "Distributed Job Scheduler")
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - HEADER_H + 0.32 * cm, f"Page {page_num}")

    c.setStrokeColor(BLUE)
    c.setLineWidth(1)
    c.line(MARGIN, FOOTER_Y + 0.35 * cm, PAGE_W - MARGIN, FOOTER_Y + 0.35 * cm)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, FOOTER_Y, "Dharshan Kumar | DharshanKumar1010")
    c.drawRightString(PAGE_W - MARGIN, FOOTER_Y, "Confidential — Assignment Submission")


def draw_section_header(c, y, text):
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(NAVY)
    c.drawString(MARGIN, y, text)
    y -= 0.3 * cm
    c.setStrokeColor(BLUE)
    c.setLineWidth(2)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    return y - 0.7 * cm


def draw_subsection(c, x, y, text, size=11, color=NAVY):
    c.setFont("Helvetica-Bold", size)
    c.setFillColor(color)
    c.drawString(x, y, text)
    return y - (size + 6)


def draw_code_block(c, x, y, code_text, width, font_size=9, min_font_size=6.2):
    lines = code_text.strip("\n").split("\n")
    padding = 6
    avail_width = width - 2 * padding - 4

    # Shrink the font until the longest line actually fits, rather than
    # truncating code (a cut-off SQL statement is worse than a smaller font).
    size = font_size
    if lines:
        while size > min_font_size:
            widest = max(stringWidth(line, "Courier", size) for line in lines)
            if widest <= avail_width:
                break
            size -= 0.2

    line_height = size + 3
    box_height = len(lines) * line_height + 2 * padding
    c.setFillColor(LIGHT_BG)
    c.rect(x, y - box_height, width, box_height, fill=1, stroke=0)
    c.setFillColor(BLUE)
    c.rect(x, y - box_height, 1.5, box_height, fill=1, stroke=0)
    c.setFont("Courier", size)
    c.setFillColor(DARK)
    ty = y - padding - size
    for line in lines:
        c.drawString(x + padding + 4, ty, line)
        ty -= line_height
    return y - box_height


def draw_caption(c, x, y, text, max_width=None):
    max_width = max_width if max_width is not None else CONTENT_W
    return draw_paragraph(c, x, y, text, font="Helvetica-Oblique", size=8, color=MUTED, leading=11, max_width=max_width)


def draw_table(c, x, y, col_widths, rows, header=True, font_size=8.5, row_h=15, header_color=NAVY):
    total_w = sum(col_widths)
    for i, row in enumerate(rows):
        row_y_top = y - i * row_h
        is_header = header and i == 0
        if is_header:
            c.setFillColor(header_color)
            c.rect(x, row_y_top - row_h, total_w, row_h, fill=1, stroke=0)
            text_color = WHITE
            font = "Helvetica-Bold"
        else:
            if (i - (1 if header else 0)) % 2 == 1:
                c.setFillColor(LIGHT_BG)
                c.rect(x, row_y_top - row_h, total_w, row_h, fill=1, stroke=0)
            text_color = DARK
            font = "Helvetica"
        c.setFont(font, font_size)
        c.setFillColor(text_color)
        cx = x + 5
        for col_i, cell in enumerate(row):
            c.drawString(cx, row_y_top - row_h + 4.5, fit_text(cell, font, font_size, col_widths[col_i] - 8))
            cx += col_widths[col_i]
    c.setStrokeColor(HexColor("#E2E8F0"))
    c.setLineWidth(0.5)
    c.rect(x, y - row_h * len(rows), total_w, row_h * len(rows), fill=0, stroke=1)
    return y - row_h * len(rows)


def draw_check_mark(c, x, y, size=7, color=SUCCESS):
    """Vector-drawn checkmark - avoids relying on a Unicode glyph (U+2713)
    being present in a non-embedded base-14 font's encoding."""
    c.setStrokeColor(color)
    c.setLineWidth(1.4)
    c.setLineCap(1)
    p = c.beginPath()
    p.moveTo(x, y + size * 0.4)
    p.lineTo(x + size * 0.38, y)
    p.lineTo(x + size, y + size * 0.8)
    c.drawPath(p, fill=0, stroke=1)


def draw_warning_mark(c, x, y, size=7, color=WARNING):
    """Vector-drawn warning triangle with an exclamation mark inside."""
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x, y)
    p.lineTo(x + size, y)
    p.lineTo(x + size / 2, y + size * 1.05)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", size * 0.75)
    c.drawCentredString(x + size / 2, y + size * 0.18, "!")


def draw_trade_off_box(c, x, y, width, good_points, bad_points):
    line_h = 12
    padding = 8
    n_lines = len(good_points) + len(bad_points)
    height = n_lines * line_h + 2 * padding + 4
    c.setFillColor(LIGHT_BG)
    c.rect(x, y - height, width, height, fill=1, stroke=0)
    ty = y - padding - 9
    for point in good_points:
        draw_check_mark(c, x + padding, ty - 1, size=7)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(DARK)
        for line in wrap_text(point, "Helvetica", 8.5, width - 2 * padding - 14):
            c.drawString(x + padding + 14, ty, line)
            ty -= line_h
    for point in bad_points:
        draw_warning_mark(c, x + padding, ty - 2, size=7)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(DARK)
        for line in wrap_text(point, "Helvetica", 8.5, width - 2 * padding - 14):
            c.drawString(x + padding + 14, ty, line)
            ty -= line_h
    return y - height


def draw_box(c, cx, cy, w, h, title, subtitle, fill=WHITE, border=BLUE, text_color=DARK, title_color=None):
    x, y = cx - w / 2, cy - h / 2
    c.setFillColor(fill)
    c.setStrokeColor(border)
    c.setLineWidth(1.4)
    c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
    tc = title_color or text_color
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(tc)
    c.drawCentredString(cx, cy + 5, title)
    c.setFont("Helvetica", 7)
    c.setFillColor(tc)
    for i, line in enumerate(wrap_text(subtitle, "Helvetica", 7, w - 10)):
        c.drawCentredString(cx, cy - 8 - i * 8.5, line)


def draw_arrow(c, x1, y1, x2, y2, label=None, color=MUTED, dashed=False):
    c.setStrokeColor(color)
    c.setLineWidth(1)
    if dashed:
        c.setDash(3, 2)
    c.line(x1, y1, x2, y2)
    c.setDash()
    angle = math.atan2(y2 - y1, x2 - x1)
    ah_len, ah_w = 6, 3.2
    tip = (x2, y2)
    left = (x2 - ah_len * math.cos(angle) + ah_w * math.sin(angle), y2 - ah_len * math.sin(angle) - ah_w * math.cos(angle))
    right = (x2 - ah_len * math.cos(angle) - ah_w * math.sin(angle), y2 - ah_len * math.sin(angle) + ah_w * math.cos(angle))
    path = c.beginPath()
    path.moveTo(*tip)
    path.lineTo(*left)
    path.lineTo(*right)
    path.close()
    c.setFillColor(color)
    c.drawPath(path, fill=1, stroke=0)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        c.setFont("Helvetica-Oblique", 7)
        c.setFillColor(MUTED)
        c.drawString(mx + 6, my, label)


# ------------------------------------------------------------------ pages --
def page_1_cover(c):
    c.setFillColor(NAVY)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    title_y = PAGE_H - 4.3 * cm
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 36)
    c.drawString(MARGIN, title_y, "Distributed Job Scheduler")

    rule_y = title_y - 0.9 * cm
    c.setStrokeColor(BLUE)
    c.setLineWidth(3)
    c.line(MARGIN, rule_y, MARGIN + 8 * cm, rule_y)

    c.setFont("Helvetica-Oblique", 16)
    c.setFillColor(WHITE)
    c.drawString(MARGIN, rule_y - 1.1 * cm, "Production-Grade Background Job Processing Platform")

    # Middle metrics box
    box_x, box_w = PAGE_W * 0.1, PAGE_W * 0.8
    box_y, box_h = PAGE_H * 0.40, 3.4 * cm
    c.setFillColor(LIGHT_BG)
    c.roundRect(box_x, box_y, box_w, box_h, 10, fill=1, stroke=0)

    metrics = [("13", "Database Tables"), ("33", "Automated Tests"), ("49", "REST Endpoints"), ("16", "Bonus Features")]
    col_w = box_w / 4
    for i, (number, label) in enumerate(metrics):
        cx = box_x + col_w * i + col_w / 2
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(BLUE)
        c.drawCentredString(cx, box_y + box_h * 0.58, number)
        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawCentredString(cx, box_y + box_h * 0.25, label.upper())

    # Bottom two columns
    bottom_y = PAGE_H * 0.20
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(MARGIN, bottom_y, "SUBMITTED BY")
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(WHITE)
    c.drawString(MARGIN, bottom_y - 0.7 * cm, "Dharshan Kumar")
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN, bottom_y - 1.3 * cm, "B.Tech CSE (Data Science) — SRM IST")
    c.drawString(MARGIN, bottom_y - 1.8 * cm, "July 5, 2025")

    right_x = PAGE_W / 2 + 1 * cm
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(right_x, bottom_y, "REPOSITORY")
    c.setFont("Helvetica", 10)
    c.setFillColor(WHITE)
    c.drawString(right_x, bottom_y - 0.7 * cm, "github.com/DharshanKumar1010/")
    c.setFillColor(BLUE)
    c.drawString(right_x, bottom_y - 1.2 * cm, "distributed-job-scheduler")
    text_w = stringWidth("distributed-job-scheduler", "Helvetica", 10)
    c.setStrokeColor(BLUE)
    c.setLineWidth(0.6)
    c.line(right_x, bottom_y - 1.28 * cm, right_x + text_w, bottom_y - 1.28 * cm)
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 9)
    c.drawString(right_x, bottom_y - 1.9 * cm, "Stack: FastAPI • PostgreSQL • Redis • React")

    c.showPage()


def page_2_executive_summary(c):
    draw_header_footer(c, 2)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "What Was Built")

    left_w = CONTENT_W * 0.58
    gap = 0.6 * cm
    right_x = MARGIN + left_w + gap
    right_w = CONTENT_W - left_w - gap

    # Right column background box - sized to hug its content (header + 10
    # metric rows), not stretched down to the footer.
    box_top = y
    metrics_count = 10
    box_height = 0.7 * cm + 0.5 * cm + metrics_count * 0.62 * cm + 0.35 * cm
    box_bottom = box_top - box_height
    c.setFillColor(LIGHT_BG)
    c.roundRect(right_x, box_bottom, right_w, box_height, 8, fill=1, stroke=0)

    # Left column content
    ly = y
    p1 = (
        "A distributed job scheduling platform capable of processing background jobs reliably at "
        "scale. The system handles five job types (immediate, delayed, scheduled, recurring, and "
        "batch), distributes work across multiple worker processes using PostgreSQL's atomic SKIP "
        "LOCKED mechanism, and provides real-time observability through a WebSocket-powered React "
        "dashboard."
    )
    ly = draw_paragraph(c, MARGIN, ly, p1, max_width=left_w - 0.3 * cm)
    ly -= 8
    p2 = (
        "Built over 13 phases, the implementation goes beyond the core requirements to include a "
        "full DAG workflow engine, distributed locking, queue sharding for horizontal scale, "
        "role-based access control, and AI-powered failure analysis using the Claude API."
    )
    ly = draw_paragraph(c, MARGIN, ly, p2, max_width=left_w - 0.3 * cm)
    ly -= 14

    ly = draw_subsection(c, MARGIN, ly, "Core Technical Achievement")
    ly -= 4
    code = """-- The atomic job claiming query that prevents duplicate execution
UPDATE jobs
SET status='claimed', worker_id=:worker_id,
    claimed_at=now(), attempts=attempts+1
WHERE id = (
  SELECT id FROM jobs
  WHERE queue_id = :queue_id
    AND status = 'queued'
    AND (scheduled_at IS NULL OR scheduled_at <= now())
  ORDER BY priority DESC, created_at ASC
  FOR UPDATE SKIP LOCKED  -- prevents two workers claiming same job
  LIMIT 1
)
RETURNING *;"""
    ly = draw_code_block(c, MARGIN, ly, code, left_w - 0.3 * cm, font_size=7.6)
    ly -= 8
    ly = draw_caption(
        c, MARGIN,
        ly,
        "This single query, running concurrently across N worker processes, guarantees each job "
        "executes exactly once — verified by automated concurrency tests.",
        max_width=left_w - 0.3 * cm,
    )

    # Right column content
    ry = box_top - 0.5 * cm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(NAVY)
    c.drawString(right_x + 0.4 * cm, ry, "Key Metrics")
    ry -= 0.7 * cm

    metrics = [
        ("REST API Endpoints", "49"),
        ("Database Tables", "13"),
        ("Automated Tests", "33 (all passing)"),
        ("Job Types Supported", "5"),
        ("WebSocket Events", "15"),
        ("RBAC Permissions", "29"),
        ("Retry Strategies", "3"),
        ("Max Queue Shards", "64"),
        ("Test Files", "6"),
        ("API Response Time", "<50ms (p99)"),
    ]
    for label, value in metrics:
        c.setFillColor(BLUE)
        c.circle(right_x + 0.5 * cm, ry + 3, 2, fill=1, stroke=0)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(DARK)
        c.drawString(right_x + 0.9 * cm, ry, label)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawRightString(right_x + right_w - 0.4 * cm, ry, value)
        ry -= 0.62 * cm

    c.showPage()


def page_3_architecture(c):
    draw_header_footer(c, 3)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "Architecture")

    diagram_top = y - 0.3 * cm
    # Shifted left of true center so the Claude API box has a clean, non-
    # overlapping column of its own on the right.
    center_x = MARGIN + CONTENT_W * 0.35

    row1_y = diagram_top - 0.9 * cm
    row2_y = row1_y - 2.3 * cm
    row3_y = row2_y - 2.5 * cm
    row4_y = row3_y - 2.3 * cm

    box_w, box_h = 6.2 * cm, 1.3 * cm
    draw_box(c, center_x, row1_y, box_w, box_h, "React Dashboard", "8 Pages • WebSocket • Live DAG Canvas", border=BLUE)
    draw_arrow(c, center_x, row1_y - box_h / 2, center_x, row2_y + box_h / 2 + 0.35 * cm, label="HTTPS + WSS")

    draw_box(c, center_x, row2_y, box_w, box_h, "FastAPI", "49 Endpoints • JWT + RBAC • WebSocket Hub", fill=NAVY, border=NAVY, title_color=WHITE)

    small_w, small_h = 3.9 * cm, 1.4 * cm
    spread = CONTENT_W * 0.27
    b1x, b2x, b3x = center_x - spread, center_x, center_x + spread
    draw_arrow(c, center_x - spread * 0.55, row2_y - box_h / 2, b1x, row3_y + small_h / 2 + 0.3 * cm)
    draw_arrow(c, center_x, row2_y - box_h / 2, b2x, row3_y + small_h / 2 + 0.3 * cm)
    draw_arrow(c, center_x + spread * 0.55, row2_y - box_h / 2, b3x, row3_y + small_h / 2 + 0.3 * cm)

    draw_box(c, b1x, row3_y, small_w, small_h, "Worker (Shard 0)", "SKIP LOCKED • Heartbeat • Retry")
    draw_box(c, b2x, row3_y, small_w, small_h, "Worker (Shard N)", "Concurrent • Graceful shutdown")
    draw_box(c, b3x, row3_y, small_w, small_h, "Dispatcher + Reaper", "Leader election • Cron • Recovery")

    infra_w, infra_h = 5.6 * cm, 1.5 * cm
    infra_spread = CONTENT_W * 0.20
    pgx, redisx = center_x - infra_spread, center_x + infra_spread
    draw_arrow(c, b1x, row3_y - small_h / 2, pgx - 0.6 * cm, row4_y + infra_h / 2 + 0.3 * cm)
    draw_arrow(c, b2x, row3_y - small_h / 2, pgx + 0.6 * cm, row4_y + infra_h / 2 + 0.3 * cm)
    draw_arrow(c, b1x, row3_y - small_h / 2, redisx - 0.6 * cm, row4_y + infra_h / 2 + 0.3 * cm, color=HexColor("#94A3B8"))
    draw_arrow(c, b3x, row3_y - small_h / 2, redisx + 0.6 * cm, row4_y + infra_h / 2 + 0.3 * cm)

    draw_box(c, pgx, row4_y, infra_w, infra_h, "PostgreSQL 15", "13 tables • Migrations • Advisory locks", fill=HexColor("#EFF6FF"))
    draw_box(c, redisx, row4_y, infra_w, infra_h, "Redis 7", "Pub/Sub • Token bucket • Shard registry", fill=HexColor("#EFF6FF"))

    # Claude API box: its own column to the right, clear of the b3 dispatcher
    # box (verified: b3's right edge sits comfortably left of claude_x's
    # left edge, unlike the first draft which overlapped).
    claude_w = 3.3 * cm
    claude_x = PAGE_W - MARGIN - claude_w / 2
    claude_y = row3_y
    draw_box(c, claude_x, claude_y, claude_w, small_h, "Claude API", "AI failure analysis", fill=HexColor("#FEF3C7"), border=WARNING)
    # Routed from the rightmost box's edge (not straight from a worker box)
    # so the line doesn't cross through the dispatcher box sitting between them.
    draw_arrow(c, b3x + small_w / 2 + 0.1 * cm, row3_y, claude_x - claude_w / 2 - 0.15 * cm, claude_y, label="On DLQ entry", color=WARNING)

    table_y = row4_y - infra_h / 2 - 1.0 * cm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(NAVY)
    c.drawString(MARGIN, table_y, "Component Details")
    table_y -= 0.5 * cm

    rows = [
        ["Component", "Responsibility", "Key Technology"],
        ["FastAPI", "REST + WebSocket", "async, Pydantic v2"],
        ["Worker", "Job execution", "asyncio, SKIP LOCKED"],
        ["Dispatcher", "Scheduling", "croniter, advisory lock"],
        ["Reaper", "Recovery", "heartbeat detection"],
        ["React", "Dashboard", "Zustand, react-query, Recharts"],
    ]
    col_widths = [CONTENT_W * 0.28, CONTENT_W * 0.4, CONTENT_W * 0.32]
    draw_table(c, MARGIN, table_y, col_widths, rows)

    c.showPage()


def page_4_feature_checklist(c):
    draw_header_footer(c, 4)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "Feature Checklist")

    col_w = CONTENT_W / 2 - 0.4 * cm
    left_x = MARGIN
    right_x = MARGIN + CONTENT_W / 2 + 0.4 * cm

    core = [
        ("JWT Authentication", "Register, login, token refresh"),
        ("Multi-tenant Orgs", "Org → Project → Queue hierarchy"),
        ("Queue Management", "Create, pause, resume, configure"),
        ("Immediate Jobs", "Execute as soon as worker available"),
        ("Delayed Jobs", "Execute after specified datetime"),
        ("Scheduled Jobs", "Execute at exact datetime"),
        ("Recurring Jobs", "Cron expression support (croniter)"),
        ("Batch Jobs", "Parent + N children in one call"),
        ("Atomic Job Claiming", "FOR UPDATE SKIP LOCKED"),
        ("Retry Strategies", "Fixed, linear, exponential backoff"),
        ("Dead Letter Queue", "Permanent failure handling"),
        ("Worker Heartbeats", "Every 10s, CPU + memory stats"),
        ("Graceful Shutdown", "Finishes in-flight jobs on SIGTERM"),
        ("Reaper Process", "Reclaims jobs from dead workers"),
        ("Idempotency Keys", "Deduplication on job creation"),
        ("Job Cancellation", "Cancel queued jobs"),
        ("Execution Logs", "Per-attempt logs with levels"),
        ("Queue Statistics", "Real-time pending/running/failed counts"),
        ("Worker Monitoring", "Status, current jobs, last seen"),
        ("React Dashboard", "8 pages, dark theme"),
    ]
    bonus = [
        ("WebSocket Updates", "15 event types, org-scoped fanout"),
        ("Live DAG Canvas", "Pure SVG, animated edges, real-time"),
        ("Workflow API", "POST /workflows for diamond patterns"),
        ("Dep Cycle Detection", "Iterative DFS with cycle path"),
        ("API Rate Limiting", "Sliding window, Lua atomic script"),
        ("Token Bucket", "Per-queue execution rate limiting"),
        ("Distributed Locking", "Redis lock + Postgres advisory lock"),
        ("Cron Deduplication", "Exactly-once across N dispatchers"),
        ("Queue Sharding", "Consistent hashing, up to 64 shards"),
        ("Auto Shard Assign", "Workers self-assign via Redis registry"),
        ("RBAC", "29 permissions across 4 roles"),
        ("Settings Page", "Team management, invite members"),
        ("AI Failure Analysis", "Claude API root cause summaries"),
        ("Error Classification", "8-category heuristic classifier"),
        ("Failure Patterns", "Queue-level analytics, peak hours"),
        ("Toast Notifications", "Real-time, clickable, auto-dismiss"),
    ]

    def draw_checklist(x, header, header_color, items, top_y):
        cy = top_y
        c.setFont("Helvetica-Bold", 10.5)
        c.setFillColor(header_color)
        c.drawString(x, cy, header)
        cy -= 0.45 * cm
        for name, desc in items:
            draw_check_mark(c, x, cy - 1, size=6.5)
            c.setFillColor(DARK)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 12, cy, name)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7.3)
            desc_lines = wrap_text(desc, "Helvetica", 7.3, col_w - 12)
            c.drawString(x + 12, cy - 9, desc_lines[0] if desc_lines else "")
            cy -= 0.62 * cm
        return cy

    draw_checklist(left_x, "CORE FEATURES", NAVY, core, y)
    draw_checklist(right_x, "BONUS FEATURES", BLUE, bonus, y)

    c.showPage()


def page_5_design_decisions(c):
    draw_header_footer(c, 5)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "Design Decisions")

    # -- Decision 1 --
    y = draw_subsection(c, MARGIN, y, "1. PostgreSQL SKIP LOCKED as Job Queue")
    body1 = (
        "Rather than introducing a dedicated message broker (Celery + RabbitMQ, BullMQ + Redis, or "
        "RQ), all job queueing runs directly in PostgreSQL. The critical insight is that job state "
        "and job data must be consistent — an external broker creates a window where a job can be "
        "dequeued but its state not yet updated, leading to phantom jobs."
    )
    y = draw_paragraph(c, MARGIN, y, body1, size=9, leading=12)
    y -= 6
    code1 = """UPDATE jobs SET status='claimed', worker_id=:worker_id, ...
WHERE id = (
  SELECT id FROM jobs WHERE queue_id=:queue_id AND status='queued'
  ORDER BY priority DESC, created_at ASC
  FOR UPDATE SKIP LOCKED LIMIT 1
) RETURNING *;"""
    y = draw_code_block(c, MARGIN, y, code1, CONTENT_W, font_size=7.6)
    y -= 6
    y = draw_trade_off_box(
        c, MARGIN, y, CONTENT_W,
        ["Zero additional broker dependency", "ACID guarantees — claim and state update are atomic", "Debug with psql — no special tooling required"],
        ["Postgres becomes both data store and queue", "At very high throughput (>50k jobs/sec), a dedicated broker wins"],
    )
    y -= 14

    # -- Decision 2 --
    y = draw_subsection(c, MARGIN, y, "2. Visibility Timeout + Reaper (not pessimistic locking)")
    body2 = (
        "Workers hold jobs by setting status='claimed' with a timestamp, not by holding a database "
        "lock for the job's full duration. A reaper process checks every 30 seconds for workers "
        "whose heartbeat went silent and reclaims their jobs. This is the visibility timeout pattern "
        "used by SQS, Celery, and most production job queues."
    )
    y = draw_paragraph(c, MARGIN, y, body2, size=9, leading=12)
    y -= 6
    y = draw_trade_off_box(
        c, MARGIN, y, CONTENT_W,
        ["No long-held locks — no cascading lock failures", "Handles worker crashes without manual intervention", "Same mechanism works across N worker processes"],
        ["At-least-once delivery — jobs must be idempotent", "45-second window before a dead job is reclaimed"],
    )
    y -= 14

    # -- Decision 3 --
    y = draw_subsection(c, MARGIN, y, "3. DAG Engine with Recursive CTE")
    body3 = (
        "Workflow dependencies are resolved using a recursive CTE in PostgreSQL rather than "
        "application-level graph traversal. This fetches the entire dependency graph in a single "
        "query regardless of depth, and check_and_unblock chains recursively through asyncio.gather "
        "for parallel unblocking of fan-in patterns."
    )
    y = draw_paragraph(c, MARGIN, y, body3, size=9, leading=12)
    y -= 6
    y = draw_trade_off_box(
        c, MARGIN, y, CONTENT_W,
        ["O(1) queries regardless of graph depth", "Parallel unblocking via asyncio.gather", "Cycle detection via iterative DFS (no stack overflow)"],
        ["Recursive CTEs have a 20-level depth guard", "Complex graphs require isolated DB sessions per branch"],
    )

    c.showPage()


def page_6_database_schema(c):
    draw_header_footer(c, 6)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "Database Schema — 13 Tables")

    rows = [
        ["Table Name", "Key Columns", "Key Indexes"],
        ["organizations", "id, name, slug, plan", "slug (unique)"],
        ["users", "id, org_id, email, role", "(org_id, email) unique"],
        ["projects", "id, org_id, name, slug", "(org_id, slug) unique"],
        ["retry_policies", "id, strategy, base_delay", "is_default"],
        ["queues", "id, project_id, concurrency_limit", "(project_id, slug)"],
        ["workers", "id, queue_id, hostname, status", "last_seen"],
        ["worker_heartbeats", "id, worker_id, ts, cpu_pct", "ts (desc)"],
        ["jobs", "id, queue_id, status, priority", "(queue_id, status, priority, created_at)"],
        ["job_executions", "id, job_id, attempt_number", "(job_id, attempt_number)"],
        ["job_logs", "id, job_id, level, timestamp", "timestamp (desc)"],
        ["scheduled_jobs", "id, job_id, next_run_at", "next_run_at"],
        ["dead_letter_queue", "id, job_id, ai_summary", "job_id, is_resolved"],
        ["job_dependencies", "job_id, depends_on_job_id", "unique (job_id, dep_id)"],
    ]
    col_widths = [CONTENT_W * 0.20, CONTENT_W * 0.36, CONTENT_W * 0.44]
    y = draw_table(c, MARGIN, y, col_widths, rows, row_h=16.5, font_size=8)
    y -= 20

    box_h = 3.1 * cm
    c.setStrokeColor(BLUE)
    c.setLineWidth(1.2)
    c.setFillColor(LIGHT_BG)
    c.roundRect(MARGIN, y - box_h, CONTENT_W, box_h, 6, fill=1, stroke=1)
    by = y - 0.5 * cm
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(NAVY)
    c.drawString(MARGIN + 0.4 * cm, by, "Critical Index: ix_jobs_claim_query")
    by -= 0.55 * cm
    code = "CREATE INDEX ix_jobs_claim_query ON jobs\n  (queue_id, status, priority DESC, created_at ASC);"
    c.setFont("Courier", 8)
    c.setFillColor(DARK)
    for line in code.split("\n"):
        c.drawString(MARGIN + 0.4 * cm, by, line)
        by -= 11
    by -= 4
    draw_caption(
        c, MARGIN + 0.4 * cm, by,
        "This compound index is what makes the SKIP LOCKED claim query O(log n) instead of O(n). "
        "Without it, every claim would do a full table scan.",
        max_width=CONTENT_W - 0.8 * cm,
    )

    c.showPage()


def page_7_test_coverage(c):
    draw_header_footer(c, 7)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "Automated Tests — 33 Passing")

    intro = (
        "All 33 tests pass against a real PostgreSQL + Redis instance (not mocks). The test suite "
        "covers unit logic, API integration, and concurrent execution scenarios."
    )
    y = draw_paragraph(c, MARGIN, y, intro, size=9.5, leading=13)
    y -= 10

    rows = [
        ["File", "Tests", "Category", "What It Proves"],
        ["test_retry.py", "8", "Unit", "All 3 backoff strategies + max_delay cap"],
        ["test_worker.py", "4", "Concurrency", "SKIP LOCKED, DLQ, reaper recovery, 2-worker race"],
        ["test_dependencies.py", "6", "Integration", "Chain, fan-in, fan-out, diamond, cycle, workflow"],
        ["test_rate_limiting.py", "5", "Concurrency", "Sliding window, Lua atomicity, token bucket, cron dedup"],
        ["test_rbac.py", "6", "Security", "All 4 roles, cross-org isolation"],
        ["test_sharding.py", "4", "Distribution", "Shard assignment, partition, worker-leave behavior"],
    ]
    col_widths = [CONTENT_W * 0.22, CONTENT_W * 0.08, CONTENT_W * 0.16, CONTENT_W * 0.54]
    y = draw_table(c, MARGIN, y, col_widths, rows, row_h=17)
    y -= 22

    box_h = 5.2 * cm
    c.setStrokeColor(BLUE)
    c.setLineWidth(1.2)
    c.setFillColor(LIGHT_BG)
    c.roundRect(MARGIN, y - box_h, CONTENT_W, box_h, 6, fill=1, stroke=1)
    by = y - 0.5 * cm
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(NAVY)
    c.drawString(MARGIN + 0.4 * cm, by, "Most Important Test: Concurrent Job Claiming")
    by -= 0.55 * cm
    code = """# Two workers compete for exactly one job
results = await asyncio.gather(
    worker_1.claim_job(queue_id),
    worker_2.claim_job(queue_id)
)
# Exactly one worker claims it - SKIP LOCKED guarantees this
executions = await db.execute(
    select(JobExecution).where(JobExecution.job_id == job_id)
)
assert len(executions.all()) == 1  # Always passes"""
    c.setFont("Courier", 7.6)
    c.setFillColor(DARK)
    for line in code.split("\n"):
        c.drawString(MARGIN + 0.4 * cm, by, line)
        by -= 10.5

    c.showPage()


def page_8_quick_start(c):
    draw_header_footer(c, 8)
    y = PAGE_H - HEADER_H - 0.9 * cm
    y = draw_section_header(c, y, "Getting Started")

    left_w = CONTENT_W * 0.56
    gap = 0.6 * cm
    right_x = MARGIN + left_w + gap
    right_w = CONTENT_W - left_w - gap

    ly = y
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(NAVY)
    c.drawString(MARGIN, ly, "Quick Start")
    ly -= 0.55 * cm

    steps = [
        ("1. Start infrastructure", "docker compose up -d"),
        ("2. Backend setup", "cd backend\npython -m venv venv\nvenv\\Scripts\\activate\npip install -r requirements.txt\nalembic upgrade head\nuvicorn app.main:app --reload"),
        ("3. Start worker", "QUEUE_ID=<uuid> python -m app.worker.entrypoint"),
        ("4. Start dispatcher", "python -m app.scheduler.entrypoint"),
        ("5. Frontend", "cd frontend && npm install && npm run dev"),
    ]
    for label, code in steps:
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(DARK)
        c.drawString(MARGIN, ly, label)
        ly -= 13
        ly = draw_code_block(c, MARGIN, ly, code, left_w, font_size=7.4)
        ly -= 10

    ry = y
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(NAVY)
    c.drawString(right_x, ry, "Links + Final Notes")
    ry -= 0.6 * cm

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(DARK)
    c.drawString(right_x, ry, "Repository")
    ry -= 13
    c.setFont("Helvetica", 8.5)
    c.setFillColor(BLUE)
    ry = draw_paragraph(c, right_x, ry, "github.com/DharshanKumar1010/distributed-job-scheduler", font="Helvetica", size=8.5, color=BLUE, leading=11, max_width=right_w)
    ry -= 12

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(DARK)
    c.drawString(right_x, ry, "API Documentation (Interactive)")
    ry -= 13
    c.setFont("Helvetica", 8.5)
    c.setFillColor(BLUE)
    c.drawString(right_x, ry, "http://localhost:8000/docs")
    ry -= 22

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(DARK)
    c.drawString(right_x, ry, "Key Files")
    ry -= 14
    key_files = [
        "CLAUDE.md — architecture decisions",
        "docs/design-decisions.md — full trade-off analysis",
        "backend/tests/ — all 33 tests",
        "backend/app/worker/worker.py — core claiming logic",
    ]
    for kf in key_files:
        c.setFont("Helvetica", 8)
        c.setFillColor(DARK)
        for line in wrap_text(kf, "Helvetica", 8, right_w - 10):
            c.drawString(right_x, ry, line)
            ry -= 11
        ry -= 3

    # Bottom banner
    banner_h = 2.4 * cm
    banner_y = FOOTER_Y + 0.7 * cm
    c.setFillColor(NAVY)
    c.roundRect(MARGIN, banner_y, CONTENT_W, banner_h, 6, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(WHITE)
    c.drawCentredString(PAGE_W / 2, banner_y + banner_h * 0.62, "All 33 automated tests pass. Zero TypeScript errors.")
    c.drawCentredString(PAGE_W / 2, banner_y + banner_h * 0.38, "All 16 bonus features implemented.")
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#94A3B8"))
    c.drawCentredString(PAGE_W / 2, banner_y + banner_h * 0.14, "Built with FastAPI • PostgreSQL • Redis • React • Claude API")

    c.showPage()


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    c = canvas.Canvas(OUTPUT_PATH, pagesize=A4)
    c.setTitle("Distributed Job Scheduler — Submission")
    c.setAuthor("Dharshan Kumar")

    page_1_cover(c)
    page_2_executive_summary(c)
    page_3_architecture(c)
    page_4_feature_checklist(c)
    page_5_design_decisions(c)
    page_6_database_schema(c)
    page_7_test_coverage(c)
    page_8_quick_start(c)

    c.save()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
