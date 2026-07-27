function rescaleHigh(sr) {
  if (sr <= 9) return sr;
  return 9 + (sr - 9) * (1 / 1.2);
}

function findNextNoteInColumn(note, times, noteSeqByColumn) {
  const k = note[0], h = note[1];
  const columnNotes = noteSeqByColumn[k];
  const idx = bisectLeft(times, h);
  if (idx + 1 < columnNotes.length) {
    return columnNotes[idx + 1];
  }
  return [0, 1e9, 1e9];
}

function preprocessParsedData(p, mod) {
  const K = p[0];
  const noteSeq = [];

  for (let i = 0; i < p[1].length; i++) {
    let h = p[2][i];
    let t = p[4][i] === 128 ? p[3][i] : -1;

    if (mod === 'DT') {
      h = Math.round(h * 2 / 3);
      t = t >= 0 ? Math.round(t * 2 / 3) : t;
    } else if (mod === 'HT') {
      h = Math.round(h * 4 / 3);
      t = t >= 0 ? Math.round(t * 4 / 3) : t;
    }

    noteSeq.push([p[1][i], h, t]);
  }

  let x = 0.3 * Math.pow((64.5 - Math.ceil(p[5] * 3)) / 500, 0.5);
  x = Math.min(x, 0.6 * (x - 0.09) + 0.09);

  noteSeq.sort((a, b) => a[1] - b[1] || a[0] - b[0]);

  const noteSeqByColumn = Array.from({ length: K }, () => []);
  for (const tup of noteSeq) {
    noteSeqByColumn[tup[0]].push(tup);
  }

  const LNSeq = noteSeq.filter(n => n[2] >= 0);
  const tailSeq = LNSeq.slice().sort((a, b) => a[2] - b[2]);

  const LNSeqByColumn = Array.from({ length: K }, () => []);
  for (const tup of LNSeq) {
    LNSeqByColumn[tup[0]].push(tup);
  }

  let maxTime = 0;
  for (const n of noteSeq) {
    maxTime = Math.max(maxTime, n[1]);
    if (n[2] >= 0) maxTime = Math.max(maxTime, n[2]);
  }
  const T = maxTime + 1;

  return { x, K, T, noteSeq, noteSeqByColumn, LNSeq, tailSeq, LNSeqByColumn };
}

function preprocessFile(fileContent, mod) {
  const parser = new OsuParser(fileContent);
  parser.process();
  return preprocessParsedData(parser.getParsedData(), mod);
}

function getCorners(T, noteSeq) {
  const cornersBase = new Set();
  for (const n of noteSeq) {
    const h = n[1], t = n[2];
    cornersBase.add(h);
    if (t >= 0) cornersBase.add(t);
  }
  for (const s of [...cornersBase]) {
    cornersBase.add(s + 501);
    cornersBase.add(s - 499);
    cornersBase.add(s + 1);
  }
  cornersBase.add(0);
  cornersBase.add(T);

  let baseArr = [...cornersBase].filter(s => s >= 0 && s <= T).sort((a, b) => a - b);

  const cornersA = new Set();
  for (const n of noteSeq) {
    cornersA.add(n[1]);
    if (n[2] >= 0) cornersA.add(n[2]);
  }
  for (const s of [...cornersA]) {
    cornersA.add(s + 1000);
    cornersA.add(s - 1000);
  }
  cornersA.add(0);
  cornersA.add(T);

  const AArr = [...cornersA].filter(s => s >= 0 && s <= T).sort((a, b) => a - b);

  const allSet = new Set([...baseArr, ...AArr]);
  const allArr = [...allSet].sort((a, b) => a - b);

  return { allCorners: allArr, baseCorners: baseArr, ACorners: AArr };
}

function getKeyUsage(K, T, noteSeq, baseCorners) {
  const keyUsage = {};
  for (let k = 0; k < K; k++) {
    keyUsage[k] = new Array(baseCorners.length).fill(false);
  }

  for (const n of noteSeq) {
    const k = n[0], h = n[1], t = n[2];
    const startTime = Math.max(h - 150, 0);
    const endTime = t < 0 ? (h + 150) : Math.min(t + 150, T - 1);
    const leftIdx = bisectLeft(baseCorners, startTime);
    const rightIdx = bisectLeft(baseCorners, endTime);
    for (let idx = leftIdx; idx < rightIdx; idx++) {
      keyUsage[k][idx] = true;
    }
  }

  return keyUsage;
}

