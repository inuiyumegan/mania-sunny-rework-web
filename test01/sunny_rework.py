import math
import bisect
import re
from collections import defaultdict

# ============================================================
# .osu file parser
# ============================================================

COLUMN_MAP_4K = {64: 0, 192: 1, 320: 2, 448: 3}
COLUMN_MAP_5K = {64: 0, 192: 1, 320: 2, 448: 3, 512: 4}
COLUMN_MAP_6K = {64: 0, 192: 1, 320: 2, 448: 3, 512: 4, 576: 5}
COLUMN_MAP_7K = {64: 0, 192: 1, 320: 2, 448: 3, 512: 4, 576: 5, 640: 6}
COLUMN_MAP_8K = {64: 0, 192: 1, 320: 2, 448: 3, 512: 4, 576: 5, 640: 6, 704: 7}

COLUMN_MAPS = {4: COLUMN_MAP_4K, 5: COLUMN_MAP_5K, 6: COLUMN_MAP_6K, 7: COLUMN_MAP_7K, 8: COLUMN_MAP_8K}


class OsuFileParser:
    def __init__(self, text):
        self.text = text

    def parse(self):
        self.hit_objects = []
        self.timing_points = []

        in_hit_objects = False
        in_timing_points = False
        in_difficulty = False

        self.od = 0
        self.cs = 4
        self.bpm = 0

        for line in self.text.split("\n"):
            line = line.strip()
            if line == "[HitObjects]":
                in_hit_objects = True
                in_timing_points = False
                in_difficulty = False
                continue
            if line == "[TimingPoints]":
                in_timing_points = True
                in_hit_objects = False
                in_difficulty = False
                continue
            if line == "[Difficulty]":
                in_difficulty = True
                in_hit_objects = False
                in_timing_points = False
                continue
            if line.startswith("[") and line.endswith("]"):
                in_hit_objects = False
                in_timing_points = False
                in_difficulty = False
                continue

            if in_hit_objects and line:
                self.hit_objects.append(line)
            elif in_timing_points and line:
                self.timing_points.append(line)
            elif in_difficulty and line:
                if line.startswith("OverallDifficulty:"):
                    self.od = float(line.split(":")[1])
                elif line.startswith("CircleSize:"):
                    self.cs = int(float(line.split(":")[1]))

        self.column_count = self.cs
        self.parse_hit_objects()

    def parse_hit_objects(self):
        self.columns = []
        self.note_starts = []
        self.note_ends = []
        self.note_types = []

        col_map = COLUMN_MAPS.get(self.column_count, {})
        if not col_map:
            all_x = set()
            for line in self.hit_objects:
                parts = line.split(",")
                if len(parts) >= 3:
                    all_x.add(int(parts[0]))
            sorted_x = sorted(all_x)
            self.column_count = len(sorted_x)
            col_map = {x: i for i, x in enumerate(sorted_x)}

        for line in self.hit_objects:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            x = int(parts[0])
            time = int(parts[2])
            note_type = int(parts[3])
            end_time = int(parts[5].split(":")[0]) if len(parts) >= 6 and parts[5] else 0

            col = col_map.get(x)
            if col is None:
                continue

            is_ln = (note_type & 128) != 0
            self.columns.append(col)
            self.note_starts.append(time)
            self.note_ends.append(end_time if is_ln and end_time > 0 else -1)
            self.note_types.append(note_type)

        self.ln_count = sum(1 for t in self.note_ends if t >= 0)
        self.total_notes = len(self.columns)
        self.ln_ratio = self.ln_count / max(self.total_notes, 1)

    def get_column_count(self):
        return self.column_count

    def get_ln_ratio(self):
        return self.ln_ratio


# ============================================================
# Sunny Rework algorithm
# ============================================================

BREAK_ZERO_THRESHOLD_MS = 400
GRAPH_RESAMPLE_INTERVAL_MS = 100
SMOOTH_SIGMA_MS = 800


def bisect_left(arr, target):
    return bisect.bisect_left(arr, target)


def bisect_right(arr, target):
    return bisect.bisect_right(arr, target)


def cumulative_sum(x, f):
    F = [0.0] * len(x)
    for i in range(1, len(x)):
        F[i] = F[i - 1] + f[i - 1] * (x[i] - x[i - 1])
    return F


def query_cumsum(q, x, F, f):
    if q <= x[0]:
        return 0.0
    if q >= x[-1]:
        return F[-1]
    i = bisect_right(x, q) - 1
    return F[i] + f[i] * (q - x[i])


def smooth_on_corners(x, f, window, scale=1.0, mode="sum"):
    F = cumulative_sum(x, f)
    g = [0.0] * len(f)
    for i in range(len(x)):
        s = x[i]
        a = max(s - window, x[0])
        b = min(s + window, x[-1])
        val = query_cumsum(b, x, F, f) - query_cumsum(a, x, F, f)
        if mode == "avg":
            g[i] = val / (b - a) if b - a > 0 else 0.0
        else:
            g[i] = scale * val
    return g


def interp_values(new_x, old_x, old_vals):
    out = [0.0] * len(new_x)
    idx = 0
    for i, xi in enumerate(new_x):
        if xi <= old_x[0]:
            out[i] = old_vals[0]
            continue
        if xi >= old_x[-1]:
            out[i] = old_vals[-1]
            continue
        while idx + 1 < len(old_x) and old_x[idx + 1] < xi:
            idx += 1
        x0 = old_x[idx]
        x1 = old_x[idx + 1]
        y0 = old_vals[idx]
        y1 = old_vals[idx + 1]
        if x1 == x0:
            out[i] = y0
            continue
        t = (xi - x0) / (x1 - x0)
        out[i] = y0 + t * (y1 - y0)
    return out


def step_interp(new_x, old_x, old_vals):
    out = [0.0] * len(new_x)
    idx = 0
    for i, xi in enumerate(new_x):
        while idx + 1 < len(old_x) and old_x[idx + 1] <= xi:
            idx += 1
        clamped = max(0, min(idx, len(old_vals) - 1))
        out[i] = old_vals[clamped]
    return out


def rescale_high(sr):
    if sr <= 9:
        return sr
    return 9 + (sr - 9) * (1.0 / 1.2)


def merge_by_head(a, b):
    result = []
    i, j = 0, 0
    while i < len(a) and j < len(b):
        if a[i][1] <= b[j][1]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    while i < len(a):
        result.append(a[i])
        i += 1
    while j < len(b):
        result.append(b[j])
        j += 1
    return result


def find_next_note_in_column(note, times, note_seq_by_column):
    k, h = note[0], note[1]
    idx = bisect_left(times, h)
    if idx + 1 < len(note_seq_by_column[k]):
        return note_seq_by_column[k][idx + 1]
    return [0, 10**9, 10**9]


CROSS_MATRIX = [
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
    [0.325, 0.55, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.55, 0.325],
]


