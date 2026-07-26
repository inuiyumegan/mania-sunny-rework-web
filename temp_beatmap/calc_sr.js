const fs = require('fs');
const path = require('path');

// Load the extension's modules (they use shared globals)
const mathUtilsCode = fs.readFileSync(path.resolve(__dirname, '..', 'sunny-rework-extension', 'src', 'math-utils.js'), 'utf-8');
const osuParserCode = fs.readFileSync(path.resolve(__dirname, '..', 'sunny-rework-extension', 'src', 'osu-parser.js'), 'utf-8');
const algorithmCode = fs.readFileSync(path.resolve(__dirname, '..', 'sunny-rework-extension', 'src', 'algorithm.js'), 'utf-8');

// Evaluate them all together so they share scope
const combinedCode = mathUtilsCode + '\n' + osuParserCode + '\n' + algorithmCode;
eval(combinedCode);

// Read the .osu file
const fileContent = fs.readFileSync(path.resolve(__dirname, '2507670_full.osu'), 'utf-8');

// Calculate SR using NM mode
const result = calculate(fileContent, 'NM');

console.log('SR:', result.sr);
console.log('Spikiness:', result.spikiness);
console.log('Switches:', result.switches);
