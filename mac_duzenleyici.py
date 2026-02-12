#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSD Otomasyon Botu - Ana Python Betiği
Bu betik, birden fazla maç için PSD şablonunu otomatik olarak güncellemek üzere
Photoshop ExtendScript'i tetikler.
"""

import os
import subprocess
import base64
import json
import datetime
import sports_cli  # Import the sports CLI module

# =============================================================================
# AYARLAR VE SABİTLER
# =============================================================================
# Mac ortamı için çalışma dizini (Windows: C:\\PSD_Bot_Calisma\\)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGOS_DIR = os.path.join(BASE_DIR, "logos")
PSD_PATH = os.path.join(BASE_DIR, "Maclar.psd")
OUTPUT_DIR = os.path.join(BASE_DIR, "Mac")
JSX_OUTPUT_PATH = os.path.join(BASE_DIR, "psd_otomasyon.jsx")

# Klasörlerin varlığından emin ol
os.makedirs(LOGOS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Minimal 1x1 Piksel PNG (Base64) - Logo simülasyonu için
DUMMY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

# =============================================================================
# II. EXTENDSCRIPT (JSX) ŞABLONU
# =============================================================================
JSX_TEMPLATE = """

app.displayDialogs = DialogModes.NO; // Disable dialogs for speed
app.preferences.rulerUnits = Units.PIXELS; // Enforce pixels

