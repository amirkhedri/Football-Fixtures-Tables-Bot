import os
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont
from utils.text_formatter import format_persian
from utils.date_converter import get_jalali_date_string

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

FONT_BOLD = os.path.join(ASSETS_DIR, "fonts", "static", "Vazirmatn-Bold.ttf")
FONT_MEDIUM = os.path.join(ASSETS_DIR, "fonts", "static", "Vazirmatn-Medium.ttf")
FONT_REGULAR = os.path.join(ASSETS_DIR, "fonts", "static", "Vazirmatn-Regular.ttf")
CONDUCTOR_TEMPLATE = os.path.join(ASSETS_DIR, "images", "template_clean.png")

def _get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except IOError:
        return ImageFont.load_default()

def _fetch_image(url: str, size: tuple) -> Image.Image:
    if not url or url.endswith(".svg"):
        return Image.new("RGBA", size, (0, 0, 0, 0))
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        img.thumbnail(size, Image.Resampling.LANCZOS)
        thumb = Image.new("RGBA", size, (0, 0, 0, 0))
        offset = ((size[0] - img.size[0]) // 2, (size[1] - img.size[1]) // 2)
        thumb.paste(img, offset, img)
        return thumb
    except Exception:
        return Image.new("RGBA", size, (0, 0, 0, 0))

def draw_conductor(matches: list, target_date: str = None) -> BytesIO:
    if os.path.exists(CONDUCTOR_TEMPLATE):
        img = Image.open(CONDUCTOR_TEMPLATE).convert("RGBA")
    else:
        img = Image.new("RGBA", (1436, 1436), (20, 20, 20, 255))

    # Create a transparent overlay for sleek semi-transparent row banners
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    w, h = img.size
    scale = w / 1436.0  # Proportional scaling based on your 1436x1436 template

    font_date = _get_font(FONT_BOLD, int(28 * scale))
    font_teams = _get_font(FONT_BOLD, int(30 * scale))
    font_badge = _get_font(FONT_BOLD, int(25 * scale))

    # 1. Top-Left Date Box on 1436x1436 template is at (68, 36) to (328, 102)
    jalali_str = format_persian(get_jalali_date_string(target_date))
    bbox = draw.textbbox((0, 0), jalali_str, font=font_date)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box_cx = int(198 * scale)
    box_cy = int(69 * scale)
    draw.text(
        (box_cx - text_w // 2, box_cy - text_h // 2 - int(4 * scale)),
        jalali_str,
        fill=(240, 240, 240, 255),
        font=font_date
    )

    # 2. Centered Match Rows Setup
    y_start = int(145 * scale)
    row_h = int(84 * scale)
    row_gap = int(96 * scale)
    logo_box_sz = int(80 * scale)
    logo_img_sz = int(64 * scale)

    # Horizontal Coordinates (Symmetric around Match Banner Center)
    away_box_x = int(68 * scale)
    home_box_x = int(1110 * scale)
    comp_box_x = int(1285 * scale)
    
    # Midpoint between Away Box right edge and Home Box left edge
    banner_center_x = (away_box_x + logo_box_sz + home_box_x) // 2
    badge_w = int(165 * scale)
    badge_h = int(56 * scale)
    badge_x1 = banner_center_x - (badge_w // 2)
    badge_x2 = banner_center_x + (badge_w // 2)

    visible_matches = matches[:10]

    for i, m in enumerate(visible_matches):
        y = y_start + (i * row_gap)

        # Full-width translucent row banner behind teams
        draw.rounded_rectangle(
            [away_box_x, y, home_box_x + logo_box_sz, y + row_h],
            radius=int(14 * scale),
            fill=(22, 25, 32, 185)
        )

        # --- Far Right: Competition Logo Badge ---
        draw.rounded_rectangle(
            [comp_box_x, y + int(4 * scale), comp_box_x + int(76 * scale), y + row_h - int(4 * scale)],
            radius=int(14 * scale),
            fill=(255, 255, 255, 245)
        )

        # --- Right Side: Home Team Logo Box & Name ---
        draw.rounded_rectangle(
            [home_box_x, y, home_box_x + logo_box_sz, y + row_h],
            radius=int(14 * scale),
            fill=(38, 43, 54, 230)
        )
        home_name = format_persian(m.get("home_team", "")[:18])
        h_bbox = draw.textbbox((0, 0), home_name, font=font_teams)
        h_w, h_h = h_bbox[2] - h_bbox[0], h_bbox[3] - h_bbox[1]
        draw.text(
            (home_box_x - int(22 * scale) - h_w, y + (row_h - h_h) // 2 - int(4 * scale)),
            home_name,
            fill=(255, 255, 255, 255),
            font=font_teams
        )

        # --- Center: Time or Live Score Badge ---
        status = m.get("status", "TIMED")
        if status in ("IN_PLAY", "PAUSED"):
            badge_color = (210, 40, 40, 240)  # Live Red
            prefix = "HT" if status == "PAUSED" else "LIVE"
            center_str = f"{prefix} | {m['away_score']} - {m['home_score']}"
        elif status == "FINISHED":
            badge_color = (40, 130, 75, 235)  # Finished Green
            center_str = f"FT | {m['away_score']} - {m['home_score']}"
        else:
            badge_color = (85, 92, 102, 230)  # Default Grey
            center_str = m.get("time", "")

        badge_y1 = y + (row_h - badge_h) // 2
        badge_y2 = badge_y1 + badge_h
        draw.rounded_rectangle([badge_x1, badge_y1, badge_x2, badge_y2], radius=int(10 * scale), fill=badge_color)

        t_bbox = draw.textbbox((0, 0), center_str, font=font_badge)
        t_w, t_h = t_bbox[2] - t_bbox[0], t_bbox[3] - t_bbox[1]
        draw.text(
            (badge_x1 + (badge_w - t_w) // 2, badge_y1 + (badge_h - t_h) // 2 - int(3 * scale)),
            center_str,
            fill=(255, 255, 255, 255),
            font=font_badge
        )

        # --- Left Side: Away Team Logo Box & Name ---
        draw.rounded_rectangle(
            [away_box_x, y, away_box_x + logo_box_sz, y + row_h],
            radius=int(14 * scale),
            fill=(38, 43, 54, 230)
        )
        away_name = format_persian(m.get("away_team", "")[:18])
        a_bbox = draw.textbbox((0, 0), away_name, font=font_teams)
        a_h = a_bbox[3] - a_bbox[1]
        draw.text(
            (away_box_x + logo_box_sz + int(22 * scale), y + (row_h - a_h) // 2 - int(4 * scale)),
            away_name,
            fill=(255, 255, 255, 255),
            font=font_teams
        )

    # Composite the translucent rectangles and text onto the base image
    img = Image.alpha_composite(img, overlay)

    # Paste club & league logos on top
    for i, m in enumerate(visible_matches):
        y = y_start + (i * row_gap)
        if m.get("league_logo"):
            comp_logo = _fetch_image(m["league_logo"], (int(60 * scale), int(60 * scale)))
            img.paste(comp_logo, (comp_box_x + int(8 * scale), y + int(12 * scale)), comp_logo)
        if m.get("home_logo"):
            h_logo = _fetch_image(m["home_logo"], (logo_img_sz, logo_img_sz))
            img.paste(h_logo, (home_box_x + int(8 * scale), y + int(10 * scale)), h_logo)
        if m.get("away_logo"):
            a_logo = _fetch_image(m["away_logo"], (logo_img_sz, logo_img_sz))
            img.paste(a_logo, (away_box_x + int(8 * scale), y + int(10 * scale)), a_logo)

    output = BytesIO()
    img.convert("RGB").save(output, format="JPEG", quality=95)
    output.seek(0)
    return output

def draw_table(league_name: str, standings: list) -> BytesIO:
    width = 1000
    row_h = 52
    header_h = 100
    height = header_h + (len(standings) * row_h) + 40

    img = Image.new("RGBA", (width, height), (24, 26, 32, 255))
    draw = ImageDraw.Draw(img)

    font_title = _get_font(FONT_BOLD, 28)
    font_col = _get_font(FONT_MEDIUM, 17)
    font_row = _get_font(FONT_REGULAR, 19)
    font_pts = _get_font(FONT_BOLD, 20)

    draw.text((40, 28), league_name, fill=(255, 255, 255), font=font_title)

    columns = ["MP", "W", "D", "L", "GF", "GA", "GD", "Pts"]
    col_x_start = 450
    col_spacing = 65

    for i, col in enumerate(columns):
        draw.text((col_x_start + (i * col_spacing), 65), col, fill=(140, 150, 165), font=font_col)

    y_pos = header_h
    for row in standings:
        if row["rank"] % 2 == 0:
            draw.rectangle([0, y_pos, width, y_pos + row_h], fill=(30, 33, 40, 255))

        draw.text((35, y_pos + 14), str(row["rank"]), fill=(200, 205, 215), font=font_row)

        logo = _fetch_image(row["team"]["logo"], (34, 34))
        img.paste(logo, (75, y_pos + 9), logo)

        draw.text((125, y_pos + 13), row["team"]["name"][:20], fill=(255, 255, 255), font=font_row)

        stats = [
            row["played"],
            row["win"],
            row["draw"],
            row["lose"],
            row["gf"],
            row["ga"],
            row["gd"],
            row["points"]
        ]

        for i, val in enumerate(stats):
            x = col_x_start + (i * col_spacing)
            font_to_use = font_pts if i == 7 else font_row
            color = (255, 255, 255) if i == 7 else (210, 215, 225)
            draw.text((x + 6, y_pos + 13), str(val), fill=color, font=font_to_use)

        y_pos += row_h

    output = BytesIO()
    img.convert("RGB").save(output, format="PNG")
    output.seek(0)
    return output