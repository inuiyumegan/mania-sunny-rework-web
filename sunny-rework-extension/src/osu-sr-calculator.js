function logistic(x, multiplier, midpointOffset) {
  return 1.0 / (1.0 + Math.exp(-multiplier * (x - midpointOffset)));
}

function computeOsuSR(fileContent, mod) {
  var parser = new OsuParser(fileContent);
  parser.process();
  return computeOsuSRFromParsed(parser.getParsedData(), mod);
}

function computeOsuSRFromParsed(p, mod) {
  var K = p[0];
  if (K <= 0) return 0;

  var rate = 1.0;
  if (mod === 'DT') rate = 1.5;
  else if (mod === 'HT') rate = 0.75;

  var objects = [];
  for (var i = 0; i < p[1].length; i++) {
    var column = p[1][i];
    var startTime = p[2][i] / rate;
    var isHold = p[4][i] === 128;
    var endTime = isHold ? p[3][i] / rate : startTime;
    objects.push({ column: column, startTime: startTime, endTime: endTime, isHold: isHold });
  }

  objects.sort(function (a, b) { return a.startTime - b.startTime || a.column - b.column; });

  if (objects.length === 0) return 0;

  var perColumn = [];
  for (var c = 0; c < K; c++) perColumn.push([]);

  var diffObjects = [];

  for (var i = 1; i < objects.length; i++) {
    var cur = objects[i];
    var prev = objects[i - 1];
    var prevHits = new Array(K).fill(null);

    if (i > 1) {
      var prevDO = diffObjects[diffObjects.length - 1];
      for (var c = 0; c < K; c++) prevHits[c] = prevDO.previousHits[c];
      prevHits[prevDO.column] = prevDO;
    }

    var columnIndex = perColumn[cur.column].length;
    var prevInCol = columnIndex > 0 ? perColumn[cur.column][columnIndex - 1] : null;
    var columnStrainTime = prevInCol ? cur.startTime - prevInCol.startTime : cur.startTime;

    var dobj = {
      index: i,
      column: cur.column,
      startTime: cur.startTime,
      endTime: cur.endTime,
      deltaTime: cur.startTime - prev.startTime,
      columnStrainTime: columnStrainTime,
      previousHits: prevHits,
      perColumn: perColumn,
      columnIndex: columnIndex
    };

    diffObjects.push(dobj);
    perColumn[cur.column].push(dobj);
  }

  var SECTION_LENGTH = 400;
  var DECAY_WEIGHT = 0.9;
  var INDIVIDUAL_DECAY_BASE = 0.125;
  var OVERALL_DECAY_BASE = 0.30;
  var DIFFICULTY_MULTIPLIER = 0.018;

  var individualStrains = new Array(K).fill(0);
  var overallStrain = 1.0;
  var highestIndividualStrain = 0;
  var currentStrain = 0;
  var currentSectionPeak = 0;
  var currentSectionEnd = 0;
  var strainPeaks = [];
  var objectDifficulties = [];

  for (var j = 0; j < diffObjects.length; j++) {
    var dobj = diffObjects[j];

    if (dobj.index === 1) {
      currentSectionEnd = Math.ceil(dobj.startTime / SECTION_LENGTH) * SECTION_LENGTH;
    }

    while (dobj.startTime > currentSectionEnd) {
      strainPeaks.push(currentSectionPeak);
      var prevTime = j > 0 ? diffObjects[j - 1].startTime : 0;
      var gap = Math.max(0, currentSectionEnd - prevTime);
      var initInd = Math.pow(INDIVIDUAL_DECAY_BASE, gap / 1000);
      var initOv = Math.pow(OVERALL_DECAY_BASE, gap / 1000);
      currentSectionPeak = highestIndividualStrain * initInd + overallStrain * initOv;
      currentSectionEnd += SECTION_LENGTH;
    }

    var indDecay = Math.pow(INDIVIDUAL_DECAY_BASE, dobj.columnStrainTime / 1000);
    individualStrains[dobj.column] *= indDecay;

    // IndividualStrainEvaluator
    var holdFactor = 1.0;
    for (var c = 0; c < K; c++) {
      var ph = dobj.previousHits[c];
      if (!ph) continue;
      if (ph.endTime > dobj.endTime + 1 && dobj.startTime > ph.startTime + 1) {
        holdFactor = 1.25;
        break;
      }
    }
    individualStrains[dobj.column] += 2.0 * holdFactor;

    if (dobj.deltaTime <= 1) {
      highestIndividualStrain = Math.max(highestIndividualStrain, individualStrains[dobj.column]);
    } else {
      highestIndividualStrain = individualStrains[dobj.column];
    }

    var ovDecay = Math.pow(OVERALL_DECAY_BASE, dobj.deltaTime / 1000);
    overallStrain = overallStrain * ovDecay;

    // OverallStrainEvaluator
    var isOverlapping = false;
    var closestEndTime = Math.abs(dobj.endTime - dobj.startTime);
    var ovHoldFactor = 1.0;

    for (var c2 = 0; c2 < K; c2++) {
      var ph2 = dobj.previousHits[c2];
      if (!ph2) continue;

      isOverlapping = isOverlapping || (
        ph2.endTime > dobj.startTime + 1 &&
        dobj.endTime > ph2.endTime + 1 &&
        dobj.startTime > ph2.startTime + 1
      );

      if (ph2.endTime > dobj.endTime + 1 && dobj.startTime > ph2.startTime + 1) {
        ovHoldFactor = 1.25;
      }

      closestEndTime = Math.min(closestEndTime, Math.abs(dobj.endTime - ph2.endTime));
    }

    var holdAddition = 0;
    if (isOverlapping) {
      holdAddition = logistic(closestEndTime, 0.27, 30);
    }

    overallStrain += (1 + holdAddition) * ovHoldFactor;

    var strainValue = highestIndividualStrain + overallStrain - currentStrain;
    currentStrain += strainValue;
    currentSectionPeak = Math.max(currentStrain, currentSectionPeak);
    objectDifficulties.push(currentStrain);
  }

  strainPeaks.push(currentSectionPeak);
  strainPeaks.sort(function (a, b) { return b - a; });

  var difficulty = 0;
  var weight = 1.0;
  for (var k = 0; k < strainPeaks.length; k++) {
    if (strainPeaks[k] <= 0) continue;
    difficulty += strainPeaks[k] * weight;
    weight *= DECAY_WEIGHT;
  }

  return difficulty * DIFFICULTY_MULTIPLIER;
}