def preprocess_file(parser, speed_rate, od_flag=None):
    od = parser.od
    if od_flag == "HR":
        od = 6.462 + 0.715 * parser.od
    elif od_flag == "EZ":
        od = -20.761 + 2.566 * parser.od
    elif od_flag is not None:
        od = float(od_flag)

    time_scale = 1.0 / speed_rate if speed_rate != 0 else 1.0

    x = 0.3 * math.sqrt((64.5 - math.ceil(od * 3)) / 500)
    x = min(x, 0.6 * (x - 0.09) + 0.09)

    note_seq = []
    for i in range(len(parser.columns)):
        k = parser.columns[i]
        h = int(parser.note_starts[i] * time_scale)
        t = int(parser.note_ends[i] * time_scale) if parser.note_ends[i] >= 0 else -1
        note_seq.append([k, h, t])

    note_seq.sort(key=lambda n: (n[1], n[0]))

    K = parser.column_count
    note_seq_by_column = [[] for _ in range(K)]
    for n in note_seq:
        col = n[0]
        if 0 <= col < K:
            note_seq_by_column[col].append(n)

    ln_seq = [n for n in note_seq if n[2] >= 0]
    tail_seq = sorted(ln_seq, key=lambda n: n[2])

    max_head = max((n[1] for n in note_seq), default=0)
    max_tail = max((n[2] for n in note_seq), default=0)
    T = max(max_head, max_tail) + 1

    return {
        "status": "OK",
        "x": x,
        "K": K,
        "T": T,
        "note_seq": note_seq,
        "note_seq_by_column": note_seq_by_column,
        "ln_seq": ln_seq,
        "tail_seq": tail_seq,
        "ln_ratio": parser.ln_ratio,
        "column_count": parser.column_count,
    }


def get_corners(T, note_seq):
    corners_base = set()
    for _, h, t in note_seq:
        corners_base.add(h)
        if t >= 0:
            corners_base.add(t)

    copy_base = list(corners_base)
    for s in copy_base:
        corners_base.add(s + 501)
        corners_base.add(s - 499)
        corners_base.add(s + 1)
    corners_base.add(0)
    corners_base.add(T)

    base_corners = sorted([s for s in corners_base if 0 <= s <= T])

    corners_a = set()
    for _, h, t in note_seq:
        corners_a.add(h)
        if t >= 0:
            corners_a.add(t)

    copy_a = list(corners_a)
    for s in copy_a:
        corners_a.add(s + 1000)
        corners_a.add(s - 1000)
    corners_a.add(0)
    corners_a.add(T)

    a_corners = sorted([s for s in corners_a if 0 <= s <= T])

    all_corners = sorted(set(base_corners + a_corners))
    return all_corners, base_corners, a_corners


def get_key_usage(K, T, note_seq, base_corners):
    key_usage = {k: [False] * len(base_corners) for k in range(K)}
    for k, h, t in note_seq:
        start_time = max(h - 150, 0)
        end_time = t if t < 0 else min(t + 150, T - 1)
        end_time = end_time if end_time >= 0 else h + 150
        left_idx = bisect_left(base_corners, start_time)
        right_idx = bisect_left(base_corners, end_time)
        for idx in range(left_idx, right_idx):
            if idx < len(key_usage[k]):
                key_usage[k][idx] = True
    return key_usage


def get_key_usage_400(K, T, note_seq, base_corners):
    key_usage_400 = {k: [0.0] * len(base_corners) for k in range(K)}
    for k, h, t in note_seq:
        start_time = max(h, 0)
        end_time = t if t >= 0 else h
        end_time = min(end_time, T - 1)

        left_400_idx = bisect_left(base_corners, start_time - 400)
        left_idx = bisect_left(base_corners, start_time)
        right_idx = bisect_left(base_corners, end_time)
        right_400_idx = bisect_left(base_corners, end_time + 400)

        duration = max(1, end_time - start_time)
        for idx in range(left_idx, right_idx):
            key_usage_400[k][idx] += 3.75 + min(duration, 1500) / 150

        for idx in range(left_400_idx, left_idx):
            dist = base_corners[idx] - start_time
            key_usage_400[k][idx] += 3.75 - (3.75 / (400 ** 2)) * (dist ** 2)

        for idx in range(right_idx, right_400_idx):
            dist = abs(base_corners[idx] - end_time)
            key_usage_400[k][idx] += 3.75 - (3.75 / (400 ** 2)) * (dist ** 2)

    return key_usage_400


def compute_anchor(K, key_usage_400, base_corners):
    anchor = [0.0] * len(base_corners)
    for idx in range(len(base_corners)):
        counts = [key_usage_400[k][idx] for k in range(K)]
        counts.sort(reverse=True)
        non_zero = [v for v in counts if v != 0]
        if len(non_zero) > 1:
            walk = 0.0
            max_walk = 0.0
            for i in range(len(non_zero) - 1):
                ratio = non_zero[i + 1] / non_zero[i] if non_zero[i] != 0 else 0
                w = 1 - 4 * ((0.5 - ratio) ** 2)
                walk += non_zero[i] * w
                max_walk += non_zero[i]
            anchor[idx] = walk / max_walk if max_walk > 0 else 0.0

    for i in range(len(anchor)):
        anchor[i] = 1 + min(anchor[i] - 0.18, 5 * ((anchor[i] - 0.22) ** 3))
    return anchor


def ln_bodies_count_sparse(ln_seq, T):
    diff = defaultdict(float)
    for _, h, t in ln_seq:
        t0 = min(h + 60, t)
        t1 = min(h + 120, t)
        diff[t0] += 1.3
        diff[t1] += -1.3 + 1.0
        diff[t] -= 1.0

    points_set = {0, T}
    for k in diff:
        points_set.add(k)
    points = sorted(points_set)

    values = []
    cumsum = [0.0]
    curr = 0.0
    for i in range(len(points) - 1):
        t_pt = points[i]
        if t_pt in diff:
            curr += diff[t_pt]
        v = min(curr, 2.5 + 0.5 * curr)
        values.append(v)
        seg_len = points[i + 1] - points[i]
        cumsum.append(cumsum[-1] + seg_len * v)

    return {"points": points, "cumsum": cumsum, "values": values}


def ln_sum(a, b, ln_rep):
    points, cumsum, values = ln_rep["points"], ln_rep["cumsum"], ln_rep["values"]
    i = bisect_right(points, a) - 1
    j = bisect_right(points, b) - 1
    if i == j:
        return (b - a) * values[i]
    total = 0.0
    total += (points[i + 1] - a) * values[i]
    total += cumsum[j] - cumsum[i + 1]
    total += (b - points[j]) * values[j]
    return total


def jack_nerfer(delta):
    return 1 - 7e-5 * ((0.15 + abs(delta - 0.08)) ** -4)


