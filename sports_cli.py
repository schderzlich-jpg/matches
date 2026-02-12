
import json
import urllib.request
import urllib.parse
from datetime import datetime
import asyncio

# TheSportsDB API Configuration
# BURAYA YENİ PREMİUM KEYİNİZİ YAZIN (Varsayılan test key: 478143 ama sınırlıdır)
API_KEY = "478143" 
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

def fetch_json(url):
    """
    Synchronous helper to fetch JSON from a URL using standard library.
    Using standard library avoids extra pip dependencies for the user.
    """
    try:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                data = response.read().decode('utf-8')
                return json.loads(data)
    except Exception as e:
        # print(f"DEBUG: Error fetching {url}: {e}")
        pass
    return {}

async def fetch_json_async(url):
    """
    Async wrapper for the fetch function to allow parallel execution.
    """
    return await asyncio.to_thread(fetch_json, url)

async def search_with_fallback(query):
    """
    Combines direct API search with a scan of major leagues to find fuzzy matches.
    """
    teams_map = {} # dict to ensure uniqueness by ID

    # 1. Direct API Search
    direct_url = f"{BASE_URL}/searchteams.php?t={urllib.parse.quote(query)}"
    direct_res = await fetch_json_async(direct_url)
    
    if direct_res.get("teams"):
        for t in direct_res["teams"]:
            teams_map[t["idTeam"]] = t

    # 1.5. Retry with suffixes removed if direct search failed
    if not teams_map:
        suffixes = ["AFC", "FC", "SK", "FK", "AS", "Calcio", "S.K.", "F.K.", "A.S.", "J.K."]
        cleaned_query = query
        changed = False
        for suffix in suffixes:
            # Check safely (case insensitive suffix at end)
            if cleaned_query.lower().endswith(" " + suffix.lower()):
                cleaned_query = cleaned_query[:-len(suffix)-1].strip()
                changed = True
            elif cleaned_query.lower().endswith("." + suffix.lower()): # like .FC
                cleaned_query = cleaned_query[:-len(suffix)-1].strip()
                changed = True

        if changed and cleaned_query:
            print(f"DEBUG: Retrying search with '{cleaned_query}'...")
            retry_url = f"{BASE_URL}/searchteams.php?t={urllib.parse.quote(cleaned_query)}"
            retry_res = await fetch_json_async(retry_url)
            if retry_res.get("teams"):
                for t in retry_res["teams"]:
                    teams_map[t["idTeam"]] = t

    # 2. Fallback: Scan Major Leagues
    leagues_to_scan = [
        'Italian Serie A',
        'Turkish Super Lig',
        'English Premier League',
        'Spanish La Liga',
        'American Major League Soccer',
        'German Bundesliga',
        'UEFA Champions League',
        'French Ligue 1',
        'NBA',
        'EuroLeague Basketball',
        'Turkish Basketbol Super Ligi'
    ]

    # Create tasks for all leagues
    tasks = [
        fetch_json_async(f"{BASE_URL}/search_all_teams.php?l={urllib.parse.quote(league)}")
        for league in leagues_to_scan
    ]

    results = await asyncio.gather(*tasks)
    
    lower_q = query.lower()

    for res in results:
        if res.get("teams"):
            for t in res["teams"]:
                name = t.get("strTeam", "").lower()
                alt = t.get("strAlternate", "")
                alt = alt.lower() if alt else ""

                if lower_q in name or lower_q in alt:
                    if t["idTeam"] not in teams_map:
                        teams_map[t["idTeam"]] = t
                # Reverse check: Is API name inside the Query? (e.g. Query="Olympique Lyonnais", API="Lyon")
                # Only if API name is significant enough (len > 3) to avoid matching "FC" etc.
                elif len(name) > 3 and name in lower_q:
                    if t["idTeam"] not in teams_map:
                        teams_map[t["idTeam"]] = t

    return list(teams_map.values())

    if res.get("teams") and len(res["teams"]) > 0:
        return res["teams"][0].get("strBadge")
    return None

