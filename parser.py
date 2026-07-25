import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import math
from collections import defaultdict


class OsuFileParser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.od = 0
        self.column_count = 4
        self.columns = []
        self.note_starts = []
        self.note_ends = []
        self.note_types = []

    def parse(self):
        with open(self.file_path, "r", encoding="utf-8") as f:
            in_section = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_section = line
                    continue

                if in_section == "[Difficulty]":
                    if line.startswith("OverallDifficulty:"):
                        self.od = float(line.split(":")[1])
                    elif line.startswith("CircleSize:"):
                        self.column_count = int(float(line.split(":")[1]))
                elif in_section == "[HitObjects]":
                    self._parse_hit_object(line)

        self.ln_count = sum(1 for t in self.note_ends if t >= 0)
        self.total_notes = len(self.columns)
        self.ln_ratio = self.ln_count / max(self.total_notes, 1)

    def _parse_hit_object(self, line):
        parts = line.split(",")
        x = int(float(parts[0]))
        time = int(parts[2])
        note_type = int(parts[3])
        end_part = parts[5].split(":")[0] if len(parts) >= 6 else "0"

        column_width = 512 // self.column_count
        col = x // column_width

        is_ln = (note_type & 128) != 0
        end_time = int(end_part) if is_ln and end_part else -1

        self.columns.append(col)
        self.note_starts.append(time)
        self.note_ends.append(end_time)
        self.note_types.append(note_type)

    def get_lists(self):
        return self.column_count, self.columns, self.note_starts, self.note_ends, self.note_types, self.od

    def get_note_seq_taps_only(self, time_scale=1.0):
        """Build tap-note sequence for Daniel (no LN distinction)."""
        note_seq = []
        for i in range(len(self.columns)):
            k = self.columns[i]
            h = int(math.floor(self.note_starts[i] * time_scale))
            note_seq.append((k, h))
        note_seq.sort(key=lambda t: (t[1], t[0]))
        return note_seq

    def get_note_seq_with_tails(self, time_scale=1.0):
        """Build full note sequence with LN tail info for Sunny."""
        note_seq = []
        for i in range(len(self.columns)):
            k = self.columns[i]
            h = int(math.floor(self.note_starts[i] * time_scale))
            t = int(math.floor(self.note_ends[i] * time_scale)) if self.note_ends[i] >= 0 else -1
            note_seq.append([k, h, t])
        note_seq.sort(key=lambda n: (n[1], n[0]))
        return note_seq

    def get_note_seq_by_column(self, note_seq, K):
        note_dict = defaultdict(list)
        for n in note_seq:
            note_dict[n[0]].append(n)
        return [note_dict.get(k, []) for k in range(K)]