function getKeyUsage400(K, T, noteSeq, baseCorners) {
  const keyUsage400 = {};
  for (let k = 0; k < K; k++) {
    keyUsage400[k] = new Array(baseCorners.length).fill(0);
  }

  for (const n of noteSeq) {
    const k = n[0], h = n[1], t = n[2];
    const startTime = Math.max(h, 0);
    const endTime = t < 0 ? h : Math.min(t, T - 1);

    const left400Idx = bisectLeft(baseCorners, startTime - 400);
    const leftIdx = bisectLeft(baseCorners, startTime);
    const rightIdx = bisectLeft(baseCorners, endTime);
    const right400Idx = bisectLeft(baseCorners, endTime + 400);

    // Inside note duration
    for (let idx = leftIdx; idx < rightIdx; idx++) {
      keyUsage400[k][idx] += 3.75 + Math.min(endTime - startTime, 1500) / 150;
    }

    // Before note
    for (let idx = left400Idx; idx < leftIdx; idx++) {
      keyUsage400[k][idx] += 3.75 - 3.75 / (400 * 400) * Math.pow(baseCorners[idx] - startTime, 2);
    }

    // After note
    for (let idx = rightIdx; idx < right400Idx; idx++) {
      keyUsage400[k][idx] += 3.75 - 3.75 / (400 * 400) * Math.pow(Math.abs(baseCorners[idx] - endTime), 2);
    }
  }

  return keyUsage400;
}

function computeAnchor(K, keyUsage400, baseCorners) {
  const anchor = new Array(baseCorners.length);

  for (let idx = 0; idx < baseCorners.length; idx++) {
    const counts = [];
    for (let k = 0; k < K; k++) {
      counts.push(keyUsage400[k][idx]);
    }
    counts.sort((a, b) => b - a);

    const nonzeroCounts = counts.filter(c => c !== 0);
    if (nonzeroCounts.length > 1) {
      let walk = 0;
      for (let i = 0; i < nonzeroCounts.length - 1; i++) {
        walk += nonzeroCounts[i] * (1 - 4 * Math.pow(0.5 - nonzeroCounts[i + 1] / nonzeroCounts[i], 2));
      }
      const maxWalk = nonzeroCounts.slice(0, -1).reduce((a, b) => a + b, 0);
      anchor[idx] = walk / maxWalk;
    } else {
      anchor[idx] = 0;
    }
  }

  for (let i = 0; i < anchor.length; i++) {
    anchor[i] = 1 + Math.min(anchor[i] - 0.18, 5 * Math.pow(anchor[i] - 0.22, 3));
  }

  return anchor;
}

function computeJbar(K, T, x, noteSeqByColumn, baseCorners) {
  const jacks = {};
  const deltas = {};
  const jackNerfer = (delta) => 1 - 7e-5 * Math.pow(0.15 + Math.abs(delta - 0.08), -4);

  for (let k = 0; k < K; k++) {
    jacks[k] = new Array(baseCorners.length).fill(0);
    deltas[k] = new Array(baseCorners.length).fill(1e9);

    const notes = noteSeqByColumn[k];
    for (let i = 0; i < notes.length - 1; i++) {
      const start = notes[i][1];
      const end = notes[i + 1][1];
      const leftIdx = bisectLeft(baseCorners, start);
      const rightIdx = bisectLeft(baseCorners, end);

      if (rightIdx <= leftIdx) continue;

      const delta = 0.001 * (end - start);
      const val = Math.pow(delta, -1) * Math.pow(delta + 0.11 * Math.pow(x, 1 / 4), -1);
      const jVal = val * jackNerfer(delta);

      for (let idx = leftIdx; idx < rightIdx; idx++) {
        jacks[k][idx] = jVal;
        deltas[k][idx] = delta;
      }
    }
  }

  const jbarKs = {};
  for (let k = 0; k < K; k++) {
    jbarKs[k] = smoothOnCorners(baseCorners, jacks[k], 500, 0.001, 'sum');
  }

  const jbar = new Array(baseCorners.length);
  for (let i = 0; i < baseCorners.length; i++) {
    const vals = [];
    const weights = [];
    for (let k = 0; k < K; k++) {
      vals.push(jbarKs[k][i]);
      weights.push(1 / deltas[k][i]);
    }

    let num = 0, den = 0;
    for (let k = 0; k < K; k++) {
      const v = Math.max(vals[k], 0);
      num += Math.pow(v, 5) * weights[k];
      den += weights[k];
    }
    jbar[i] = Math.pow(num / Math.max(1e-9, den), 1 / 5);
  }

  return { deltas, jbar };
}