def get_team_logo_url(team_name):
    """
    Synchronous helper to get just the logo URL for a team name.
    Useful when match is not found but we need the logo.
    """
    async def _get():
        teams = await search_with_fallback(team_name)
        if teams:
            # En iyi eşleşmeyi bul (örn: tam isim)
            # Şimdilik ilkini döndür
            return teams[0].get("strBadge") or teams[0].get("strTeamBadge")
        return None
    
    return asyncio.run(_get())

def get_team_info(team_name):
    """
    Synchronous helper to get (canonical_name, logo_url) for a team.
    """
    async def _get():
        teams = await search_with_fallback(team_name)
        if teams:
            t = teams[0]
            return t.get("strTeam"), t.get("strBadge") or t.get("strTeamBadge")
        return None, None
    
    return asyncio.run(_get())

def convert_to_tr_time(date_str, time_str):
    if not date_str or not time_str:
        return ""
    
    try:
        dt_str = f"{date_str}T{time_str}"
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
        import datetime as dt_module
        tr_time = dt + dt_module.timedelta(hours=3)
        return tr_time.strftime("%H:%M")
    except:
        return time_str

def format_tr_date(date_str):
    if not date_str:
        return ""
    
    tr_months = {
        1: "OCAK", 2: "ŞUBAT", 3: "MART", 4: "NİSAN",
        5: "MAYIS", 6: "HAZİRAN", 7: "TEMMUZ", 8: "AĞUSTOS",
        9: "EYLÜL", 10: "EKİM", 11: "KASIM", 12: "ARALIK"
    }
    
    try:
        # Try YYYY-MM-DD
        if "-" in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            return date_str
            
        return f"{dt.day} {tr_months[dt.month]}"
    except:
        return date_str

async def display_match(e):
    tr_time = convert_to_tr_time(e.get("dateEvent"), e.get("strTime"))
    
    print("\n⏳ Takım logoları getiriliyor...")
    
    # Get IDs
    home_id = e.get("idHomeTeam")
    away_id = e.get("idAwayTeam")
    
    # Try to get badges from event first, else fetch
    home_badge = e.get("strHomeTeamBadge")
    away_badge = e.get("strAwayTeamBadge")
    
    # Fetch in parallel if missing
    tasks = []
    if not home_badge:
        tasks.append(get_team_badge(home_id))
    else:
        tasks.append(asyncio.sleep(0, result=home_badge)) # Mock task
        
    if not away_badge:
        tasks.append(get_team_badge(away_id))
    else:
        tasks.append(asyncio.sleep(0, result=away_badge))
    
    results = await asyncio.gather(*tasks)
    # Mapping results back depends on order
    final_home_badge = results[0] if not home_badge else home_badge
    final_away_badge = results[1] if not away_badge else away_badge

    print("\n⚽ MAÇ DETAYLARI ⚽")
    print("==========================================")
    print(f"{e.get('strHomeTeam')} vs {e.get('strAwayTeam')}")
    print("==========================================")
    print(f"🏆 Lig        : {e.get('strLeague')}")
    print(f"📅 Tarih      : {e.get('dateEvent')}")
    print(f"⏰ Saat (TR)  : {tr_time}")
    
    status = e.get("strStatus")
    if status:
        print(f"ℹ️  Durum      : {status}")
        
    print("------------------------------------------")
    print(f"🏠 Ev Sahibi Logo : {final_home_badge or 'Bulunamadı'}")
    print(f"✈️  Deplasman Logo : {final_away_badge or 'Bulunamadı'}")
    print("==========================================")