def compute_jbar(K, x, note_seq_by_column, base_corners):
    Jks = {k: [0.0] * len(base_corners) for k in range(K)}
    delta_ks = {k: [1e9] * len(base_corners) for k in range(K)}

    for k in range(K):
        notes = note_seq_by_column[k]
        for i in range(len(notes) - 1):
            start = notes[i][1]
            end = notes[i + 1][1]
            left_idx = bisect_left(base_corners, start)
            right_idx = bisect_left(base_corners, end)
            if left_idx >= right_idx:
                continue
            delta = 0.001 * (end - start)
            val = (delta ** -1) * ((delta + 0.11 * (x ** 0.25)) ** -1)
            j_val = val * jack_nerfer(delta)
            for idx in range(left_idx, right_idx):
                Jks[k][idx] = j_val
                delta_ks[k][idx] = delta

    Jbar_ks = {k: smooth_on_corners(base_corners, Jks[k], 500, 0.001, "sum") for k in range(K)}

    Jbar = [0.0] * len(base_corners)
    for i in range(len(base_corners)):
        num = 0.0
        den = 0.0
        for k in range(K):
            v = Jbar_ks[k][i]
            w = 1.0 / delta_ks[k][i]
            num += (max(v, 0) ** 5) * w
            den += w
        raw = num / max(1e-9, den)
        Jbar[i] = raw ** (1.0 / 5.0)

    return delta_ks, Jbar


def compute_xbar(K, x, note_seq_by_column, active_columns, base_corners):
    if K < 1 or K > 10:
        return [0.0] * len(base_corners)

    Xks = {k: [0.0] * len(base_corners) for k in range(K + 1)}
    fast_cross = {k: [0.0] * len(base_corners) for k in range(K + 1)}
    cross_coeff = CROSS_MATRIX[K - 1] if K <= len(CROSS_MATRIX) else CROSS_MATRIX[-1]

    for k in range(K + 1):
        if k == 0:
            notes_in_pair = note_seq_by_column[0]
        elif k == K:
            notes_in_pair = note_seq_by_column[K - 1]
        else:
            notes_in_pair = merge_by_head(note_seq_by_column[k - 1], note_seq_by_column[k])

        for i in range(1, len(notes_in_pair)):
            start = notes_in_pair[i - 1][1]
            end = notes_in_pair[i][1]
            idx_start = bisect_left(base_corners, start)
            idx_end = bisect_left(base_corners, end)
            if idx_start >= idx_end:
                continue
            delta = 0.001 * (end - start)
            val = 0.16 * (max(x, delta) ** -2)

            left_active = active_columns[min(idx_start, len(active_columns) - 1)]
            right_active = active_columns[min(idx_end - 1, len(active_columns) - 1)]

            if ((k - 1 not in left_active and k - 1 not in right_active) or
                    (k not in left_active and k not in right_active)):
                val *= (1 - cross_coeff[min(k, len(cross_coeff) - 1)])

            fast = max(0, 0.4 * (max(delta, 0.06, 0.75 * x) ** -2) - 80)
            for idx in range(idx_start, idx_end):
                Xks[k][idx] = val
                fast_cross[k][idx] = fast

    x_base = [0.0] * len(base_corners)
    for i in range(len(base_corners)):
        sum1 = 0.0
        for k in range(K + 1):
            sum1 += Xks[k][i] * cross_coeff[min(k, len(cross_coeff) - 1)]

        sum2 = 0.0
        for k in range(K):
            cc_k = cross_coeff[min(k, len(cross_coeff) - 1)]
            cc_k1 = cross_coeff[min(k + 1, len(cross_coeff) - 1)]
            sum2 += math.sqrt(fast_cross[k][i] * cc_k * fast_cross[k + 1][i] * cc_k1)

        x_base[i] = sum1 + sum2

    return smooth_on_corners(base_corners, x_base, 500, 0.001, "sum")


def stream_booster(delta):
    expr = 7.5 / delta
    if 160 < expr < 360:
        return 1 + 1.7e-7 * (expr - 160) * ((expr - 360) ** 2)
    return 1.0


def compute_pbar(x, note_seq, ln_rep, anchor, base_corners):
    p_step = [0.0] * len(base_corners)

    for i in range(len(note_seq) - 1):
        h_l = note_seq[i][1]
        h_r = note_seq[i + 1][1]
        delta_time = h_r - h_l

        if delta_time < 1e-9:
            spike = 1000 * ((0.02 * (4 / x - 24)) ** 0.25)
            left_idx = bisect_left(base_corners, h_l)
            right_idx = bisect_right(base_corners, h_l)
            for idx in range(left_idx, right_idx):
                p_step[idx] += spike
            continue

        left_idx = bisect_left(base_corners, h_l)
        right_idx = bisect_left(base_corners, h_r)
        if left_idx >= right_idx:
            continue

        delta = 0.001 * delta_time
        v = 1 + 6 * 0.001 * ln_sum(h_l, h_r, ln_rep)
        b_val = stream_booster(delta)

        if delta < (2 * x) / 3:
            inner = 0.08 * (x ** -1) * (1 - 24 * (x ** -1) * ((delta - x / 2) ** 2))
            inc = (delta ** -1) * (max(inner, 0) ** 0.25) * max(b_val, v)
        else:
            inner = 0.08 * (x ** -1) * (1 - 24 * (x ** -1) * ((x / 6) ** 2))
            inc = (delta ** -1) * (max(inner, 0) ** 0.25) * max(b_val, v)

        for idx in range(left_idx, right_idx):
            anc = anchor[idx] if idx < len(anchor) else 1.0
            p_step[idx] += min(inc * anc, max(inc, inc * 2 - 10))

    return smooth_on_corners(base_corners, p_step, 500, 0.001, "sum")


def compute_abar(K, active_columns, delta_ks, a_corners, base_corners):
    dks = {k: [0.0] * len(base_corners) for k in range(K - 1)}

    for i in range(len(base_corners)):
        cols = active_columns[i]
        for j in range(len(cols) - 1):
            k0 = cols[j]
            k1 = cols[j + 1]
            dks[k0][i] = abs(delta_ks[k0][i] - delta_ks[k1][i]) + 0.4 * max(0, max(delta_ks[k0][i], delta_ks[k1][i]) - 0.11)

    a_step = [1.0] * len(a_corners)
    for i in range(len(a_corners)):
        s = a_corners[i]
        idx = bisect_left(base_corners, s)
        if idx >= len(base_corners):
            idx = len(base_corners) - 1
        cols = active_columns[idx]
        for j in range(len(cols) - 1):
            k0 = cols[j]
            k1 = cols[j + 1]
            d_val = dks[k0][idx]
            if d_val < 0.02:
                a_step[i] *= min(0.75 + 0.5 * max(delta_ks[k0][idx], delta_ks[k1][idx]), 1)
            elif d_val < 0.07:
                a_step[i] *= min(0.65 + 5 * d_val + 0.5 * max(delta_ks[k0][idx], delta_ks[k1][idx]), 1)

    return smooth_on_corners(a_corners, a_step, 250, 1.0, "avg")