function computeXbar(K, T, x, noteSeqByColumn, activeColumns, baseCorners) {
  const crossMatrix = [
    [-1],
    [0.075, 0.075],
    [0.125, 0.05, 0.125],
    [0.125, 0.125, 0.125, 0.125],
    [0.175, 0.25, 0.05, 0.25, 0.175],
    [0.175, 0.25, 0.175, 0.175, 0.25, 0.175],
    [0.225, 0.35, 0.25, 0.05, 0.25, 0.35, 0.225],
    [0.225, 0.35, 0.25, 0.225, 0.225, 0.25, 0.35, 0.225],
    [0.275, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.275],
    [0.275, 0.45, 0.35, 0.25, 0.275, 0.275, 0.25, 0.35, 0.45, 0.275],
    [0.325, 0.55, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.55, 0.325]
  ];

  const crossCoeff = crossMatrix[K];
  const xKs = {};
  const fastCross = {};

  for (let k = 0; k <= K; k++) {
    xKs[k] = new Array(baseCorners.length).fill(0);
    fastCross[k] = new Array(baseCorners.length).fill(0);
  }

  for (let k = 0; k <= K; k++) {
    let notesInPair;
    if (k === 0) {
      notesInPair = noteSeqByColumn[0];
    } else if (k === K) {
      notesInPair = noteSeqByColumn[K - 1];
    } else {
      notesInPair = [...noteSeqByColumn[k - 1], ...noteSeqByColumn[k]].sort((a, b) => a[1] - b[1]);
    }

    for (let i = 1; i < notesInPair.length; i++) {
      const start = notesInPair[i - 1][1];
      const end = notesInPair[i][1];
      const idxStart = bisectLeft(baseCorners, start);
      const idxEnd = bisectLeft(baseCorners, end);

      if (idxEnd <= idxStart) continue;

      const delta = 0.001 * (end - start);
      let val = 0.16 * Math.pow(Math.max(x, delta), -2);

      const colLeftInactive = (k === 0) ||
        (!activeColumns[idxStart].includes(k - 1) && !activeColumns[idxEnd].includes(k - 1));
      const colRightInactive = (k === K) ||
        (!activeColumns[idxStart].includes(k) && !activeColumns[idxEnd].includes(k));

      if (colLeftInactive || colRightInactive) {
        val *= (1 - crossCoeff[k]);
      }

      const fastVal = Math.max(0, 0.4 * Math.pow(Math.max(delta, 0.06, 0.75 * x), -2) - 80);

      for (let idx = idxStart; idx < idxEnd; idx++) {
        xKs[k][idx] = val;
        fastCross[k][idx] = fastVal;
      }
    }
  }

  const xBase = new Array(baseCorners.length).fill(0);
  for (let i = 0; i < baseCorners.length; i++) {
    let sum1 = 0;
    for (let k = 0; k <= K; k++) {
      sum1 += xKs[k][i] * crossCoeff[k];
    }
    let sum2 = 0;
    for (let k = 0; k < K; k++) {
      sum2 += Math.sqrt(fastCross[k][i] * crossCoeff[k] * fastCross[k + 1][i] * crossCoeff[k + 1]);
    }
    xBase[i] = sum1 + sum2;
  }

  return smoothOnCorners(baseCorners, xBase, 500, 0.001, 'sum');
}

