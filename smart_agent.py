
import os
import json
import datetime
import re
from duckduckgo_search import DDGS

# Opsiyonel: OpenAI ve Gemini importları
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

def safe_search(query, max_results=5):
    """
    DuckDuckGo üzerinden güvenli arama yapar.
    Hata durumunda veya sonuç yoksa farklı varyasyonları dener.
    """
    from time import sleep
    
    # 1. İlk Deneme (Standart)
    try:
        results = DDGS().text(query, max_results=max_results)
        if results: return results
    except Exception as e:
        print(f"⚠️ Arama hatası (Standart): {e}")

    sleep(1)

    # 2. İkinci Deneme (Backend: html - daha yavaş ama bazen daha stabil)
    try:
        results = DDGS().text(query, max_results=max_results, backend='html')
        if results: return results
    except Exception as e:
        print(f"⚠️ Arama hatası (HTML Backend): {e}")
        
    return []

def heuristic_parse_match_time(search_results):
    print("⚠️ AI kullanılamadı, arama sonuçları manuel analiz ediliyor...")
    
    # Saat Regex (HH:MM)
    time_pattern = re.compile(r'\b([0-1]?[0-9]|2[0-3]):([0-5][0-9])\b')
    
    # Tarih Regex (DD Mod) - Türkçe ve İngilizce Aylar
    months_str = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December|Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık"
    date_pattern = re.compile(r'\b([1-9]|[12][0-9]|3[01])\s+(' + months_str + r')\b', re.IGNORECASE)
    
    found_time = None
    found_date = None
    
    for r in search_results:
        text = (r['title'] + " " + r['body'])
        
        # Saat Ara
        if not found_time:
            t_match = time_pattern.search(text)
            if t_match:
                found_time = t_match.group(0)
        
        # Tarih Ara
        if not found_date:
            d_match = date_pattern.search(text)
            if d_match:
                day, month = d_match.groups()
                # Ay ismini Türkçeye/Büyük harfe çevir (Basit mapping)
                tr_map = {
                    "jan": "OCAK", "january": "OCAK",
                    "feb": "ŞUBAT", "february": "ŞUBAT",
                    "mar": "MART", "march": "MART",
                    "apr": "NİSAN", "april": "NİSAN",
                    "may": "MAYIS",
                    "jun": "HAZİRAN", "june": "HAZİRAN",
                    "jul": "TEMMUZ", "july": "TEMMUZ",
                    "aug": "AĞUSTOS", "august": "AĞUSTOS",
                    "sep": "EYLÜL", "september": "EYLÜL",
                    "oct": "EKİM", "october": "EKİM",
                    "nov": "KASIM", "november": "KASIM",
                    "dec": "ARALIK", "december": "ARALIK"
                }
                m_lower = month.lower()
                final_month = tr_map.get(m_lower, month.upper())
                found_date = f"{day} {final_month}"
        
        if found_time and found_date:
            break
            
    if found_time or found_date:
        print(f"🤖 Manuel Analiz Sonucu: Tarih={found_date}, Saat={found_time}")
        return found_time, found_date
    
    return None, None

def ask_gpt_for_match_time(home_team, away_team, api_key):
    """
    OpenAI API kullanarak verilen maçın tarih ve saatini bulur.
    """
    if not OpenAI:
        print("❌ OpenAI paketi yüklü değil.")
        return None, None

    # 1. İnternet Araması
    query = f"{home_team} vs {away_team} match date time 2026 fixture"
    print(f"🤖 İnternet taranıyor (OpenAI Modu): '{query}'...")
    
    search_results = safe_search(query, max_results=5)
    
    if not search_results:
        return None, None

    context_text = "\n".join([f"- {r['title']}: {r['body']}" for r in search_results])
    
    # 2. OpenAI Parse İşlemi
    try:
        client = OpenAI(api_key=api_key)
        
        system_prompt = """
        Sen uzman bir spor asistanısın. Görevin, sana verilen arama sonuçlarını analiz ederek 
        belirtilen futbol maçının TARİHİNİ ve SAATİNİ (Türkiye Saati - TSİ/TRT) bulmaktır.
        
        Çıktı Formatı (JSON):
        {
            "date": "10 OCAK", 
            "time": "20:00"
        }
        
        Kurallar:
        - Tarih formatı: GÜN ve AY İSMİ (Büyük harf, Türkçe). Örn: 10 OCAK.
        - Saat formatı: HH:MM.
        - Türkiye saatini hesapla (gerekirse +3 ekle).
        """
        
        user_prompt = f"Maç: {home_team} vs {away_team}\n\nArama Sonuçları:\n{context_text}"
        
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={ "type": "json_object" },
            temperature=0
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        return data.get("date", "").strip(), data.get("time", "").strip()
        
    except Exception as e:
        print(f"❌ OpenAI Hatası: {e}")
        return heuristic_parse_match_time(search_results)

