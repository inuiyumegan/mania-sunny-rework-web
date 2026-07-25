(function () {
  'use strict';
  var mapData = null;
  var debounceTimer = null;
  var odRecalcTimer = null;
  var lastBeatmapId = null;
  var activeAlgo = 'auto';
  var activeMods = {};

  var RC4K_TABLE = [
    [1.502,1.631,"I1l"],[1.631,1.760,"I1ml"],[1.760,1.890,"I1"],[1.890,2.019,"I1mh"],[2.019,2.148,"I1h"],
    [2.148,2.278,"I2l"],[2.278,2.407,"I2ml"],[2.407,2.502,"I2"],[2.502,2.560,"I2mh"],[2.560,2.619,"I2h"],
    [2.619,2.679,"I3l"],[2.679,2.737,"I3ml"],[2.737,2.821,"I3"],[2.821,2.929,"I3mh"],[2.929,3.037,"I3h"],
    [3.037,3.145,"1l"],[3.145,3.253,"1ml"],[3.253,3.346,"1"],[3.346,3.424,"1mh"],[3.424,3.503,"1h"],
    [3.503,3.581,"2l"],[3.581,3.659,"2ml"],[3.659,3.701,"2"],[3.701,3.708,"2mh"],[3.708,3.714,"2h"],
    [3.714,3.720,"3l"],[3.720,3.727,"3ml"],[3.727,3.810,"3"],[3.810,3.970,"3mh"],[3.970,4.130,"3h"],
    [4.130,4.290,"4l"],[4.290,4.450,"4ml"],[4.450,4.569,"4"],[4.569,4.648,"4mh"],[4.648,4.726,"4h"],
    [4.726,4.804,"5l"],[4.804,4.883,"5ml"],[4.883,4.972,"5"],[4.972,5.072,"5mh"],[5.072,5.173,"5h"],
    [5.173,5.273,"6l"],[5.273,5.373,"6ml"],[5.373,5.441,"6"],[5.441,5.476,"6mh"],[5.476,5.511,"6h"],
    [5.511,5.547,"7l"],[5.547,5.582,"7ml"],[5.582,5.646,"7"],[5.646,5.738,"7mh"],[5.738,5.829,"7h"],
    [5.829,5.921,"8l"],[5.921,6.013,"8ml"],[6.013,6.069,"8"],[6.069,6.090,"8mh"],[6.090,6.110,"8h"],
    [6.110,6.130,"9l"],[6.130,6.151,"9ml"],[6.151,6.205,"9"],[6.205,6.294,"9mh"],[6.294,6.382,"9h"],
    [6.382,6.471,"10l"],[6.471,6.560,"10ml"],[6.560,6.616,"10"],[6.616,6.641,"10mh"],[6.641,6.666,"10h"],
    [6.666,6.691,"Al"],[6.691,6.716,"Aml"],[6.716,6.773,"A"],[6.773,6.860,"Amh"],[6.860,6.947,"Ah"],
    [6.947,7.034,"Bl"],[7.034,7.121,"Bml"],[7.121,7.214,"B"],[7.214,7.312,"Bmh"],[7.312,7.410,"Bh"],
    [7.410,7.509,"Gl"],[7.509,7.607,"Gml"],[7.607,7.705,"G"],[7.705,7.803,"Gmh"],[7.803,7.901,"Gh"],
    [7.901,8.000,"Dl"],[8.000,8.098,"Dml"],[8.098,8.244,"D"],[8.244,8.438,"Dmh"],[8.438,8.631,"Dh"],
    [8.631,8.825,"El"],[8.825,9.019,"Eml"],[9.019,9.172,"E"],[9.172,9.285,"Emh"],[9.285,9.398,"Eh"],
    [9.398,9.511,"Zl"],[9.511,9.624,"Zml"],[9.624,9.742,"Z"],[9.742,9.867,"Zmh"],[9.867,9.991,"Zh"],
    [9.991,10.116,"Hl"],[10.116,10.241,"Hml"],[10.241,10.358,"H"],[10.358,10.468,"Hmh"],[10.468,10.578,"Hh"],
    [10.578,10.689,"Ql"],[10.689,10.799,"Qml"],[10.799,10.909,"Q"],[10.909,11.019,"Qmh"],[11.019,11.129,"Qh"]
  ];

  var GREEK_CODE = { A:'α',B:'β',G:'γ',D:'δ',E:'ε',Z:'ζ',H:'η',Q:'θ' };
  var K7_GREEK = { G:'γ', A:'ψ', Z:'ζ', S:'★' };
  var INTRO_MAP = { I1:'intro 1', I2:'intro 2', I3:'intro 3' };

  function formatTier(code, keys) {
    if (!code) return '??';
    if (code.startsWith('>')) return '>' + formatTier(code.slice(1), keys);
    if (code.startsWith('<')) return '<' + formatTier(code.slice(1), keys);

    var base = code, suffix = '';
    if (code.match(/[lhm]$/)) {
      var m = code.match(/^(.+?)(ml|mh|l|h)$/);
      if (m) { base = m[1]; suffix = m[2]; }
    }

    var isNum = /^\d+$/.test(base);
    var isLN = base.startsWith('L');
    var realBase = isLN ? base.slice(1) : base;
    var isGreek = !isNum && !(realBase in INTRO_MAP);

    var baseStr, shortBase;
    if (isLN) {
      shortBase = realBase;
      if (!isNum) {
        var gk = keys === 7 ? K7_GREEK : GREEK_CODE;
        shortBase = gk[realBase] || realBase;
      }
      baseStr = 'LN ' + shortBase;
    } else if (realBase in INTRO_MAP) {
      baseStr = INTRO_MAP[realBase];
      shortBase = baseStr;
    } else if (isGreek) {
      var gk = keys === 7 ? K7_GREEK : GREEK_CODE;
      shortBase = gk[realBase] || realBase;
      baseStr = keys === 4 ? shortBase : 'reg ' + shortBase;
    } else {
      shortBase = realBase;
      baseStr = (keys === 4 ? 'rf' : 'reg') + realBase;
    }

    if (suffix === 'l') return baseStr + '⁻';
    if (suffix === 'ml') return baseStr + '/' + shortBase + '⁻';
    if (suffix === 'mh') return baseStr + '/' + shortBase + '⁺';
    if (suffix === 'h') return baseStr + '⁺';
    return baseStr;
  }

  function rcLookup(sr, keys) {
    var table;
    if (keys === 4) table = RC4K_TABLE;
    else if (keys === 6) table = RC6K_TABLE;
    else if (keys === 7) table = RC7K_TABLE;
    else return '';
    for (var i = 0; i < table.length; i++) {
      if (sr >= table[i][0] && sr <= table[i][1]) return formatTier(table[i][2], keys);
    }
    if (sr < table[0][0]) return '<' + formatTier(table[0][2], keys);
    return '>' + formatTier(table[table.length - 1][2], keys);
  }

  var RC6K_TABLE = [
    [3.430,3.526,"0l"],[3.526,3.622,"0ml"],[3.622,3.718,"0"],[3.718,3.814,"0mh"],[3.814,3.910,"0h"],
    [3.910,4.006,"1l"],[4.006,4.102,"1ml"],[4.102,4.210,"1"],[4.210,4.330,"1mh"],[4.330,4.450,"1h"],
    [4.450,4.570,"2l"],[4.570,4.690,"2ml"],[4.690,4.831,"2"],[4.831,4.993,"2mh"],[4.993,5.155,"2h"],
    [5.155,5.317,"3l"],[5.317,5.479,"3ml"],[5.479,5.590,"3"],[5.590,5.650,"3mh"],[5.650,5.710,"3h"],
    [5.710,5.770,"4l"],[5.770,5.830,"4ml"],[5.830,5.919,"4"],[5.919,6.037,"4mh"],[6.037,6.155,"4h"],
    [6.155,6.273,"5l"],[6.273,6.391,"5ml"],[6.391,6.490,"5"],[6.490,6.570,"5mh"],[6.570,6.650,"5h"],
    [6.650,6.730,"6l"],[6.730,6.810,"6ml"],[6.810,6.873,"6"],[6.873,6.919,"6mh"],[6.919,6.965,"6h"],
    [6.965,7.011,"7l"],[7.011,7.057,"7ml"],[7.057,7.119,"7"],[7.119,7.197,"7mh"],[7.197,7.275,"7h"],
    [7.275,7.353,"8l"],[7.353,7.431,"8ml"],[7.431,7.503,"8"],[7.503,7.569,"8mh"],[7.569,7.635,"8h"],
    [7.635,7.701,"9l"],[7.701,7.767,"9ml"],[7.767,7.833,"9"],[7.833,7.899,"9mh"],[7.899,7.965,"9h"]
  ];

  var RC7K_TABLE = [
    [3.5085,3.6631,"0l"],[3.6631,3.8177,"0ml"],[3.8177,3.9723,"0"],[3.9723,4.1269,"0mh"],[4.1269,4.2815,"0h"],
    [4.2815,4.4361,"1l"],[4.4361,4.5907,"1ml"],[4.5907,4.7202,"1"],[4.7202,4.8246,"1mh"],[4.8246,4.929,"1h"],
    [4.929,5.0334,"2l"],[5.0334,5.1378,"2ml"],[5.1378,5.2379,"2"],[5.2379,5.3337,"2mh"],[5.3337,5.4295,"2h"],
    [5.4295,5.5253,"3l"],[5.5253,5.6211,"3ml"],[5.6211,5.6927,"3"],[5.6927,5.7401,"3mh"],[5.7401,5.7875,"3h"],
    [5.7875,5.8349,"4l"],[5.8349,5.8823,"4ml"],[5.8823,5.9313,"4"],[5.9313,5.9819,"4mh"],[5.9819,6.0325,"4h"],
    [6.0325,6.0831,"5l"],[6.0831,6.1337,"5ml"],[6.1337,6.2176,"5"],[6.2176,6.3348,"5mh"],[6.3348,6.452,"5h"],
    [6.452,6.5692,"6l"],[6.5692,6.6864,"6ml"],[6.6864,6.7772,"6"],[6.7772,6.8416,"6mh"],[6.8416,6.906,"6h"],
    [6.906,6.9704,"7l"],[6.9704,7.0348,"7ml"],[7.0348,7.1085,"7"],[7.1085,7.1915,"7mh"],[7.1915,7.2745,"7h"],
    [7.2745,7.3575,"8l"],[7.3575,7.4405,"8ml"],[7.4405,7.5096,"8"],[7.5096,7.5648,"8mh"],[7.5648,7.62,"8h"],
    [7.62,7.6752,"9l"],[7.6752,7.7304,"9ml"],[7.7304,7.8134,"9"],[7.8134,7.9242,"9mh"],[7.9242,8.035,"9h"],
    [8.035,8.1458,"10l"],[8.1458,8.2566,"10ml"],[8.2566,8.357,"10"],[8.357,8.447,"10mh"],[8.447,8.537,"10h"],
    [8.537,8.627,"Gl"],[8.627,8.717,"Gml"],[8.717,8.8079,"G"],[8.8079,8.8997,"Gmh"],[8.8997,8.9915,"Gh"],
    [8.9915,9.0833,"Al"],[9.0833,9.1751,"Aml"],[9.1751,9.2921,"A"],[9.2921,9.4343,"Amh"],[9.4343,9.5765,"Ah"],
    [9.5765,9.7187,"Zl"],[9.7187,9.8609,"Zml"],[9.8609,9.9728,"Z"],[9.9728,10.0544,"Zmh"],[10.0544,10.136,"Zh"],
    [10.136,10.2176,"Sl"],[10.2176,10.2992,"Sml"],[10.2992,10.3808,"S"],[10.3808,10.4624,"Smh"],[10.4624,10.544,"Sh"]
  ];

  var LN4K_TABLE = [
    [4.832,4.898,"L5"],[4.898,4.963,"L5mh"],[4.963,5.095,"L5h"],
    [5.095,5.160,"L6l"],[5.143,5.160,"L6ml"],[5.160,5.213,"L6"],[5.213,5.264,"L6mh"],[5.264,5.314,"L6h"],
    [5.314,5.446,"L7l"],[5.446,5.521,"L7ml"],[5.521,5.577,"L7"],[5.577,5.631,"L7mh"],[5.631,5.686,"L7h"],
    [5.686,5.740,"L8l"],[5.740,5.794,"L8ml"],[5.794,5.853,"L8"],[5.853,5.917,"L8mh"],[5.917,5.981,"L8h"],
    [5.981,6.044,"L9l"],[6.044,6.108,"L9ml"],[6.108,6.175,"L9"],[6.175,6.246,"L9mh"],[6.246,6.318,"L9h"],
    [6.318,6.389,"L10l"],[6.389,6.461,"L10ml"],[6.461,6.534,"L10"],[6.534,6.611,"L10mh"],[6.611,6.687,"L10h"],
    [6.687,6.763,"L11l"],[6.763,6.839,"L11ml"],[6.839,6.898,"L11"],[6.898,6.920,"L11mh"],[6.920,6.941,"L11h"],
    [6.941,7.023,"L12l"],[7.023,7.068,"L12ml"],[7.068,7.136,"L12"],[7.136,7.225,"L12mh"],[7.225,7.313,"L12h"],
    [7.313,7.401,"L13l"],[7.401,7.490,"L13ml"],[7.490,7.578,"L13"],[7.578,7.665,"L13mh"],[7.665,7.753,"L13h"],
    [7.753,7.841,"L14l"],[7.841,7.929,"L14ml"],[7.929,8.013,"L14"],[8.013,8.093,"L14mh"],[8.093,8.173,"L14h"],
    [8.173,8.253,"L15l"],[8.253,8.333,"L15ml"],[8.333,8.389,"L15"],[8.389,8.428,"L15mh"],[8.428,8.470,"L15h"],
    [8.470,8.509,"L16l"],[8.509,8.548,"L16ml"],[8.548,8.586,"L16"],[8.586,8.635,"L16mh"],[8.635,8.908,"L16h"],
    [8.908,9.044,"L17l"],[9.044,9.180,"L17ml"],[9.180,9.316,"L17"],[9.316,9.452,"L17mh"],[9.452,9.589,"L17h"]
  ];

  var LN6K_TABLE = [
    [3.530,3.718,"L0l"],[3.718,3.906,"L0ml"],[3.906,4.094,"L0"],[4.094,4.282,"L0mh"],[4.282,4.470,"L0h"],
    [4.470,4.658,"L1l"],[4.658,4.846,"L1ml"],[4.846,4.974,"L1"],[4.974,5.042,"L1mh"],[5.042,5.110,"L1h"],
    [5.110,5.178,"L2l"],[5.178,5.246,"L2ml"],[5.246,5.294,"L2"],[5.294,5.322,"L2mh"],[5.322,5.350,"L2h"],
    [5.350,5.378,"L3l"],[5.378,5.406,"L3ml"],[5.406,5.513,"L3"],[5.513,5.699,"L3mh"],[5.699,5.885,"L3h"],
    [5.885,6.071,"L4l"],[6.071,6.257,"L4ml"],[6.257,6.347,"L4"],[6.347,6.341,"L4mh"],[6.341,6.335,"L4h"],
    [6.335,6.329,"L5l"],[6.329,6.323,"L5ml"],[6.323,6.371,"L5"],[6.371,6.473,"L5mh"],[6.473,6.575,"L5h"],
    [6.575,6.677,"L6l"],[6.677,6.779,"L6ml"],[6.779,6.840,"L6"],[6.840,6.860,"L6mh"],[6.860,6.880,"L6h"],
    [6.880,6.900,"L7l"],[6.900,6.920,"L7ml"],[6.920,6.973,"L7"],[6.973,7.059,"L7mh"],[7.059,7.145,"L7h"],
    [7.145,7.231,"L8l"],[7.231,7.317,"L8ml"],[7.317,7.366,"L8"],[7.366,7.378,"L8mh"],[7.378,7.390,"L8h"],
    [7.390,7.402,"L9l"],[7.402,7.414,"L9ml"],[7.414,7.469,"L9"],[7.469,7.567,"L9mh"],[7.567,7.665,"L9h"],
    [7.665,7.763,"L10l"],[7.763,7.861,"L10ml"],[7.861,7.952,"L10"],[7.952,8.036,"L10mh"],[8.036,8.120,"L10h"],
    [8.120,8.204,"L11l"],[8.204,8.288,"L11ml"],[8.288,8.367,"L11"],[8.367,8.441,"L11mh"],[8.441,8.515,"L11h"],
    [8.515,8.589,"L12l"],[8.589,8.663,"L12ml"],[8.663,8.737,"L12"],[8.737,8.811,"L12mh"],[8.811,8.885,"L12h"],
    [8.885,8.959,"L13l"],[8.959,9.033,"L13ml"],[9.033,9.112,"L13"],[9.112,9.196,"L13mh"],[9.196,9.280,"L13h"],
    [9.280,9.364,"L14l"],[9.364,9.448,"L14ml"],[9.448,9.532,"L14"],[9.532,9.616,"L14mh"],[9.616,9.700,"L14h"]
  ];

  var LN7K_TABLE = [
    [4.836,4.9704,"L3l"],[4.9704,5.1048,"L3ml"],[5.1048,5.2392,"L3"],[5.2392,5.3736,"L3mh"],[5.3736,5.508,"L3h"],
    [5.508,5.5592,"L4l"],[5.5592,5.6104,"L4ml"],[5.6104,5.6616,"L4"],[5.6616,5.7128,"L4mh"],[5.7128,5.764,"L4h"],
    [5.764,5.8824,"L5l"],[5.8824,6.0008,"L5ml"],[6.0008,6.1192,"L5"],[6.1192,6.2376,"L5mh"],[6.2376,6.356,"L5h"],
    [6.356,6.4708,"L6l"],[6.4708,6.5856,"L6ml"],[6.5856,6.7004,"L6"],[6.7004,6.8152,"L6mh"],[6.8152,6.93,"L6h"],
    [6.93,6.9372,"L7l"],[6.9372,6.9444,"L7ml"],[6.9444,6.9516,"L7"],[6.9516,6.9588,"L7mh"],[6.9588,7.053,"L7h"],
    [7.053,7.1472,"L8l"],[7.1472,7.2414,"L8ml"],[7.2414,7.3356,"L8"],[7.3356,7.4298,"L8mh"],[7.4298,7.4872,"L8h"],
    [7.4872,7.5446,"L9l"],[7.5446,7.602,"L9ml"],[7.602,7.6594,"L9"],[7.6594,7.7168,"L9mh"],[7.7168,7.8572,"L9h"],
    [7.8572,7.9976,"L10l"],[7.9976,8.138,"L10ml"],[8.138,8.2784,"L10"],[8.2784,8.4188,"L10mh"],[8.4188,8.4938,"L10h"],
    [8.4938,8.5688,"LGl"],[8.5688,8.6438,"LGml"],[8.6438,8.7188,"LG"],[8.7188,8.7938,"LGmh"],[8.7938,8.8878,"LGh"],
    [8.8878,8.9818,"LAl"],[8.9818,9.0758,"LAml"],[9.0758,9.1698,"LA"],[9.1698,9.2638,"LAmh"],[9.2638,9.3784,"LAh"],
    [9.3784,9.493,"LZl"],[9.493,9.6076,"LZml"],[9.6076,9.7222,"LZ"],[9.7222,9.8368,"LZmh"],[9.8368,9.975,"LZh"],
    [9.975,10.1132,"LSl"],[10.1132,10.2514,"LSml"],[10.2514,10.3896,"LS"],[10.3896,10.5278,"LSmh"],[10.5278,10.666,"LSh"]
  ];

  function lnLookup(sr, keys) {
    var table;
    if (keys === 4) table = LN4K_TABLE;
    else if (keys === 6) table = LN6K_TABLE;
    else if (keys === 7) table = LN7K_TABLE;
    else return '';
    for (var i = 0; i < table.length; i++) {
      if (sr >= table[i][0] && sr <= table[i][1]) return formatTier(table[i][2], keys);
    }
    if (sr < table[0][0]) return '<' + formatTier(table[0][2], keys);
    return '>' + formatTier(table[table.length - 1][2], keys);
  }

  function $(id) { return document.getElementById(id); }

  function estimateSR(srNM, srDT, srHT, rate) {
    if (!srNM) return 0;
    if (Math.abs(rate - 1.0) < 0.001) return srNM;
    if (srDT && srDT > srNM && Math.abs(rate - 1.5) < 0.001) return srDT;
    if (srHT && srHT < srNM && Math.abs(rate - 0.75) < 0.001) return srHT;
    if (srDT && srDT > srNM) {
      var k = Math.log(srDT / srNM) / Math.log(1.5);
      return srNM * Math.pow(rate, k);
    }
    return srNM * rate;
  }

  function computeSunnyPP(sr, od, accuracy, miss, mods, totalNotes, variety, accScalar, isHO, isIN) {
    // Real Sunny Rework PP formula from ManiaPerformanceCalculator.cs
    var acc = Math.min(1, Math.max(0, (accuracy || 100) / 100));
    var modsStr = mods ? mods.join('') : '';

    // Use HO/IN specific variety and accScalar if available
    if (isHO && mapData && typeof mapData.varietyHO !== 'undefined') variety = mapData.varietyHO;
    if (isHO && mapData && typeof mapData.accScalarHO !== 'undefined') accScalar = mapData.accScalarHO;
    if (isIN && mapData && typeof mapData.varietyIN !== 'undefined') variety = mapData.varietyIN;
    if (isIN && mapData && typeof mapData.accScalarIN !== 'undefined') accScalar = mapData.accScalarIN;

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

  function formatPP(val) { return val < 10 ? val.toFixed(1) : Math.round(val).toString(); }
  function srColor(sr) { if (sr >= 8) return '#ff6b6b'; if (sr >= 6) return '#ffd93d'; if (sr >= 4) return '#6bcb77'; return '#4d96ff'; }
  function formatTime(sec) { if (!sec || sec <= 0) return '--'; var m = Math.floor(sec / 60); var s = Math.floor(sec % 60); return m + ':' + (s < 10 ? '0' : '') + s; }

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
    return { acc: acc, miss: miss, rate: rate };
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

    ppEl.innerHTML = '<span style="color:' + srColor(sunnyPP.pp / 6) + ';font-weight:700;">' + formatPP(sunnyPP.pp) + ' / ' + formatPP(sunnyPP100.pp) + '</span>pp';
    ppOsuEl.innerHTML = '<span style="color:' + srColor(officialPP / 6) + ';font-weight:700;">' + formatPP(officialPP) + '</span>pp';
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
    if (activeAlgo === 'daniel') return mapData['danielSR' + srSuffix] || mapData['sr' + srSuffix] || 0;
    if (activeAlgo === 'sunny') return mapData['sr' + srSuffix] || 0;
    if (mapData.columnCount === 4) {
      var d = mapData['danielSR' + srSuffix];
      var dNM = mapData.danielSR;
      if (d && d > 0 && dNM >= 6.36) return d;
    }
    return mapData['sr' + srSuffix] || 0;
  }

  function getEffectiveOD() {
    var v = parseFloat($('stat-od').value);
    var maxOD = activeMods.SV2 ? 15 : 10;
    return isNaN(v) ? (mapData ? mapData.od || 8 : 8) : Math.min(maxOD, Math.max(0, v));
  }

  function updateAll() {
    if (!mapData) return;
    try {
    var inp = getInputs();
    var n = mapData.totalNotes || 0;
    var isCustom = Math.abs(inp.rate - 1.0) >= 0.01;
    var effectiveOD = getEffectiveOD();

    $('col-dt').style.display = isCustom ? 'none' : '';
    $('col-ht').style.display = isCustom ? 'none' : '';
    $('nm-head').textContent = isCustom ? '' : 'NM';
    $('nm-rate').textContent = inp.rate.toFixed(2) + 'x';
    $('mod-cols').style.gridTemplateColumns = isCustom ? '1fr' : '1fr 1fr 1fr';

    var mods = [
      { pref: 'nm', mod: [], rate: 1.0 },
      { pref: 'dt', mod: ['DT'], rate: 1.5 },
      { pref: 'ht', mod: ['HT'], rate: 0.75 }
    ];

    for (var i = 0; i < mods.length; i++) {
      var m = mods[i];
      if (isCustom && i > 0) continue;
      var r = isCustom ? inp.rate : m.rate;
      var gameMods = isCustom ? [] : m.mod;
      var extraMods = getActiveMods();
      var allMods = gameMods.concat(extraMods);
      var ho = activeMods.HO;
      var inMod = activeMods.IN;
      var sunnyNM = ho ? (mapData.srHO || mapData.sr) : (inMod ? (mapData.srIN || mapData.sr) : mapData.sr);
      var sunnyDT = ho ? (mapData.srHO_DT || mapData.sr_DT) : (inMod ? (mapData.srIN_DT || mapData.sr_DT) : mapData.sr_DT);
      var sunnyHT = ho ? (mapData.srHO_HT || mapData.sr_HT) : (inMod ? (mapData.srIN_HT || mapData.sr_HT) : mapData.sr_HT);
      var sr = estimateSR(sunnyNM, sunnyDT, sunnyHT, r);
      var osuNM = ho ? (mapData.osuSR_HO || mapData.osuSR) : (inMod ? (mapData.osuSR_IN || mapData.osuSR) : (mapData.osuSR || sunnyNM));
      var osuDT = ho ? (mapData.osuSR_HO_DT || mapData.osuSR_DT) : (inMod ? (mapData.osuSR_IN_DT || mapData.osuSR_DT) : (mapData.osuSR_DT || sunnyDT));
      var osuHT = ho ? (mapData.osuSR_HO_HT || mapData.osuSR_HT) : (inMod ? (mapData.osuSR_IN_HT || mapData.osuSR_HT) : (mapData.osuSR_HT || sunnyHT));
      var osuSR = estimateSR(osuNM, osuDT, osuHT, r);
      var effLnRatio = inMod ? (mapData.lnRatioIN || 1) : (ho ? (mapData.lnRatioHO || 0) : (mapData.lnRatio || 0));
      var hasLN = effLnRatio >= 0.15;
      var keySup = mapData.columnCount === 4 || mapData.columnCount === 6 || mapData.columnCount === 7;
      var rcSR, lnSR, tier = '';
      if (keySup) {
        if (hasLN) {
          var rcHO = mapData.srHO || mapData.sr;
          var rcHO_DT = mapData.srHO_DT || mapData.sr_DT;
          var rcHO_HT = mapData.srHO_HT || mapData.sr_HT;
          rcSR = estimateSR(rcHO, rcHO_DT, rcHO_HT, r);
          if (ho) {
          } else if (inMod) {
            var inNM = mapData.srIN || mapData.sr;
            var inDT = mapData.srIN_DT || mapData.sr_DT;
            var inHT = mapData.srIN_HT || mapData.sr_HT;
            lnSR = estimateSR(inNM, inDT, inHT, r);
          } else {
            lnSR = estimateSR(mapData.sr, mapData.sr_DT, mapData.sr_HT, r);
          }
        } else {
          var algoNM, algoDT, algoHT;
          if (ho) {
            algoNM = mapData.srHO || mapData.sr; algoDT = mapData.srHO_DT || mapData.sr_DT; algoHT = mapData.srHO_HT || mapData.sr_HT;
          } else if (inMod) {
            algoNM = mapData.srIN || mapData.sr; algoDT = mapData.srIN_DT || mapData.sr_DT; algoHT = mapData.srIN_HT || mapData.sr_HT;
          } else {
            algoNM = getAlgoSR(''); algoDT = getAlgoSR('_DT'); algoHT = getAlgoSR('_HT');
          }
          rcSR = estimateSR(algoNM, algoDT, algoHT, r);
        }
        tier = rcLookup(rcSR, mapData.columnCount);
        if (hasLN && lnSR) {
          var lnTier = lnLookup(lnSR, mapData.columnCount);
          if (lnTier) tier += ' | ' + lnTier;
        }
      }
      var sunny = computeSunnyPP(sr, effectiveOD, inp.acc, inp.miss, allMods, mapData.totalNotes, mapData.variety, mapData.accScalar, ho, inMod);
      var sunny100 = computeSunnyPP(sr, effectiveOD, 100, 0, allMods, mapData.totalNotes, mapData.variety, mapData.accScalar, ho, inMod);
      var official = computeOfficialPP(osuSR, inp.acc, n, allMods);
      updateCol(m.pref, sr, sunny, official, sunny100, tier, osuSR);
    }

    $('stat-notes').textContent = mapData.totalNotes || '--';
    var effLn = inMod ? (mapData.lnRatioIN || 1) : (ho ? (mapData.lnRatioHO || 0) : (mapData.lnRatio || 0));
    $('stat-lnpct').textContent = ((effLn || 0) * 100).toFixed(1) + '%';
    var odVal = mapData.od || 8;
    var hpVal = mapData.hp || 8;
    var activeGameMods = getActiveMods();
    if (activeGameMods.indexOf('EZ') >= 0) { odVal = (odVal * 0.5).toFixed(1); hpVal = (hpVal * 0.5).toFixed(1); }
    if (!activeMods._odDirty) { $('stat-od').value = odVal; }
    $('stat-hp').textContent = hpVal;
    $('stat-keys').textContent = mapData.columnCount + 'K';
    $('pp-acc-display').textContent = inp.acc.toFixed(2) + '%';
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

  function initAlgoButtons() {
    var btns = document.querySelectorAll('.algo-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener('click', function () {
        var algo = this.dataset.algo;
        activeAlgo = algo;
        var all = document.querySelectorAll('.algo-btn');
        for (var j = 0; j < all.length; j++) all[j].classList.remove('active');
        this.classList.add('active');
        chrome.storage.local.set({ sunnyAlgo: algo });
        updateAll();
      });
    }
    chrome.storage.local.get(['sunnyAlgo'], function (r) {
      if (r.sunnyAlgo) {
        activeAlgo = r.sunnyAlgo;
        var all = document.querySelectorAll('.algo-btn');
        for (var j = 0; j < all.length; j++) {
          all[j].classList.toggle('active', all[j].dataset.algo === activeAlgo);
        }
        updateAll();
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
        $('map-tier-line').textContent = '';
      }
    });
  }

  function applyMapData(md) {
    mapData = md;
    lastBeatmapId = md.beatmapId;
    $('map-name').textContent = md.title || ('Beatmap #' + md.beatmapId);
    $('map-tier-line').textContent = md.subTitle || '';
    $('map-artist').textContent = md.artist || '';
    if (!activeMods._judgmentsDirty) {
      $('j-320').value = md.totalNotes || 0;
    }
    $('stat-od').value = md.od || 8;
    $('status').textContent = 'Ready';
    $('algo-bar').style.display = md.columnCount === 4 ? 'flex' : 'none';
    activeMods._odDirty = false;
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
          var v = parseFloat(e.target.value);
          var maxOD = activeMods.SV2 ? 15 : 10;
          if (isNaN(v)) e.target.value = mapData ? (mapData.od || 8) : 8;
          else e.target.value = Math.min(maxOD, Math.max(0, v)).toFixed(1);
          activeMods._odDirty = true;
          scheduleOdRecalc(parseFloat(e.target.value));
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

  function scheduleOdRecalc(newOd) {
    if (odRecalcTimer) clearTimeout(odRecalcTimer);
    odRecalcTimer = setTimeout(function () { doOdRecalc(newOd); }, 150);
  }

  function doOdRecalc(newOd) {
    if (!mapData || !mapData.beatmapId || isNaN(newOd)) return;
    $('status').textContent = 'Recalculating...';
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs[0]) { loadMapData(); return; }
      chrome.tabs.sendMessage(tabs[0].id, { type: 'recalculateOd', od: newOd }, function (resp) {
        // Reload from storage whether success or error
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
            activeMods._odDirty = true;
          } else {
            $('stat-od').max = 10;
            var currentV = parseFloat($('stat-od').value);
            if (isNaN(currentV) || currentV > 10) {
              $('stat-od').value = Math.min(10, mapData ? (mapData.od || 8) : 8);
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