function lnBodiesCountSparseRep(LNSeq, T) {
  const diff = {};

  for (const n of LNSeq) {
    const h = n[1], t = n[2];
    const t0 = Math.min(h + 60, t);
    const t1 = Math.min(h + 120, t);

    diff[t0] = (diff[t0] || 0) + 1.3;
    diff[t1] = (diff[t1] || 0) + (-1.3 + 1);
    diff[t] = (diff[t] || 0) - 1;
  }

  const points = new Set([0, T, ...Object.keys(diff).map(Number)]);
  const pointsArr = [...points].sort((a, b) => a - b);

  const values = [];
  const cumsumVals = [0];
  let curr = 0.0;

  for (let i = 0; i < pointsArr.length - 1; i++) {
    const pt = pointsArr[i];
    if (diff[pt] !== undefined) {
      curr += diff[pt];
    }
    const v = Math.min(curr, 2.5 + 0.5 * curr);
    values.push(v);
    const segLength = pointsArr[i + 1] - pointsArr[i];
    cumsumVals.push(cumsumVals[cumsumVals.length - 1] + segLength * v);
  }

  return { points: pointsArr, cumsum: cumsumVals, values };
}

function lnSum(a, b, lnRep) {
  const { points, cumsum, values } = lnRep;

  let lo = 0, hi = points.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (points[mid] <= a) lo = mid + 1;
    else hi = mid;
  }
  const i = lo - 1;

  lo = 0; hi = points.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (points[mid] <= b) lo = mid + 1;
    else hi = mid;
  }
  const j = lo - 1;

  let total = 0.0;
  if (i === j) {
    total = (b - a) * values[i];
  } else {
    total += (points[i + 1] - a) * values[i];
    total += cumsum[j] - cumsum[i + 1];
    total += (b - points[j]) * values[j];
  }
  return total;
}

function computePbar(K, T, x, noteSeq, lnRep, anchor, baseCorners) {
  const streamBooster = (delta) => {
    const t = 7.5 / delta;
    if (t > 160 && t < 360) {
      return 1 + 1.7e-7 * (t - 160) * Math.pow(t - 360, 2);
    }
    return 1;
  };

  const pStep = new Array(baseCorners.length).fill(0);

  for (let i = 0; i < noteSeq.length - 1; i++) {
    const hL = noteSeq[i][1];
    const hR = noteSeq[i + 1][1];
    const deltaTime = hR - hL;

    if (deltaTime < 1e-9) {
      const spike = 1000 * Math.pow(0.02 * (4 / x - 24), 1 / 4);
      const leftIdx = bisectLeft(baseCorners, hL);
      const rightIdx = bisectRight(baseCorners, hL);
      for (let idx = leftIdx; idx < rightIdx; idx++) {
        pStep[idx] += spike;
      }
      continue;
    }

    const leftIdx = bisectLeft(baseCorners, hL);
    const rightIdx = bisectLeft(baseCorners, hR);

    if (rightIdx <= leftIdx) continue;

    const delta = 0.001 * deltaTime;
    const v = 1 + 6 * 0.001 * lnSum(hL, hR, lnRep);
    const bVal = streamBooster(delta);

    let inc;
    if (delta < 2 * x / 3) {
      inc = Math.pow(delta, -1) * Math.pow(0.08 * Math.pow(x, -1) * (1 - 24 * Math.pow(x, -1) * Math.pow(delta - x / 2, 2)), 1 / 4) * Math.max(bVal, v);
    } else {
      inc = Math.pow(delta, -1) * Math.pow(0.08 * Math.pow(x, -1) * (1 - 24 * Math.pow(x, -1) * Math.pow(x / 6, 2)), 1 / 4) * Math.max(bVal, v);
    }

    for (let idx = leftIdx; idx < rightIdx; idx++) {
      pStep[idx] += Math.min(inc * anchor[idx], Math.max(inc, inc * 2 - 10));
    }
  }

  return smoothOnCorners(baseCorners, pStep, 500, 0.001, 'sum');
}

