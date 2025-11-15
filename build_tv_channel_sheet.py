#!/usr/bin/env python3
"""
home-tv-channel-list
Builds a 2-page, 4-column, accordion-friendly TV channel list from channels.csv.

- Reads config from config.yaml
- Reads channels from channels.csv
- Produces a PDF like: "My House Name / TV Channels" with:
  - 4 columns
  - One line per channel
  - Balanced 2-page split
  - Per-column header
  - Color-coded channel names by category
  - Compact 2-line legend at the bottom of each column
"""

import csv
import math
import os
import sys
from xml.sax.saxutils import escape

import yaml  # pip install pyyaml
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors

from fetch_channel_logos import fetch_channel_logos


# ---------- CONFIG LOADING ----------

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ---------- DATA LOADING ----------

def load_channels(csv_path):
    channels = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].lower() == "number":
                continue
            try:
                int(row[0])
            except ValueError:
                continue
            number = row[0].strip()
            name = row[1].strip() if len(row) > 1 else ""
            channels.append((number, name))
    return sorted(channels, key=lambda x: int(x[0]))


# ---------- CATEGORY / COLOR ----------

def classify_desc(num, name):
    n = name.upper()
    i = int(num)
    if i < 70:
        return "Local"
    if any(k in n for k in ["CNN", "HLN", "MSNBC", "NEWS", "CSPAN", "CNBC", "OAN", "WEATH"]):
        return "News"
    if any(k in n for k in ["ESPN", "NFL", "NHL", "MLB", "FOXS1"]):
        return "Sports"
    if any(k in n for k in ["NICK", "DIS", "TOON", "BABY"]):
        return "Kids"
    if any(k in n for k in ["TBN", "BIBLE", "EWTN", "CTN", "INSP", "3ABN", "VICTR"]):
        return "Faith"
    if any(k in n for k in ["HSN", "QVC", "SHOP", "BUY", "MALL", "SALE", "JTV", "VALU"]):
        return "Shop"
    if i >= 900 or any(k in n for k in ["AUD", "CD", "LMUSC", "OTTO"]):
        return "Music"
    if any(k in n for k in ["PRTGS", "VIX", "HITN", "TODOC", "TONOM", "ES24", "ENLC", "SIC", "RTPI"]):
        return "Intl"
    return "TV"


def color_for(desc):
    return {
        "Local": "#3366CC",
        "News": "#CC0000",
        "Sports": "#008800",
        "Kids": "#FF9900",
        "Faith": "#663399",
        "Shop": "#CC33CC",
        "Music": "#0099CC",
        "Intl": "#996600",
        "TV": "#000000",
    }.get(desc, "#000000")


def logo_filename(num, code):
    return f"{num}_{code}.png"


def build_logo_lookup(channels, logo_dir):
    lookup = {}
    if not logo_dir:
        return lookup
    for num, name in channels:
        path = os.path.join(logo_dir, logo_filename(num, name))
        if os.path.exists(path):
            lookup[(num, name)] = os.path.abspath(path)
    return lookup


def ensure_logos(cfg, channels):
    logos_cfg = cfg.get("logos") or {}
    if not logos_cfg.get("enabled"):
        return {}, logos_cfg

    output_dir = logos_cfg.get("output_dir", "outputs/logos")
    target_px = logos_cfg.get("target_px")
    overrides_csv = logos_cfg.get("overrides_csv")

    # Wrap log lines so they are easy to distinguish from PDF steps
    def log(msg):
        print(f"[logos] {msg}")

    fetch_channel_logos(
        channels_csv=cfg["channels_csv"],
        overrides_csv=overrides_csv,
        output_dir=output_dir,
        target_px=target_px,
        logger=log,
    )
    return build_logo_lookup(channels, output_dir), logos_cfg


# ---------- TABLE CONSTRUCTION ----------

