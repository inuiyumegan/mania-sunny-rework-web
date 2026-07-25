function stringToInt(str) {
  return parseInt(str, 10);
}

class OsuParser {
  constructor(fileContent) {
    this.content = fileContent;
    this.columnCount = -1;
    this.od = -1;
    this.hp = -1;
    this.columns = [];
    this.noteStarts = [];
    this.noteEnds = [];
    this.noteTypes = [];
    this.mode = 0;
  }

  process() {
    const lines = this.content.split(/\r?\n/);
    let inHitObjects = false;
    let inGeneral = false;
    let inDifficulty = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      if (line === '[General]') {
        inGeneral = true;
        inDifficulty = false;
        inHitObjects = false;
        continue;
      }
      if (line === '[Difficulty]') {
        inGeneral = false;
        inDifficulty = true;
        inHitObjects = false;
        continue;
      }
      if (line === '[HitObjects]') {
        inGeneral = false;
        inDifficulty = false;
        inHitObjects = true;
        continue;
      }
      if (line.startsWith('[Event') || line.startsWith('[TimingPoints]') || line.startsWith('[Colours]') || line.startsWith('[Editor]') || line.startsWith('[Metadata]')) {
        inGeneral = false;
        inDifficulty = false;
        inHitObjects = false;
        continue;
      }

      if (inGeneral) {
        if (line.startsWith('Mode:')) {
          const parts = line.split(':');
          if (parts.length > 1) this.mode = parseInt(parts[1].trim(), 10);
        }
      }

      if (inDifficulty) {
        if (line.startsWith('CircleSize:')) {
          const parts = line.split(':');
          if (parts.length > 1) {
            const val = parts[1].trim();
            this.columnCount = stringToInt(val === '0' ? '10' : val);
          }
        }
        if (line.startsWith('OverallDifficulty:')) {
          const parts = line.split(':');
          if (parts.length > 1) {
            this.od = parseFloat(parts[1].trim());
          }
        }
        if (line.startsWith('HPDrainRate:')) {
          const parts = line.split(':');
          if (parts.length > 1) {
            this.hp = parseFloat(parts[1].trim());
          }
        }
      }

      if (inHitObjects && line && !line.startsWith('[')) {
        this.parseHitObject(line);
      }
    }
  }

  parseHitObject(objectLine) {
    const params = objectLine.split(',');

    let column = parseInt(params[0], 10);
    const columnWidth = Math.floor(512 / this.columnCount);
    column = Math.floor(column / columnWidth);
    this.columns.push(column);

    const noteStart = parseInt(params[2], 10);
    this.noteStarts.push(noteStart);

    const noteType = parseInt(params[3], 10);
    this.noteTypes.push(noteType);

    const lastParamChunk = params[5].split(':');
    const noteEnd = parseInt(lastParamChunk[0], 10);
    this.noteEnds.push(noteEnd);
  }

  getParsedData() {
    return [
      this.columnCount,
      this.columns,
      this.noteStarts,
      this.noteEnds,
      this.noteTypes,
      this.od,
      this.hp
    ];
  }
}