function computeAbar(K, T, x, noteSeqByColumn, activeColumns, deltas, ACorners, baseCorners) {
  const dks = {};
  for (let k = 0; k < K - 1; k++) {
    dks[k] = new Array(baseCorners.length).fill(0);
  }

  for (let i = 0; i < baseCorners.length; i++) {
    const cols = activeColumns[i];
    for (let j = 0; j < cols.length - 1; j++) {
      const k0 = cols[j];
      const k1 = cols[j + 1];
      dks[k0][i] = Math.abs(deltas[k0][i] - deltas[k1][i]) + 0.4 * Math.max(0, Math.max(deltas[k0][i], deltas[k1][i]) - 0.11);
    }
  }

  const aStep = new Array(ACorners.length).fill(1);

  for (let i = 0; i < ACorners.length; i++) {
    const s = ACorners[i];
    let idx = bisectLeft(baseCorners, s);
    if (idx >= baseCorners.length) idx = baseCorners.length - 1;

    const cols = activeColumns[idx];
    for (let j = 0; j < cols.length - 1; j++) {
      const k0 = cols[j];
      const k1 = cols[j + 1];
      const dVal = dks[k0][idx];

      if (dVal < 0.02) {
        aStep[i] *= Math.min(0.75 + 0.5 * Math.max(deltas[k0][idx], deltas[k1][idx]), 1);
      } else if (dVal < 0.07) {
        aStep[i] *= Math.min(0.65 + 5 * dVal + 0.5 * Math.max(deltas[k0][idx], deltas[k1][idx]), 1);
      }
    }
  }

  return smoothOnCorners(ACorners, aStep, 250, undefined, 'avg');
}

function computeRbar(K, T, x, noteSeqByColumn, tailSeq, baseCorners) {
  const iArr = new Array(baseCorners.length).fill(0);
  const rStep = new Array(baseCorners.length).fill(0);
  if (tailSeq.length < 2) return smoothOnCorners(baseCorners, rStep, 500, 0.001, 'sum');

  const timesByColumn = {};
  for (let i = 0; i < noteSeqByColumn.length; i++) {
    timesByColumn[i] = noteSeqByColumn[i].map(n => n[1]);
  }

  const iList = [];
  for (let i = 0; i < tailSeq.length; i++) {
    const note = tailSeq[i];
    const k = note[0], hI = note[1], tI = note[2];
    const nextNote = findNextNoteInColumn(note, timesByColumn[k], noteSeqByColumn);
    const hJ = nextNote[1];
    const iH = 0.001 * Math.abs(tI - hI - 80) / x;
    const iT = 0.001 * Math.abs(hJ - tI - 80) / x;
    iList.push(2 / (2 + Math.exp(-5 * (iH - 0.75)) + Math.exp(-5 * (iT - 0.75))));
  }

  for (let i = 0; i < tailSeq.length - 1; i++) {
    const tStart = tailSeq[i][2];
    const tEnd = tailSeq[i + 1][2];
    const leftIdx = bisectLeft(baseCorners, tStart);
    const rightIdx = bisectLeft(baseCorners, tEnd);

    if (rightIdx <= leftIdx) continue;

    for (let idx = leftIdx; idx < rightIdx; idx++) {
      iArr[idx] = 1 + iList[i];
    }

    const deltaR = 0.001 * (tEnd - tStart);
    const rVal = 0.08 * Math.pow(deltaR, -0.5) * Math.pow(x, -1) * (1 + 0.8 * (iList[i] + iList[i + 1]));

    for (let idx = leftIdx; idx < rightIdx; idx++) {
      rStep[idx] = rVal;
    }
  }

  return smoothOnCorners(baseCorners, rStep, 500, 0.001, 'sum');
}

function computeCAndKs(K, T, noteSeq, keyUsage, baseCorners) {
  const noteHitTimes = noteSeq.map(n => n[1]).sort((a, b) => a - b);

  const cStep = new Array(baseCorners.length);
  for (let i = 0; i < baseCorners.length; i++) {
    const s = baseCorners[i];
    const low = s - 500;
    const high = s + 500;
    const cnt = bisectLeft(noteHitTimes, high) - bisectLeft(noteHitTimes, low);
    cStep[i] = cnt;
  }

  const ksStep = new Array(baseCorners.length);
  for (let i = 0; i < baseCorners.length; i++) {
    let cnt = 0;
    for (let k = 0; k < K; k++) {
      if (keyUsage[k][i]) cnt++;
    }
    ksStep[i] = Math.max(cnt, 1);
  }

  return { cStep, ksStep };
}