def compute_rbar(K, x, note_seq_by_column, tail_seq, base_corners):
    r_step = [0.0] * len(base_corners)

    times_by_column = {}
    for i in range(K):
        times_by_column[i] = [n[1] for n in note_seq_by_column[i]]

    I_list = []
    for i, (k, h_i, t_i) in enumerate(tail_seq):
        _, h_j, _ = find_next_note_in_column([k, h_i, t_i], times_by_column[k], note_seq_by_column)
        I_h = 0.001 * abs(t_i - h_i - 80) / x
        I_t = 0.001 * abs(h_j - t_i - 80) / x
        I_list.append(2 / (2 + math.exp(-5 * (I_h - 0.75)) + math.exp(-5 * (I_t - 0.75))))

    for i in range(len(tail_seq) - 1):
        t_start = tail_seq[i][2]
        t_end = tail_seq[i + 1][2]
        left_idx = bisect_left(base_corners, t_start)
        right_idx = bisect_left(base_corners, t_end)
        if left_idx >= right_idx:
            continue
        delta_r = 0.001 * (t_end - t_start)
        r_value = 0.08 * (delta_r ** -0.5) * (x ** -1) * (1 + 0.8 * (I_list[i] + I_list[i + 1]))
        for idx in range(left_idx, right_idx):
            r_step[idx] = r_value

    return smooth_on_corners(base_corners, r_step, 500, 0.001, "sum")


def compute_c_and_ks(K, note_seq, key_usage, base_corners):
    note_hit_times = sorted([n[1] for n in note_seq])

    C_step = [0.0] * len(base_corners)
    lo = 0
    hi = 0
    for i, s in enumerate(base_corners):
        low = s - 500
        high = s + 500
        while lo < len(note_hit_times) and note_hit_times[lo] < low:
            lo += 1
        while hi < len(note_hit_times) and note_hit_times[hi] < high:
            hi += 1
        C_step[i] = hi - lo

    Ks_step = [1.0] * len(base_corners)
    for i in range(len(base_corners)):
        count = sum(1 for k in range(K) if key_usage[k][i])
        Ks_step[i] = max(count, 1)

    return C_step, Ks_step


# ============================================================
# RC difficulty intervals (from 4k-rc-reform.js)
# ============================================================

RC_4K_REFORM = [
    [1.502, 1.631, "Intro 1 low"],
    [1.631, 1.760, "Intro 1 mid/low"],
    [1.760, 1.890, "Intro 1 mid"],
    [1.890, 2.019, "Intro 1 mid/high"],
    [2.019, 2.148, "Intro 1 high"],
    [2.148, 2.278, "Intro 2 low"],
    [2.278, 2.407, "Intro 2 mid/low"],
    [2.407, 2.502, "Intro 2 mid"],
    [2.502, 2.560, "Intro 2 mid/high"],
    [2.560, 2.619, "Intro 2 high"],
    [2.619, 2.679, "Intro 3 low"],
    [2.679, 2.737, "Intro 3 mid/low"],
    [2.737, 2.821, "Intro 3 mid"],
    [2.821, 2.929, "Intro 3 mid/high"],
    [2.929, 3.037, "Intro 3 high"],
    [3.037, 3.145, "Reform 1 low"],
    [3.145, 3.253, "Reform 1 mid/low"],
    [3.253, 3.346, "Reform 1 mid"],
    [3.346, 3.424, "Reform 1 mid/high"],
    [3.424, 3.503, "Reform 1 high"],
    [3.503, 3.581, "Reform 2 low"],
    [3.581, 3.659, "Reform 2 mid/low"],
    [3.659, 3.701, "Reform 2 mid"],
    [3.701, 3.708, "Reform 2 mid/high"],
    [3.708, 3.714, "Reform 2 high"],
    [3.714, 3.720, "Reform 3 low"],
    [3.720, 3.727, "Reform 3 mid/low"],
    [3.727, 3.810, "Reform 3 mid"],
    [3.810, 3.970, "Reform 3 mid/high"],
    [3.970, 4.130, "Reform 3 high"],
    [4.130, 4.290, "Reform 4 low"],
    [4.290, 4.450, "Reform 4 mid/low"],
    [4.450, 4.569, "Reform 4 mid"],
    [4.569, 4.648, "Reform 4 mid/high"],
    [4.648, 4.726, "Reform 4 high"],
    [4.726, 4.804, "Reform 5 low"],
    [4.804, 4.883, "Reform 5 mid/low"],
    [4.883, 4.972, "Reform 5 mid"],
    [4.972, 5.072, "Reform 5 mid/high"],
    [5.072, 5.173, "Reform 5 high"],
    [5.173, 5.273, "Reform 6 low"],
    [5.273, 5.373, "Reform 6 mid/low"],
    [5.373, 5.441, "Reform 6 mid"],
    [5.441, 5.476, "Reform 6 mid/high"],
    [5.476, 5.511, "Reform 6 high"],
    [5.511, 5.547, "Reform 7 low"],
    [5.547, 5.582, "Reform 7 mid/low"],
    [5.582, 5.646, "Reform 7 mid"],
    [5.646, 5.738, "Reform 7 mid/high"],
    [5.738, 5.829, "Reform 7 high"],
    [5.829, 5.921, "Reform 8 low"],
    [5.921, 6.013, "Reform 8 mid/low"],
    [6.013, 6.069, "Reform 8 mid"],
    [6.069, 6.090, "Reform 8 mid/high"],
    [6.090, 6.110, "Reform 8 high"],
    [6.110, 6.130, "Reform 9 low"],
    [6.130, 6.151, "Reform 9 mid/low"],
    [6.151, 6.205, "Reform 9 mid"],
    [6.205, 6.294, "Reform 9 mid/high"],
    [6.294, 6.382, "Reform 9 high"],
    [6.382, 6.471, "Reform 10 low"],
    [6.471, 6.560, "Reform 10 mid/low"],
    [6.560, 6.616, "Reform 10 mid"],
    [6.616, 6.641, "Reform 10 mid/high"],
    [6.641, 6.666, "Reform 10 high"],
    [6.666, 6.691, "Alpha low"],
    [6.691, 6.716, "Alpha mid/low"],
    [6.716, 6.773, "Alpha mid"],
    [6.773, 6.860, "Alpha mid/high"],
    [6.860, 6.947, "Alpha high"],
    [6.947, 7.034, "Beta low"],
    [7.034, 7.121, "Beta mid/low"],
    [7.121, 7.214, "Beta mid"],
    [7.214, 7.312, "Beta mid/high"],
    [7.312, 7.410, "Beta high"],
    [7.410, 7.509, "Gamma low"],
    [7.509, 7.607, "Gamma mid/low"],
    [7.607, 7.705, "Gamma mid"],
    [7.705, 7.803, "Gamma mid/high"],
    [7.803, 7.901, "Gamma high"],
    [7.901, 8.000, "Delta low"],
    [8.000, 8.098, "Delta mid/low"],
    [8.098, 8.244, "Delta mid"],
    [8.244, 8.438, "Delta mid/high"],
    [8.438, 8.631, "Delta high"],
    [8.631, 8.825, "Epsilon low"],
    [8.825, 9.019, "Epsilon mid/low"],
    [9.019, 9.172, "Epsilon mid"],
    [9.172, 9.285, "Epsilon mid/high"],
    [9.285, 9.398, "Epsilon high"],
    [9.398, 9.511, "Emik Zeta low"],
    [9.511, 9.624, "Emik Zeta mid/low"],
    [9.624, 9.742, "Emik Zeta mid"],
    [9.742, 9.867, "Emik Zeta mid/high"],
    [9.867, 9.991, "Emik Zeta high"],
    [9.991, 10.116, "Thaumiel Eta low"],
    [10.116, 10.241, "Thaumiel Eta mid/low"],
    [10.241, 10.358, "Thaumiel Eta mid"],
    [10.358, 10.468, "Thaumiel Eta mid/high"],
    [10.468, 10.578, "Thaumiel Eta high"],
    [10.578, 10.689, "CloverWisp Theta low"],
    [10.689, 10.799, "CloverWisp Theta mid/low"],
    [10.799, 10.909, "CloverWisp Theta mid"],
    [10.909, 11.019, "CloverWisp Theta mid/high"],
    [11.019, 11.129, "CloverWisp Theta high"],
]