function main() {
    // Python'dan enjekte edilen veri nesnesi
    var data = {{DATA_JSON}};

    // 1. DOSYA AÇMA
    var fileRef = new File(data.psdPath);
    if (!fileRef.exists) {
        alert("Hata: PSD dosyası bulunamadı -> " + data.psdPath);
        return;
    }
    var doc = app.open(fileRef);

    // --- YARDIMCI FONKSİYONLAR ---
    function findLayerByName(root, name) {
        try {
            var layers = root.layers;
            for (var i = 0; i < layers.length; i++) {
                if (layers[i].name === name) return layers[i];
                if (layers[i].typename === "LayerSet") {
                    var found = findLayerByName(layers[i], name);
                    if (found) return found;
                }
            }
        } catch(e) {}
        return null;
    }

    function findLayerByFuzzyName(root, name) {
        try {
            var searchName = name.toLowerCase().replace(/\\s/g, "");
            var layers = root.layers;
            for (var i = 0; i < layers.length; i++) {
                var layer = layers[i];
                var layerName = layer.name.toLowerCase().replace(/\\s/g, "");
                if (layerName === searchName) return layer;
                if (layer.typename === "LayerSet") {
                    var found = findLayerByFuzzyName(layer, name);
                    if (found) return found;
                }
            }
        } catch(e) {}
        return null;
    }

    function getLayerWidth(layer) {
        var bounds = layer.bounds;
        return bounds[2].as("px") - bounds[0].as("px");
    }

    function placeAndCleanup(docRef, fileRef) {
        // Hızlandırılmış yerleştirme ve temizleme
        docRef.activeLayer = docRef.layers[0]; 
        
        // 1. Place
        var idPlc = charIDToTypeID("Plc ");
        var desc = new ActionDescriptor();
        desc.putPath(charIDToTypeID("null"), fileRef);
        desc.putEnumerated(charIDToTypeID("FTcs"), charIDToTypeID("QCSt"), charIDToTypeID("Qcsa"));
        executeAction(idPlc, desc, DialogModes.NO);
        
        var newLogoLayer = docRef.activeLayer;
        newLogoLayer.name = "Logo";

        // --- RESIZE LOGIC (FIT TO CANVAS) ---
        // Kullanıcı isteği: Akıllı nesne boyutlarına sadık kal (Fit)
        try {
            var docW = docRef.width.as("px");
            var docH = docRef.height.as("px");
            var lb = newLogoLayer.bounds;
            var lW = lb[2].as("px") - lb[0].as("px");
            var lH = lb[3].as("px") - lb[1].as("px");
            
            if (lW > 0 && lH > 0) {
                 // Fit Logic: Scale to fit within canvas bounds (touching edges)
                 // Or keep original if smaller? Usually "Fit" means maximize.
                 
                 var scaleX = (docW / lW) * 100;
                 var scaleY = (docH / lH) * 100;
                 
                 // Use the smaller scale to ensure it fits entirely
                 // Optional: Use 95% to leave a small margin, or 100% for full bleed.
                 // Using 100% as requested ("sadık kal" interpretation: fill the placeholder box)
                 var scale = Math.min(scaleX, scaleY);
                 
                 // Ancak, eğer görsel zaten canvas'tan küçükse ve büyütme istenmiyorsa?
                 // Genelde logolar büyük indirilir, bu yüzden küçültme gerekir.
                 // Eğer çok küçükse büyütmeli mi? Evet, placeholder'ı doldurmalı.
                 
                 newLogoLayer.resize(scale, scale, AnchorPosition.MIDDLECENTER);
            }
        } catch(e) {}

        // 2. Cleanup (Faster Loop)
        var len = docRef.layers.length;
        for (var i = len - 1; i >= 0; i--) {
            var lyr = docRef.layers[i];
            if (lyr !== newLogoLayer) {
                // Basketbol fallback koruması
                if (data.isBasketball) {
                    var lName = lyr.name.toLowerCase();
                    if (lName.indexOf("elips") !== -1 || lName.indexOf("ellipse") !== -1 || lName.indexOf("shape") !== -1) continue;
                }
                lyr.remove();
            }
        }
        
        // Rasterize if needed
        try {
             if (newLogoLayer.kind === LayerKind.SMARTOBJECT) {
                 newLogoLayer.rasterize(RasterizeType.ENTIRELAYER);
             }
        } catch (e) {}
    }

    function replaceSmartObjectContent(layer, filePath) {
        var fileRef = new File(filePath);
        if (!fileRef.exists) return false;
        
        doc.activeLayer = layer;
        try {
            // Smart Object Aç
            executeAction(stringIDToTypeID("placedLayerEditContents"), new ActionDescriptor(), DialogModes.NO);
            var smartDoc = app.activeDocument;
            
            // Nested Check (Basketball)
            var processedNested = false;
            if (data.isBasketball) {
                var nestedLogoLayer = findLayerByName(smartDoc, "Logo");
                if (!nestedLogoLayer) nestedLogoLayer = findLayerByFuzzyName(smartDoc, "Logo");
                
                if (nestedLogoLayer && nestedLogoLayer.kind === LayerKind.SMARTOBJECT) {
                    smartDoc.activeLayer = nestedLogoLayer;
                    executeAction(stringIDToTypeID("placedLayerEditContents"), new ActionDescriptor(), DialogModes.NO);
                    var nestedDoc = app.activeDocument;
                    
                    placeAndCleanup(nestedDoc, fileRef);
                    
                    nestedDoc.close(SaveOptions.SAVECHANGES);
                    processedNested = true;
                }
            }
            
            if (!processedNested) {
                placeAndCleanup(smartDoc, fileRef);
            }
            
            smartDoc.close(SaveOptions.SAVECHANGES);
            return true;
        } catch (e) {
            // Hata durumunda kurtarma
            while (app.activeDocument !== doc) {
                 app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
            }
            return false;
        }
    }

    // --- 2. KATMANLARI GÜNCELLEME ---
    var updateLog = "";
    var textUpdateCount = 0;
    var soUpdateCount = 0;
    
    // Oran Yok Modu (Tüm oranları ve kutusunu gizle)
    if (data.hideOdds) {
        var targets = ["1.Oran", "BerabereOran", "2.Oran", "Oran"];
        var suffixes = ["", "Kutusu", "Box", "Zemin", "Bg", "ArkaPlan", "Dikdortgeni", "Shape", "Sekli", "Alani", "Background"];
        var extras = ["Oranlar", "Odds", "OranKutulari", "OranBolumu"]; // Grup isimleri veya genel kutular
        
        var allToHide = [];
        // Oran isimleri + Ekler (Örn: 1.OranKutusu, BerabereOranZemin)
        for(var t=0; t<targets.length; t++){
            for(var s=0; s<suffixes.length; s++){
                allToHide.push(targets[t] + suffixes[s]);
            }
        }
        // Ekstra manuel tanımlar
        for(var e=0; e<extras.length; e++) allToHide.push(extras[e]);
        
        for (var k = 0; k < allToHide.length; k++) {
            var oLayer = findLayerByName(doc, allToHide[k]) || findLayerByFuzzyName(doc, allToHide[k]);
            if (oLayer) oLayer.visible = false;
        }
    }

    // Metin Güncellemeleri
    var textUpdates = [
        { keys: ["MacSaati", "Saat", "Time", "Mac_Saat"], value: data.saat },
        { keys: ["MacGunu", "MacGünü", "Tarih", "Date", "Mac_Gunu", "Günü", "MacTarihi"], value: data.gun },
        { keys: ["1.MacAdi", "EvSahibi", "HomeTeam"], value: data.evSahibi },
        { keys: ["2.MacAdi", "Deplasman", "AwayTeam"], value: data.deplasman },
        { keys: ["1.Oran", "Oran1"], value: data.oran1 },
        { keys: ["BerabereOran", "OranX", "OranB"], value: data.oranX },
        { keys: ["2.Oran", "Oran2"], value: data.oran2 }
    ];

    for (var i = 0; i < textUpdates.length; i++) {
        var update = textUpdates[i];
        var keys = update.keys;
        var value = update.value;

        // Eğer oranlar gizlendiyse ve bu bir oran katmanıysa atla
        if (data.hideOdds && (keys[0].indexOf("Oran") !== -1)) {
            continue;
        }

        var layer = null;
        for (var k = 0; k < keys.length; k++) {
            layer = findLayerByName(doc, keys[k]) || findLayerByFuzzyName(doc, keys[k]);
            if (layer) break;
        }

        if (layer) {
             // Basketbol gizleme mantığı (Berabere Oranı yoksa)
            if (keys[0] === "BerabereOran" && value === "") {
                layer.visible = false;
                continue;
            } else if (keys[0] === "BerabereOran") {
                if (!data.hideOdds) layer.visible = true;
            }

            if (layer.kind === LayerKind.TEXT) {
                // Kısaltma ve Güncelleme Mantığı
                var content = value;
                var mainKey = keys[0];
                
                if (mainKey === "1.MacAdi" || mainKey === "2.MacAdi") {
                     // Basit Kısaltmalar
                     content = content.replace(/Football Club/gi, "FC")
                                      .replace(/United/gi, "Utd")
                                      .replace(/Sporting/gi, "Sp.")
                                      .replace(/Olympique/gi, "O.")
                                      .replace(/Saint/gi, "St.")
                                      .replace(/Borussia/gi, "B.");
                     // Özel Kısaltmalar (Örnek)
                     if (content.match(/Paris Saint-Germain/i)) content = "PSG";
                     
                     layer.textItem.contents = content;
                     
                     // Dikdörtgen ve Hizalama Mantığı (Basitleştirilmiş)
                     try {
                         var rectName = mainKey.replace("MacAdi", "MacDikdortgeni");
                         var rectLayer = findLayerByName(doc, rectName) || findLayerByFuzzyName(doc, rectName);
                         if (rectLayer) {
                             // Basitçe metin genişliğine göre scale
                             var tW = getLayerWidth(layer);
                             var rW = rectLayer.bounds[2].as("px") - rectLayer.bounds[0].as("px");
                             var targetW = tW + 50; 
                             var scaleP = (targetW / rW) * 100;
                             rectLayer.resize(scaleP, 100, AnchorPosition.MIDDLECENTER);
                         }
                     } catch(err) {}

                } else {
                    layer.textItem.contents = content;
                }
                
                // Saat/Gün Ortalama
                 if (mainKey === "MacSaati" || mainKey === "MacGunu") {
                    try {
                        layer.textItem.justification = Justification.CENTER;
                        var docCX = doc.width.as("px") / 2;
                        var lB = layer.bounds;
                        var lCX = (lB[0].as("px") + lB[2].as("px")) / 2;
                        layer.translate(new UnitValue(docCX - lCX, "px"), 0);
                    } catch(e) {}
                }
                
                textUpdateCount++;
                updateLog += "OK: " + mainKey + " (" + layer.name + ") -> " + content + "\\n";
            }
        } else {
            updateLog += "MISS: " + keys[0] + "\\n";
        }
    }

    // Akıllı Nesne Güncellemeleri
    var soUpdates = [
        { name: "1.MacGorseli", path: data.logo1 },
        { name: "2.MacGorseli", path: data.logo2 }
    ];

    for (var i = 0; i < soUpdates.length; i++) {
        var item = soUpdates[i];
        var soLayer = findLayerByName(doc, item.name) || findLayerByFuzzyName(doc, item.name);
        
        if (soLayer && soLayer.kind === LayerKind.SMARTOBJECT) {
            if (replaceSmartObjectContent(soLayer, item.path)) {
                soUpdateCount++;
            }
        }
    }
    
    // Görsel Hizalamaları (MacGorseline Gore Metin ve Dikdortgeni YATAY (X Ekseni) Ortalama)
    try {
        function unlockAndTranslate(layer, dx, dy) {
            if (!layer) return;
            try {
                if(layer.allLocked) layer.allLocked = false;
                if(layer.positionLocked) layer.positionLocked = false;
                
                layer.translate(dx, dy);
            } catch(err) {}
        }

        var alignSets = [
            {logo: "1.MacGorseli", text: "1.MacAdi", rects: ["1.MacDikdortgeni", "1.MacBox", "1.MacShape", "1.MacZemin"]},
            {logo: "2.MacGorseli", text: "2.MacAdi", rects: ["2.MacDikdortgeni", "2.MacBox", "2.MacShape", "2.MacZemin"]}
        ];
        
        for(var a=0; a<alignSets.length; a++){
            var item = alignSets[a];
            var lLogo = findLayerByName(doc, item.logo) || findLayerByFuzzyName(doc, item.logo);
            
            if(lLogo){
                 // Referans (Logo) Merkez X (Yatay)
                 var bLogo = lLogo.bounds;
                 var cLogoX = (bLogo[0].as("px") + bLogo[2].as("px")) / 2;
                 
                 // 1. Metni Hizala (X Ekseni)
                 var lText = findLayerByName(doc, item.text) || findLayerByFuzzyName(doc, item.text);
                 if(lText){
                     var bText = lText.bounds;
                     var cTextX = (bText[0].as("px") + bText[2].as("px")) / 2;
                     
                     // Fark Hesapla (X)
                     var diffX = cLogoX - cTextX;
                     if (Math.abs(diffX) > 0.5) {
                        unlockAndTranslate(lText, new UnitValue(diffX, "px"), 0);
                     }
                 }
                 
                 // 2. Dikdortgeni Hizala (X Ekseni)
                 var lRect = null;
                 for(var r=0; r<item.rects.length; r++){
                     lRect = findLayerByName(doc, item.rects[r]) || findLayerByFuzzyName(doc, item.rects[r]);
                     if(lRect) break;
                 }
                 
                 if(lRect){
                     var bRect = lRect.bounds;
                     var cRectX = (bRect[0].as("px") + bRect[2].as("px")) / 2;
                     var diffRectX = cLogoX - cRectX;
                     
                     if (Math.abs(diffRectX) > 0.5) {
                         unlockAndTranslate(lRect, new UnitValue(diffRectX, "px"), 0);
                     }
                 }
            }
        }
    } catch(e) {}

    // --- 3. KAYDETME ---
    if (soUpdateCount < 2) {
        // Hata
        doc.close(SaveOptions.DONOTSAVECHANGES);
    } else {
        var saveFile = new File(data.outputDir + "/" + data.outputFileName.replace(".jpg", ".png"));
        var pngOpts = new PNGSaveOptions();
        pngOpts.compression = 9;
        pngOpts.interlaced = false;
        
        doc.saveAs(saveFile, pngOpts, true, Extension.LOWERCASE);
        doc.close(SaveOptions.DONOTSAVECHANGES);
    }
    
    // MEMORY PURGE (RAM TEMİZLİĞİ) - LAG ÖNLEME
    try {
        app.purge(PurgeTarget.ALLCACHES);
        app.purge(PurgeTarget.HISTORY);
    } catch(e) {}
}