function calculate(fileContent, mod) {
  mod = mod || 'NM';
  return calculateCore(preprocessFile(fileContent, mod));
}

function calculateFromParsed(p, mod) {
  mod = mod || 'NM';
  const pre = preprocessParsedData(p, mod);
  const result = calculateCore(pre);
  result.variety = computeVarietyFromPre(pre.noteSeq, pre.noteSeqByColumn, pre.K);
  return result;
}

function computeVarietyFromPre(noteSeq, noteSeqByColumn, keyCount) {
  const tailSeq = noteSeq.filter(n => n[2] >= 0).sort((a, b) => a[2] - b[2]);

  const headGaps = [];
  for (let i = 0; i < noteSeq.length - 1; i++) {
    headGaps.push(noteSeq[i + 1][1] - noteSeq[i][1]);
  }
  const tailSeqGaps = [];
  for (let i = 0; i < tailSeq.length - 1; i++) {
    tailSeqGaps.push(tailSeq[i + 1][2] - tailSeq[i][2]);
  }

  const headVariety = raoQuadraticEntropyLog(headGaps);
  const tailVariety = raoQuadraticEntropyLog(tailSeqGaps);

  const headGapsNew = [];
  for (let k = 0; k < keyCount; k++) {
    const heads = noteSeqByColumn[k];
    for (let i = 0; i < heads.length - 1; i++) {
      headGapsNew.push(heads[i + 1][1] - heads[i][1]);
    }
  }
  const colVariety = 2.5 * raoQuadraticEntropyLog(headGapsNew, 2);

  return 0.5 * headVariety + 0.11 * tailVariety + 0.45 * colVariety;
}