def ask_gemini_for_match_time(home_team, away_team, api_key):
    """
    Gemini API kullanarak verilen maçın tarih ve saatini bulur.
    """
    if not genai:
        print("❌ google-generativeai paketi yüklü değil.")
        return None, None

    # 1. İnternet Araması
    # Hem İngilizce Hem Türkçe Ara
    query = f"{home_team} vs {away_team} match date time 2026 fixture"
    print(f"🤖 İnternet taranıyor (Gemini Modu): '{query}'...")
    
    search_results = safe_search(query, max_results=5)
    
    if not search_results:
        # Türkçe deneme
        query_tr = f"{home_team} {away_team} maç tarihi saati 2026"
        print(f"🤖 Türkçe taranıyor: '{query_tr}'...")
        search_results = safe_search(query_tr, max_results=5)

    if not search_results:
        # Son çare: Çok basit sorgu
        query_simple = f"{home_team} {away_team} match"
        print(f"🤖 Geniş kapsamlı taranıyor: '{query_simple}'...")
        search_results = safe_search(query_simple, max_results=5)

    if not search_results:
        print("❌ İnternette hiç sonuç bulunamadı.")
        return None, None
    
    print(f"DEBUG: {len(search_results)} sonuç bulundu. Analiz ediliyor...")

    context_text = "\n".join([f"- {r['title']}: {r['body']}" for r in search_results])
    
    # 2. Gemini Parse İşlemi
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = f"""
        Sen uzman bir spor asistanısın. Aşağıdaki arama sonuçlarına bakarak
        {home_team} vs {away_team} maçının BUGÜN (Varsayıyoruz ki bugün 10 OCAK 2026) oynanıp oynanmadığını kontrol et.
        Sadece bugünün maçını arıyoruz.

        Eğer bugüne ait (10 Ocak 2026) bir maç varsa saatini TSİ olarak ver.
        Eğer maç başka bir gündeyse (örneğin Şubat, Nisan vb.), tarih ve saati BOŞ bırak.
        
        ÖNEMLİ: Sadece JSON formatında yanıt ver. Başka bir şey yazma.
        
        JSON Formatı:
        {{
            "date": "GÜN AY_İSMİ", 
            "time": "HH:MM",
            "reason": "Neden bu tarihi seçtin?"
        }}
        
        Örnek: {{ "date": "10 OCAK", "time": "20:00", "reason": "TFF sitesinde 10 Ocak yazıyor" }}
        Not: Ay ismi Türkçe ve BÜYÜK HARF olmalı. Saat Türkiye saati olmalı.

        Arama Sonuçları:
        {context_text}
        """

        response = model.generate_content(prompt)
        text = response.text
        print(f"DEBUG: Gemini Yanıtı: {text}")
        
        # JSON temizliği (Gemini markdown ```json ... ``` dönebilir)
        text = text.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
             # Bazen düz metin dönebilir, basitçe regex ile ayıklamayı dene veya hata ver
             print("⚠️ Gemini JSON döndürmedi.")
             return heuristic_parse_match_time(search_results)
        
        d = data.get("date", "").strip()
        t = data.get("time", "").strip()
        
        if not d or not t:
            print("⚠️ Gemini tarih veya saati bulamadı.")
            return heuristic_parse_match_time(search_results)
            
        return d, t

    except Exception as e:
        print(f"❌ Gemini Hatası: {e}")
        return heuristic_parse_match_time(search_results)
