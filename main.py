import os
import json
import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, TABLE_TRIGGERS, CONDUCTOR_TRIGGERS, FAMOUS_TEAMS
from services.api_fetcher import get_daily_matches, get_league_standings
from services.image_renderer import draw_conductor, draw_table

GROUPS_FILE = "groups.json"
PROXY_URL = "socks5://127.0.0.1:10808"

# Memory cache to track live match scores: {match_id: (home_score, away_score)}
LIVE_SCORE_CACHE = {}

def load_groups() -> list:
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r") as f:
            return json.load(f)
    return []

def save_group(chat_id: int):
    groups = load_groups()
    if chat_id not in groups:
        groups.append(chat_id)
        with open(GROUPS_FILE, "w") as f:
            json.dump(groups, f)

def is_famous_match(match: dict) -> bool:
    """Returns True if either the home or away team is in our FAMOUS_TEAMS set."""
    candidates = {
        match.get("home_team", ""),
        match.get("away_team", ""),
        match.get("home_full_name", ""),
        match.get("away_full_name", "")
    }
    return bool(candidates.intersection(FAMOUS_TEAMS))

async def live_goal_monitor(context: ContextTypes.DEFAULT_TYPE):
    """Polls live matches every 60s and sends goal alerts for famous teams."""
    groups = load_groups()
    if not groups:
        return

    tehran_tz = pytz.timezone("Asia/Tehran")
    today_iso = datetime.datetime.now(tehran_tz).date().isoformat()
    matches = get_daily_matches(today_iso)

    for m in matches:
        if not is_famous_match(m):
            continue

        match_id = m["id"]
        status = m["status"]
        h_score = m["home_score"]
        a_score = m["away_score"]

        # Initialize score in cache on first sight without spamming old goals
        if match_id not in LIVE_SCORE_CACHE:
            LIVE_SCORE_CACHE[match_id] = (h_score, a_score)
            continue

        prev_h, prev_a = LIVE_SCORE_CACHE[match_id]

        # Check if a new goal was scored while match is active
        if status in ("IN_PLAY", "PAUSED") and (h_score > prev_h or a_score > prev_a):
            LIVE_SCORE_CACHE[match_id] = (h_score, a_score)
            scoring_team = m["home_team"] if h_score > prev_h else m["away_team"]

            # --- NEW: Enhanced Goalscorer Formatting ---
            goal_detail_line = ""
            if m.get("goals"):
                # Grab the most recent goal added to the array
                last_goal = m["goals"][-1]
                scorer = last_goal.get("scorer", "بازیکن نامشخص")
                minute = last_goal.get("minute", "?")
                
                # Prevent API edge cases where scorer name is missing
                if not scorer:
                    scorer = "بازیکن نامشخص"
                    
                goal_detail_line = f"👟 گلزن: {scorer} (دقیقه '{minute})\n"

            alert_text = (
                f"⚽️ **گل برای {scoring_team}!**\n\n"
                f"🔥 {m['home_team']} {h_score} - {a_score} {m['away_team']}\n"
                f"{goal_detail_line}"
                f"🏆 {m['league_name']}"
            )

            for chat_id in groups:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=alert_text, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to send goal alert to {chat_id}: {e}")
        else:
            LIVE_SCORE_CACHE[match_id] = (h_score, a_score)

async def morning_broadcast(context: ContextTypes.DEFAULT_TYPE):
    tehran_tz = pytz.timezone("Asia/Tehran")
    today_iso = datetime.datetime.now(tehran_tz).date().isoformat()
    matches = get_daily_matches(today_iso)
    if not matches:
        return
        
    photo_stream = draw_conductor(matches, target_date=today_iso)
    photo_bytes = photo_stream.getvalue() 
    
    for chat_id in load_groups():
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption="📅 برنامه بازی‌های مهم امروز")
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ['group', 'supergroup', 'private']:
        save_group(chat.id)
    await update.message.reply_text(
        "✅ ربات فعال شد!\n"
        "• ارسال «کنداکتور» یا «نتایج زنده» برای تصویر بازی‌ها و نتایج لحظه‌ای\n"
        "• ارسال «جدول لالیگا»، «جدول لیگ قهرمانان» و... برای مشاهده جدول\n"
        "• اعلام خودکار گل‌های تیم‌های مطرح اروپایی"
    )

async def handle_text_triggers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    chat = update.effective_chat
    if chat.type in ['group', 'supergroup', 'private']:
        save_group(chat.id)
        
    text = update.message.text.strip().lower()
    
    if text in CONDUCTOR_TRIGGERS:
        status_msg = await update.message.reply_text("⏳ در حال دریافت کنداکتور و نتایج زنده...")
        try:
            tehran_tz = pytz.timezone("Asia/Tehran")
            today_iso = datetime.datetime.now(tehran_tz).date().isoformat()
            matches = get_daily_matches(today_iso)
            if not matches:
                await status_msg.edit_text("امروز بازی مهمی در تقویم نیست.")
                return
            photo_stream = draw_conductor(matches, target_date=today_iso)
            await update.message.reply_photo(photo=photo_stream, caption="📅 کنداکتور و نتایج زنده بازی‌های امروز")
            await status_msg.delete()
        except Exception as e:
            print(f"Conductor Error: {e}")
            await status_msg.edit_text("❌ خطا در ساخت کنداکتور.")
        return

    league_id = TABLE_TRIGGERS.get(text)
    if league_id:
        status_msg = await update.message.reply_text("⏳ در حال ساخت جدول...")
        try:
            data = get_league_standings(league_id)
            if data and "table" in data:
                photo_stream = draw_table(data["league_name"], data["table"])
                await update.message.reply_photo(photo=photo_stream)
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ خطا در دریافت اطلاعات جدول.")
        except Exception as e:
            print(f"Table Generation Error: {e}")
            await status_msg.edit_text("❌ خطای سیستمی در ساخت تصویر جدول.")

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Error: Please set TELEGRAM_BOT_TOKEN in your .env file.")
        return

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
        print(f"Running with proxy: {PROXY_URL}")
        
    app = builder.build()

    tehran_tz = pytz.timezone("Asia/Tehran")
    # 1. Daily Morning Schedule at 08:30 AM
    app.job_queue.run_daily(morning_broadcast, time=datetime.time(hour=8, minute=30, tzinfo=tehran_tz))
    # 2. Live Goal Monitor every 60 seconds
    app.job_queue.run_repeating(live_goal_monitor, interval=60, first=10)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_triggers))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()