async def find_match_by_names(home_name, away_name, subtract_day_for_night=False):
    """
    Finds a match between two team names.
    Returns (time_str, date_str, home_badge, away_badge) or (None, None, None, None).
    """
    # 1. Search for Home Team
    teams = await search_with_fallback(home_name)
    if not teams:
        return None, None, None, None
    
    # Check top 3 results
    for team in teams[:3]:
        team_id = team["idTeam"]
        
        # 2. Get next 15 events for this team
        url = f"{BASE_URL}/eventsnext.php?id={team_id}"
        res = await fetch_json_async(url)
        
        events = res.get("events", [])
        
        if not events:
            # Try season search immediately if no next events
            pass
             
            # Collect all candidates first
            candidates = []
            
            # Check eventsnext
            for e in events:
                e_away = e.get("strAwayTeam", "").lower()
                e_home = e.get("strHomeTeam", "").lower()
                target_away = away_name.lower()
                
                match_found = False
                if target_away in e_away or target_away in e_home:
                    match_found = True
                elif e_away in target_away or e_home in target_away:
                    match_found = True
                else:
                    target_words = [w for w in target_away.split() if len(w) > 3]
                    for word in target_words:
                        if word in e_away or word in e_home:
                            match_found = True
                            break
                
                if match_found:
                    candidates.append(e)

            # Check season events if needed (or combine)
            # Assuming eventsnext covers near future, but if empty, check season
            if not candidates:
                now = datetime.now()
                if now.month > 6: season = f"{now.year}-{now.year+1}"
                else: season = f"{now.year-1}-{now.year}"
                
                url_season = f"{BASE_URL}/eventsseason.php?id={team_id}&s={season}"
                res_season = await fetch_json_async(url_season)
                season_events = res_season.get("events", [])
                
                if season_events:
                     today_str = datetime.now().strftime("%Y-%m-%d")
                     future_events = [e for e in season_events if e.get("dateEvent") >= today_str]
                     
                     for e in future_events:
                         e_away = e.get("strAwayTeam", "").lower()
                         e_home = e.get("strHomeTeam", "").lower()
                         target_away = away_name.lower()
                         
                         match_found = False
                         if target_away in e_away or target_away in e_home:
                            match_found = True
                         
                         if match_found:
                             candidates.append(e)

            # Process candidates: Extract date and sort by proximity to today
            if candidates:
                from datetime import datetime
                today = datetime.now()
                
                best_candidate = None
                min_diff = float('inf')
                
                for cand in candidates:
                    try:
                        edate = datetime.strptime(cand.get("dateEvent"), "%Y-%m-%d")
                        diff = abs((edate - today).days)
                        if diff < min_diff:
                            min_diff = diff
                            best_candidate = cand
                    except: pass
                
                if best_candidate:
                     e = best_candidate
                     # Found the match
                     date_event = e.get("dateEvent")
                     time_event = e.get("strTime")
                     
                     # Convert time
                     tr_time = convert_to_tr_time(date_event, time_event)
                     
                     # Determine correct badge order
                     api_home_name = e.get("strHomeTeam", "").lower()
                     requested_home_name = home_name.lower()
                     
                     is_home_match = False
                     if requested_home_name in api_home_name or api_home_name in requested_home_name:
                         is_home_match = True
                     else:
                         req_words = [w for w in requested_home_name.split() if len(w) > 3]
                         for w in req_words:
                             if w in api_home_name:
                                 is_home_match = True
                                 break
                     
                     if is_home_match:
                         ret_home_badge = e.get("strHomeTeamBadge")
                         ret_away_badge = e.get("strAwayTeamBadge")
                     else:
                         ret_home_badge = e.get("strAwayTeamBadge")
                         ret_away_badge = e.get("strHomeTeamBadge")
                     
                    # Format date
                     try:
                         dt_obj = datetime.strptime(date_event, "%Y-%m-%d")
                         
                         # Night Mode Logic
                         if subtract_day_for_night:
                             try:
                                 hour = int(tr_time.split(":")[0])
                                 if 0 <= hour < 6:
                                     from datetime import timedelta
                                     dt_obj = dt_obj - timedelta(days=1)
                             except: pass

                         months = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]
                         month_name = months[dt_obj.month - 1]
                         tr_date = f"{dt_obj.day} {month_name}"
                         
                         # Canonical Names for correcting typos
                         canon_home = e.get("strHomeTeam")
                         canon_away = e.get("strAwayTeam")
                         
                         return tr_time, tr_date, ret_home_badge, ret_away_badge, canon_home, canon_away
                     except:
                         canon_home = e.get("strHomeTeam")
                         canon_away = e.get("strAwayTeam")
                         return tr_time, date_event, ret_home_badge, ret_away_badge, canon_home, canon_away
    
    return None, None, None, None, None, None

