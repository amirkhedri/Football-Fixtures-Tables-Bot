import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "YOUR_API_KEY")

TRACKED_COMPETITIONS = {
    "PL": "لیگ برتر انگلیس",
    "PD": "لالیگا اسپانیا",
    "SA": "سری آ ایتالیا",
    "BL1": "بوندسلیگا آلمان",
    "FL1": "لیگ ۱ فرانسه",
    "CL": "لیگ قهرمانان اروپا",
    "WC": "جام جهانی"
}

TABLE_TRIGGERS = {
    "جدول لالیگا": "PD", "laliga": "PD",
    "جدول لیگ برتر انگلیس": "PL", "premier league": "PL", "pl": "PL",
    "جدول سری آ": "SA", "serie a": "SA",
    "جدول بوندسلیگا": "BL1", "bundesliga": "BL1",
    "جدول لیگ فرانسه": "FL1", "ligue 1": "FL1",
}

CONDUCTOR_TRIGGERS = {"کنداکتور", "نتایج زنده", "بازی های امروز", "live", "matches"}

# Top famous clubs that trigger live goal alerts in groups
FAMOUS_TEAMS = {
    # Spain
    "Real Madrid", "Real Madrid CF", "Barcelona", "FC Barcelona", "Atlético", "Club Atlético de Madrid",
    # England
    "Arsenal", "Arsenal FC", "Man City", "Manchester City FC", "Liverpool", "Liverpool FC",
    "Man United", "Manchester United FC", "Chelsea", "Chelsea FC", "Tottenham", "Tottenham Hotspur FC",
    # Italy
    "Inter", "FC Internazionale Milano", "Milan", "AC Milan", "Juventus", "Juventus FC", "Napoli", "SSC Napoli",
    # Germany
    "Bayern", "FC Bayern München", "Dortmund", "Borussia Dortmund", "Leverkusen", "Bayer 04 Leverkusen",
    # France
    "PSG", "Paris Saint-Germain FC"
}