function calculateCore(pre) {
  const { x, K, T, noteSeq, noteSeqByColumn, LNSeq, tailSeq } = pre;

  const { allCorners, baseCorners, ACorners } = getCorners(T, noteSeq);

  const keyUsage = getKeyUsage(K, T, noteSeq, baseCorners);

  const activeColumns = new Array(baseCorners.length);
  for (let i = 0; i < baseCorners.length; i++) {
    activeColumns[i] = [];
    for (let k = 0; k < K; k++) {
      if (keyUsage[k][i]) activeColumns[i].push(k);
    }
  }

  const keyUsage400 = getKeyUsage400(K, T, noteSeq, baseCorners);
  const anchor = computeAnchor(K, keyUsage400, baseCorners);

  const { deltas, jbar } = computeJbar(K, T, x, noteSeqByColumn, baseCorners);
  const jbarInterp = interpValues(allCorners, baseCorners, jbar);

  const xbar = computeXbar(K, T, x, noteSeqByColumn, activeColumns, baseCorners);
  const xbarInterp = interpValues(allCorners, baseCorners, xbar);

  const lnRep = lnBodiesCountSparseRep(LNSeq, T);

  const pbar = computePbar(K, T, x, noteSeq, lnRep, anchor, baseCorners);
  const pbarInterp = interpValues(allCorners, baseCorners, pbar);

  const abar = computeAbar(K, T, x, noteSeqByColumn, activeColumns, deltas, ACorners, baseCorners);
  const abarInterp = interpValues(allCorners, ACorners, abar);

  const rbar = computeRbar(K, T, x, noteSeqByColumn, tailSeq, baseCorners);
  const rbarInterp = interpValues(allCorners, baseCorners, rbar);

  const { cStep, ksStep } = computeCAndKs(K, T, noteSeq, keyUsage, baseCorners);
  const cArr = stepInterp(allCorners, baseCorners, cStep);
  const ksArr = stepInterp(allCorners, baseCorners, ksStep);

  const sAll = new Array(allCorners.length);
  const tAll = new Array(allCorners.length);
  const dAll = new Array(allCorners.length);

  for (let i = 0; i < allCorners.length; i++) {
    const term1 = Math.pow(abarInterp[i], 3 / ksArr[i]) * Math.min(jbarInterp[i], 8 + 0.85 * jbarInterp[i]);
    const term2 = Math.pow(abarInterp[i], 2 / 3) * (0.8 * pbarInterp[i] + rbarInterp[i] * 35 / (cArr[i] + 8));
    sAll[i] = Math.pow(0.4 * Math.pow(term1, 1.5) + (1 - 0.4) * Math.pow(term2, 1.5), 2 / 3);
    tAll[i] = (Math.pow(abarInterp[i], 3 / ksArr[i]) * xbarInterp[i]) / (xbarInterp[i] + sAll[i] + 1);
    dAll[i] = 2.7 * Math.pow(sAll[i], 0.5) * Math.pow(tAll[i], 1.5) + sAll[i] * 0.27;
  }

  const gaps = new Array(allCorners.length);
  gaps[0] = (allCorners[1] - allCorners[0]) / 2.0;
  gaps[gaps.length - 1] = (allCorners[allCorners.length - 1] - allCorners[allCorners.length - 2]) / 2.0;
  for (let i = 1; i < allCorners.length - 1; i++) {
    gaps[i] = (allCorners[i + 1] - allCorners[i - 1]) / 2.0;
  }

  const effectiveWeights = new Array(allCorners.length);
  for (let i = 0; i < allCorners.length; i++) {
    effectiveWeights[i] = cArr[i] * gaps[i];
  }

  const sortedIndices = [];
  for (let i = 0; i < dAll.length; i++) {
    sortedIndices.push({ idx: i, d: dAll[i] });
  }
  sortedIndices.sort((a, b) => a.d - b.d);

  const dSorted = sortedIndices.map(s => s.d);
  const wSorted = sortedIndices.map(s => effectiveWeights[s.idx]);

  const cumWeights = new Array(wSorted.length);
  let cs = 0;
  for (let i = 0; i < wSorted.length; i++) {
    cs += wSorted[i];
    cumWeights[i] = cs;
  }
  const totalWeight = cumWeights[cumWeights.length - 1];
  const normCumWeights = cumWeights.map(w => w / totalWeight);

  const targetPercentiles = [0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815];

  const indices = targetPercentiles.map(p => bisectLeft(normCumWeights, p));

  const percentile93 = (dSorted[indices[0]] + dSorted[indices[1]] + dSorted[indices[2]] + dSorted[indices[3]]) / 4;
  const percentile83 = (dSorted[indices[4]] + dSorted[indices[5]] + dSorted[indices[6]] + dSorted[indices[7]]) / 4;

  let num = 0, den = 0;
  for (let i = 0; i < dSorted.length; i++) {
    num += Math.pow(dSorted[i], 5) * wSorted[i];
    den += wSorted[i];
  }
  const weightedMean = Math.pow(num / den, 1 / 5);

  let SR = (0.88 * percentile93) * 0.25 + (0.94 * percentile83) * 0.2 + weightedMean * 0.55;
  let totalNotes = 0;
  for (const n of noteSeq) {
    let contrib = 1;
    if (n[2] >= 0) {
      contrib = 1 + 0.5 * Math.min(n[2] - n[1], 1000) / 200;
    }
    totalNotes += contrib;
  }

  SR *= totalNotes / (totalNotes + 60);
  SR = rescaleHigh(SR);
  SR *= 0.975;

  // Compute spikiness (weighted variance of D^8)
  let varianceTop = 0;
  for (let i = 0; i < dSorted.length; i++) {
    const diff = Math.pow(dSorted[i], 8) - Math.pow(weightedMean, 8);
    varianceTop += diff * diff * wSorted[i];
  }
  const weightedVariance = Math.pow(varianceTop / den, 1 / 8);
  const spikiness = Math.sqrt(weightedVariance) / weightedMean;

  // Compute switches (column transition measure)
  const switches = computeSwitches(noteSeq, tailSeq, allCorners, ksArr, dAll, effectiveWeights);

  return { sr: SR, spikiness: spikiness, switches: switches };
}