main();
"""

# =============================================================================
# I. PYTHON ANA BETİĞİ FONKSİYONLARI
# =============================================================================

def get_match_data_from_user(boost_odds=False):
    """A. Giriş Verileri - Kullanıcıdan maç verisi al (basitleştirilmiş format)"""
    matches = []
    
    print("=" * 60)
    print("PSD OTOMASYON BOTU - MAÇ VERİSİ GİRİŞİ")
    print("=" * 60)
    print("Her satıra bir maç bilgisi girin.")
    print("Format: Takım1 vs Takım2 Oran1 OranX Oran2")
    print("Örnek: Kocaelispor vs Antalyaspor 1.63 3.70 5.75")
    print("Örnek: Valencia vs Mallorca 1.97 3.20 4.25")
    if boost_odds:
        print("⚡ Oran Artırma Modu: Girdiğiniz oranlara otomatik +0.20 eklenecek")
    print("Bitirmek için boş satır bırakın.\n")
    
    while True:
        line = input(f"Maç {len(matches)+1} (veya Enter ile bitir): ").strip()
        
        if not line:
            break
            
        try:
            # Önce "vs" veya "vs." ile ayır
            ev_sahibi = ""
            deplasman = ""
            oran_1 = ""
            oran_x = ""
            oran_2 = ""
            
            # Ayırıcıları kontrol et (öncelik sırasına göre)
            separators = [" vs. ", " vs ", " - ", " / ", " VS. ", " VS ", " Vs. ", " Vs "]
            found_sep = False
            
            for sep in separators:
                if sep in line:
                    # Ayırıcıyı bulduk, şimdi takımları ve oranları ayıralım
                    parts = line.split(sep, 1)  # Sadece ilk ayırıcıda böl
                    if len(parts) == 2:
                        ev_sahibi = parts[0].strip()
                        
                        # İkinci kısımdan takım adı ve oranları ayır
                        remaining = parts[1].strip().split()
                        
                        # Son 2 veya 3 eleman oran olmalı
                        if len(remaining) >= 3:
                            # Check for No Odds Indicator (Manual Input)
                            if remaining[-1].lower() in ["yok", "-", "0", "oran_yok", "no_odds"]:
                                oran_1 = ""
                                oran_x = ""
                                oran_2 = ""
                                deplasman = " ".join(remaining[:-1])
                                found_sep = True
                                # Flag needed in dictionary? get_match_data_from_user returns specific dict structure.
                                # I need to ensure the dict structure includes hide_odds or handle empty strings later.
                                # The current dict doesn't carry extra flags easily unless I add them.
                                # But wait, the return dict keys are fixed in lines 440-446.
                                # I will add "hide_odds": True to that dict.
                                pass

                            # Son 3 elemanın sayı olup olmadığını kontrol et
                            try:
                                float(remaining[-1])
                                float(remaining[-2])
                                float(remaining[-3])
                                # 3'lü oran (Futbol: 1 X 2)
                                oran_2 = remaining[-1]
                                oran_x = remaining[-2]
                                oran_1 = remaining[-3]
                                deplasman = " ".join(remaining[:-3])
                                found_sep = True
                                break
                            except (ValueError, IndexError):
                                pass
                        
                        if len(remaining) >= 2 and not found_sep:
                            # Check for No Odds (Short)
                            if remaining[-1].lower() in ["yok", "-", "0", "oran_yok", "no_odds"]:
                                oran_1 = ""
                                oran_x = ""
                                oran_2 = ""
                                deplasman = " ".join(remaining[:-1])
                                found_sep = True
                                pass

                            # Son 2 elemanın sayı olup olmadığını kontrol et
                            try:
                                float(remaining[-1])
                                float(remaining[-2])
                                # 2'li oran (Basketbol: 1 2)
                                oran_2 = remaining[-1]
                                oran_1 = remaining[-2]
                                oran_x = ""  # Beraberlik yok
                                deplasman = " ".join(remaining[:-2])
                                found_sep = True
                                break
                            except (ValueError, IndexError):
                                pass
            
            # Ayırıcı bulunamadıysa hata ver
            if not found_sep:
                print("❌ Hatalı format! 'vs' veya 'vs.' kullanarak takımları ayırın.")
                print("   Örnek: Kocaelispor vs Antalyaspor 1.63 3.70 5.75")
                continue
            
            # Takım isimlerini kontrol et
            if not ev_sahibi or not deplasman:
                print("❌ Takım isimleri boş olamaz!")
                continue
            
            # Oranları kontrol et
            if not oran_1 or not oran_2:
                print("❌ En az 2 oran gerekli (1 ve 2)!")
                continue

            # Oran artırma (Boost)
            if boost_odds:
                try:
                    # 1. Oran
                    o1 = float(oran_1) + 0.20
                    oran_1 = f"{o1:.2f}"
                    
                    # 2. Oran
                    o2 = float(oran_2) + 0.20
                    oran_2 = f"{o2:.2f}"
                    
                    # Beraberlik (Sadece varsa)
                    if oran_x and oran_x.strip():
                        ox = float(oran_x) + 0.20
                        oran_x = f"{ox:.2f}"
                except:
                    pass # Sayı değilse dokunma

            matches.append({
                "ev_sahibi": ev_sahibi,
                "deplasman": deplasman,
                "oran_1": oran_1,
                "oran_x": oran_x,
                "oran_2": oran_2,
                "hide_odds": True if not oran_1 else False
            })
            print(f"✅ Eklendi: {ev_sahibi} vs {deplasman} (Oranlar: {oran_1}, {oran_x}, {oran_2})")
            
        except Exception as e:
            print(f"❌ Hata oluştu: {e}")
            continue
    
    if not matches:
        print("\n⚠️ Hiç maç girilmedi, demo veriler kullanılacak.")
        return get_demo_match_data()
    
    return matches

def get_demo_match_data():
    """A. Giriş Verileri - Demo: 5 örnek maç verisi"""
    return [
        {
            "ev_sahibi": "Fenerbahçe",
            "deplasman": "Beşiktaş",
            "oran_1": "1.85",
            "oran_x": "3.20",
            "oran_2": "4.10"
        },
        {
            "ev_sahibi": "Beşiktaş",
            "deplasman": "Trabzonspor",
            "oran_1": "1.75",
            "oran_x": "3.50",
            "oran_2": "4.20"
        },
        {
            "ev_sahibi": "Barcelona",
            "deplasman": "Real Madrid",
            "oran_1": "2.10",
            "oran_x": "3.40",
            "oran_2": "3.30"
        },
        {
            "ev_sahibi": "Manchester United",
            "deplasman": "Liverpool",
            "oran_1": "2.50",
            "oran_x": "3.20",
            "oran_2": "2.80"
        },
        {
            "ev_sahibi": "Bayern Munich",
            "deplasman": "Borussia Dortmund",
            "oran_1": "1.65",
            "oran_x": "3.80",
            "oran_2": "5.00"
        }
    ]

def scrape_match_time_sportsdb(team1, team2, subtract_day_for_night=False):
    """B. Saat ve Gün Arama - TheSportsDB API üzerinden (sports_cli.py kullanarak)"""
    print(f"🔍 TheSportsDB üzerinden aranıyor: {team1} vs {team2}...")
    
    try:
        # Unpack 6 values (Added canon_home, canon_away)
        saat, gun, home_badge, away_badge, canon_home, canon_away = sports_cli.get_match_details(team1, team2, subtract_day_for_night=subtract_day_for_night)
        
        if saat and gun:
            print(f"✅ MAÇ BULUNDU: {gun} {saat} (TSİ)")
            print(f"   (Resmi İsimler: {canon_home} vs {canon_away})")
            return saat, gun, home_badge, away_badge, canon_home, canon_away
        
        print(f"❌ TheSportsDB'de bulunamadı.")
        return None, None, None, None, None, None
        
    except Exception as e:
        print(f"⚠️ Arama hatası: {e}")
        return None, None, None, None, None, None

def smart_match_search(team1, team2, api_key):
    """C. Akıllı Arama (OpenAI veya Gemini + DuckDuckGo)"""
    import smart_agent
    print(f"🧠 Yapay Zeka Devrede: {team1} vs {team2} internetten araştırılıyor...")
    
    try:
        # Key tipine göre fonksiyon seç
        if api_key.startswith("sk-"):
            # OpenAI
            saat, gun = smart_agent.ask_gpt_for_match_time(team1, team2, api_key)
        else:
            # Gemini (Varsayılan olarak AIza... ile başlar ama else yeterli)
            saat, gun = smart_agent.ask_gemini_for_match_time(team1, team2, api_key)
            
        if saat and gun:
            print(f"✅ AI SONUCU: {gun} {saat}")
            return saat, gun
        else:
             print("❌ AI da kesin bir tarih bulamadı.")
             return None, None
    except Exception as e:
        print(f"⚠️ AI Hatası: {e}")
        return None, None

def simulate_data_fetching(team1, team2):
    """B. Saat ve Gün Arama - Fallback simülasyon"""
    from datetime import datetime as dt
    
    now = dt.now()
    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    aylar = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    
    # Genelde akşam maçları
    gun_ismi = gunler[now.weekday()]
    ay_ismi = aylar[now.month - 1]
    mac_gunu = f"{gun_ismi}, {now.day} {ay_ismi}"
    
    # Simüle edilmiş saat (akşam saatleri)
    saatler = ["19:00", "20:00", "21:00", "21:45", "22:30"]
    tr_mac_saati = saatler[hash(team1 + team2) % len(saatler)]
    
    print(f"📅 Simülasyon: {team1} vs {team2} - {mac_gunu} {tr_mac_saati}")
    return tr_mac_saati, mac_gunu

def download_logos(team1, team2, url1=None, url2=None):
    """
    B. Logo İndirme Fonksiyonu
    
    ÖNEMLİ: Bu fonksiyon SADECE takım isimlerine göre logo arar.
    url1 ve url2 parametreleri API'den gelir ama GÖRMEZDEn GELİNİR.
    Çünkü API'deki ev sahibi/deplasman sırası kullanıcının girdiği sıradan farklı olabilir.
    
    KURAL: 
    - team1 (kullanıcının girdiği ilk takım) -> logo1 (1.MacGorseli)
    - team2 (kullanıcının girdiği ikinci takım) -> logo2 (2.MacGorseli)
    """
    import requests
    from PIL import Image, ImageDraw
    import os
    from shutil import copyfile
    
    # API'den gelen URL'leri GÖRMEZDEN GEL (veya opsiyonel kullan)
    
    def safe_filename(name):
        replacements = {
            'ı': 'i', 'İ': 'I', 'ş': 's', 'Ş': 'S',
            'ç': 'c', 'Ç': 'C', 'ğ': 'g', 'Ğ': 'G',
            'ü': 'u', 'Ü': 'U', 'ö': 'o', 'Ö': 'O',
            ' ': '_'
        }
        for old, new in replacements.items():
            name = name.replace(old, new)
        return name.lower()
    
    def resize_and_mask_logo(image_path, size=177):
        """Logoyu işle: Beyaz arka planı temizle, transparan yap, kırp ve kaydet"""
        try:
            img = Image.open(image_path).convert("RGBA")
            
            # Beyaz arka plan temizleme (Basit threshold)
            datas = img.getdata()
            new_data = []
            
            # İlk piksel beyaz mı? Kontrol et (Basit heuristic)
            first_pixel = datas[0]
            is_white_bg = first_pixel[0] > 240 and first_pixel[1] > 240 and first_pixel[2] > 240
            
            if is_white_bg:
                for item in datas:
                    # Beyaza yakın pikselleri transparan yap (Threshold: 240)
                    if item[0] > 240 and item[1] > 240 and item[2] > 240:
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append(item)
                img.putdata(new_data)
            
            # 1. Transparan boşlukları kırp (Trim)
            # Alpha kanalını kullanarak bbox bul
            alpha = img.split()[-1]
            bbox = alpha.getbbox()
            
            if bbox:
                img = img.crop(bbox)
            
            # 2. Devasa boyutları engelle (Opsiyonel optimizasyon)
            if img.width > 500 or img.height > 500:
                img.thumbnail((500, 500), Image.Resampling.LANCZOS)
                
            img.save(image_path, 'PNG')
            return True
        except Exception as e:
            print(f"⚠️ Logo işleme hatası: {e}")
            return False

    def search_wikimedia_logo(team_name, output_path):
        """Wikimedia Commons üzerinden logo ara ve indir"""
        try:
            url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query", "format": "json", "generator": "search",
                "gsrnamespace": "6", "gsrsearch": f"{team_name} logo filetype:png",
                "gsrlimit": 1, "prop": "imageinfo", "iiprop": "url"
            }
            headers = {'User-Agent': 'MacBot/1.0'}
            res = requests.get(url, params=params, headers=headers, timeout=10)
            data = res.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id in pages:
                image_info = pages[page_id].get("imageinfo", [])
                if image_info:
                    image_url = image_info[0].get("url")
                    if image_url:
                        img_res = requests.get(image_url, headers=headers, timeout=10)
                        if img_res.status_code == 200:
                            with open(output_path, 'wb') as f:
                                f.write(img_res.content)
                            print(f"✅ Logo Wikimedia'dan indirildi: {team_name}")
                            return True
            return False
        except: return False

    def download_team_logo(team_name, output_path):
        """TheSportsDB API üzerinden logo indir"""
        try:
            search_url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={team_name}"
            response = requests.get(search_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('teams'):
                    logo_url = data['teams'][0].get('strBadge') or data['teams'][0].get('strTeamBadge')
                    if logo_url:
                        logo_res = requests.get(logo_url, timeout=10)
                        if logo_res.status_code == 200:
                            with open(output_path, 'wb') as f:
                                f.write(logo_res.content)
                            print(f"✅ Logo API'den indirildi: {team_name}")
                            return True
            return False
        except: return False

    def search_tr_wikipedia_logo(team_name, output_path):
        """Wikipedia (TR) üzerinden logo ara"""
        try:
            formatted_name = team_name.replace(" ", "_")
            url = f"https://tr.wikipedia.org/wiki/{formatted_name}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                import re
                img_match = re.search(r'<img[^>]+src="([^"]+\.(?:png|svg|jpg|jpeg))"', res.text, re.IGNORECASE)
                if img_match:
                    img_url = img_match.group(1)
                    if img_url.startswith("//"): img_url = "https:" + img_url
                    img_res = requests.get(img_url, headers=headers, timeout=10)
                    if img_res.status_code == 200:
                        with open(output_path, 'wb') as f:
                            f.write(img_res.content)
                        print(f"✅ Logo Wikipedia'dan indirildi: {team_name}")
                        return True
            return False
        except: return False

    def get_local_logo(team_name, target_path):
        """Yerel klasörde logo ara (Tam ve Bulanık) - PNG ve WEBP destekli"""
        
        def try_convert_and_use(source_path, dest_path):
            try:
                # Eğer kaynak webp ise veya farklıysa açıp png olarak kaydet
                img = Image.open(source_path).convert("RGBA")
                img.save(dest_path, "PNG")
                resize_and_mask_logo(dest_path)
                return True
            except Exception as e:
                print(f"⚠️ Dönüştürme hatası ({source_path}): {e}")
                return False

        # 1. Tam Eşleşme (PNG ve WEBP)
        possible_names = [
            f"{team_name}.png", f"{safe_filename(team_name)}.png", f"{team_name.replace(' ', '_')}.png",
            f"{team_name}.webp", f"{safe_filename(team_name)}.webp", f"{team_name.replace(' ', '_')}.webp"
        ]
        
        for pname in possible_names:
            local_path = os.path.join(LOGOS_DIR, pname)
            if os.path.exists(local_path) and os.path.getsize(local_path) > 100:
                # Bulundu!
                if try_convert_and_use(local_path, target_path):
                    return True, "Tam"
        
        # 2. Bulanık Eşleşme (PNG ve WEBP)
        try:
            t_clean = "".join(c for c in team_name.lower() if c.isalnum())
            for f in os.listdir(LOGOS_DIR):
                valid_exts = (".png", ".webp")
                if not f.lower().endswith(valid_exts): continue
                
                # Dosya adını temizle (uzantısız)
                base_name = f.rsplit(".", 1)[0]
                if base_name.lower().endswith(".svg"): base_name = base_name.rsplit(".", 1)[0]
                
                f_clean = "".join(c for c in base_name.lower() if c.isalnum())
                
                if t_clean == f_clean or t_clean in f_clean or f_clean in t_clean:
                    local_path = os.path.join(LOGOS_DIR, f)
                    if try_convert_and_use(local_path, target_path):
                         return True, f"Bulanık ({f})"
        except: pass
        return False, None

    def download_from_url(url, path, name):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                with open(path, 'wb') as f: f.write(res.content)
                resize_and_mask_logo(path)
                print(f"✅ Logo URL'den indirildi: {name}")
                return True
        except: return False

    t1_safe = safe_filename(team1)
    t2_safe = safe_filename(team2)
    path1 = os.path.join(LOGOS_DIR, f"{t1_safe}.png")
    path2 = os.path.join(LOGOS_DIR, f"{t2_safe}.png")

    # --- YENİ EKLENTİ: AGRESİF LOGO ARAMA (DuckDuckGo Images) ---
    def aggressive_image_search(team_name, save_path):
        """
        Placeholder yerine interneti didik didik edip logo bulur.
        "Sike sike o görsel bulunacak" modudur.
        """
        print(f"🕵️‍♂️ '{team_name}' logosu için derin arama başlatılıyor...")
        
        # 1. Önce Wikipedia/Wikimedia Tekrar Deneyelim (Farklı Varyasyonlarla)
        # Bazen "FC" eklemek veya çıkarmak işe yarar
        variations = [team_name, team_name + " FC", team_name.replace(" FC", "").replace("SK", "").strip()]
        for v in variations:
            if search_wikimedia_logo(v, save_path): return True

        # 2. DuckDuckGo (DDGS)
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            try:
                # Fallback implementation if package name changed?
                # User env seems to have it but warns about renaming. 
                # We assume standard import works despite warning.
                pass
            except:
                print("⚠️ DuckDuckGo modülü yüklenemedi.")
                return False

        import time
        import random

        queries = [
            f"{team_name} logo png transparent",
            f"{team_name} football club logo",
            f"{team_name} crest png",
            f"{team_name} logo",
            f"{team_name} arması"
        ]

        try:
            with DDGS() as ddgs:
                for q in queries:
                    print(f"   🔎 Deneniyor: '{q}'")
                    try:
                        # DDG Images search
                        results = list(ddgs.images(q, max_results=3)) 
                        
                        for r in results:
                            img_url = r.get('image')
                            if not img_url: continue
                            
                            try:
                                headers = {
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
                                }
                                res = requests.get(img_url, headers=headers, timeout=5)
                                if res.status_code == 200:
                                    from io import BytesIO
                                    test_img = Image.open(BytesIO(res.content))
                                    test_img.verify() 
                                    
                                    with open(save_path, 'wb') as f:
                                        f.write(res.content)
                                    
                                    print(f"✅ BULUNDU (Deep Search): {team_name} -> {img_url}")
                                    resize_and_mask_logo(save_path)
                                    return True
                            except: continue
                        
                        # Wait between queries to avoid Rate Limit
                        time.sleep(random.uniform(2.0, 4.0))
                        
                    except Exception as e:
                        err_str = str(e).lower()
                        if "ratelimit" in err_str or "403" in err_str:
                            print("⚠️ DuckDuckGo Rate Limit! (Biraz bekleniyor...)")
                            time.sleep(5)
                            continue
                        print(f"⚠️ Arama hatası ({q}): {e}")
                        
        except Exception as e:
            print(f"⚠️ Derin arama başlatılamadı: {e}")
            
        print(f"❌ '{team_name}' için internette bile düzgün logo bulunamadı!")
        return False

    # Team 1 İşlemi
    success1 = False
    
    # 1. Öncelik: API URL'si (Varsa ve çalışırsa kesinlikle bunu kullan)
    if url1:
        print(f"⬇️  API'den logo indiriliyor: {team1}")
        if download_from_url(url1, path1, team1):
            success1 = True

    # 2. Öncelik: Yerel Dosya (Sadece API başarısızsa veya URL yoksa)
    if not success1 and os.path.exists(path1) and os.path.getsize(path1) > 1000:
        print(f"✅ Logo zaten mevcut: {team1}")
        resize_and_mask_logo(path1)
        success1 = True
    
    if not success1:
        found, mode = get_local_logo(team1, path1)
        if found:
            print(f"✅ Logo yerel klasörden bulundu ({mode}): {team1}")
            success1 = True

    if not success1:
        if download_team_logo(team1, path1): success1 = True
        elif search_wikimedia_logo(team1, path1): success1 = True
        elif search_tr_wikipedia_logo(team1, path1): success1 = True
        else:
            try:
                cli_url = sports_cli.get_team_logo_url(team1)
                if cli_url and download_from_url(cli_url, path1, team1): success1 = True
            except: pass
            
        if not success1:
            # Placeholder YOK! Aggressive Search VAR!
            if aggressive_image_search(team1, path1):
                success1 = True
            else:
                print(f"💀 KRİTİK: {team1} logosu hiçbir yerde yok. Acil durum görseli oluşturuluyor.")
                img = Image.new('RGBA', (500, 500), color=(255, 0, 0, 255))
                d = ImageDraw.Draw(img)
                d.text((50, 250), f"{team1}\nLOGO BULUNAMADI", fill=(255, 255, 255))
                img.save(path1, "PNG")

    # Team 2 İşlemi
    success2 = False
    
    # 1. Öncelik: API URL'si
    if url2:
        print(f"⬇️  API'den logo indiriliyor: {team2}")
        if download_from_url(url2, path2, team2):
            success2 = True
            
    # 2. Öncelik: Yerel Dosya
    if not success2 and os.path.exists(path2) and os.path.getsize(path2) > 1000:
        print(f"✅ Logo zaten mevcut: {team2}")
        resize_and_mask_logo(path2)
        success2 = True
    
    if not success2:
        found, mode = get_local_logo(team2, path2)
        if found:
            print(f"✅ Logo yerel klasörden bulundu ({mode}): {team2}")
            success2 = True

    if not success2:
        if download_team_logo(team2, path2): success2 = True
        elif search_wikimedia_logo(team2, path2): success2 = True
        elif search_tr_wikipedia_logo(team2, path2): success2 = True
        else:
            try:
                cli_url = sports_cli.get_team_logo_url(team2)
                if cli_url and download_from_url(cli_url, path2, team2): success2 = True
            except: pass
            
        if not success2:
             # Placeholder YOK! Aggressive Search VAR!
            if aggressive_image_search(team2, path2):
                success2 = True
            else:
                print(f"💀 KRİTİK: {team2} logosu hiçbir yerde yok. Acil durum görseli oluşturuluyor.")
                img = Image.new('RGBA', (500, 500), color=(255, 0, 0, 255))
                d = ImageDraw.Draw(img)
                d.text((50, 250), f"{team2}\nLOGO BULUNAMADI", fill=(255, 255, 255))
                img.save(path2, "PNG")

    return path1, path2


def create_output_filename(team1, team2, index=1):
    """C. Çıktı Dosya Adı Hazırlama - Sıralı numaralandırma"""
    return f"mac-{index}.png"

def trigger_photoshop_for_match(match_data, psd_filename="Maclar.psd", is_basketball=False):
    """C. ExtendScript Tetikleme ve Veri Aktarımı"""
    
    # 0. PSD Dosyası Kontrolü
    psd_full_path = os.path.join(BASE_DIR, psd_filename)
    if not os.path.exists(psd_full_path):
        print(f"❌ HATA: '{psd_filename}' dosyası bulunamadı!")
        print(f"Konum: {psd_full_path}")
        return False

    # 1. Veriyi JSON formatına hazırla
    js_data = {
        "psdPath": psd_full_path,
        "outputDir": OUTPUT_DIR,
        "outputFileName": match_data["output_filename"],
        "evSahibi": match_data["ev_sahibi"],
        "deplasman": match_data["deplasman"],
        "saat": match_data["saat"],
        "gun": match_data["gun"],
        "oran1": match_data["oran_1"],
        "oranX": match_data["oran_x"],
        "oran2": match_data["oran_2"],
        "logo1": match_data["logo1"],
        "logo2": match_data["logo2"],
        "highlightOdds": match_data.get("hide_odds", False), # Legacy support might expect this logic differently, but using hideOdds consistent with new JSX
        "hideOdds": match_data.get("hide_odds", False),
        "isBasketball": is_basketball
    }
    
    # Python dict -> JSON string
    json_str = json.dumps(js_data, ensure_ascii=False)
    
    # 2. JSX dosyasını oluştur
    script_content = JSX_TEMPLATE.replace("{{DATA_JSON}}", json_str)
    
    with open(JSX_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(script_content)
    
    # 3. Photoshop'u Tetikle (open komutu ile - daha güvenilir)
    print(f"\n🎨 Photoshop tetikleniyor: {match_data['ev_sahibi']} vs {match_data['deplasman']}")
    
    try:
        # 'open' komutu dosyayı ilgili uygulama ile açar (Photoshop JSX'i çalıştırır)
        # Bu yöntem AppleScript'in izin sorunlarını ve donmalarını aşar.
        cmd = ["open", "-a", "Adobe Photoshop 2026", JSX_OUTPUT_PATH]
        
        # Debugging prints
        print(f"JSX Dosyası: {JSX_OUTPUT_PATH}")
        print("Çalıştırılan Komut: " + " ".join(cmd))
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ Komut başarıyla gönderildi (Dosya açıldı).")
            # Print stdout if there is any output from the script (e.g. log messages)
            if result.stdout.strip():
                print(f"Photoshop Yanıtı: {result.stdout}")
            return True
        else:
            print("⚠️ Photoshop ile iletişimde sorun oluştu.")
            error_msg = result.stderr
            print(f"Hata Detayı: {error_msg}")
            
            if "-1743" in error_msg:
                print("\n🔐 GÜVENLİK HATASI: macOS, Terminal'e Photoshop'u kontrol etme izni vermiyor.")
                print("Çözüm için:")
                print("1. Sistem Ayarları > Gizlilik ve Güvenlik > Otomasyon'a gidin.")
                print("2. 'Terminal' veya kullandığınız IDE altında 'Adobe Photoshop 2026' anahtarını açın.")
                print("3. Eğer listede yoksa, Terminal'den 'tccutil reset AppleEvents' komutunu deneyebilirsiniz.")
            
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ İşlem zaman aşımına uğradı (600+ saniye)")
        return False
    except Exception as e:
        print(f"❌ Beklenmeyen Hata: {e}")
        return False

# =============================================================================
# MAIN FLOW
# =============================================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("PSD OTOMASYON BOTU BAŞLATILIYOR")
    print("="*60 + "\n")
    
    # Kullanıcıya seçenek sun
    print("Veri girişi türünü seçin:")
    print("1. Manuel giriş")
    print("2. Demo veriler (Otomatik 5 örnek maç)")
    print("3. Manuel giriş + Oran Artırma (+0.20)")
    print("4. Basketbol Manuel Giriş (+0.20 Oran Artırma)")
    print("5. maclar.txt dosyasından oku (+0.20 Oran Artırma)")
    
    choice = input("\nSeçiminiz (1/2/3/4/5): ").strip()
    
    # Tarih Ayarı Sorusu
    print("\n------------------------------------------------------------")
    print("❓ Gece Yarısı Maçları (00:00 - 05:59) Tarih Ayarı:")
    print("E:  Önceki Günün Tarihini Yaz (Örn: 10 Ocak 01:00 -> 9 Ocak)")
    print("D:  Takvim Gününü Yaz (Örn: 10 Ocak 01:00 -> 10 Ocak)")
    date_choice = input("Seçiminiz (E/D) [Varsayılan: D]: ").strip().upper()
    subtract_day = (date_choice == "E")
    
    if subtract_day:
        print("✅ Ayarlandı: Gece yarısı maçları bir önceki günün tarihiyle yazılacak.")
    else:
        print("✅ Ayarlandı: Maç tarihleri olduğu gibi yazılacak.")
    print("✅ Ayarlandı: Maç tarihleri olduğu gibi yazılacak.")
    print("------------------------------------------------------------")
    
    # İnteraktif Mod Sorusu
    print("\n------------------------------------------------------------")
    print("❓ Doğrulama Modu:")
    print("Her maç için API'den bulunan tarih/saati onaylamak ister misiniz?")
    print("E:  Evet, her maçta bana sor/onayımı al.")
    print("H:  Hayır, otomatik devam et (Hızlı Mod).")
    interactive_choice = input("Seçiminiz (E/H) [Varsayılan: H]: ").strip().upper()
    interactive_mode = (interactive_choice == "E")
    
    if interactive_mode:
        print("✅ İnteraktif Mod: Her maç için onay istenecek.")
    else:
        print("✅ Otomatik Mod: API verilerine güvenilip devam edilecek.")
    print("------------------------------------------------------------\n")
    
    print("------------------------------------------------------------\n")
    
    # OpenAI / Gemini Key (Gömülü)
    openai_key = "AIzaSyCR1-16foOI5f7r5MkF1DN4ef1zT1ZmNEM"
    print(f"✅ Gemini Modu Aktif (Key Gömülü).")
    print("------------------------------------------------------------\n")

    selected_psd = "Maclar.psd"
    
    if choice == "1":
        matches = get_match_data_from_user(boost_odds=False)
    elif choice == "3":
        matches = get_match_data_from_user(boost_odds=True)
    elif choice == "4":
        print("\n🏀 BASKETBOL MODU AKTİF: Beraberlik oranı otomatik olarak boş bırakılacak.")
        matches = get_match_data_from_user(boost_odds=True)
        selected_psd = "basketbol.psd"
    elif choice == "5":
        print("\n📂 'maclar.txt' dosyasından okunuyor...")
        txt_path = os.path.join(BASE_DIR, "maclar.txt")
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Simulate user input by feeding lines into a processing logic
            print("⚡ Dosyadaki maçlar +0.20 Oran Artırma ile işleniyor.\n")
            # Reuse logic by temporary mocking input or just parsing directly.
            # Parsing directly is cleaner.
            # Improved Parsing Logic: Supports both single-line and multi-line blocks
            matches = []
            raw_lines = [line.strip() for line in lines if line.strip()]
            
            i = 0
            while i < len(raw_lines):
                line = raw_lines[i]
                found_match = False
                
                # 1. Try to parse as single-line match with optional Date/Time
                separators = [" vs. ", " vs ", " - ", " / ", " VS. ", " VS ", " Vs. ", " Vs ", " v "]
                for sep in separators:
                    if sep in line:
                        parts = line.split(sep, 1)
                        if len(parts) == 2:
                            ev_sahibi = parts[0].strip()
                            remaining = parts[1].strip().split()
                            
                            # Akıllı Oran Bulucu (Smart Odds Parser)
                            # Sondan başa değil, pattern tarayarak bulalım.
                            # Football: [Float, Float, Float]
                            # Basketball: [Float, Float]
                            
                            odds_found = False
                            
                            # Futbol (3 Oran) Tarama
                            for k in range(len(remaining) - 2):
                                try:
                                    o1 = float(remaining[k])
                                    ox = float(remaining[k+1])
                                    o2 = float(remaining[k+2])
                                    
                                    # Bulundu!
                                    # Deplasman ismini oluşturmadan önce, oranlardan önceki son kelimeye bak
                                    # Eğer saat formatındaysa (20:00), onu al ve takımdan çıkar.
                                    
                                    pre_odds_tokens = remaining[:k]
                                    dt_from_prev = None
                                    
                                    import re
                                    import re
                                    # Geriye doğru tarama (Backwards scan)
                                    # Oranlardan hemen önceki tokenlar Tarih/Saat olabilir
                                    # Örn: Freiburg 22:30 14 OCAK 1.79...
                                    
                                    found_datetime_parts = []
                                    while pre_odds_tokens:
                                        last_t = pre_odds_tokens[-1]
                                        is_dt = False
                                        
                                        # Saat kontrolü
                                        if re.match(r'^\d{1,2}[:.]\d{2}$', last_t): 
                                            is_dt = True
                                        
                                        # Ay ismi kontrolü
                                        elif re.search(r'(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', last_t.lower()):
                                            is_dt = True
                                            
                                        # Gün (sayı) ve Yıl kontrolü
                                        elif last_t.isdigit():
                                            if len(last_t) == 4 or int(last_t) <= 31:
                                                is_dt = True
                                        
                                        if is_dt:
                                            found_datetime_parts.insert(0, pre_odds_tokens.pop())
                                        else:
                                            # Tarih/Saat değilse, muhtemelen takım isminin son parçasıdır.
                                            # Ancak bazen "14 OCAK" gibi arada boşluk olunca split ayrı token yapar.
                                            # Bu döngü contiguous (bitişik) tarih bloğunu alır.
                                            break
                                            
                                    dt_from_prev = " ".join(found_datetime_parts) if found_datetime_parts else None
                                    
                                    deplasman = " ".join(pre_odds_tokens)
                                    
                                    # Oranlardan sonra kalan kısım TARİH/SAAT olabilir
                                    dt_from_post = " ".join(remaining[k+3:])
                                    
                                    # Hangisi varsa onu kullan (Öncelik: Explicit yazılan)
                                    final_dt = dt_from_prev if dt_from_prev else (dt_from_post if dt_from_post.strip() else None)
                                    
                                    matches.append({
                                        "ev_sahibi": ev_sahibi,
                                        "deplasman": deplasman,
                                        "oran_1": f"{o1 + 0.20:.2f}",
                                        "oran_x": f"{ox + 0.20:.2f}",
                                        "oran_2": f"{o2 + 0.20:.2f}",
                                        "manual_datetime": final_dt
                                    })
                                    found_match = True
                                    print(f"✅ Eklendi (BOOST +0.20): {ev_sahibi} vs {deplasman}" + (f" 🕒 {final_dt}" if final_dt else ""))
                                    odds_found = True
                                    break
                                except: continue
                            
                            if odds_found: break

                            # Basketbol (2 Oran) Tarama
                            if not odds_found:
                                for k in range(len(remaining) - 1):
                                    try:
                                        o1 = float(remaining[k])
                                        o2 = float(remaining[k+1])
                                        
                                        # Deplasman ve Saat Ayrıştırma (Önceki kelime kontrolü)
                                        pre_odds_tokens = remaining[:k]
                                        dt_from_prev = None
                                        
                                        import re
                                        if pre_odds_tokens and re.match(r'^\d{1,2}[:.]\d{2}$', pre_odds_tokens[-1]):
                                            dt_from_prev = pre_odds_tokens.pop()
                                            dt_from_prev = dt_from_prev.replace(".", ":")
                                        
                                        deplasman = " ".join(pre_odds_tokens)
                                        dt_from_post = " ".join(remaining[k+2:])
                                        
                                        final_dt = dt_from_prev if dt_from_prev else (dt_from_post if dt_from_post.strip() else None)
                                        
                                        matches.append({
                                            "ev_sahibi": ev_sahibi,
                                            "deplasman": deplasman,
                                            "oran_1": f"{o1 + 0.20:.2f}",
                                            "oran_x": "",
                                            "oran_2": f"{o2 + 0.20:.2f}",
                                            "manual_datetime": final_dt
                                        })
                                        found_match = True
                                        print(f"🏀 Basketbol Eklendi: {ev_sahibi} vs {deplasman}" + (f" 🕒 {final_dt}" if final_dt else ""))
                                        odds_found = True
                                        break
                                    except: continue
                            
                            # C. No Odds (Single Line) Tarama
                            # Eğer oran bulamadıysak, geri kalan kısmın tamamını Deplasman + Tarih olarak al
                            # Örnek: Freiburg 22:30 14 OCAK
                            if not odds_found:
                                try:
                                    # Sondan başa doğru tarih/saat parçalarını ayıkla
                                    # Basit heuristic: Tarih/Saat formatına uyanları topla
                                    date_tokens = []
                                    team_tokens = list(remaining) # Copy
                                    
                                    while team_tokens:
                                        last_token = team_tokens[-1]
                                        # Basit kontrol: Sayı içeriyor mu veya ay ismi mi?
                                        is_time = ":" in last_token or "." in last_token # 22:30, 22.30
                                        is_date_part = False
                                        
                                        import re
                                        # Ay isimleri kontrolü
                                        months_regex = r'(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)'
                                        if re.search(months_regex, last_token.lower()):
                                            is_date_part = True
                                        elif last_token.isdigit() and int(last_token) < 32: # Gün
                                            is_date_part = True
                                        elif re.match(r'^\d{4}$', last_token): # Yıl
                                            is_date_part = True
                                            
                                        if is_time or is_date_part:
                                            date_tokens.insert(0, team_tokens.pop())
                                        else:
                                            break
                                    
                                    if team_tokens: # En az bir kelime takım adı kalmalı
                                        deplasman = " ".join(team_tokens)
                                        manual_dt = " ".join(date_tokens) if date_tokens else None
                                        
                                        matches.append({
                                            "ev_sahibi": ev_sahibi,
                                            "deplasman": deplasman,
                                            "oran_1": "",
                                            "oran_x": "",
                                            "oran_2": "",
                                            "manual_datetime": manual_dt,
                                            "hide_odds": True
                                        })
                                        found_match = True
                                        print(f"✅ Eklendi (Oransız): {ev_sahibi} vs {deplasman}" + (f" 🕒 {manual_dt}" if manual_dt else ""))
                                        break # Stop looking for separators
                                except Exception as e:
                                    print(e)
                                    pass

                if found_match:
                    i += 1
                    continue
                    
                # 2. Try to parse as multi-line block (Standard 5 lines or No Odds 3-5 lines)
                if i + 2 < len(raw_lines):
                    # A. Check for "No Odds" indicator at line 3 (index i+2)
                    first_odd_line = raw_lines[i+2].lower().strip()
                    if first_odd_line in ["yok", "-", "0", "oran_yok", "no_odds"]:
                        consumed = 3
                        # Dynamically check for 4th and 5th lines being placeholders too
                        # Check line 4
                        if i + 3 < len(raw_lines):
                            l4 = raw_lines[i+3].lower().strip()
                            is_placeholder = l4 in ["yok", "-", "0", "oran_yok", "no_odds"]
                            if is_placeholder:
                                consumed += 1
                                # Check line 5 (only if line 4 was placeholder)
                                if i + 4 < len(raw_lines):
                                    l5 = raw_lines[i+4].lower().strip()
                                    is_placeholder_5 = l5 in ["yok", "-", "0", "oran_yok", "no_odds"]
                                    if is_placeholder_5:
                                        consumed += 1
                        
                        matches.append({
                            "ev_sahibi": raw_lines[i],
                            "deplasman": raw_lines[i+1],
                            "oran_1": "",
                            "oran_x": "",
                            "oran_2": "",
                            "hide_odds": True
                        })
                        print(f"✅ Bloktan Eklendi (Oransız): {raw_lines[i]} vs {raw_lines[i+1]}")
                        # Check for Optional Date/Time line (Tarih: ...)
                        if i + consumed < len(raw_lines):
                            next_line = raw_lines[i + consumed].strip()
                            if next_line.lower().startswith(("tarih:", "date:", "saat:", "time:")):
                                manual_dt = next_line.split(":", 1)[1].strip()
                                last_match = matches[-1]
                                last_match["manual_datetime"] = manual_dt
                                print(f"📅 Manuel Tarih Bulundu: {manual_dt}")
                                consumed += 1
                        
                        i += consumed
                        continue

                    # B. Check for Standard 5 Lines (Floats)
                    if i + 4 < len(raw_lines):
                        try:
                            o1 = float(raw_lines[i+2])
                            ox = float(raw_lines[i+3])
                            o2 = float(raw_lines[i+4])
                            matches.append({
                                "ev_sahibi": raw_lines[i],
                                "deplasman": raw_lines[i+1],
                                "oran_1": f"{o1 + 0.20:.2f}",
                                "oran_x": f"{ox + 0.20:.2f}",
                                "oran_2": f"{o2 + 0.20:.2f}",
                                "hide_odds": False
                            })
                            print(f"✅ Bloktan Eklendi (BOOST +0.20): {raw_lines[i]} vs {raw_lines[i+1]}")
                            
                            # Check for Optional Date/Time line
                            if i + 5 < len(raw_lines):
                                next_line = raw_lines[i+5].strip()
                                if next_line.lower().startswith(("tarih:", "date:", "saat:", "time:")):
                                    manual_dt = next_line.split(":", 1)[1].strip()
                                    matches[-1]["manual_datetime"] = manual_dt
                                    print(f"📅 Manuel Tarih Bulundu: {manual_dt}")
                                    i += 6
                                else:
                                    i += 5
                            else:
                                i += 5
                            continue
                        except: pass

                    
                # 3. Try to parse as multi-line block (4 lines: T1, T2, O1, O2 - Basketball)
                if i + 3 < len(raw_lines):
                    try:
                        o1 = float(raw_lines[i+2])
                        o2 = float(raw_lines[i+3])
                        matches.append({
                            "ev_sahibi": raw_lines[i],
                            "deplasman": raw_lines[i+1],
                            "oran_1": f"{o1 + 0.20:.2f}",
                            "oran_x": "",
                            "oran_2": f"{o2 + 0.20:.2f}",
                            "hide_odds": False
                        })
                        print(f"🏀 Bloktan Eklendi (Basketbol): {raw_lines[i]} vs {raw_lines[i+1]}")
                        i += 4
                        continue
                    except: pass
                
                # If everything fails
                print(f"⚠️ Format Hatası (Satır Atlandı veya Blok Geçersiz): {line}")
                i += 1
            
            for m in matches:
                print(f"✅ Hazır: {m['ev_sahibi']} vs {m['deplasman']} ({m['oran_1']} {m['oran_x']} {m['oran_2']})")

            
            if not matches:
                print("⚠️ Dosyada geçerli maç bulunamadı.")
                import sys; sys.exit()
        else:
            print(f"❌ '{txt_path}' bulunamadı!")
            print("Lütfen takımları alt alta yazdığınız 'maclar.txt' dosyasını oluşturun.")
            import sys; sys.exit()

    else:
        print("\n📋 Demo verileri kullanılıyor...\n")
        matches = get_demo_match_data()
    
    # Her maç için işlem yap
    for idx, match in enumerate(matches, 1):
        print(f"\n{'='*60}")
        print(f"MAÇ {idx}/{len(matches)}: {match['ev_sahibi']} vs {match['deplasman']}")
        print(f"{'='*60}")
        
        if match.get("manual_datetime"):
             # Manuel tarih varsa onu kullan
             mdt = match["manual_datetime"].strip()
             

             # SAAT Format Kontrolü (HH:MM)
             # Önce tüm string içinde saat formatı (HH:MM veya HH.MM) ara
             import re
             # \b ensures word boundary, but note time can be at end of string
             time_matches = re.findall(r'\b(\d{1,2}[:.]\d{2})\b', mdt)
             
             found_time = None
             if time_matches:
                 # Filter out things that look like years (2025) - but regex checks for : or .
                 found_time = time_matches[-1].replace('.', ':')
             
             if found_time:
                 saat = found_time
                 # Tarih kısmını ayıkla: Saati sil
                 # mdt'yi geçici olarak temizle
                 clean_mdt = mdt.replace(time_matches[-1], "").strip()
                 clean_mdt = re.sub(r'\s+', ' ', clean_mdt)
                 gun = clean_mdt
                 
                 if not gun: # Sadece 22:30 yazıldıysa
                     import datetime
                     tr_days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
                     tr_months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
                     now = datetime.datetime.now()
                     gun = f"{tr_days[now.weekday()]}, {now.day} {tr_months[now.month-1]}"
                     
             else:
                 # Saat bulunamadı, tamamı tarih
                 gun = mdt
                 saat = ""
                 
             print(f"👉 Manuel Tarih Kullanılıyor: {gun} {saat}")
             
             # Eğer saat boşsa, API'den saati bulmaya çalış
             # DEBUG PRRINTS
             print(f"DEBUG: Saat kontrolü. Şu anki saat değeri: '{saat}' (Tipi: {type(saat)})")
             if not saat:
                print(f"ℹ️  Manuel saat belirtilmedi (saat boş), API'den aranıyor...")
                api_saat, api_gun, _, _, _, _ = scrape_match_time_sportsdb(match["ev_sahibi"], match["deplasman"], subtract_day_for_night=subtract_day)
                 
                # Fallback to AI if API fails for time
                if not api_saat and openai_key:
                    print("ℹ️  Standart API'de saat bulunamadı, AI deneniyor...")
                    api_saat, _ = smart_match_search(match["ev_sahibi"], match["deplasman"], openai_key)

                print(f"DEBUG: API (veya AI) Sonucu -> Saat: {api_saat}, Gün: {api_gun}")
                
                if api_saat:
                    saat = api_saat
                    print(f"✅ Saat API/AI'den eklendi: {saat}")
                else:
                    print("⚠️ Saat API'den bulunamadı.")

        else:
             # Saat ve gün - TheSportsDB (sports_cli.py)
             # NOT: API'den gelen home_badge ve away_badge KULLANILMAZ
             saat, gun, api_logo1, api_logo2, canon1, canon2 = scrape_match_time_sportsdb(match["ev_sahibi"], match["deplasman"], subtract_day_for_night=subtract_day)
             
             # API'den gelen verileri kullan
             if canon1 and canon2:
                 # Doğru isimlerle güncelle (Opsiyonel: Eğer çok farklıysa kullanıcıyı uyarabiliriz ama oto-düzeltme premium hissettirir)
                 print(f"🔄 Takım isimleri güncelleniyor: {match['ev_sahibi']} -> {canon1} | {match['deplasman']} -> {canon2}")
                 match["ev_sahibi"] = canon1
                 match["deplasman"] = canon2
                 
             if api_logo1: match["api_logo1"] = api_logo1
             if api_logo2: match["api_logo2"] = api_logo2

             # TheSportsDB bulamazsa ve Key varsa -> Smart Search
             if (saat is None or gun is None) and openai_key:
                 saat_ai, gun_ai = smart_match_search(match["ev_sahibi"], match["deplasman"], openai_key)
                 if saat_ai and gun_ai:
                     saat = saat_ai
                     gun = gun_ai
        
        if (saat is None or gun is None) and not match.get("manual_datetime"):
            print(f"⚠️ Kaynaklarda saat bulunamadı. Otomatik devam ediliyor (Varsayılan değerler).")
            
            # Otomatik Varsayılan Atama (User Interaction Yok!)
            import datetime
            tr_days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
            tr_months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
            
            now = datetime.datetime.now()
            gun = f"{tr_days[now.weekday()]}, {now.day} {tr_months[now.month-1]}"
            saat = "20:00" 
            
            print(f"👉 Atanan: {gun} {saat}")


            # Apply to All Check
            if idx < len(matches):
                if interactive_mode:
                    apply_all = input("   👉 Bu tarihi/saati kalan taranmamış maçlar için varsayılan yap? (e/h): ").strip().lower()
                else:
                    apply_all = 'e'
                    print(f"   ℹ️  Otomatik Mod: {gun} {saat} kalan maçlara uygulandı.")

                if apply_all == 'e':
                    for rem_match in matches[idx:]:
                        if not rem_match.get("saat"): # Sadece henüz bulunamamış olanlara uygula
                            rem_match["saat"] = saat
                            rem_match["gun"] = gun
                            rem_match["manual_datetime"] = f"{gun} {saat}" # Flag as manually set
                    print(f"✅ Kalan tüm maçlara uygulandı: {gun} {saat}")
        
        # =========================================================================
        # 📌 TAKIM İSMİ VE LOGO DOĞRULAMA (HER DURUMDA)
        # =========================================================================
        # Eğer yukarıdaki adımlarda (örneğin manuel tarih girildiği için) API'den 
        # takım bilgileri çekilmediyse, şimdi sadece isim ve logo için çekelim.
        if "api_logo1" not in match and "api_logo2" not in match:
             print(f"ℹ️  Takım isimleri ve logoları için API kontrolü yapılıyor...")
             try:
                 # Ev Sahibi
                 t1_info = sports_cli.get_team_info(match["ev_sahibi"])
                 if t1_info[0]: 
                     print(f"   ✅ Ev Sahibi Güncellendi: {match['ev_sahibi']} -> {t1_info[0]}")
                     match["ev_sahibi"] = t1_info[0]
                     if t1_info[1]: match["api_logo1"] = t1_info[1]
                 
                 # Deplasman
                 t2_info = sports_cli.get_team_info(match["deplasman"])
                 if t2_info[0]:
                     print(f"   ✅ Deplasman Güncellendi: {match['deplasman']} -> {t2_info[0]}")
                     match["deplasman"] = t2_info[0]
                     if t2_info[1]: match["api_logo2"] = t2_info[1]
             except Exception as e:
                 print(f"⚠️ API Hatası: {e}")

        # --- İNTERAKTİF DOĞRULAMA MODU ---
        if interactive_mode:
             print(f"\n🔍 TEYİT LÜTFEN:")
             print(f"👉 Maç: {match['ev_sahibi']} vs {match['deplasman']}")
             print(f"👉 Bulunan Zaman: {gun} {saat}")
             
             conf = input("✅ Onaylıyor musunuz? (E/h - Düzenlemek için 'd'): ").strip().lower()
             
             if conf == 'd':
                 print("✏️  Yeni bilgileri girin:")
                 new_gun = input(f"   Gün (Enter: {gun}): ").strip()
                 new_saat = input(f"   Saat (Enter: {saat}): ").strip()
                 
                 if new_gun: gun = new_gun
                 if new_saat: saat = new_saat
                 
                 print(f"✅ Güncellendi: {gun} {saat}")
                 
             elif conf == 'h':
                 print("❌ Maç atlanıyor (Kullanıcı iptali).")
                 continue

        match["saat"] = saat
        match["gun"] = gun
        
        # Logo indirme - API URL'leri varsa öncelikli kullan
        logo1, logo2 = download_logos(match["ev_sahibi"], match["deplasman"], url1=match.get("api_logo1"), url2=match.get("api_logo2"))
        match["logo1"] = logo1
        match["logo2"] = logo2
        
        # Çıktı dosya adı (sıralı numara ile)
        match["output_filename"] = create_output_filename(match["ev_sahibi"], match["deplasman"], idx)
        
        # Photoshop'u tetikle
        is_basketball_mode = (selected_psd == "basketbol.psd")
        
        # Eğer oran yoksa ve basketbol değilse Maclar1.psd kullan - İPTAL EDİLDİ (Kullanıcı Talebi: Her zaman Maclar.psd)
        current_psd = selected_psd
        # if match.get("hide_odds") and not is_basketball_mode:
        #      current_psd = "Maclar1.psd"
        #      print(f"ℹ️  Oran yok, '{current_psd}' kullanılıyor.")

        success = trigger_photoshop_for_match(match, psd_filename=current_psd, is_basketball=is_basketball_mode)
        
        if success:
            # Photoshop'un işlemi tamamlaması için kısa bekleme
            import time
            # Photoshop'un işlemi tamamlaması için bekleme (open komutu asenkron olduğu için artırıldı)
            import time
            print("⏳ Photoshop'un işlemi tamamlaması bekleniyor (5 sn)...")
            time.sleep(5)
            
            # Kullanıcıya bilgi ver
            print(f"\n📊 Photoshop'ta '{match['output_filename']}' dosyası oluşturuldu.")
            print("✅ JPEG kaydedildi ve PSD kapatıldı.")
            
            # Bir sonraki maça geçmeden önce onay al
            if interactive_mode and idx < len(matches):
                input(f"\n⏸️  Bir sonraki maça geçmek için ENTER'a basın... ({idx}/{len(matches)} tamamlandı)")
        else:
            print("❌ Bu maç için işlem başarısız oldu. Devam ediliyor...")
    
    print("\n" + "="*60)
    print("TÜM MAÇLAR İŞLENDİ!")
    print("="*60 + "\n")

    # Otomatik Sıkıştırma İşlemi
    try:
        import compressor
        print("\n⏳ Görseller sıkıştırılıyor...")
        compressor.compress_and_rename_images(OUTPUT_DIR)
    except ImportError:
        print("⚠️ compressor.py bulunamadı, sıkıştırma atlandı.")
    except Exception as e:
        print(f"⚠️ Sıkıştırma hatası: {e}")
