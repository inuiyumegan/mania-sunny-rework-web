(function () {
  'use strict';

  var fontUrl = chrome.runtime.getURL('Torus-Regular.otf');
  var fontStyle = document.createElement('style');
  fontStyle.textContent = '@font-face{font-family:Torus;src:url(' + fontUrl + ') format("opentype");font-weight:400}';
  document.head.appendChild(fontStyle);

  var CONTAINER_ID = 'sunny-sr-badge';
  var lastBeatmapId = null;
  var calculating = false;

  function getBeatmapId() {
    var url = window.location.href;
    var bMatch = url.match(/osu\.ppy\.sh\/b\/(\d+)/);
    if (bMatch) return bMatch[1];
    var beatmapsMatch = url.match(/osu\.ppy\.sh\/beatmaps\/(\d+)/);
    if (beatmapsMatch) return beatmapsMatch[1];
    var hashMatch = window.location.hash.match(/#(?:mania|osu|taiko|fruits)\/(\d+)/);
    if (hashMatch) return hashMatch[1];
    return null;
  }

  function srColor(sr) {
    if (sr >= 8) return '#ff6b6b';
    if (sr >= 6) return '#ffd93d';
    if (sr >= 4) return '#6bcb77';
    return '#4d96ff';
  }

  function computeSunnyPP(sr, od, accuracy, miss, mods, totalNotes, variety, accScalar) {
    // Real Sunny Rework PP formula from ManiaPerformanceCalculator.cs
    var acc = Math.min(1, Math.max(0, (accuracy || 100) / 100));
    var modsStr = mods ? mods.join('') : '';

    // Mod multiplier
    var mult = 1.0;
    if (modsStr.indexOf('NF') >= 0) mult *= 0.75;
    if (modsStr.indexOf('EZ') >= 0) mult *= 0.90;

    // Difficulty value
    var proportion = 0;
    if (acc > 0.80) {
      proportion = 4.5 * (acc - 0.8) / Math.pow(100 * (1 - acc) + Math.pow(0.9, 20), 0.05);
    }
    var difficultyValue = 9.8 * Math.pow(Math.max(sr - 0.15, 0.05), 2.2) * proportion;

    // Variety multiplier
    var v = variety || 0;
    var varietyMult = 0.945 + 0.11 / (1 + Math.exp(-3 * (v - 3.25)));

    // Accuracy multiplier
    var ac = accScalar || 1;
    var sigmoidScaler = 0.87 + 0.26 / (1.0 + Math.exp(-20 * (ac - 1)));
    var accMult = sigmoidScaler * (2 * Math.pow(acc, 20) - 1) + 2 - 2 * Math.pow(acc, 20);

    // Length multiplier
    var tn = totalNotes || 1;
    var lengthMult = 1.1 / (1.0 + Math.sqrt(sr / (2 * tn)));

    var pp = difficultyValue * mult * varietyMult * accMult * lengthMult;
    return { pp: pp, diffPP: difficultyValue, strain: sr };
  }

  function applyHO(content) {
    var lines = content.split(/\r?\n/);
    var inH = false;
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim() === '[HitObjects]') { inH = true; continue; }
      if (inH && lines[i].trim() && !lines[i].startsWith('[')) {
        var p = lines[i].split(',');
        if (p.length >= 4 && parseInt(p[3]) === 128) { p[3] = '1'; lines[i] = p.join(','); }
      }
    }
    return lines.join('\n');
  }

  function parseTimingPoints(content) {
    var lines = content.split(/\r?\n/);
    var inTP = false;
    var timings = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (line === '[TimingPoints]') { inTP = true; continue; }
      if (inTP && line && !line.startsWith('[')) {
        var p = line.split(',');
        var t = parseInt(p[0]), beatLen = parseFloat(p[1]), unin = parseInt(p[6]) || 0;
        timings.push({ time: t, beatLength: beatLen, uninherited: unin === 1 });
      }
      if (inTP && line.startsWith('[')) break;
    }
    if (!timings.length) timings.push({ time: 0, beatLength: 600, uninherited: true });
    return timings;
  }

  function getBeatLengthAt(timings, time) {
    var bl = 600;
    for (var i = 0; i < timings.length; i++) {
      if (timings[i].time > time) break;
      if (timings[i].uninherited) bl = timings[i].beatLength;
    }
    return bl;
  }

  function applyIN(content) {
    var lines = content.split(/\r?\n/);
    var timings = parseTimingPoints(content);
    var inH = false, notes = [];
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim() === '[HitObjects]') { inH = true; continue; }
      if (inH && lines[i].trim() && !lines[i].startsWith('[')) {
        var p = lines[i].split(',');
        if (p.length >= 4) notes.push({ line: i, col: parseInt(p[0]), time: parseInt(p[2]), parts: p });
      }
    }
    if (!notes.length) return content;
    var maxCol = 0;
    for (var j = 0; j < notes.length; j++) { if (notes[j].col > maxCol) maxCol = notes[j].col; }
    var cols = []; for (var c = 0; c <= maxCol; c++) cols.push([]);
    for (var k = 0; k < notes.length; k++) cols[notes[k].col].push(notes[k]);
    for (var c2 = 0; c2 < cols.length; c2++) {
      var cn = cols[c2];
      for (var n = 0; n < cn.length - 1; n++) {
        var dur = cn[n + 1].time - cn[n].time;
        var beatLength = getBeatLengthAt(timings, cn[n + 1].time);
        dur = Math.max(dur / 2, dur - beatLength / 4);
        dur = Math.floor(dur);
        if (dur < 1) dur = 1;
        var p = cn[n].parts;
        p[3] = '128';
        var extra = (p[5] || '0:0:0:0:').split(':').slice(1).join(':') || '0:0:0:';
        p[5] = (cn[n].time + dur) + ':' + extra;
        lines[cn[n].line] = p.join(',');
      }
    }
    return lines.join('\n');
  }

  function createBadge() {
    var badge = document.getElementById(CONTAINER_ID);
    if (badge) return badge;
    badge = document.createElement('div');
    badge.id = CONTAINER_ID;
    document.body.appendChild(badge);
    return badge;
  }

  function showBadge(sr, pp, tierLabel, keys) {
    var badge = createBadge();
    var color = srColor(sr);
    var isSup = keys === 4 || keys === 6 || keys === 7;
    var tierHtml = (tierLabel && isSup) ? '<span class="sunny-sr-tier" style="color:' + color + ';">' + tierLabel + '</span>' : '';
    var keysHtml = isSup ? '<span class="sunny-sr-tier" style="color:' + color + ';">' + keys + 'K</span>' : '';
    var ppRounded = pp > 10 ? Math.round(pp) : pp.toFixed(1);
    badge.innerHTML =
      tierHtml +
      '<div class="sunny-sr-row">' +
        '<span class="sunny-sr-label">Sunny</span>' +
        '<span class="sunny-sr-value" style="color:' + color + ';">' + sr.toFixed(2) + '\u2605</span>' +
      '</div>' +
      '<div class="sunny-sr-row">' +
        '<span class="sunny-sr-label">Rework PP</span>' +
        '<span class="sunny-sr-value" style="color:' + color + ';">' + ppRounded + 'pp</span>' +
      '</div>' + keysHtml;
    badge.style.display = 'flex';
  }

  function hideBadge() {
    var badge = document.getElementById(CONTAINER_ID);
    if (badge) badge.style.display = 'none';
  }

  async function fetchOsuFile(beatmapId) {
    var url = 'https://osu.ppy.sh/osu/' + beatmapId;
    var resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.text();
  }

  function getMapTitle() {
    var el = document.querySelector('.beatmapset-header__details-text--title');
    if (el) return el.textContent.trim();
    el = document.querySelector('.beatmapset-header__details-text');
    if (el) return el.textContent.trim();
    return '';
  }

  function getDifficultyName() {
    var el = document.querySelector('.beatmapset-header__diff-name');
    if (el) {
      var t = '';
      for (var i = 0; i < el.childNodes.length; i++) {
        if (el.childNodes[i].nodeType === 3) t += el.childNodes[i].textContent;
      }
      return t.trim();
    }
    var activeTab = document.querySelector('.beatmapset-difficulty-tabs__tab--active');
    if (activeTab) {
      var t2 = activeTab.textContent.trim();
      t2 = t2.replace(/^\d+(?:\.\d+)?\s*\S?\s*/, '');
      while (/^\[\d+K\]\s*/.test(t2)) t2 = t2.replace(/^\[\d+K\]\s*/, '');
      return t2.trim();
    }
    return '';
  }

  function getArtist() {
    var el = document.querySelector('.beatmapset-header__details-text--artist');
    if (el) {
      var artist = '';
      for (var i = 0; i < el.childNodes.length; i++) {
        if (el.childNodes[i].nodeType === 3) artist += el.childNodes[i].textContent;
      }
      return artist.trim();
    }
    el = document.querySelector('[class*="artist"]');
    if (el) return el.textContent.trim();
    return '';
  }

  async function calculateAndStore(beatmapId) {
    if (calculating) return;
    calculating = true;

    try {
      var fileContent = await fetchOsuFile(beatmapId);

      var parser = new OsuParser(fileContent);
      parser.process();

      if (parser.mode !== 3) {
        hideBadge();
        calculating = false;
        return;
      }

      var parsedData = parser.getParsedData();
      var od = parser.od > 0 ? parser.od : 8;
      var hp = parser.hp > 0 ? parser.hp : 8;

      var srResult = calculateFromParsed(parsedData, 'NM');
      var sr = srResult.sr;
      var srDT = calculateFromParsed(parsedData, 'DT').sr;
      var srHT = calculateFromParsed(parsedData, 'HT').sr;
      var variety = srResult.variety;
      var accScalar = 0.5 * srResult.spikiness + 0.5 * srResult.switches;
      var spikiness = srResult.spikiness;
      var switches = srResult.switches;
      var osuSR = computeOsuSRFromParsed(parsedData, 'NM');
      var osuSR_DT = computeOsuSRFromParsed(parsedData, 'DT');
      var osuSR_HT = computeOsuSRFromParsed(parsedData, 'HT');
      var danielSR = computeDanielSR(parser.columns, parser.noteStarts, parser.noteEnds, parser.noteTypes, parser.columnCount, 1.0);
      var danielSR_DT = computeDanielSR(parser.columns, parser.noteStarts, parser.noteEnds, parser.noteTypes, parser.columnCount, 1.5);
      var danielSR_HT = computeDanielSR(parser.columns, parser.noteStarts, parser.noteEnds, parser.noteTypes, parser.columnCount, 0.75);

       var hoContent = applyHO(fileContent);
      var hoParser = new OsuParser(hoContent);
      hoParser.process();
      var hoParsed = hoParser.getParsedData();
      var hoStats = analyzeMap(hoParser);
      var srHO, srHO_DT, srHO_HT, osuSR_HO, osuSR_HO_DT, osuSR_HO_HT, hoVariety, hoAccScalar;
      try { var hoRes = calculateFromParsed(hoParsed, 'NM'); srHO = hoRes.sr; hoVariety = hoRes.variety; hoAccScalar = 0.5 * hoRes.spikiness + 0.5 * hoRes.switches; srHO_DT = calculateFromParsed(hoParsed, 'DT').sr; srHO_HT = calculateFromParsed(hoParsed, 'HT').sr; } catch(e) { srHO = sr; srHO_DT = srDT; srHO_HT = srHT; hoVariety = variety; hoAccScalar = accScalar; }
      try { osuSR_HO = computeOsuSRFromParsed(hoParsed, 'NM'); osuSR_HO_DT = computeOsuSRFromParsed(hoParsed, 'DT'); osuSR_HO_HT = computeOsuSRFromParsed(hoParsed, 'HT'); } catch(e) { osuSR_HO = osuSR; osuSR_HO_DT = osuSR_DT; osuSR_HO_HT = osuSR_HT; }

      var inContent = applyIN(fileContent);
      var inParser = new OsuParser(inContent);
      inParser.process();
      var inParsed = inParser.getParsedData();
      var inStats = analyzeMap(inParser);
      var srIN, srIN_DT, srIN_HT, osuSR_IN, osuSR_IN_DT, osuSR_IN_HT, inVariety, inAccScalar;
      try { var inRes = calculateFromParsed(inParsed, 'NM'); srIN = inRes.sr; inVariety = inRes.variety; inAccScalar = 0.5 * inRes.spikiness + 0.5 * inRes.switches; srIN_DT = calculateFromParsed(inParsed, 'DT').sr; srIN_HT = calculateFromParsed(inParsed, 'HT').sr; } catch(e) { srIN = sr; srIN_DT = srDT; srIN_HT = srHT; inVariety = variety; inAccScalar = accScalar; }
      try { osuSR_IN = computeOsuSRFromParsed(inParsed, 'NM'); osuSR_IN_DT = computeOsuSRFromParsed(inParsed, 'DT'); osuSR_IN_HT = computeOsuSRFromParsed(inParsed, 'HT'); } catch(e) { osuSR_IN = osuSR; osuSR_IN_DT = osuSR_DT; osuSR_IN_HT = osuSR_HT; }

      var title = getMapTitle();
      var diffName = getDifficultyName();
      var artist = getArtist();
      var stats = analyzeMap(parser);
      var isSupKeys = stats.columnCount === 4 || stats.columnCount === 6 || stats.columnCount === 7;
      var tier = { label: '' };
      if (isSupKeys) {
        var hasLN = stats.lnRatio >= 0.15;
        // RC tier: for LN maps use HO SR (match popup behavior)
        var rcSR = sr;
        if (stats.columnCount === 4) {
          rcSR = (danielSR >= 6.36) ? danielSR : sr;
        }
        if (hasLN) rcSR = srHO || sr;
        var rcTier = getRCTier(rcSR, stats.columnCount);
        if (rcTier) {
          tier.label = rcTier;
          if (hasLN) {
            var lnTier = getLNTier(sr, stats.columnCount);
            if (lnTier) tier.label = rcTier + ' || ' + lnTier;
          }
        }
      }
      var headerTitle = title;
      var headerSub = '[' + stats.columnCount + 'K]';
      if (diffName) {
        diffName = diffName.replace(/^\[\d+K\]\s*/, '');
        headerSub += ' ' + diffName;
      }

      hideBadge();

      chrome.storage.local.set({
        sunnyMapData: {
          beatmapId: beatmapId,
          fileContent: fileContent,
          hoFileContent: hoContent,
          inFileContent: inContent,
          sr: sr, sr_DT: srDT, sr_HT: srHT,
          srHO: srHO, srHO_DT: srHO_DT, srHO_HT: srHO_HT,
          srIN: srIN, srIN_DT: srIN_DT, srIN_HT: srIN_HT,
          osuSR: osuSR, osuSR_DT: osuSR_DT, osuSR_HT: osuSR_HT,
          osuSR_HO: osuSR_HO, osuSR_HO_DT: osuSR_HO_DT, osuSR_HO_HT: osuSR_HO_HT,
          osuSR_IN: osuSR_IN, osuSR_IN_DT: osuSR_IN_DT, osuSR_IN_HT: osuSR_IN_HT,
          danielSR: danielSR, danielSR_DT: danielSR_DT, danielSR_HT: danielSR_HT,
          od: od,
          hp: hp,
          variety: variety,
          accScalar: accScalar,
          spikiness: spikiness,
          switches: switches,
          varietyHO: hoVariety,
          accScalarHO: hoAccScalar,
          varietyIN: inVariety,
          accScalarIN: inAccScalar,
          maxCombo: stats.maxCombo,
          totalNotes: stats.totalNotes,
          riceCount: stats.riceCount,
          lnCount: stats.lnCount,
          lnRatio: stats.lnRatio,
          lnRatioHO: hoStats.lnRatio,
          lnRatioIN: inStats.lnRatio,
          totalTime: stats.totalTime,
          columnCount: stats.columnCount,
          diffLabel: tier.label,
          title: headerTitle,
          subTitle: headerSub,
          artist: artist
        }
      }, function () {
        var pp = computeSunnyPP(sr, od, 100, 0, [], stats.totalNotes, variety, accScalar);
        showBadge(sr, pp.pp, tier.label, stats.columnCount);
        chrome.runtime.sendMessage({ type: 'dataReady', beatmapId: beatmapId }).catch(function() {});
      });
    } catch (err) {
      console.error('[SunnyRework] error:', err);
      hideBadge();
    }

    calculating = false;
  }

  function checkAndRun() {
    var beatmapId = getBeatmapId();
    if (!beatmapId) { hideBadge(); lastBeatmapId = null; return; }
    if (beatmapId === lastBeatmapId) return;
    lastBeatmapId = beatmapId;
    calculateAndStore(beatmapId);
  }

  function watchPage() {
    window.addEventListener('hashchange', checkAndRun);
    window.addEventListener('popstate', checkAndRun);

    var lastUrl = location.href;
    new MutationObserver(function () {
      if (location.href !== lastUrl) {
        lastUrl = location.href;
        hideBadge();
        lastBeatmapId = null;
        checkAndRun();
      }
    }).observe(document.body, { childList: true, subtree: true });

    setInterval(function () {
      if (location.href !== lastUrl) {
        lastUrl = location.href;
        hideBadge();
        lastBeatmapId = null;
        checkAndRun();
      }
    }, 2000);
  }

  watchPage();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkAndRun);
  } else {
    checkAndRun();
  }

  function recalcOd(content, odOverride) {
    var parser = new OsuParser(content);
    parser.process();
    var d = parser.getParsedData();
    d[5] = odOverride;
    var res = calculateFromParsed(d, 'NM');
    return {
      sr: res.sr,
      srDT: calculateFromParsed(d, 'DT').sr,
      srHT: calculateFromParsed(d, 'HT').sr,
      variety: res.variety,
      spikiness: res.spikiness,
      switches: res.switches,
      accScalar: 0.5 * res.spikiness + 0.5 * res.switches
    };
  }

  chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
    if (request.type === 'getCurrentBeatmapId') {
      sendResponse({ beatmapId: getBeatmapId() });
      return;
    }
    if (request.type === 'triggerRecalc') {
      lastBeatmapId = null;
      checkAndRun();
      sendResponse({ ok: true });
      return;
    }
    if (request.type === 'recalculateOd') {
      try {
        chrome.storage.local.get(['sunnyMapData'], function (result) {
          var md = result.sunnyMapData;
          if (!md || !md.fileContent) { sendResponse({ error: 'no data' }); return; }

          var od = parseFloat(request.od) || md.od || 8;
          var base = recalcOd(md.fileContent, od);
          var ho = md.hoFileContent ? recalcOd(md.hoFileContent, od) : base;
          var inv = md.inFileContent ? recalcOd(md.inFileContent, od) : base;

          var updates = {
            sr: base.sr, sr_DT: base.srDT, sr_HT: base.srHT,
            srHO: ho.sr, srHO_DT: ho.srDT, srHO_HT: ho.srHT,
            srIN: inv.sr, srIN_DT: inv.srDT, srIN_HT: inv.srHT,
            variety: base.variety, varietyHO: ho.variety, varietyIN: inv.variety,
            accScalar: base.accScalar, accScalarHO: ho.accScalar, accScalarIN: inv.accScalar,
            spikiness: base.spikiness, switches: base.switches,
            od: od
          };

          chrome.storage.local.set({ sunnyMapData: Object.assign({}, md, updates) }, function () {
            sendResponse({ ok: true });
          });
        });
        return true;
      } catch (e) {
        sendResponse({ error: e.message });
      }
    }
  });
})();