LN_4K = [
    [4.832, 4.898, "LN 5 mid"],
    [4.898, 4.963, "LN 5 mid/high"],
    [4.963, 5.095, "LN 5 high"],
    [5.095, 5.160, "LN 6 low"],
    [5.160, 5.143, "LN 6 mid/low"],
    [5.143, 5.213, "LN 6 mid"],
    [5.213, 5.264, "LN 6 mid/high"],
    [5.264, 5.314, "LN 6 high"],
    [5.314, 5.446, "LN 7 low"],
    [5.446, 5.521, "LN 7 mid/low"],
    [5.521, 5.577, "LN 7 mid"],
    [5.577, 5.631, "LN 7 mid/high"],
    [5.631, 5.686, "LN 7 high"],
    [5.686, 5.740, "LN 8 low"],
    [5.740, 5.794, "LN 8 mid/low"],
    [5.794, 5.853, "LN 8 mid"],
    [5.853, 5.917, "LN 8 mid/high"],
    [5.917, 5.981, "LN 8 high"],
    [5.981, 6.044, "LN 9 low"],
    [6.044, 6.108, "LN 9 mid/low"],
    [6.108, 6.175, "LN 9 mid"],
    [6.175, 6.246, "LN 9 mid/high"],
    [6.246, 6.318, "LN 9 high"],
    [6.318, 6.389, "LN 10 low"],
    [6.389, 6.461, "LN 10 mid/low"],
    [6.461, 6.534, "LN 10 mid"],
    [6.534, 6.611, "LN 10 mid/high"],
    [6.611, 6.687, "LN 10 high"],
    [6.687, 6.763, "LN 11 low"],
    [6.763, 6.839, "LN 11 mid/low"],
    [6.839, 6.898, "LN 11 mid"],
    [6.898, 6.920, "LN 11 mid/high"],
    [6.920, 6.941, "LN 11 high"],
    [6.941, 7.023, "LN 12 low"],
    [7.023, 7.068, "LN 12 mid/low"],
    [7.068, 7.136, "LN 12 mid"],
    [7.136, 7.225, "LN 12 mid/high"],
    [7.225, 7.313, "LN 12 high"],
    [7.313, 7.401, "LN 13 low"],
    [7.401, 7.490, "LN 13 mid/low"],
    [7.490, 7.578, "LN 13 mid"],
    [7.578, 7.665, "LN 13 mid/high"],
    [7.665, 7.753, "LN 13 high"],
    [7.753, 7.841, "LN 14 low"],
    [7.841, 7.929, "LN 14 mid/low"],
    [7.929, 8.013, "LN 14 mid"],
    [8.013, 8.093, "LN 14 mid/high"],
    [8.093, 8.173, "LN 14 high"],
    [8.173, 8.253, "LN 15 low"],
    [8.253, 8.333, "LN 15 mid/low"],
    [8.333, 8.389, "LN 15 mid"],
    [8.389, 8.428, "LN 15 mid/high"],
    [8.428, 8.470, "LN 15 high"],
    [8.470, 8.509, "Hypersovae LN 16 low"],
    [8.509, 8.548, "Hypersovae LN 16 mid/low"],
    [8.548, 8.586, "Hypersovae LN 16 mid"],
    [8.586, 8.635, "Hypersovae LN 16 mid/high"],
    [8.635, 8.908, "Hypersovae LN 16 high"],
    [8.908, 9.044, "Lnlism LN 17 low"],
    [9.044, 9.180, "Lnlism LN 17 mid/low"],
    [9.180, 9.316, "Lnlism LN 17 mid"],
    [9.316, 9.452, "Lnlism LN 17 mid/high"],
    [9.452, 9.589, "Lnlism LN 17 high"],
]


def interval_lookup(sr, table, fallback_label):
    for lower, upper, name in table:
        if lower <= sr <= upper:
            return name
    if sr < table[0][0]:
        return f"< {table[0][2]}"
    if sr > table[-1][1]:
        return f"> {table[-1][2]}"
    return fallback_label


def est_diff(sr, ln_ratio, column_count):
    if column_count == 4:
        rc_diff = interval_lookup(sr, RC_4K_REFORM, "Unknown RC difficulty")
        if ln_ratio < 0.15:
            return rc_diff
        ln_diff = interval_lookup(sr, LN_4K, "Unknown LN difficulty")
        return f"{rc_diff} || {ln_diff}"
    return f"SR {sr:.3f} (column_count={column_count}, no lookup table)"


# ============================================================
# Main calculation
# ============================================================

