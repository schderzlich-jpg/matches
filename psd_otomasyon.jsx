

app.displayDialogs = DialogModes.NO; // Disable dialogs for speed
app.preferences.rulerUnits = Units.PIXELS; // Enforce pixels

function main() {
    // Python'dan enjekte edilen veri nesnesi
    var data = {"psdPath": "/Users/eda/Documents/match-automation/Maclar.psd", "outputDir": "/Users/eda/Documents/match-automation/Mac", "outputFileName": "Match_Vitória_vs_Flamengo.png", "evSahibi": "Vitória", "deplasman": "Flamengo", "saat": "03:30", "gun": "11 ŞUBAT", "oran1": "2.15", "oranX": "3.40", "oran2": "3.20", "logo1": "/Users/eda/Documents/match-automation/logos/vitória.png", "logo2": "/Users/eda/Documents/match-automation/logos/flamengo.png", "highlightOdds": false, "hideOdds": false, "isBasketball": false};

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
            var searchName = name.toLowerCase().replace(/\s/g, "");
            var layers = root.layers;
            for (var i = 0; i < layers.length; i++) {
                var layer = layers[i];
                var layerName = layer.name.toLowerCase().replace(/\s/g, "");
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
                updateLog += "OK: " + mainKey + " (" + layer.name + ") -> " + content + "\n";
            }
        } else {
            updateLog += "MISS: " + keys[0] + "\n";
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