def build_column_table(channels, cfg, styles, logo_lookup=None, logo_cfg=None):
    cols = cfg.get("columns", 4)
    house_name = cfg.get("house_name", "My House")
    title_suffix = cfg.get("title_suffix", "TV Channels")
    fonts_cfg = cfg.get("fonts", {})
    header_font = fonts_cfg.get("header_font")
    cell_font = fonts_cfg.get("cell_font")
    legend_font = fonts_cfg.get("legend_font")
    logo_cfg = logo_cfg or {}

    # Styles
    hdr_style = ParagraphStyle(
        "Hdr",
        parent=styles["Title"],
        alignment=1,
        fontSize=fonts_cfg["header_size"],
        leading=fonts_cfg["header_leading"],
        fontName=header_font or styles["Title"].fontName,
    )

    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=fonts_cfg["cell_size"],
        leading=fonts_cfg["cell_leading"],
        fontName=cell_font or styles["Normal"].fontName,
        leftIndent=cfg.get("cell_left_indent", 36),
    )

    legend_style = ParagraphStyle(
        "Leg",
        parent=styles["Normal"],
        fontSize=fonts_cfg["legend_size"],
        leading=fonts_cfg["legend_leading"],
        fontName=legend_font or styles["Normal"].fontName,
        alignment=1,
    )

    # Parse legend lines from config
    leg1_labels = cfg.get("legend_line1", "Local|News|Sports|Kids|Faith").split("|")
    leg2_labels = cfg.get("legend_line2", "Shop|Music|Intl|TV").split("|")

    # Map label -> color using the same category colors
    def legend_html_line(labels):
        parts = []
        for label in labels:
            label = label.strip()
            col = color_for(label if label != "TV" else "TV")
            parts.append(f"<font color='{col}'>{label}</font>")
        return " | ".join(parts)

    legend_line1_html = legend_html_line(leg1_labels)
    legend_line2_html = legend_html_line(leg2_labels)

    rows = []

    # Header row — repeated in each column
    header_html = f"{house_name}<br/>{title_suffix}<br/><br/>"
    header_cells = [Paragraph(header_html, hdr_style) for _ in range(cols)]
    rows.append(header_cells)

    # Column-major distribution of channels
    rows_per_col = math.ceil(len(channels) / cols)
    col_blocks = [
        channels[i * rows_per_col:(i + 1) * rows_per_col]
        for i in range(cols)
    ]
    max_rows = max(len(b) for b in col_blocks) if col_blocks else 0

    for r in range(max_rows):
        row_cells = []
        for c in range(cols):
            if r < len(col_blocks[c]):
                num, name = col_blocks[c][r]
                d = classify_desc(num, name)
                color = color_for(d)
                logo_html = ""
                if logo_lookup:
                    display_px = logo_cfg.get("display_px", min(logo_cfg.get("target_px", 48), 48))
                    logo_path = logo_lookup.get((num, name))
                    if logo_path:
                        safe_path = escape(str(logo_path), {"'": "&apos;", '"': "&quot;"})
                        logo_html = (
                            f"<img src=\"{safe_path}\" width=\"{display_px}\" "
                            f"height=\"{display_px}\" valign=\"middle\"/> &nbsp;"
                        )
                html = f"{logo_html}<font color='{color}'><b>{num}</b> {name}</font>"
                row_cells.append(Paragraph(html, cell_style))
            else:
                row_cells.append("")
        rows.append(row_cells)

    # Blank row between channels and legend
    rows.append(["" for _ in range(cols)])

    # Legend rows (2 lines)
    leg1 = [Paragraph(legend_line1_html, legend_style) for _ in range(cols)]
    leg2 = [Paragraph(legend_line2_html, legend_style) for _ in range(cols)]
    rows.append(leg1)
    rows.append(leg2)

    return rows


# ---------- MAIN PDF GENERATION ----------

def build_pdf(cfg_path="config.yaml"):
    cfg = load_config(cfg_path)
    channels = load_channels(cfg["channels_csv"])
    total = len(channels)
    logo_lookup, logos_cfg = ensure_logos(cfg, channels)

    # Balanced split across two pages
    if cfg.get("balanced_split", True):
        cut = total // 2
        page1_channels = channels[:cut]
        page2_channels = channels[cut:]
    else:
        # Fallback: old behavior, split by channel number 399
        page1_channels = [c for c in channels if int(c[0]) <= 399]
        page2_channels = [c for c in channels if int(c[0]) > 399]

    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        cfg["output_pdf"],
        pagesize=landscape(letter),
        leftMargin=cfg["margins"]["left"],
        rightMargin=cfg["margins"]["right"],
        topMargin=cfg["margins"]["top"],
        bottomMargin=cfg["margins"]["bottom"],
    )

    story = []

    rows1 = build_column_table(page1_channels, cfg, styles, logo_lookup, logos_cfg)
    rows2 = build_column_table(page2_channels, cfg, styles, logo_lookup, logos_cfg)

    page_width, _ = landscape(letter)
    cols = cfg.get("columns", 4)
    col_width = (page_width - (cfg["margins"]["left"] + cfg["margins"]["right"])) / cols

    dotted_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        # dotted vertical fold guides
        ("LINEBEFORE", (1, 1), (1, -1), 0.5, colors.lightgrey),
        ("LINEBEFORE", (2, 1), (2, -1), 0.5, colors.lightgrey),
        ("LINEBEFORE", (3, 1), (3, -1), 0.5, colors.lightgrey),
        ("LINESTYLE", (1, 1), (3, -1), "dotted"),
    ])

    # Page 1
    tbl1 = Table(rows1, colWidths=[col_width] * cols)
    tbl1.setStyle(dotted_style)
    story.append(tbl1)
    story.append(PageBreak())

    # Page 2
    tbl2 = Table(rows2, colWidths=[col_width] * cols)
    tbl2.setStyle(dotted_style)
    story.append(tbl2)

    doc.build(story)
    print(f"Built: {cfg['output_pdf']}")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    build_pdf(config_path)