def calculate(osu_text, speed_rate=1.0, od_flag=None):
    parser = OsuFileParser(osu_text)
    parser.parse()

    if parser.total_notes == 0:
        return {"error": "No notes found", "star": 0, "est_diff": "Unknown"}

    pp = preprocess_file(parser, speed_rate, od_flag)
    if pp["status"] != "OK":
        return {"error": pp["status"], "star": 0, "est_diff": "Unknown"}

    x = pp["x"]
    K = pp["K"]
    T = pp["T"]
    note_seq = pp["note_seq"]
    note_seq_by_column = pp["note_seq_by_column"]
    ln_seq = pp["ln_seq"]
    tail_seq = pp["tail_seq"]
    ln_ratio = pp["ln_ratio"]
    column_count = pp["column_count"]

    print(f"  Parsed: {len(note_seq)} notes, {K}K, OD={parser.od}, LN ratio={ln_ratio:.3f}")
    print(f"  x-factor: {x:.6f}")
    print(f"  Map length: {max((n[1] for n in note_seq), default=0) / 1000:.1f}s")

    all_corners, base_corners, a_corners = get_corners(T, note_seq)
    print(f"  Corners: {len(all_corners)} all, {len(base_corners)} base, {len(a_corners)} A")

    key_usage = get_key_usage(K, T, note_seq, base_corners)
    active_columns = [[k for k in range(K) if key_usage[k][i]] for i in range(len(base_corners))]

    print("  Computing key_usage_400...")
    key_usage_400 = get_key_usage_400(K, T, note_seq, base_corners)

    print("  Computing anchor...")
    anchor = compute_anchor(K, key_usage_400, base_corners)

    print("  Computing Jbar...")
    delta_ks, Jbar_base = compute_jbar(K, x, note_seq_by_column, base_corners)
    Jbar = interp_values(all_corners, base_corners, Jbar_base)

    print("  Computing Xbar...")
    Xbar_base = compute_xbar(K, x, note_seq_by_column, active_columns, base_corners)
    Xbar = interp_values(all_corners, base_corners, Xbar_base)

    print("  Computing Pbar...")
    ln_rep = ln_bodies_count_sparse(ln_seq, T)
    Pbar_base = compute_pbar(x, note_seq, ln_rep, anchor, base_corners)
    Pbar = interp_values(all_corners, base_corners, Pbar_base)

    print("  Computing Abar...")
    Abar_base = compute_abar(K, active_columns, delta_ks, a_corners, base_corners)
    Abar = interp_values(all_corners, a_corners, Abar_base)

    print("  Computing Rbar...")
    Rbar_base = compute_rbar(K, x, note_seq_by_column, tail_seq, base_corners)
    Rbar = interp_values(all_corners, base_corners, Rbar_base)

    print("  Computing C and Ks...")
    C_step, Ks_step = compute_c_and_ks(K, note_seq, key_usage, base_corners)
    CArr = step_interp(all_corners, base_corners, C_step)
    KsArr = step_interp(all_corners, base_corners, Ks_step)

    print("  Computing D...")
    DAll = [0.0] * len(all_corners)
    for i in range(len(all_corners)):
        j_val = Jbar[i] if i < len(Jbar) else 0
        x_val = Xbar[i] if i < len(Xbar) else 0
        p_val = Pbar[i] if i < len(Pbar) else 0
        a_val = Abar[i] if i < len(Abar) else 0
        r_val = Rbar[i] if i < len(Rbar) else 0
        c_val = CArr[i] if i < len(CArr) else 0
        ks_val = KsArr[i] if i < len(KsArr) else 1

        j_eff = min(j_val, 8 + 0.85 * j_val)
        left_part = 0.4 * ((a_val ** (3.0 / max(ks_val, 1)) * j_eff) ** 1.5)
        right_part = 0.6 * ((a_val ** (2.0 / 3.0) * (0.8 * p_val + r_val * 35.0 / max(c_val + 8, 1))) ** 1.5)
        SAll = (left_part + right_part) ** (2.0 / 3.0)
        TAll = (a_val ** (3.0 / max(ks_val, 1)) * x_val) / max(x_val + SAll + 1, 1e-9)
        DAll[i] = 2.7 * (SAll ** 0.5) * (TAll ** 1.5) + SAll * 0.27

    print("  Computing percentiles...")
    gaps = [0.0] * len(all_corners)
    gaps[0] = (all_corners[1] - all_corners[0]) / 2
    gaps[-1] = (all_corners[-1] - all_corners[-2]) / 2
    for i in range(1, len(all_corners) - 1):
        gaps[i] = (all_corners[i + 1] - all_corners[i - 1]) / 2

    effective_weights = [CArr[i] * gaps[i] for i in range(len(CArr))]

    sorted_indices = sorted(range(len(DAll)), key=lambda j: DAll[j])
    D_sorted = [DAll[j] for j in sorted_indices]
    w_sorted = [effective_weights[j] for j in sorted_indices]

    cum_weights = [0.0] * len(w_sorted)
    running = 0.0
    for i in range(len(w_sorted)):
        running += w_sorted[i]
        cum_weights[i] = running

    total_weight = cum_weights[-1]
    norm_cum_weights = [w / total_weight for w in cum_weights]

    target_percentiles = [0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815]
    pct_indices = [bisect_left(norm_cum_weights, p) for p in target_percentiles]

    first_group = [D_sorted[min(i, len(D_sorted) - 1)] for i in pct_indices[:4]]
    second_group = [D_sorted[min(i, len(D_sorted) - 1)] for i in pct_indices[4:]]

    pct93 = sum(first_group) / len(first_group)
    pct83 = sum(second_group) / len(second_group)

    num = 0.0
    den = 0.0
    for i in range(len(D_sorted)):
        num += (D_sorted[i] ** 5) * w_sorted[i]
        den += w_sorted[i]
    weighted_mean = (num / den) ** (1.0 / 5.0) if den > 0 else 0.0

    sr = (0.88 * pct93) * 0.25 + (0.94 * pct83) * 0.2 + weighted_mean * 0.55
    sr = (sr ** 1) / (8 ** 1) * 8

    ln_length_term = 0.0
    for _, h, t in ln_seq:
        ln_length_term += min(t - h, 1000) / 200.0
    total_notes = len(note_seq) + 0.5 * ln_length_term

    sr *= total_notes / (total_notes + 60)
    sr = rescale_high(sr)
    sr *= 0.975

    result = {
        "star": sr,
        "ln_ratio": ln_ratio,
        "column_count": column_count,
        "total_notes": len(note_seq),
        "ln_count": len(ln_seq),
        "od": parser.od,
    }
    result["est_diff"] = est_diff(sr, ln_ratio, column_count)

    return result


# ============================================================
# Daniel algorithm
# ============================================================

DAN_MEANS = [
    (6.562, "Alpha"),
    (6.957, "Beta"),
    (7.459, "Gamma"),
    (7.939, "Delta"),
    (9.095, "Epsilon"),
    (9.473, "Emik Zeta"),
    (10.162, "Thaumiel Eta"),
    (10.782, "CloverWisp Theta"),
]


def estimate_daniel_dan(sr):
    if not math.isfinite(sr):
        return {"label": "Unknown", "numeric": None}

    means = [m[0] for m in DAN_MEANS]
    names = [m[1] for m in DAN_MEANS]
    boundaries = []
    for i in range(len(means)):
        if i > 0:
            lower = (means[i - 1] + means[i]) / 2
        else:
            lower = means[i] - ((means[1] + means[i]) / 2 - means[i])
        if i < len(means) - 1:
            upper = (means[i] + means[i + 1]) / 2
        else:
            upper = means[i] + ((means[i] - means[i - 1]) / 2)
        boundaries.append((lower, upper))

    if sr < boundaries[0][0]:
        return {"label": f"< {names[0]} Low", "numeric": None}

    if sr >= boundaries[-1][1]:
        return {"label": f"> {names[-1]} High", "numeric": None}

    for i, (lower, upper) in enumerate(boundaries):
        if lower <= sr < upper:
            t_raw = (sr - lower) / (upper - lower)
            t = max(0.0, min(1.0, t_raw))
            numeric = round(11 + i + t, 2)

            if t < 1 / 3:
                label = f"{names[i]} Low"
            elif t < 2 / 3:
                label = f"{names[i]} Mid"
            else:
                label = f"{names[i]} High"

            return {"label": label, "numeric": numeric}

    return {"label": "Unknown", "numeric": None}


