import os
import requests
import datetime
import pytz
from datetime import timezone
from config import FOOTBALL_DATA_API_KEY, TRACKED_COMPETITIONS, FAMOUS_TEAMS

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {
    "X-Auth-Token": FOOTBALL_DATA_API_KEY
}

def _extract_score(score_obj: dict) -> tuple[int, int]:
    """Safely extracts the latest available score across fullTime, regularTime, and halfTime."""
    if not score_obj:
        return 0, 0
    for key in ("fullTime", "regularTime", "halfTime"):
        sub = score_obj.get(key)
        if isinstance(sub, dict) and sub.get("home") is not None and sub.get("away") is not None:
            return int(sub["home"]), int(sub["away"])
    return 0, 0

def get_daily_matches(target_date: str) -> list:
    url = f"{BASE_URL}/matches"
    
    # Query exact target_date and next_day to cover UTC-to-Tehran evening offset
    dt_target = datetime.date.fromisoformat(target_date)
    prev_day = (dt_target - datetime.timedelta(days=1)).isoformat()
    next_day = (dt_target + datetime.timedelta(days=1)).isoformat()
    
    params = {
        "dateFrom": prev_day,
        "dateTo": next_day
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        data = response.json()
        
        if "message" in data or "errorCode" in data:
            print(f"Primary API Warning: {data}")
            return []
            
        all_matches = data.get("matches") or []
        filtered_matches = []
        tehran_tz = pytz.timezone("Asia/Tehran")
        
        for match in all_matches:
            comp = match.get("competition") or {}
            comp_code = comp.get("code")
            
            if comp_code in TRACKED_COMPETITIONS:
                utc_time = match.get("utcDate")
                if not utc_time:
                    continue
                    
                dt_utc = datetime.datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
                dt_tehran = dt_utc.astimezone(tehran_tz)
                
                if dt_tehran.date().isoformat() != target_date:
                    continue
                    
                time_str = dt_tehran.strftime("%H:%M")
                
                home_team_data = match.get("homeTeam") or {}
                away_team_data = match.get("awayTeam") or {}
                
                home_team = home_team_data.get("shortName") or home_team_data.get("name") or "میزبان"
                away_team = away_team_data.get("shortName") or away_team_data.get("name") or "میهمان"
                
                raw_status = match.get("status", "TIMED")
                if raw_status in ("FINISHED", "AWARDED"):
                    status = "FINISHED"
                elif raw_status in ("IN_PLAY", "PAUSED", "LIVE"):
                    status = "IN_PLAY"
                else:
                    status = "TIMED"
                
                home_score, away_score = _extract_score(match.get("score") or {})

                goals_raw = match.get("goals") or []
                parsed_goals = []
                for g in goals_raw:
                    scorer = g.get("scorer") or {}
                    team = g.get("team") or {}
                    parsed_goals.append({
                        "minute": g.get("minute"),
                        "scorer": scorer.get("name", "بازیکن"),
                        "team": team.get("name", ""),
                        "type": g.get("type", "REGULAR")
                    })

                match_info = {
                    "id": match.get("id"),
                    "time": time_str,
                    "status": status,
                    "raw_status": raw_status,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_full_name": home_team_data.get("name", home_team),
                    "away_full_name": away_team_data.get("name", away_team),
                    "home_score": home_score,
                    "away_score": away_score,
                    "goals": parsed_goals,
                    "home_logo": home_team_data.get("crest", ""),
                    "away_logo": away_team_data.get("crest", ""),
                    "home_crest": home_team_data.get("crest", ""),
                    "away_crest": away_team_data.get("crest", ""),
                    "league_code": comp_code,
                    "league_name": TRACKED_COMPETITIONS.get(comp_code, comp.get("name", "")),
                    "league_logo": comp.get("emblem", "")
                }
                filtered_matches.append(match_info)
                
        return sorted(filtered_matches, key=lambda x: x["time"])
        
    except Exception as e:
        print(f"Error fetching daily matches: {e}")
        return []


def get_secondary_matches(date_iso: str, include_main_leagues: bool = True) -> list:
    """
    Fetches matches from api-sports.io in a SINGLE request.
    Also acts as a live/finished score backup for Premier League & major leagues!
    """
    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        return []

    url = f"https://v3.football.api-sports.io/fixtures?date={date_iso}&timezone=Asia/Tehran"
    headers = {"x-apisports-key": api_key}
    tehran_tz = pytz.timezone("Asia/Tehran")

    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()

        # Secondary cups + Primary top leagues (so nothing is ever missed in the conductor)
        TARGET_LEAGUES = {
            3: "لیگ اروپا",
            5: "لیگ ملت‌های اروپا",
            45: "جام حذفی انگلیس",
            48: "جام اتحادیه انگلیس",
            137: "جام حذفی ایتالیا",
            143: "کوپا دل ری",
            529: "دی‌اف‌بی پوکال",
            66: "جام حذفی فرانسه"
        }
        
        if include_main_leagues:
            TARGET_LEAGUES.update({
                2: "لیگ قهرمانان اروپا",
                39: "لیگ برتر انگلیس",
                140: "لالیگا اسپانیا",
                135: "سری آ ایتالیا",
                78: "بوندسلیگا آلمان",
                61: "لیگ ۱ فرانسه",
            })

        results = []
        for item in data.get("response", []):
            league = item.get("league") or {}
            league_id = league.get("id")
            if league_id not in TARGET_LEAGUES:
                continue

            fixture = item.get("fixture") or {}
            teams = item.get("teams") or {}
            goals = item.get("goals") or {}
            status_obj = fixture.get("status") or {}

            status_short = status_obj.get("short", "NS")
            if status_short in ["FT", "AET", "PEN", "AWD", "WO"]:
                status = "FINISHED"
            elif status_short in ["1H", "2H", "HT", "ET", "BT", "P", "LIVE"]:
                status = "IN_PLAY"
            else:
                status = "TIMED"

            ts = fixture.get("timestamp")
            if ts:
                dt_utc = datetime.datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                date_str = fixture.get("date", "")
                if date_str:
                    dt_utc = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    continue
                    
            dt_tehran = dt_utc.astimezone(tehran_tz)
            if dt_tehran.date().isoformat() != date_iso:
                continue

            time_str = dt_tehran.strftime("%H:%M")
            utc_date = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            home_team_info = teams.get("home") or {}
            away_team_info = teams.get("away") or {}

            results.append({
                "id": fixture.get("id"),
                "time": time_str,
                "status": status,
                "raw_status": status_short,
                "utcDate": utc_date,
                "minute": status_obj.get("elapsed"),
                "home_team": home_team_info.get("name", "میزبان"),
                "away_team": away_team_info.get("name", "میهمان"),
                "home_full_name": home_team_info.get("name", "میزبان"),
                "away_full_name": away_team_info.get("name", "میهمان"),
                "home_logo": home_team_info.get("logo", ""),
                "away_logo": away_team_info.get("logo", ""),
                "home_crest": home_team_info.get("logo", ""),
                "away_crest": away_team_info.get("logo", ""),
                "home_score": goals.get("home") if goals.get("home") is not None else 0,
                "away_score": goals.get("away") if goals.get("away") is not None else 0,
                "goals": [],
                "league_name": TARGET_LEAGUES[league_id],
                "league_logo": league.get("logo", ""),
            })

        return sorted(results, key=lambda x: x["time"])
    except Exception as e:
        print(f"Secondary API Error: {e}")
        return []


def get_merged_conductor_matches(date_iso: str) -> list:
    """
    Combines primary and secondary matches, deduplicates them, 
    ensures live/finished scores are up-to-date, and prioritizes famous/Premier League matches
    so they never get cut off by the 10-match image limit!
    """
    primary = get_daily_matches(date_iso)
    secondary = get_secondary_matches(date_iso, include_main_leagues=True)

    def _norm(name: str) -> str:
        name = name.lower()
        for word in ["fc", "cf", "sc", "ac", "afc", "united", "city", "hotspur", "albion", "wanderers", "rovers", "1.", "sv", "vfb", "tsg", "rb", "ud", "cd", "rcd"]:
            name = name.replace(word, "")
        return "".join(ch for ch in name if ch.isalnum())

    merged = list(primary)

    for sec in secondary:
        sec_h = _norm(sec["home_team"])
        sec_a = _norm(sec["away_team"])
        matched = False

        for pri in merged:
            pri_h = _norm(pri["home_full_name"])
            pri_a = _norm(pri["away_full_name"])
            
            # Match by same kickoff time and overlapping normalized team names
            if pri["time"] == sec["time"] and (
                (sec_h and (sec_h in pri_h or pri_h in sec_h)) or
                (sec_a and (sec_a in pri_a or pri_a in sec_a))
            ):
                matched = True
                # If secondary API has a more advanced status (e.g. FINISHED or IN_PLAY) or higher score, update primary!
                status_rank = {"TIMED": 0, "SCHEDULED": 0, "IN_PLAY": 1, "PAUSED": 1, "FINISHED": 2}
                if status_rank.get(sec["status"], 0) > status_rank.get(pri["status"], 0):
                    pri["status"] = sec["status"]
                if (sec["home_score"] + sec["away_score"]) > (pri["home_score"] + pri["away_score"]):
                    pri["home_score"] = sec["home_score"]
                    pri["away_score"] = sec["away_score"]
                if not pri.get("home_logo") and sec.get("home_logo"):
                    pri["home_logo"] = sec["home_logo"]
                    pri["away_logo"] = sec["away_logo"]
                break

        if not matched:
            merged.append(sec)

    # Prioritize matches involving FAMOUS_TEAMS and Premier League / Champions League 
    # if there are more than 10 matches today so big games (like Chelsea vs Tottenham or City vs Villa) are NEVER cut off!
    def _priority_score(m: dict) -> int:
        names = {m.get("home_team", ""), m.get("away_team", ""), m.get("home_full_name", ""), m.get("away_full_name", "")}
        is_famous = bool(names.intersection(FAMOUS_TEAMS)) or any(
            ft.lower() in n.lower() for ft in FAMOUS_TEAMS for n in names if n
        )
        is_top_league = m.get("league_code") in ("CL", "PL", "PD") or m.get("league_name") in ("لیگ قهرمانان اروپا", "لیگ برتر انگلیس", "لالیگا اسپانیا")
        if is_famous and is_top_league:
            return 3
        if is_famous:
            return 2
        if is_top_league:
            return 1
        return 0

    if len(merged) > 10:
        # Take the top 10 highest-priority matches of the day
        top_matches = sorted(merged, key=lambda x: (-_priority_score(x), x["time"]))[:10]
        # Re-sort those top 10 chronologically by time for a clean conductor display
        return sorted(top_matches, key=lambda x: x["time"])

    return sorted(merged, key=lambda x: x["time"])


def get_league_standings(league_code: str) -> dict:
    url = f"{BASE_URL}/competitions/{league_code}/standings"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        data = response.json()
        
        if "errorCode" in data or "standings" not in data or len(data["standings"]) == 0:
            return None
            
        table = data["standings"][0]["table"]
        league_name = data["competition"]["name"]
        
        formatted_table = []
        for row in table:
            formatted_table.append({
                "rank": row["position"],
                "team": {
                    "name": row["team"]["shortName"] or row["team"]["name"],
                    "logo": row["team"].get("crest", "")
                },
                "played": row["playedGames"],
                "win": row["won"],
                "draw": row["draw"],
                "lose": row["lost"],
                "gf": row["goalsFor"],
                "ga": row["goalsAgainst"],
                "gd": row["goalDifference"],
                "points": row["points"]
            })
            
        return {
            "league_name": league_name,
            "table": formatted_table
        }
    except Exception as e:
        print(f"Error fetching standings: {e}")
        return None