def get_match_details(home, away, subtract_day_for_night=False):
    """
    Synchronous wrapper for external use.
    """
    return asyncio.run(find_match_by_names(home, away, subtract_day_for_night))

async def main():
    # Clear screen (OS dependent, simple newlines for compatibility)
    print("\n" * 50) 
    print("=== SPOR PUSULASI (PREMIUM - PYTHON) ===")
    print("Takım arayın (örn: 'inter', 'fener'), seçin ve maç detaylarına ulaşın.\n")

    while True:
        try:
            query = input("Takım Adı Girin (Çıkış için q): ").strip()
            if not query: continue
            if query.lower() == 'q': break
            
            print(f"\n'{query}' için geniş kapsamlı aranıyor...")
            
            teams = await search_with_fallback(query)
            
            if not teams:
                print("❌ Takım bulunamadı. Başka bir isim deneyin.")
                continue
                
            print("\n🔎 Bulunan Takımlar:")
            for idx, t in enumerate(teams):
                print(f"{idx + 1}. {t.get('strTeam')} ({t.get('strSport', 'N/A')} - {t.get('strLeague', 'Lig Bilgisi Yok')})")
                
            sel_str = input("\nSeçiminiz (Numara girin, q çıkış): ").strip()
            if sel_str.lower() == 'q': break
            
            try:
                sel_idx = int(sel_str) - 1
                if sel_idx < 0 or sel_idx >= len(teams):
                    raise ValueError()
            except ValueError:
                print("❌ Geçersiz seçim.")
                continue
                
            selected_team = teams[sel_idx]
            print(f"\n✅ Seçim: {selected_team.get('strTeam')}")
            
            # Date Handling Logic
            now = datetime.now()
            current_day = now.day
            current_month = now.month
            current_year = now.year
            
            day_input = input(f"\nMaç Günü (Örn: {current_day}, varsayılan bugün): ").strip()
            
            final_date = ""
            if not day_input:
                final_date = now.strftime("%Y-%m-%d")
            else:
                # User entered just a day number (e.g. "9", "25")
                try:
                    d = int(day_input)
                    # Create date object to handle overflow properly or valid format
                    target_date = datetime(current_year, current_month, d)
                    final_date = target_date.strftime("%Y-%m-%d")
                except ValueError:
                    print("❌ Hatalı gün formatı. Lütfen sayı giriniz (1-31).")
                    continue

            print(f"\n📅 {final_date} için veriler taranıyor...")
            
            match_found = None
            
            # Method A: Check eventsday
            day_url = f"{BASE_URL}/eventsday.php?d={final_date}"
            day_res = await fetch_json_async(day_url)
            
            tid = selected_team.get("idTeam")
            if day_res.get("events"):
                for e in day_res["events"]:
                    if e.get("idHomeTeam") == tid or e.get("idAwayTeam") == tid:
                        match_found = e
                        break
            
            # Method B: Check seasons
            if not match_found:
                seasons = ["2025-2026", "2024-2025"]
                for s in seasons:
                    if match_found: break
                    s_url = f"{BASE_URL}/eventsseason.php?id={tid}&s={s}"
                    s_res = await fetch_json_async(s_url)
                    if s_res.get("events"):
                        for e in s_res["events"]:
                            if e.get("dateEvent") == final_date:
                                match_found = e
                                break
            
            if match_found:
                await display_match(match_found)
            else:
                print(f"\n❌ {final_date} tarihinde {selected_team.get('strTeam')} maçı bulunamadı.")
            
            again = input("\nYeni arama? (e/h): ").strip()
            if again.lower() != 'e':
                break
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Bir hata oluştu: {e}")

if __name__ == "__main__":
    asyncio.run(main())