def preprocess_daniel(parser, speed_rate):
    column_count = parser.column_count
    ln_ratio = parser.ln_ratio

    if column_count != 4:
        return {"status": "UnsupportedKeys", "K": column_count}

    od = 9  # Daniel always uses OD=9
    time_scale = 1.0 / speed_rate if speed_rate != 0 else 1.0

    note_seq = []
    for i in range(len(parser.columns)):
        k = parser.columns[i]
        h = int(parser.note_starts[i] * time_scale)
        note_seq.append([k, h])

    note_seq.sort(key=lambda n: (n[1], n[0]))

    K = column_count
    note_seq_by_column = [[] for _ in range(K)]
    for n in note_seq:
        col = n[0]
        if 0 <= col < K:
            note_seq_by_column[col].append(n)

    x = 0.3 * math.sqrt((64.5 - math.ceil(od * 3)) / 500)
    x = min(x, 0.6 * (x - 0.09) + 0.09)

    T = note_seq[-1][1] + 1 if note_seq else 0

    return {
        "status": "OK",
        "x": x,
        "K": K,
        "T": T,
        "note_seq": note_seq,
        "note_seq_by_column": note_seq_by_column,
        "ln_ratio": ln_ratio,
        "column_count": column_count,
    }


def get_corners_daniel(T, note_seq):
    corners_base = set()
    for _, h in note_seq:
        corners_base.add(h)
        corners_base.add(h + 501)
        corners_base.add(h - 499)
        corners_base.add(h + 1)
    corners_base.add(0)
    corners_base.add(T)
    base_corners = sorted([s for s in corners_base if 0 <= s <= T])

    corners_a = set()
    for _, h in note_seq:
        corners_a.add(h)
        corners_a.add(h + 1000)
        corners_a.add(h - 1000)
    corners_a.add(0)
    corners_a.add(T)
    a_corners = sorted([s for s in corners_a if 0 <= s <= T])

    all_corners = sorted(set(base_corners + a_corners))
    return all_corners, base_corners, a_corners


def get_key_usage_daniel(K, T, note_seq, base_corners):
    key_usage = {k: [0] * len(base_corners) for k in range(K)}
    for k, h in note_seq:
        start_time = max(h - 150, 0)
        end_time = min(h + 150, T - 1)
        left_idx = bisect_left(base_corners, start_time)
        right_idx = bisect_left(base_corners, end_time)
        for idx in range(left_idx, right_idx):
            if idx < len(key_usage[k]):
                key_usage[k][idx] = 1
    return key_usage


def get_key_usage_400_daniel(K, note_seq, base_corners):
    key_usage_400 = {k: [0.0] * len(base_corners) for k in range(K)}
    for k, h in note_seq:
        left_400_idx = bisect_left(base_corners, h - 400)
        center_idx = bisect_left(base_corners, h)
        right_400_idx = bisect_left(base_corners, h + 400)

        if 0 <= center_idx < len(base_corners):
            key_usage_400[k][center_idx] += 3.75

        for idx in range(left_400_idx, center_idx):
            dist = base_corners[idx] - h
            key_usage_400[k][idx] += 3.75 - (3.75 / (400 ** 2)) * (dist ** 2)

        for idx in range(center_idx + 1, right_400_idx):
            dist = base_corners[idx] - h
            key_usage_400[k][idx] += 3.75 - (3.75 / (400 ** 2)) * (dist ** 2)

    return key_usage_400


def daniel_stream_booster(delta):
    bpm = max(0.0, min(7.5 / max(delta, 1e-9), 420.0))
    primary = 0.10 / (1 + math.exp(-0.06 * (bpm - 175)))
    secondary = 0.30 * (1 - math.exp(-0.02 * (bpm - 200))) if 200 <= bpm <= 350 else 0.0
    return 1 + primary + secondary


def compute_pbar_daniel(x, note_seq, anchor, base_corners):
    p_step = [0.0] * len(base_corners)

    for i in range(len(note_seq) - 1):
        h_l = note_seq[i][1]
        h_r = note_seq[i + 1][1]
        delta_time = h_r - h_l

        if delta_time < 1e-9:
            spike = 1000 * ((0.02 * (4 / x - 24)) ** 0.25)
            left_idx = bisect_left(base_corners, h_l)
            right_idx = bisect_right(base_corners, h_l)
            for idx in range(left_idx, right_idx):
                p_step[idx] += spike
            continue

        left_idx = bisect_left(base_corners, h_l)
        right_idx = bisect_left(base_corners, h_r)
        if left_idx >= right_idx:
            continue

        delta = 0.001 * delta_time
        b_val = daniel_stream_booster(delta)
        base_inc = (0.08 * (x ** -1) * (1 - 24 * (x ** -1) * ((x / 6) ** 2))) ** 0.25

        if delta < (2 * x) / 3:
            inner = 0.08 * (x ** -1) * (1 - 24 * (x ** -1) * ((delta - x / 2) ** 2))
            inc = (delta ** -1) * (max(inner, 0) ** 0.25) * max(b_val, 1.0)
        else:
            inc = (delta ** -1) * base_inc * max(b_val, 1.0)

        for idx in range(left_idx, right_idx):
            anc = anchor[idx] if idx < len(anchor) else 1.0
            p_step[idx] += min(inc * anc, max(inc, inc * 2 - 10))

    return smooth_on_corners(base_corners, p_step, 500, 0.001, "sum")