function computeSwitches(noteSeq, tailSeq, allCorners, ksArr, weights) {
  const heads = noteSeq.map(n => n[1]);
  const idxList = heads.map(h => bisectLeft(allCorners, h));

  const ksAtNote = idxList.slice(0, -1).map(i => ksArr[i]);
  const weightsAtNote = idxList.slice(0, -1).map(i => weights[i]);

  const headGaps = [];
  for (let i = 0; i < heads.length - 1; i++) {
    headGaps.push(heads[i + 1] - heads[i]);
  }

  // sliding window average via prefix sum — O(n) instead of O(n×k)
  const numHeadGaps = headGaps.length;
  function slidingWindowAvg(arr, window) {
    const n = arr.length;
    const pref = new Array(n);
    pref[0] = arr[0];
    for (let i = 1; i < n; i++) pref[i] = pref[i - 1] + arr[i];
    const avgs = new Array(n);
    for (let i = 0; i < n; i++) {
      const start = Math.max(0, i - window);
      const end = Math.min(i + window, n - 1);
      const sum = pref[end] - (start > 0 ? pref[start - 1] : 0);
      avgs[i] = sum / (end - start + 1);
    }
    return avgs;
  }

  const avgs = slidingWindowAvg(headGaps, 50);

  let signatureHead = 0;
  for (let i = 0; i < numHeadGaps; i++) {
    if (avgs[i] > 0) {
      signatureHead += Math.sqrt((headGaps[i] / avgs[i] / numHeadGaps) * weightsAtNote[i])
        * Math.pow(ksAtNote[i], 0.25);
    }
  }

  let sumRefHead = 0;
  for (let i = 0; i < numHeadGaps; i++) {
    if (avgs[i] > 0) sumRefHead += (headGaps[i] / avgs[i]) * weightsAtNote[i];
  }
  const refSignatureHead = Math.sqrt(sumRefHead);

  const tails = tailSeq.map(n => n[2]);
  const idxListTails = tails.map(t => bisectLeft(allCorners, t));
  const ksAtTail = idxListTails.slice(0, -1).map(i => ksArr[i]);
  const weightsAtTail = idxListTails.slice(0, -1).map(i => weights[i]);

  const tailGaps = [];
  for (let i = 0; i < tails.length - 1; i++) {
    tailGaps.push(tails[i + 1] - tails[i]);
  }

  let signatureTail = 0, refSignatureTail = 0;
  if (tails.length > 0 && tails[tails.length - 1] > tails[0] && tailGaps.length > 0) {
    const numTailGaps = tailGaps.length;
    const avgsTail = slidingWindowAvg(tailGaps, 50);
    for (let i = 0; i < numTailGaps; i++) {
      if (avgsTail[i] > 0) {
        signatureTail += Math.sqrt((tailGaps[i] / avgsTail[i] / numTailGaps) * weightsAtTail[i])
          * Math.pow(ksAtTail[i], 0.25);
      }
    }
    let sumRefTail = 0;
    for (let i = 0; i < numTailGaps; i++) {
      if (avgsTail[i] > 0) sumRefTail += (tailGaps[i] / avgsTail[i]) * weightsAtTail[i];
    }
    refSignatureTail = Math.sqrt(sumRefTail);
  }

  const numerator = signatureHead * numHeadGaps + signatureTail * tailGaps.length;
  const denominator = refSignatureHead * numHeadGaps + refSignatureTail * tailGaps.length;
  const sw = denominator > 0 ? numerator / denominator : 0.5;

  return sw / 2 + 0.5;
}

function raoQuadraticEntropyLog(values, logIterations) {
  logIterations = logIterations || 1;
  if (!values || values.length === 0) return 0;

  const counts = {};
  for (const v of values) {
    counts[v] = (counts[v] || 0) + 1;
  }
  const unique = Object.keys(counts).map(Number);
  const total = values.length;
  const p = unique.map(v => counts[v] / total);

  function distanceFunc(x, y, logIter) {
    let acc = Math.abs(x - y);
    for (let i = 0; i < logIter; i++) {
      acc = Math.log(1 + acc);
    }
    return acc;
  }

  // WARNING: O(n²) on unique values — for dense beatmaps where unique ≈ n, this is O(n²)
  let Q = 0;
  for (let i = 0; i < unique.length; i++) {
    for (let j = 0; j < unique.length; j++) {
      Q += p[i] * p[j] * distanceFunc(unique[i], unique[j], logIterations);
    }
  }
  return Q;
}
