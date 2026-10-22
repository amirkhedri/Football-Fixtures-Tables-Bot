import os
import datetime
import pytz
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncpg

from config import TELEGRAM_BOT_TOKEN, TABLE_TRIGGERS, CONDUCTOR_TRIGGERS, FAMOUS_TEAMS
from services.api_fetcher import get_daily_matches, get_league_standings
from services.image_renderer import draw_conductor, draw_table

# Vercel will inject this securely from your environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()
bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).updater(None).build()

# --- Database Setup (Neon Postgres) ---
async def get_db_pool():
    if not hasattr(get_db_pool, "pool"):
        # We strip the extra Neon parameters just in case they conflict with asyncpg
        clean_url = DATABASE_URL.split("?")[0] + "?sslmode=require"
        get_db_pool.pool = await asyncpg.create_pool(clean_url)
        async with get_db_pool.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS football_groups (
                    chat_id BIGINT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS live_scores (
                    match_id BIGINT PRIMARY KEY,
                    home_score INT,
                    away_score INT
                );
            """)
    return get_db_pool.pool

async def load_groups() -> list:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT chat_id FROM football_groups")
        return [row["chat_id"] for row in rows]

async def save_group(chat_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO football_groups (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)

async def get_cached_score(match_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT home_score, away_score FROM live_scores WHERE match_id = $1", match_id)
        return (row["home_score"], row["away_score"]) if row else (None, None)

async def update_cached_score(match_id: int, home_score: int, away_score: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO live_scores (match_id, home_score, away_score) 
            VALUES ($1, $2, $3)
            ON CONFLICT (match_id) DO UPDATE 
            SET home_score = EXCLUDED.home_score, away_score = EXCLUDED.away_score
        """, match_id, home_score, away_score)

def is_famous_match(match: dict) -> bool:
    candidates = {match.get("home_team", ""), match.get("away_team", ""), match.get("home_full_name", ""), match.get("away_full_name", "")}
    return bool(candidates.intersection(FAMOUS_TEAMS))

# --- Telegram Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ['group', 'supergroup', 'private']:
        await save_group(chat.id)
    await update.message.reply_text("✅ ربات فعال شد! با موفقیت به سرورهای ابری متصل شدیم.")

async def handle_text_triggers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat = update.effective_chat
    if chat.type in ['group', 'supergroup', 'private']:
        await save_group(chat.id)
        
    text = update.message.text.strip().lower()
    if text in CONDUCTOR_TRIGGERS:
        status_msg = await update.message.reply_text("⏳ در حال دریافت کنداکتور...")
        try:
            today_iso = datetime.datetime.now(pytz.timezone("Asia/Tehran")).date().isoformat()
            matches = get_daily_matches(today_iso)
            if not matches:
                await status_msg.edit_text("امروز بازی مهمی در تقویم نیست.")
                return
            photo_stream = draw_conductor(matches, target_date=today_iso)
            await update.message.reply_photo(photo=photo_stream, caption="📅 کنداکتور و نتایج زنده")
            await status_msg.delete()
        except Exception:
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
                await status_msg.edit_text("❌ خطا در دریافت جدول.")
        except Exception:
            await status_msg.edit_text("❌ خطای سیستمی.")

# --- FastAPI Vercel Endpoints ---
@app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_triggers))

@app.post("/api/webhook")
async def webhook(request: Request):
    """Telegram sends user messages here."""
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return Response(status_code=200)

@app.get("/api/cron")
async def run_cron():
    """External cron service pings this every minute to check live goals."""
    tehran_tz = pytz.timezone("Asia/Tehran")
    now = datetime.datetime.now(tehran_tz)
    today_iso = now.date().isoformat()
    
    matches = get_daily_matches(today_iso)
    groups = await load_groups()
    
    # 1. Live Goal Monitor
    for m in matches:
        if not is_famous_match(m): continue
        match_id = m["id"]
        status = m["status"]
        h_score, a_score = m["home_score"], m["away_score"]

        prev_h, prev_a = await get_cached_score(match_id)

        if prev_h is None:
            await update_cached_score(match_id, h_score, a_score)
            continue

        if status in ("IN_PLAY", "PAUSED") and (h_score > prev_h or a_score > prev_a):
            await update_cached_score(match_id, h_score, a_score)
            scoring_team = m["home_team"] if h_score > prev_h else m["away_team"]
            
            goal_detail_line = ""
            if m.get("goals"):
                last_goal = m["goals"][-1]
                scorer = last_goal.get("scorer", "بازیکن نامشخص")
                minute = last_goal.get("minute", "?")
                goal_detail_line = f"👟 گلزن: {scorer} (دقیقه '{minute})\n"

            alert_text = (f"⚽️ **گل برای {scoring_team}!**\n\n"
                          f"🔥 {m['home_team']} {h_score} - {a_score} {m['away_team']}\n"
                          f"{goal_detail_line}🏆 {m['league_name']}")
            
            for chat_id in groups:
                try:
                    await bot_app.bot.send_message(chat_id=chat_id, text=alert_text, parse_mode="Markdown")
                except Exception:
                    pass
        else:
            if h_score != prev_h or a_score != prev_a:
                await update_cached_score(match_id, h_score, a_score)

    # 2. Morning Broadcast (Runs only when pinged between 08:30 and 08:31)
    if now.hour == 8 and now.minute == 30:
        if matches:
            photo_stream = draw_conductor(matches, target_date=today_iso)
            photo_bytes = photo_stream.getvalue()
            for chat_id in groups:
                try:
                    await bot_app.bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption="📅 برنامه بازی‌های مهم امروز")
                except Exception:
                    pass

    return {"status": "success"}