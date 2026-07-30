(function () {
  'use strict';
  var mapData = null;
  var debounceTimer = null;
  var odRecalcTimer = null;
  var lastBeatmapId = null;
  var activeAlgo = 'auto';
  var active7KMode = 'auto';
  var active6KMode = 'rating';
  var activeMods = {};

  function rcLookup(sr, keys, mode) {
    return tierAbbr(getRCTier(sr, keys, mode));
  }

  function lnLookup(sr, keys) {
    return tierAbbr(getLNTier(sr, keys));
  }

  function $(id) { return document.getElementById(id); }

  function estimateSR(srNM, srDT, srHT, rate) {
    if (!srNM) return 0;
    if (Math.abs(rate - 1.0) < 0.001) return srNM;
    if (srDT && srDT > srNM && Math.abs(rate - 1.5) < 0.001) return srDT;
    if (srHT && srHT < srNM && Math.abs(rate - 0.75) < 0.001) return srHT;
    if (rate > 1.0 && srDT && srDT > srNM) {
      // DT range: use exponent derived from DT/NM ratio
      var k = Math.log(srDT / srNM) / Math.log(1.5);
      return srNM * Math.pow(rate, k);
    }
    if (rate < 1.0 && srHT && srHT > 0 && srHT < srNM) {
      // HT range: use exponent derived from HT/NM ratio (slower speeds decay faster)
      var k = Math.log(srNM / srHT) / Math.log(1.0 / 0.75);
      return srNM * Math.pow(rate, k);
    }
    return srNM * rate;
  }

  var _computeSunnyPP = window.computeSunnyPP;

  function computeSunnyPP(sr, accuracy, mods, totalNotes, variety, accScalar, isHO, isIN) {
    if (isHO && mapData && typeof mapData.varietyHO !== 'undefined') variety = mapData.varietyHO;
    if (isHO && mapData && typeof mapData.accScalarHO !== 'undefined') accScalar = mapData.accScalarHO;
    if (isIN && mapData && typeof mapData.varietyIN !== 'undefined') variety = mapData.varietyIN;
    if (isIN && mapData && typeof mapData.accScalarIN !== 'undefined') accScalar = mapData.accScalarIN;
    return _computeSunnyPP(sr, accuracy, mods, totalNotes, variety, accScalar);
  }

  function computeOfficialPP(sr, accuracy, totalNotes, mods) {
    var acc = Math.min(1, Math.max(0, (accuracy || 100) / 100));
    var accFactor = Math.max(0, 5 * acc - 4);
    var lenBonus = 1 + 0.1 * Math.min(1, totalNotes / 1500);
    var mult = 1.0;
    if (mods && mods.includes('NF')) mult *= 0.75;
    if (mods && mods.includes('EZ')) mult *= 0.5;
    var diff = 8.0 * Math.pow(Math.max(sr - 0.15, 0.05), 2.2) * accFactor * lenBonus;
    return diff * mult;
  }

  function formatTime(sec) { if (!sec || sec <= 0) return '--'; var m = Math.floor(sec / 60); var s = Math.floor(sec % 60); return m + ':' + (s < 10 ? '0' : '') + s; }

  // Difficulty constant (定数) from Sunny SR for mania-rating-gui style
  function calcDiffConst(sr) { return sr * 200.0 / 81.0 + 7.0 / 6.0; }

  function calcRating(diffConst, acc) {
    if (acc < 0 || acc > 100) return 0;
    var diffLower = Math.max(diffConst - 3.0, 0);
    if (acc <= 80.0) return 0;
    if (acc <= 93.0) return diffLower * (acc - 80.0) / 13.0;
    if (acc <= 96.0) return (diffConst - diffLower) * (acc - 93.0) / 3.0 + diffLower;
    if (acc <= 98.0) {
      var accXtra = acc - 96.0;
      return 1.5 * accXtra / (3.0 - accXtra / 2.0) + diffConst;
    }
    if (acc <= 99.5) {
      var accXtra2 = (acc - 98.0) / 1.5;
      return 4.0 * accXtra2 / (3.0 - accXtra2) + diffConst + 1.5;
    }
    var accXtra3 = (acc - 99.5) * 2.0;
    return 2.0 * accXtra3 / (3.0 - accXtra3) + diffConst + 3.5;
  }

  // 310-weight accuracy used in mania-rating-gui rating formula
  function getRatingAcc() {
    var p320 = parseInt($('j-320').value) || 0, p300 = parseInt($('j-300').value) || 0;
    var p200 = parseInt($('j-200').value) || 0, p100 = parseInt($('j-100').value) || 0;
    var p50 = parseInt($('j-50').value) || 0, miss = parseInt($('j-0').value) || 0;
    var total = p320 + p300 + p200 + p100 + p50 + miss;
    if (total === 0) return 100;
    return (p320 * 310 + p300 * 300 + p200 * 200 + p100 * 100 + p50 * 50) / (total * 310) * 100;
  }

  function getActiveMods() {
    var mods = [];
    if (activeMods.NF) mods.push('NF');
    if (activeMods.EZ) mods.push('EZ');
    return mods;
  }

  function getInputs() {
    var p320 = parseInt($('j-320').value) || 0, p300 = parseInt($('j-300').value) || 0;
    var p200 = parseInt($('j-200').value) || 0, p100 = parseInt($('j-100').value) || 0;
    var p50 = parseInt($('j-50').value) || 0, miss = parseInt($('j-0').value) || 0;
    var totalJ = p320 + p300 + p200 + p100 + p50 + miss;
    var acc;
    if (totalJ > 0) {
      if (activeMods.SV1) {
        acc = ((p320 + p300) * 300 + p200 * 200 + p100 * 100 + p50 * 50) / (totalJ * 300) * 100;
      } else {
        acc = (p320 * 320 + p300 * 300 + p200 * 200 + p100 * 100 + p50 * 50) / (totalJ * 320) * 100;
      }
    } else {
      acc = 100;
    }

    var rate = parseFloat($('pp-rate').value) || 1.0;
    rate = Math.min(2.0, Math.max(0.5, rate));
    return { acc: acc, rate: rate };
  }

  function updateCol(pref, sr, sunnyPP, officialPP, sunnyPP100, tier, osuSR) {
    var srEl = $(pref + '-sr'), tierEl = $(pref + '-tier');
    var ppEl = $(pref + '-pp'), ppOsuEl = $(pref + '-pp-osu'), badgeEl = $(pref + '-diff-badge');

    srEl.textContent = (sr || 0).toFixed(2) + '\u2605';
    srEl.style.color = srColor(sr);
    if (tierEl) {
      if (tier) {
        tierEl.textContent = tier;
        tierEl.style.color = srColor(sr);
        tierEl.style.display = '';
      } else {
        tierEl.style.display = 'none';
      }
    }

    ppEl.innerHTML = '<span style="color:' + ppColor(sunnyPP.pp) + ';font-weight:700;">' + formatPP(sunnyPP.pp) + ' / ' + formatPP(sunnyPP100.pp) + '</span>pp';
    ppOsuEl.innerHTML = '<span style="color:' + ppColor(officialPP) + ';font-weight:700;">' + formatPP(officialPP) + '</span>pp';
    if (osuSR) {
      ppOsuEl.innerHTML += ' <span style="font-size:8px;color:#555;">' + osuSR.toFixed(2) + '\u2605</span>';
    }

    var delta = sunnyPP.pp - officialPP;
    var deltaStr = delta >= 0 ? '+' + formatPP(delta) : formatPP(delta);
    badgeEl.textContent = deltaStr + 'pp';
    badgeEl.style.color = delta >= 0 ? '#6bcb77' : '#ff6b6b';
  }

  function getAlgoSR(srSuffix) {
    if (!mapData) return 0;
    var ho = activeMods.HO, inMod = activeMods.IN;
    var sunnyKey = ho ? 'srHO' + srSuffix : inMod ? 'srIN' + srSuffix : 'sr' + srSuffix;
    var danielKey = 'danielSR' + srSuffix;
    var sunnyVal = mapData[sunnyKey] || mapData['sr' + srSuffix] || 0;
    var danielVal = mapData[danielKey] || 0;
    if (mapData.columnCount === 4) {
      if (activeAlgo === 'sunny') return sunnyVal;
      if (danielVal > 0 && mapData.danielSR >= 6.36) return danielVal;
    }
    return sunnyVal;
  }

  function getEffectiveOD() {
    var raw = $('stat-od').value;
    var v = parseFloat(raw);
    var maxOD = activeMods.SV2 ? 15 : 10;
    return isNaN(v) ? 0 : Math.min(maxOD, Math.max(0, v));
  }

  function updateAll() {
    if (!mapData) return;
    try {
    var inp = getInputs();
    var n = mapData.totalNotes || 0;
    var isCustom = Math.abs(inp.rate - 1.0) >= 0.01;
    $('nm-rate').textContent = inp.rate.toFixed(2) + 'x';

    var mods = [
      { pref: 'nm', mod: [], rate: 1.0 },
      { pref: 'dt', mod: ['DT'], rate: 1.5 },
      { pref: 'ht', mod: ['HT'], rate: 0.75 }
    ];

    var nmSR = 0;
    for (var i = 0; i < mods.length; i++) {
      var m = mods[i];
      if (isCustom && i > 0) continue;
      var r = isCustom ? inp.rate : m.rate;
      var gameMods = isCustom ? [] : m.mod;
      var extraMods = getActiveMods();
      var allMods = gameMods.concat(extraMods);
      var ho = activeMods.HO;
      var inMod = activeMods.IN;
      // SR display always uses Sunny algorithm; algorithm selection (auto/daniel/sunny)
      // only affects tier lookup via getAlgoSR below — intentional design.
      var sunnyNM = ho ? (mapData.srHO != null ? mapData.srHO : mapData.sr) : (inMod ? (mapData.srIN != null ? mapData.srIN : mapData.sr) : mapData.sr);
      var sunnyDT = ho ? (mapData.srHO_DT != null ? mapData.srHO_DT : mapData.sr_DT) : (inMod ? (mapData.srIN_DT != null ? mapData.srIN_DT : mapData.sr_DT) : mapData.sr_DT);
      var sunnyHT = ho ? (mapData.srHO_HT != null ? mapData.srHO_HT : mapData.sr_HT) : (inMod ? (mapData.srIN_HT != null ? mapData.srIN_HT : mapData.sr_HT) : mapData.sr_HT);
      var sr = estimateSR(sunnyNM, sunnyDT, sunnyHT, r);
      if (i === 0) nmSR = sr;
      var osuNM = ho ? (mapData.osuSR_HO != null ? mapData.osuSR_HO : mapData.osuSR) : (inMod ? (mapData.osuSR_IN != null ? mapData.osuSR_IN : mapData.osuSR) : (mapData.osuSR != null ? mapData.osuSR : sunnyNM));
      var osuDT = ho ? (mapData.osuSR_HO_DT != null ? mapData.osuSR_HO_DT : mapData.osuSR_DT) : (inMod ? (mapData.osuSR_IN_DT != null ? mapData.osuSR_IN_DT : mapData.osuSR_DT) : (mapData.osuSR_DT != null ? mapData.osuSR_DT : sunnyDT));
      var osuHT = ho ? (mapData.osuSR_HO_HT != null ? mapData.osuSR_HO_HT : mapData.osuSR_HT) : (inMod ? (mapData.osuSR_IN_HT != null ? mapData.osuSR_IN_HT : mapData.osuSR_HT) : (mapData.osuSR_HT != null ? mapData.osuSR_HT : sunnyHT));
      var osuSR = estimateSR(osuNM, osuDT, osuHT, r);
      var effLnRatio = inMod ? (mapData.lnRatioIN || 1) : (ho ? (mapData.lnRatioHO || 0) : (mapData.lnRatio || 0));
      var hasLN = effLnRatio >= 0.15;
      var keySup = mapData.columnCount === 4 || mapData.columnCount === 6 || mapData.columnCount === 7 || mapData.columnCount === 10;
      var rcSR, lnSR, tier = '';
      if (mapData.columnCount === 6 && active6KMode === 'rating') {
        // 6K Rating mode: show rating / diff_const instead of CT Dan tier
        if (!sr || sr <= 0) {
          tier = '-';
        } else {
          var ratingAcc = getRatingAcc();
          var dc = calcDiffConst(sr);
          tier = calcRating(dc, ratingAcc).toFixed(2) + ' / ' + dc.toFixed(2);
        }
      } else if (keySup) {
        var danielR = mapData.columnCount === 4 ? estimateSR(mapData.danielSR, mapData.danielSR_DT, mapData.danielSR_HT, r) : 0;
        var useDanielForRC = (mapData.columnCount === 4 && activeAlgo !== 'sunny' && danielR >= 6.365);
        var tierNM, tierDT, tierHT;
        if (hasLN && (mapData.columnCount === 4 || mapData.columnCount === 6 || mapData.columnCount === 7)) {
          // LN map: RC uses Daniel (if rate-adjusted >= 6.365) else srHO; LN uses Sunny
          if (useDanielForRC) {
            tierNM = mapData.danielSR; tierDT = mapData.danielSR_DT; tierHT = mapData.danielSR_HT;
          } else {
            tierNM = mapData.srHO != null ? mapData.srHO : mapData.sr;
            tierDT = mapData.srHO_DT != null ? mapData.srHO_DT : mapData.sr_DT;
            tierHT = mapData.srHO_HT != null ? mapData.srHO_HT : mapData.sr_HT;
          }
        } else {
          // RC map: RC uses Daniel (if rate-adjusted >= 6.365) else Sunny; no LN
          tierNM = useDanielForRC ? mapData.danielSR : sunnyNM;
          tierDT = useDanielForRC ? mapData.danielSR_DT : sunnyDT;
          tierHT = useDanielForRC ? mapData.danielSR_HT : sunnyHT;
        }
        rcSR = estimateSR(tierNM, tierDT, tierHT, r);
        tier = useDanielForRC ? tierAbbr(getDanielTier(rcSR).label) : rcLookup(rcSR, mapData.columnCount, mapData.columnCount === 7 ? active7KMode : undefined);
        if (hasLN && (mapData.columnCount === 4 || mapData.columnCount === 6 || mapData.columnCount === 7)) {
          // LN tier always uses Sunny SR, bypass algorithm selection
          var lnNM = inMod ? (mapData.srIN != null ? mapData.srIN : mapData.sr) : mapData.sr;
          var lnDT = inMod ? (mapData.srIN_DT != null ? mapData.srIN_DT : mapData.sr_DT) : mapData.sr_DT;
          var lnHT = inMod ? (mapData.srIN_HT != null ? mapData.srIN_HT : mapData.sr_HT) : mapData.sr_HT;
          lnSR = estimateSR(lnNM, lnDT, lnHT, r);
          var lnTier = lnLookup(lnSR, mapData.columnCount);
          if (lnTier) tier += ' | ' + lnTier;
        }
      }
      var sunny = computeSunnyPP(sr, inp.acc, allMods, mapData.totalNotes, mapData.variety, mapData.accScalar, ho, inMod);
      var sunny100 = computeSunnyPP(sr, 100, allMods, mapData.totalNotes, mapData.variety, mapData.accScalar, ho, inMod);
      var official = computeOfficialPP(osuSR, inp.acc, n, allMods);
      updateCol(m.pref, sr, sunny, official, sunny100, tier, osuSR);
    }

    $('stat-notes').textContent = mapData.totalNotes || '--';
    var effLn = inMod ? (mapData.lnRatioIN || 1) : (ho ? (mapData.lnRatioHO || 0) : (mapData.lnRatio || 0));
    $('stat-lnpct').textContent = ((effLn || 0) * 100).toFixed(1) + '%';
    var odVal = mapData.od >= 0 ? mapData.od : 8;
    var hpVal = mapData.hp >= 0 ? mapData.hp : 8;
    var activeGameMods = getActiveMods();
    if (activeGameMods.indexOf('EZ') >= 0) { odVal = (odVal * 0.5).toFixed(1); hpVal = (hpVal * 0.5).toFixed(1); }
    if (!activeMods._odDirty) { $('stat-od').value = odVal; }
    $('stat-hp').textContent = hpVal;
    $('stat-keys').textContent = mapData.columnCount + 'K';
    $('pp-acc-display').textContent = inp.acc.toFixed(2) + '%';

    // LN difficulty inversion warning for 6K LN maps below 5th dan
    var warnEl = $('ln-warning');
    var is6KLN = mapData.columnCount === 6 && (mapData.lnRatio || 0) >= 0.15;
    if (is6KLN && nmSR < 7.5 && nmSR > 0) {
      warnEl.textContent = '\u26A0 6K LN tier may invert vs actual difficulty \u2014 for reference only';
      warnEl.style.display = '';
    } else {
      warnEl.style.display = 'none';
    }
    } catch(e) { console.error('[Sunny] updateAll error:', e); }
  }

  function computeAccFromJudgments() {
    var p320 = parseInt($('j-320').value) || 0, p300 = parseInt($('j-300').value) || 0;
    var p200 = parseInt($('j-200').value) || 0, p100 = parseInt($('j-100').value) || 0;
    var p50 = parseInt($('j-50').value) || 0, p0 = parseInt($('j-0').value) || 0;
    var total = p320 + p300 + p200 + p100 + p50 + p0;
    if (total === 0) return;
    var acc;
    if (activeMods.SV1) {
      acc = ((p320 + p300) * 300 + p200 * 200 + p100 * 100 + p50 * 50) / (total * 300) * 100;
    } else {
      acc = (p320 * 320 + p300 * 300 + p200 * 200 + p100 * 100 + p50 * 50) / (total * 320) * 100;
    }
    $('pp-acc-display').textContent = acc.toFixed(2) + '%';
  }

  function debounceUpdate() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(updateAll, 80);
  }

  function setupAlgoBar(keys) {
    var btns = document.querySelectorAll('.algo-btn');
    var bar = $('algo-bar');
    if (keys === 4) {
      btns[0].textContent = 'Auto'; btns[0].dataset.mode = 'auto';
      btns[1].style.display = 'none';
      btns[2].textContent = 'Sunny'; btns[2].dataset.mode = 'sunny';
      btns[2].style.display = '';
      var active = activeAlgo;
      for (var j = 0; j < btns.length; j++) btns[j].classList.toggle('active', btns[j].dataset.mode === active);
    } else if (keys === 7) {
      btns[0].textContent = 'Auto'; btns[0].dataset.mode = 'auto';
      btns[1].textContent = 'Wild'; btns[1].dataset.mode = 'wild';
      btns[1].style.display = '';
      btns[2].style.display = 'none';
      var active = active7KMode;
      for (var j = 0; j < 2; j++) btns[j].classList.toggle('active', btns[j].dataset.mode === active);
    } else if (keys === 6) {
      btns[0].textContent = 'Rating'; btns[0].dataset.mode = 'rating';
      btns[1].textContent = 'Sunny'; btns[1].dataset.mode = 'sunny';
      btns[1].style.display = '';
      btns[2].style.display = 'none';
      var active = active6KMode;
      for (var j = 0; j < 2; j++) btns[j].classList.toggle('active', btns[j].dataset.mode === active);
    }
  }

  function initAlgoButtons() {
    var btns = document.querySelectorAll('.algo-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener('click', function () {
        var mode = this.dataset.mode;
        if (mapData && mapData.columnCount === 7) {
          active7KMode = mode;
          setupAlgoBar(7);
          chrome.storage.local.set({ sunny7KMode: mode });
        } else if (mapData && mapData.columnCount === 6) {
          active6KMode = mode;
          setupAlgoBar(6);
          chrome.storage.local.set({ sunny6KMode: mode });
        } else {
          activeAlgo = mode;
          setupAlgoBar(4);
          chrome.storage.local.set({ sunnyAlgo: mode });
        }
        updateAll();
      });
    }
    chrome.storage.local.get(['sunnyAlgo'], function (r) {
      if (r.sunnyAlgo) { activeAlgo = r.sunnyAlgo === 'daniel' ? 'auto' : r.sunnyAlgo; }
    });
    chrome.storage.local.get(['sunny7KMode'], function (r) {
      if (r.sunny7KMode) { active7KMode = r.sunny7KMode; }
    });
    chrome.storage.local.get(['sunny6KMode'], function (r) {
      if (r.sunny6KMode) {
        // Migrate legacy CT Dan mode value to Sunny
        active6KMode = r.sunny6KMode === 'ctdan' ? 'sunny' : r.sunny6KMode;
      }
    });
  }

  function loadMapData(retryCount) {
    retryCount = retryCount || 0;
    chrome.storage.local.get(['sunnyMapData'], function (result) {
      if (result.sunnyMapData && result.sunnyMapData.beatmapId) {
        applyMapData(result.sunnyMapData);
        // Async verify against current tab's beatmap
         chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
          if (!tabs[0]) return;
          chrome.tabs.sendMessage(tabs[0].id, { type: 'getCurrentBeatmapId' }, function (resp) {
            if (chrome.runtime.lastError) return;
            if (resp && resp.beatmapId && resp.beatmapId !== result.sunnyMapData.beatmapId) {
              chrome.tabs.sendMessage(tabs[0].id, { type: 'triggerRecalc' });
            }
          });
        });
      } else if (retryCount < 5) {
        setTimeout(function () { loadMapData(retryCount + 1); }, 500);
      } else {
        $('status').textContent = 'Open a beatmap page first';
        $('map-name').textContent = 'No beatmap detected';
        $('map-artist').textContent = '';
        $('map-mapper').textContent = '';
        $('map-tier-line').textContent = '';
      }
    });
  }

  function applyMapData(md) {
    mapData = md;
    lastBeatmapId = md.beatmapId;
    $('map-name').textContent = md.title || ('Beatmap #' + md.beatmapId);
    $('map-tier-line').textContent = md.subTitle || '';
    $('map-artist').textContent = md.artist ? 'by ' + md.artist : '';
    $('map-mapper').textContent = md.mapper ? 'mapped by ' + md.mapper : '';
    if (activeMods._judgmentsDirty !== true) {
      $('j-320').value = md.totalNotes || 0;
    }
    if (!activeMods._odDirty) {
      $('stat-od').value = md.od >= 0 ? md.od : 5;
    }
    $('status').textContent = 'Ready';
    $('algo-bar').style.display = (md.columnCount === 4 || md.columnCount === 6 || md.columnCount === 7) ? 'flex' : 'none';
    if (md.columnCount === 4 || md.columnCount === 6 || md.columnCount === 7) setupAlgoBar(md.columnCount);
    updateAll();
  }
  function initInputs() {
    var els = ['pp-acc','pp-combo','pp-rate','j-320','j-300','j-200','j-100','j-50','j-0','stat-od'];
    for (var i = 0; i < els.length; i++) {
      var el = $(els[i]); if (el) el.addEventListener('input', function(e) {
        if (e.target.id.match(/^j-/)) {
          clampJudgments();
          computeAccFromJudgments();
          activeMods._judgmentsDirty = true;
        }
        if (e.target.id === 'pp-rate') highlightPreset(parseFloat(e.target.value) || 1.0);
        if (e.target.id === 'stat-od') {
          var raw = e.target.value;
          activeMods._odDirty = true;
          if (raw === '' || raw === '.') { debounceUpdate(); return; }
          var v = parseFloat(raw);
          var maxOD = activeMods.SV2 ? 15 : 10;
          if (!isNaN(v)) {
            v = Math.min(maxOD, Math.max(0, v));
            if (String(v) !== raw) e.target.value = String(v);
            scheduleOdRecalc(v);
          }
        }
        debounceUpdate();
      });
    }

    $('rate-plus').addEventListener('click', function () {
      var rateEl = $('pp-rate');
      var rate = parseFloat(rateEl.value) || 1.0;
      rate = Math.min(2.0, rate + 0.01);
      rateEl.value = rate.toFixed(2);
      highlightPreset(rate);
      debounceUpdate();
    });
    $('rate-minus').addEventListener('click', function () {
      var rateEl = $('pp-rate');
      var rate = parseFloat(rateEl.value) || 1.0;
      rate = Math.max(0.5, rate - 0.01);
      rateEl.value = rate.toFixed(2);
      highlightPreset(rate);
      debounceUpdate();
    });

    var presetBtns = document.querySelectorAll('.preset-btn');
    for (var j = 0; j < presetBtns.length; j++) {
      presetBtns[j].addEventListener('click', function () {
        var rate = parseFloat(this.dataset.rate);
        $('pp-rate').value = rate.toFixed(2);
        highlightPreset(rate);
        debounceUpdate();
      });
    }
  }

  function highlightPreset(rate) {
    var btns = document.querySelectorAll('.preset-btn');
    for (var i = 0; i < btns.length; i++) {
      var r = parseFloat(btns[i].dataset.rate);
      btns[i].classList.toggle('active', Math.abs(r - rate) < 0.005);
    }
  }

  var _recalcSeq = 0;

  function scheduleOdRecalc(newOd) {
    if (odRecalcTimer) clearTimeout(odRecalcTimer);
    odRecalcTimer = setTimeout(function () { doOdRecalc(newOd); }, 500);
  }

  function doOdRecalc(newOd) {
    if (!mapData || !mapData.beatmapId || isNaN(newOd)) return;
    var seq = ++_recalcSeq;
    $('status').textContent = 'Recalculating...';
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs[0]) { loadMapData(); return; }
      chrome.tabs.sendMessage(tabs[0].id, { type: 'recalculateOd', od: newOd }, function (resp) {
        if (seq !== _recalcSeq) return;
        if (chrome.runtime.lastError) { loadMapData(); return; }
        loadMapData();
      });
    });
  }

  function clampJudgments() {
    if (!mapData || !mapData.totalNotes) return;
    var tn = mapData.totalNotes;
    var fields = ['j-320','j-300','j-200','j-100','j-50','j-0'];
    var values = fields.map(function(f) {
      var v = parseInt($(f).value) || 0;
      if (v < 0) $(f).value = 0;
      return Math.max(0, v);
    });
    var sum = values.reduce(function(a, b) { return a + b; }, 0);
    if (sum > tn) {
      var excess = sum - tn;
      for (var i = 0; i < values.length && excess > 0; i++) {
        var reduce = Math.min(values[i], excess);
        values[i] -= reduce;
        excess -= reduce;
      }
      for (var i = 0; i < fields.length; i++) {
        $(fields[i]).value = values[i];
      }
    }
  }

  initInputs();
  initMods();
  $('footer-version').textContent = 'v' + chrome.runtime.getManifest().version;
  loadMapData();
  initAlgoButtons();

  function initMods() {
    activeMods = { SV1: true };
    $('mod-sv1').classList.add('active');
    var btns = document.querySelectorAll('.mod-tog');
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener('click', function () {
        var mod = this.dataset.mod;
        if (mod === 'SV1' || mod === 'SV2') {
          activeMods.SV1 = mod === 'SV1'; activeMods.SV2 = mod === 'SV2';
          $('mod-sv1').classList.toggle('active', activeMods.SV1);
          $('mod-sv2').classList.toggle('active', activeMods.SV2);
          if (activeMods.SV2) {
            $('stat-od').max = 15;
            $('stat-od').setAttribute('max', '15');
            activeMods._odDirty = true;
          } else {
            $('stat-od').max = 10;
            $('stat-od').setAttribute('max', '10');
            var currentV = parseFloat($('stat-od').value);
            if (isNaN(currentV) || currentV > 10) {
              $('stat-od').value = Math.min(10, mapData ? (mapData.od >= 0 ? mapData.od : 8) : 8);
            }
            activeMods._odDirty = true;
          }
        } else if (mod === 'HO' || mod === 'IN') {
          if (this.classList.contains('active')) { this.classList.remove('active'); activeMods[mod] = false; }
          else {
            activeMods.HO = mod === 'HO'; activeMods.IN = mod === 'IN';
            $('mod-ho').classList.toggle('active', activeMods.HO);
            $('mod-in').classList.toggle('active', activeMods.IN);
          }
        } else {
          activeMods[mod] = !activeMods[mod];
          this.classList.toggle('active', activeMods[mod]);
        }
        if (mod === 'SV1' || mod === 'SV2') computeAccFromJudgments();
        debounceUpdate();
      });
    }
  }

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg.type === 'dataReady') loadMapData();
  });

  chrome.storage.onChanged.addListener(function (changes) {
    if (changes.sunnyMapData && !document.hidden) loadMapData();
  });

  document.addEventListener('wheel', function(e) {
    var el = document.activeElement;
    if (!el || el.tagName !== 'INPUT' || el.type !== 'number') return;
    var step = parseFloat(el.step) || 1;
    var val = parseFloat(el.value) || 0;
    var min = el.min !== '' ? parseFloat(el.min) : -Infinity;
    var max = el.max !== '' ? parseFloat(el.max) : Infinity;
    if (e.deltaY < 0) val = Math.min(max, val + step);
    else if (e.deltaY > 0) val = Math.max(min, val - step);
    else return;
    val = Math.round(val / step) * step;
    var decimals = (step.toString().split('.')[1] || '').length;
    el.value = val.toFixed(decimals);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    e.preventDefault();
  }, { passive: false });
})();
