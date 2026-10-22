import requests
import datetime
import pytz
from config import FOOTBALL_DATA_API_KEY, TRACKED_COMPETITIONS

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {
    "X-Auth-Token": FOOTBALL_DATA_API_KEY
}

def get_daily_matches(target_date: str) -> list:
    url = f"{BASE_URL}/matches"
    
    dt_target = datetime.date.fromisoformat(target_date)
    next_day = (dt_target + datetime.timedelta(days=1)).isoformat()
    
    params = {
        "dateFrom": target_date,
        "dateTo": next_day
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        data = response.json()
        
        if "message" in data or "errorCode" in data:
            print(f"API Error Message: {data}")
            return []
            
        all_matches = data.get("matches", [])
        filtered_matches = []
        tehran_tz = pytz.timezone("Asia/Tehran")
        
        for match in all_matches:
            comp_code = match.get("competition", {}).get("code")
            
            if comp_code in TRACKED_COMPETITIONS:
                utc_time = match["utcDate"]
                dt_utc = datetime.datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
                dt_tehran = dt_utc.astimezone(tehran_tz)
                
                if dt_tehran.date().isoformat() != target_date:
                    continue
                    
                time_str = dt_tehran.strftime("%H:%M")
                home_team = match["homeTeam"].get("shortName") or match["homeTeam"].get("name")
                away_team = match["awayTeam"].get("shortName") or match["awayTeam"].get("name")
                
                status = match.get("status", "TIMED")
                full_time = match.get("score", {}).get("fullTime", {})
                home_score = full_time.get("home")
                away_score = full_time.get("away")

                # Parse goals list if provided by the API tier
                goals_raw = match.get("goals", [])
                parsed_goals = []
                for g in goals_raw:
                    parsed_goals.append({
                        "minute": g.get("minute"),
                        "scorer": g.get("scorer", {}).get("name", "بازیکن"),
                        "team": g.get("team", {}).get("name", ""),
                        "type": g.get("type", "REGULAR")
                    })

                match_info = {
                    "id": match["id"],
                    "time": time_str,
                    "status": status,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_full_name": match["homeTeam"].get("name", home_team),
                    "away_full_name": match["awayTeam"].get("name", away_team),
                    "home_score": home_score if home_score is not None else 0,
                    "away_score": away_score if away_score is not None else 0,
                    "goals": parsed_goals,
                    "home_logo": match["homeTeam"].get("crest", ""),
                    "away_logo": match["awayTeam"].get("crest", ""),
                    "league_name": match["competition"]["name"],
                    "league_logo": match["competition"].get("emblem", "")
                }
                filtered_matches.append(match_info)
                
        return sorted(filtered_matches, key=lambda x: x["time"])
        
    except Exception as e:
        print(f"Error fetching daily matches: {e}")
        return []

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
def get_secondary_matches(date_iso: str) -> list:
    """Fetches Europa League and Nations League safely in a single request."""
    import os
    import requests
    import pytz
    from datetime import datetime, timezone

    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        return []

    url = f"https://v3.football.api-sports.io/fixtures?date={date_iso}"
    headers = {"x-apisports-key": api_key}
    tehran_tz = pytz.timezone("Asia/Tehran")

    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()

        TARGET_LEAGUES = {
            3: "لیگ اروپا",
            5: "لیگ ملت‌های اروپا",
        }

        results = []
        for item in data.get("response", []):
            league = item["league"]
            league_id = league["id"]
            if league_id not in TARGET_LEAGUES:
                continue

            fixture = item["fixture"]
            teams = item["teams"]
            goals = item["goals"]

            status_short = fixture["status"]["short"]
            if status_short in ["FT", "AET", "PEN"]:
                status = "FINISHED"
            elif status_short in ["1H", "2H", "HT", "ET", "BT", "P", "LIVE"]:
                status = "IN_PLAY"
            else:
                status = "TIMED"

            # UTC datetime from the timestamp, then convert to Tehran (same as main API)
            ts = fixture.get("timestamp")
            if ts:
                dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                dt_utc = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00"))
            dt_tehran = dt_utc.astimezone(tehran_tz)

            time_str = dt_tehran.strftime("%H:%M")
            utc_date = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            league_logo = league.get("logo", "")

            results.append({
                "id": fixture["id"],
                "time": time_str,                      # <-- what your renderer reads
                "status": status,
                "utcDate": utc_date,
                "minute": fixture["status"].get("elapsed"),
                "home_team": teams["home"]["name"],
                "away_team": teams["away"]["name"],
                "home_full_name": teams["home"]["name"],
                "away_full_name": teams["away"]["name"],
                "home_logo": teams["home"]["logo"],
                "away_logo": teams["away"]["logo"],
                "home_crest": teams["home"]["logo"],
                "away_crest": teams["away"]["logo"],
                "home_score": goals["home"] if goals["home"] is not None else 0,
                "away_score": goals["away"] if goals["away"] is not None else 0,
                "goals": [],
                "league_name": TARGET_LEAGUES[league_id],
                "league_logo": league_logo,
            })

        return sorted(results, key=lambda x: x["time"])
    except Exception:
        return []