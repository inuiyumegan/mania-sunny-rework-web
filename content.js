(function () {
  'use strict';
  console.log('[SunnyRework] content script loaded');

  var CONTAINER_ID = 'sunny-sr-badge';
  var lastBeatmapId = null;
  var _extInvalidated = false;

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

  function escapeHtml(str) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(str));
    return d.innerHTML;
  }

  function calcDiffConst(sr) { return sr * 200.0 / 81.0 + 7.0 / 6.0; }

  function showBadge(sr, pp, tierLabel, keys) {
    var badge = createBadge();
    var color = srColor(sr);
    var isSup = keys === 4 || keys === 6 || keys === 7 || keys === 10;
    var tierHtml = (tierLabel && isSup) ? '<span class="sunny-sr-tier" style="color:' + color + ';">' + escapeHtml(tierLabel) + '</span>' : '';
    var keysHtml = isSup ? '<span class="sunny-sr-keys" style="color:' + color + ';">' + keys + 'K</span>' : '';
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

  function showLoading() {
    var badge = createBadge();
    badge.innerHTML =
      '<div class="sunny-sr-row">' +
        '<span class="sunny-sr-value" style="color:#7a7a8c;">...</span>' +
      '</div>';
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
    var el = document.querySelector('.beatmapset-header__details-text--title .beatmapset-header__details-text-link');
    if (el) return el.textContent.trim();
    el = document.querySelector('.beatmapset-header__details-text--title');
    if (el) return el.textContent.replace(/\s*不良内容\s*|\s*NSFW\s*|\s*聚光灯\s*|\s*Spotlight\s*/gi, '').trim();
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

  function getMapper() {
    var el = document.querySelector('.beatmapset-header__details-text--mapper');
    if (el) {
      var mapper = '';
      for (var i = 0; i < el.childNodes.length; i++) {
        if (el.childNodes[i].nodeType === 3) mapper += el.childNodes[i].textContent;
      }
      var t = mapper.trim();
      if (t.toLowerCase().startsWith('mapped by ')) t = t.slice(10);
      return t;
    }
    el = document.querySelector('.beatmapset-mapper__name');
    if (el) return el.textContent.trim();
    return '';
  }

  function ensureFont() {
    if (!document.getElementById('sunny-font-injected')) {
      var s = document.createElement('style');
      s.id = 'sunny-font-injected';
      s.textContent = '@font-face{font-family:Torus;src:url(' + chrome.runtime.getURL('Torus-Regular.otf') + ') format("opentype");font-weight:400}';
      document.head.appendChild(s);
    }
  }

  async function calculateAndStore(beatmapId) {
    if (beatmapId === lastBeatmapId) return;
    if (_extInvalidated) return;
    lastBeatmapId = beatmapId;

    try {
      ensureFont();
      var fileContent = await fetchOsuFile(beatmapId);

      var parser = new OsuParser(fileContent);
      parser.process();

      if (parser.mode !== 3) {
        hideBadge();
        return;
      }

      var parsedData = parser.getParsedData();
      var od = parser.od >= 0 ? parser.od : 5;
      var hp = parser.hp >= 0 ? parser.hp : 5;

      // Base: compute NM, DT, HT (3 Sunny runs). DT/HT ratios derived for HO/IN below.
      var srResult = calculateFromParsed(parsedData, 'NM');
      var sr = srResult.sr;
      var srDT = calculateFromParsed(parsedData, 'DT').sr;
      var srHT = calculateFromParsed(parsedData, 'HT').sr;
      var variety = srResult.variety;
      var accScalar = 0.5 * srResult.spikiness + 0.5 * srResult.switches;
      var spikiness = srResult.spikiness;
      var switches = srResult.switches;
      var dtRatio = sr > 0 ? srDT / sr : 1.0;
      var htRatio = sr > 0 ? srHT / sr : 1.0;

      var osuSR = computeOsuSRFromParsed(parsedData, 'NM');
      var osuSR_DT = computeOsuSRFromParsed(parsedData, 'DT');
      var osuSR_HT = computeOsuSRFromParsed(parsedData, 'HT');
      var danielSR = computeDanielSR(parser.columns, parser.noteStarts, parser.noteEnds, parser.noteTypes, parser.columnCount, 1.0);
      var danielSR_DT = computeDanielSR(parser.columns, parser.noteStarts, parser.noteEnds, parser.noteTypes, parser.columnCount, 1.5);
      var danielSR_HT = computeDanielSR(parser.columns, parser.noteStarts, parser.noteEnds, parser.noteTypes, parser.columnCount, 0.75);

      // HO: only NM run (saves 2 Sunny runs). DT/HT derived from base ratio.
      var hoContent = applyHO(fileContent);
      var hoParser = new OsuParser(hoContent);
      hoParser.process();
      var hoParsed = hoParser.getParsedData();
      var hoStats = analyzeMap(hoParser);
      var srHO, srHO_DT, srHO_HT, osuSR_HO, osuSR_HO_DT, osuSR_HO_HT, hoVariety, hoAccScalar;
      try { var hoRes = calculateFromParsed(hoParsed, 'NM'); srHO = hoRes.sr; hoVariety = hoRes.variety; hoAccScalar = 0.5 * hoRes.spikiness + 0.5 * hoRes.switches; } catch(e) { console.warn('[SunnyRework] HO calc failed, fallback to NM:', e); srHO = sr; hoVariety = variety; hoAccScalar = accScalar; }
      srHO_DT = srHO * dtRatio; srHO_HT = srHO * htRatio;
      try { osuSR_HO = computeOsuSRFromParsed(hoParsed, 'NM'); osuSR_HO_DT = computeOsuSRFromParsed(hoParsed, 'DT'); osuSR_HO_HT = computeOsuSRFromParsed(hoParsed, 'HT'); } catch(e) { osuSR_HO = osuSR; osuSR_HO_DT = osuSR_DT; osuSR_HO_HT = osuSR_HT; }

      // IN: only NM run (saves 2 Sunny runs). DT/HT derived.
      var inContent = applyIN(fileContent);
      var inParser = new OsuParser(inContent);
      inParser.process();
      var inParsed = inParser.getParsedData();
      var inStats = analyzeMap(inParser);
      var srIN, srIN_DT, srIN_HT, osuSR_IN, osuSR_IN_DT, osuSR_IN_HT, inVariety, inAccScalar;
      try { var inRes = calculateFromParsed(inParsed, 'NM'); srIN = inRes.sr; inVariety = inRes.variety; inAccScalar = 0.5 * inRes.spikiness + 0.5 * inRes.switches; } catch(e) { console.warn('[SunnyRework] IN calc failed, fallback to NM:', e); srIN = sr; inVariety = variety; inAccScalar = accScalar; }
      srIN_DT = srIN * dtRatio; srIN_HT = srIN * htRatio;
      try { osuSR_IN = computeOsuSRFromParsed(inParsed, 'NM'); osuSR_IN_DT = computeOsuSRFromParsed(inParsed, 'DT'); osuSR_IN_HT = computeOsuSRFromParsed(inParsed, 'HT'); } catch(e) { osuSR_IN = osuSR; osuSR_IN_DT = osuSR_DT; osuSR_IN_HT = osuSR_HT; }

      var title = getMapTitle();
      var diffName = getDifficultyName();
      var artist = getArtist();
      var mapper = getMapper();
      var stats = analyzeMap(parser);
      var isSupKeys = stats.columnCount === 4 || stats.columnCount === 6 || stats.columnCount === 7 || stats.columnCount === 10;
      var tier = { label: '' };
      if (isSupKeys) {
        var hasLN = stats.lnRatio >= 0.15;
        var useDaniel = (stats.columnCount === 4 && danielSR >= 6.365);
        var rcSR;
        if (hasLN && (stats.columnCount === 4 || stats.columnCount === 6 || stats.columnCount === 7)) {
          // LN map: RC uses Daniel (if >= 6.365) else srHO; LN uses Sunny
          rcSR = useDaniel ? danielSR : (srHO != null ? srHO : sr);
        } else {
          // RC map: RC uses Daniel (if >= 6.365) else Sunny; no LN
          rcSR = useDaniel ? danielSR : sr;
        }
        var rcTier = useDaniel ? getDanielTier(rcSR).label : getRCTier(rcSR, stats.columnCount);
        if (rcTier) {
          tier.label = rcTier;
          if (hasLN && (stats.columnCount === 4 || stats.columnCount === 6 || stats.columnCount === 7)) {
            // LN tier always uses Sunny SR
            var lnTier = getLNTier(sr, stats.columnCount);
            if (lnTier) tier.label = rcTier + ' || ' + lnTier;
          }
        }
      }
      if (stats.columnCount === 6) {
        // 6K badge defaults to Rating mode: show difficulty constant only
        tier.label = sr > 0 ? calcDiffConst(sr).toFixed(2) : '';
      }
      var headerTitle = title;
      var headerSub = '[' + stats.columnCount + 'K]';
      if (diffName) {
        diffName = diffName.replace(/^\[\d+K\]\s*/, '');
        headerSub += ' ' + diffName;
      }

      showLoading();
      chrome.storage.local.set({
        sunnyMapData: {
          beatmapId: beatmapId,
          parsed: parsedData,
          hoParsed: hoParsed,
          inParsed: inParsed,
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
          artist: artist,
          mapper: mapper
        }
      }, function () {
        var pp = computeSunnyPP(sr, 100, [], stats.totalNotes, variety, accScalar);
        showBadge(sr, pp.pp, tier.label, stats.columnCount);
        chrome.runtime.sendMessage({ type: 'dataReady', beatmapId: beatmapId }).catch(function() {});
      });
    } catch (err) {
      if (err.message && err.message.includes('Extension context invalidated')) {
        _extInvalidated = true;
        return;
      }
      console.error('[SunnyRework] error:', err);
      hideBadge();
      lastBeatmapId = null;
    }

  }

  function checkAndRun() {
    var beatmapId = getBeatmapId();
    if (!beatmapId) { hideBadge(); lastBeatmapId = null; return; }
    if (beatmapId === lastBeatmapId) return;
    hideBadge();
    calculateAndStore(beatmapId);
  }

  var _pollTimer = null;

  function onUrlChanged() {
    checkAndRun();
  }

  function pollBeatmap() {
    var beatmapId = getBeatmapId();
    if (beatmapId) calculateAndStore(beatmapId);
  }

  function startPolling() {
    if (_pollTimer) return;
    _pollTimer = setInterval(pollBeatmap, 500);
  }

  window.addEventListener('hashchange', onUrlChanged);
  window.addEventListener('popstate', onUrlChanged);
  document.addEventListener('turbo:load', onUrlChanged);

  var observer = new MutationObserver(function () {
    var id = getBeatmapId();
    if (id && id !== lastBeatmapId) onUrlChanged();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: false });

  startPolling();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', pollBeatmap);
  } else {
    pollBeatmap();
  }

  var _lastUrl = window.location.href;
  function watchUrl() {
    var cur = window.location.href;
    if (cur !== _lastUrl) { _lastUrl = cur; onUrlChanged(); }
    requestAnimationFrame(watchUrl);
  }
  requestAnimationFrame(watchUrl);

  function recalcOd(parsed, odOverride) {
    var d = parsed.slice();
    d[5] = odOverride;
    var resNM = calculateFromParsed(d, 'NM');
    var resDT = calculateFromParsed(d, 'DT');
    var resHT = calculateFromParsed(d, 'HT');
    return {
      sr: resNM.sr,
      srDT: resDT.sr,
      srHT: resHT.sr,
      variety: resNM.variety,
      spikiness: resNM.spikiness,
      switches: resNM.switches,
      accScalar: 0.5 * resNM.spikiness + 0.5 * resNM.switches
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
          if (!md || !md.parsed) { sendResponse({ error: 'no data' }); return; }

          var od = parseFloat(request.od); if (isNaN(od)) od = md.od >= 0 ? md.od : 8;
          var dtRatio = md.sr > 0 ? (md.sr_DT || 0) / md.sr : 1.5;
          var htRatio = md.sr > 0 ? (md.sr_HT || 0) / md.sr : 0.75;
          var base = recalcOd(md.parsed, od);
          var ho = md.hoParsed ? recalcOd(md.hoParsed, od) : base;
          var inv = md.inParsed ? recalcOd(md.inParsed, od) : base;

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
            var pp = computeSunnyPP(base.sr, 100, [], md.totalNotes, base.variety, base.accScalar);
            showBadge(base.sr, pp.pp, md.diffLabel, md.columnCount);
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