def calculate_daniel(osu_text, speed_rate=1.0):
    parser = OsuFileParser(osu_text)
    parser.parse()

    if parser.total_notes == 0:
        return {"error": "No notes found", "star": 0, "est_diff": "Unknown"}

    pp = preprocess_daniel(parser, speed_rate)
    if pp["status"] != "OK":
        return {"error": pp["status"], "star": 0, "est_diff": "Unknown"}

    x = pp["x"]
    K = pp["K"]
    T = pp["T"]
    note_seq = pp["note_seq"]
    note_seq_by_column = pp["note_seq_by_column"]
    ln_ratio = pp["ln_ratio"]
    column_count = pp["column_count"]

    print(f"  [Daniel] Parsed: {len(note_seq)} notes, {K}K, OD=9 (fixed), LN ratio={ln_ratio:.3f}")
    print(f"  [Daniel] x-factor: {x:.6f}")
    print(f"  [Daniel] Map length: {max((n[1] for n in note_seq), default=0) / 1000:.1f}s")

    all_corners, base_corners, a_corners = get_corners_daniel(T, note_seq)
    print(f"  [Daniel] Corners: {len(all_corners)} all, {len(base_corners)} base, {len(a_corners)} A")

    key_usage = get_key_usage_daniel(K, T, note_seq, base_corners)
    active_columns = [[k for k in range(K) if key_usage[k][i]] for i in range(len(base_corners))]

    print("  [Daniel] Computing key_usage_400...")
    key_usage_400 = get_key_usage_400_daniel(K, note_seq, base_corners)

    print("  [Daniel] Computing anchor...")
    anchor = compute_anchor(K, key_usage_400, base_corners)

    print("  [Daniel] Computing Jbar...")
    delta_ks, Jbar_base = compute_jbar(K, x, note_seq_by_column, base_corners)
    Jbar = interp_values(all_corners, base_corners, Jbar_base)

    print("  [Daniel] Computing Xbar...")
    Xbar_base = compute_xbar(K, x, note_seq_by_column, active_columns, base_corners)
    Xbar = interp_values(all_corners, base_corners, Xbar_base)

    print("  [Daniel] Computing Pbar...")
    Pbar_base = compute_pbar_daniel(x, note_seq, anchor, base_corners)
    Pbar = interp_values(all_corners, base_corners, Pbar_base)

    print("  [Daniel] Computing Abar...")
    Abar_base = compute_abar(K, active_columns, delta_ks, a_corners, base_corners)
    Abar = interp_values(all_corners, a_corners, Abar_base)

    print("  [Daniel] Computing C and Ks...")
    C_step, Ks_step = compute_c_and_ks(K, note_seq, key_usage, base_corners)
    CArr = step_interp(all_corners, base_corners, C_step)
    KsArr = step_interp(all_corners, base_corners, Ks_step)

    print("  [Daniel] Computing D...")
    DAll = [0.0] * len(all_corners)
    for i in range(len(all_corners)):
        j_val = Jbar[i] if i < len(Jbar) else 0
        x_val = Xbar[i] if i < len(Xbar) else 0
        p_val = Pbar[i] if i < len(Pbar) else 0
        a_val = Abar[i] if i < len(Abar) else 0
        c_val = CArr[i] if i < len(CArr) else 0
        ks_val = KsArr[i] if i < len(KsArr) else 1

        j_eff = min(j_val, 8 + 0.85 * j_val)
        left_part = 0.4 * ((a_val ** (3.0 / max(ks_val, 1)) * j_eff) ** 1.5)
        right_part = 0.6 * ((a_val ** (2.0 / 3.0) * (0.8 * p_val)) ** 1.5)
        SAll = (left_part + right_part) ** (2.0 / 3.0)
        TAll = (a_val ** (3.0 / max(ks_val, 1)) * x_val) / max(x_val + SAll + 1, 1e-9)
        DAll[i] = 2.7 * (SAll ** 0.5) * (TAll ** 1.5) + SAll * 0.27

    print("  [Daniel] Computing percentiles...")
    gaps = [0.0] * len(all_corners)
    gaps[0] = (all_corners[1] - all_corners[0]) / 2
    gaps[-1] = (all_corners[-1] - all_corners[-2]) / 2
    for i in range(1, len(all_corners) - 1):
        gaps[i] = (all_corners[i + 1] - all_corners[i - 1]) / 2

    effective_weights = [CArr[i] * gaps[i] for i in range(len(CArr))]

    sorted_indices = sorted(range(len(DAll)), key=lambda j: DAll[j])
    D_sorted = [DAll[j] for j in sorted_indices]
    w_sorted = [effective_weights[j] for j in sorted_indices]

    cum_weights = [0.0] * len(w_sorted)
    running_cum = 0.0
    for i in range(len(w_sorted)):
        running_cum += w_sorted[i]
        cum_weights[i] = running_cum

    total_weight = cum_weights[-1]
    if not math.isfinite(total_weight) or total_weight <= 0:
        return {"star": 0, "ln_ratio": ln_ratio, "column_count": column_count, "est_diff": "Unknown"}

    norm_cum_weights = [w / total_weight for w in cum_weights]

    target_percentiles = [0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815]
    pct_indices = [bisect_left(norm_cum_weights, p) for p in target_percentiles]

    first_group = [D_sorted[min(i, len(D_sorted) - 1)] for i in pct_indices[:4]]
    second_group = [D_sorted[min(i, len(D_sorted) - 1)] for i in pct_indices[4:]]

    pct93 = sum(first_group) / len(first_group)
    pct83 = sum(second_group) / len(second_group)

    num = 0.0
    den = 0.0
    for i in range(len(D_sorted)):
        num += (D_sorted[i] ** 5) * w_sorted[i]
        den += w_sorted[i]
    weighted_mean = (num / max(den, 1e-9)) ** 0.2

    sr = (0.88 * pct93) * 0.25 + (0.94 * pct83) * 0.2 + weighted_mean * 0.55
    sr *= len(note_seq) / (len(note_seq) + 60)
    sr = rescale_high(sr)
    sr *= 0.975

    dan_result = estimate_daniel_dan(sr)

    return {
        "star": sr,
        "ln_ratio": ln_ratio,
        "column_count": column_count,
        "total_notes": len(note_seq),
        "ln_count": parser.ln_count,
        "od": 9,
        "est_diff": dan_result["label"],
        "est_diff_numeric": dan_result["numeric"],
    }


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    import time

    with open("5732935.osu", "r", encoding="utf-8") as f:
        osu_text = f.read()

    print("=" * 60)
    print("  osumania_map_analyser - Sunny Rework + Daniel Algorithm")
    print("  Beatmap: Once Forgotten, Nothing Remains (MWC4K 2025 GF TB)")
    print("=" * 60)

    start = time.time()
    result_sunny = calculate(osu_text)
    elapsed_sunny = time.time() - start

    print()
    print("=" * 60)
    print(f"  [Sunny] Time: {elapsed_sunny:.2f}s")
    print(f"  [Sunny] Star Rating: {result_sunny['star']:.4f}")
    print(f"  [Sunny] Estimated Difficulty: {result_sunny['est_diff']}")
    print(f"  [Sunny] LN Ratio: {result_sunny['ln_ratio']:.3f} ({result_sunny['ln_count']}/{result_sunny['total_notes']} LN)")
    print(f"  [Sunny] OD: {result_sunny['od']}")
    print("=" * 60)

    start = time.time()
    result_daniel = calculate_daniel(osu_text)
    elapsed_daniel = time.time() - start

    print()
    print("=" * 60)
    print(f"  [Daniel] Time: {elapsed_daniel:.2f}s")
    print(f"  [Daniel] Star Rating: {result_daniel['star']:.4f}")
    print(f"  [Daniel] Estimated Difficulty: {result_daniel['est_diff']}")
    if result_daniel.get("est_diff_numeric") is not None:
        print(f"  [Daniel] Numeric Difficulty: {result_daniel['est_diff_numeric']:.2f}")
    print(f"  [Daniel] LN Ratio: {result_daniel['ln_ratio']:.3f} ({result_daniel['ln_count']}/{result_daniel['total_notes']} LN)")
    print(f"  [Daniel] OD: {result_daniel['od']} (fixed)")
    print("=" * 60)
