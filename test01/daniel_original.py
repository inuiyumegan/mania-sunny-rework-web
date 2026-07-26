import math
import numpy as np


class Parser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.od = -1
        self.column_count = -1
        self.columns = []
        self.note_starts = []
        self.note_ends = []
        self.note_types = []

    def process(self):
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                self._read_metadata(line)
                cc = self._read_column_count(line)
                if cc != -1:
                    self.column_count = cc
                self.od = 9
                if self.column_count != -1:
                    self._read_notes(f, line, self.column_count)
                    break

    def _read_metadata(self, line):
        if "[Metadata]" in line:
            return

    def _read_column_count(self, line):
        if "CircleSize:" not in line:
            return -1
        val = line.strip()[-1]
        if val == "0":
            val = "10"
        return int(float(val))

    def _read_notes(self, f, line, column_count):
        if "[HitObjects]" not in line:
            return
        for note_line in f:
            note_line = note_line.strip()
            if not note_line or note_line.startswith("["):
                break
            self._parse_hit_object(note_line, column_count)

    def _parse_hit_object(self, line, column_count):
        params = line.split(",")
        column_width = 512 // column_count
        self.columns.append(int(float(params[0])) // column_width)
        self.note_starts.append(int(params[2]))
        self.note_types.append(int(params[3]))
        self.note_ends.append(int(params[5].split(":")[0]))

    def get_parsed_data(self):
        return [
            self.column_count,
            self.columns,
            self.note_starts,
            self.note_ends,
            self.note_types,
            self.od,
        ]


def cumulative_sum(x, f):
    F = np.zeros(len(x))
    F[1:] = np.cumsum(f[:-1] * np.diff(x))
    return F


def smooth_on_corners(x, f, window, scale=1.0, mode="sum"):
    x = np.asarray(x, dtype=float)
    f = np.asarray(f, dtype=float)
    F = cumulative_sum(x, f)
    a = np.clip(x - window, x[0], x[-1])
    b = np.clip(x + window, x[0], x[-1])

    def _query_vec(q_arr):
        idx = np.searchsorted(x, q_arr) - 1
        idx = np.clip(idx, 0, len(x) - 2)
        return F[idx] + f[idx] * (q_arr - x[idx])

    val = _query_vec(b) - _query_vec(a)
    if mode == "avg":
        span = b - a
        return np.where(span > 0, val / span, 0.0)
    return scale * val


def rescale_high(sr):
    if sr <= 9:
        return sr
    return 9 + (sr - 9) / 1.2


def preprocess_file(file_path, mod="NM"):
    p_obj = Parser(file_path)
    p_obj.process()
    p = p_obj.get_parsed_data()

    note_seq = []
    for i in range(len(p[1])):
        k = p[1][i]
        h = p[2][i]
        if mod == "DT":
            h = int(math.floor(h * 2 / 3))
        elif mod == "HT":
            h = int(math.floor(h * 4 / 3))
        note_seq.append((k, h))

    x = 0.3 * ((64.5 - math.ceil(p[5] * 3)) / 500) ** 0.5
    x = min(x, 0.6 * (x - 0.09) + 0.09)
    note_seq.sort(key=lambda tup: (tup[1], tup[0]))

    note_dict = {}
    for tup in note_seq:
        note_dict.setdefault(tup[0], []).append(tup)
    note_seq_by_column = sorted(note_dict.values(), key=lambda lst: lst[0][0])

    K = p[0]
    T = max(n[1] for n in note_seq) + 1

    return x, K, T, note_seq, note_seq_by_column


def get_corners(T, note_seq):
    corners_base = set()
    for _, h in note_seq:
        corners_base.update([h, h + 501, h - 499, h + 1])
    corners_base.update([0, T])
    corners_base = sorted(s for s in corners_base if 0 <= s <= T)

    corners_A = set()
    for _, h in note_seq:
        corners_A.update([h, h + 1000, h - 1000])
    corners_A.update([0, T])
    corners_A = sorted(s for s in corners_A if 0 <= s <= T)

    all_corners = sorted(set(corners_base) | set(corners_A))
    return (
        np.array(all_corners, dtype=float),
        np.array(corners_base, dtype=float),
        np.array(corners_A, dtype=float),
    )


def get_key_usage(K, T, note_seq, base_corners):
    key_usage = {k: np.zeros(len(base_corners), dtype=bool) for k in range(K)}
    for k, h in note_seq:
        start = max(h - 150, 0)
        end = min(h + 150, T - 1)
        li = np.searchsorted(base_corners, start, side="left")
        ri = np.searchsorted(base_corners, end, side="left")
        key_usage[k][li:ri] = True
    return key_usage


def get_key_usage_400(K, T, note_seq, base_corners):
    key_usage_400 = {k: np.zeros(len(base_corners), dtype=float) for k in range(K)}
    for k, h in note_seq:
        start = max(h, 0)
        li = np.searchsorted(base_corners, start - 400, side="left")
        ri = np.searchsorted(base_corners, start + 400, side="left")
        mid = np.searchsorted(base_corners, start, side="left")
        key_usage_400[k][mid] += 3.75
        for idx_range in [np.arange(li, mid), np.arange(mid + 1, ri)]:
            if len(idx_range) > 0:
                key_usage_400[k][idx_range] += 3.75 - 3.75 / 400 ** 2 * (base_corners[idx_range] - start) ** 2
    return key_usage_400


def compute_anchor(K, key_usage_400, base_corners):
    counts = np.stack([key_usage_400[k] for k in range(K)], axis=1)
    counts = np.sort(counts, axis=1)[:, ::-1]
    nonzero_mask = counts > 0
    n_nz = nonzero_mask.sum(axis=1)
    c0 = counts[:, :-1]
    c1 = counts[:, 1:]
    safe_c0 = np.where(c0 > 0, c0, 1.0)
    ratio = np.where(c0 > 0, c1 / safe_c0, 0.0)
    weight = 1 - 4 * (0.5 - ratio) ** 2
    pair_valid = nonzero_mask[:, :-1] & nonzero_mask[:, 1:]
    walk = np.sum(np.where(pair_valid, c0 * weight, 0.0), axis=1)
    max_walk = np.sum(np.where(pair_valid, c0, 0.0), axis=1)
    raw_anchor = np.where(n_nz > 1, walk / np.maximum(max_walk, 1e-9), 0.0)
    return 1 + np.minimum(raw_anchor - 0.18, 5 * (raw_anchor - 0.22) ** 3)


def compute_Jbar(K, T, x, note_seq_by_column, base_corners):
    def jack_nerfer(delta):
        return 1 - 7e-5 * (0.15 + np.abs(delta - 0.08)) ** (-4)

    J_ks = {k: np.zeros(len(base_corners)) for k in range(K)}
    delta_ks = {k: np.full(len(base_corners), 1e9) for k in range(K)}

    for k in range(K):
        notes = note_seq_by_column[k]
        if len(notes) < 2:
            continue
        starts = np.array([n[1] for n in notes[:-1]], dtype=float)
        ends = np.array([n[1] for n in notes[1:]], dtype=float)
        deltas = 0.001 * (ends - starts)
        vals = deltas ** -1 * (deltas + 0.11 * x ** 0.25) ** -1 * jack_nerfer(deltas)

        for start, end, delta, val in zip(starts, ends, deltas, vals):
            li = np.searchsorted(base_corners, start, side="left")
            ri = np.searchsorted(base_corners, end, side="left")
            if ri > li:
                J_ks[k][li:ri] = val
                delta_ks[k][li:ri] = delta

    Jbar_ks = {
        k: smooth_on_corners(base_corners, J_ks[k], window=500, scale=0.001, mode="sum")
        for k in range(K)
    }
    Jbar_stack = np.stack([Jbar_ks[k] for k in range(K)], axis=0)
    delta_stack = np.stack([delta_ks[k] for k in range(K)], axis=0)
    weights = 1.0 / delta_stack
    num = np.sum(np.maximum(Jbar_stack, 0) ** 5 * weights, axis=0)
    den = np.sum(weights, axis=0)
    Jbar = (num / np.maximum(den, 1e-9)) ** 0.2

    return delta_ks, Jbar


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


def compute_Xbar(K, T, x, note_seq_by_column, active_columns, base_corners):
    cross_coeff = CROSS_MATRIX[K]
    X_ks = {k: np.zeros(len(base_corners)) for k in range(K + 1)}
    fast_cross = {k: np.zeros(len(base_corners)) for k in range(K + 1)}

    for k in range(K + 1):
        if k == 0:
            notes_in_pair = note_seq_by_column[0]
        elif k == K:
            notes_in_pair = note_seq_by_column[K - 1]
        else:
            notes_in_pair = sorted(
                note_seq_by_column[k - 1] + note_seq_by_column[k], key=lambda t: t[1]
            )

        for i in range(1, len(notes_in_pair)):
            start = notes_in_pair[i - 1][1]
            end = notes_in_pair[i][1]
            if end <= start:
                continue

            li = np.searchsorted(base_corners, start, side="left")
            ri = np.searchsorted(base_corners, end, side="left")
            if ri <= li:
                continue

            delta = 0.001 * (end - start)
            val = 0.16 * max(x, delta) ** -2

            left_inactive = (
                (k - 1) not in active_columns[li]
                and (k - 1) not in active_columns[min(ri, len(active_columns) - 1)]
            )
            right_inactive = (
                k not in active_columns[li]
                and k not in active_columns[min(ri, len(active_columns) - 1)]
            )
            if left_inactive or right_inactive:
                val *= 1 - cross_coeff[k]

            X_ks[k][li:ri] = val
            fast_cross[k][li:ri] = max(0, 0.4 * max(delta, 0.06, 0.75 * x) ** -2 - 80)

    X_base = np.zeros(len(base_corners))
    for i in range(len(base_corners)):
        sum1 = sum(X_ks[k][i] * cross_coeff[k] for k in range(K + 1))
        sum2 = 0.0
        for k in range(K):
            val = fast_cross[k][i] * cross_coeff[k] * fast_cross[k + 1][i] * cross_coeff[k + 1]
            if val > 0:
                sum2 += np.sqrt(val)
        X_base[i] = sum1 + sum2

    return smooth_on_corners(base_corners, X_base, window=500, scale=0.001, mode="sum")


def compute_Pbar(K, T, x, note_seq, anchor, base_corners):
    def stream_booster(delta):
        bpm = np.clip(7.5 / delta, 0, 420)
        primary = 0.10 / (1 + np.exp(-0.06 * (bpm - 175)))
        secondary = np.where(
            (bpm >= 200) & (bpm <= 350),
            0.30 * (1 - np.exp(-0.02 * (bpm - 200))),
            0.0,
        )
        return 1 + primary + secondary

    P_step = np.zeros(len(base_corners))

    for i in range(len(note_seq) - 1):
        h_l = note_seq[i][1]
        h_r = note_seq[i + 1][1]
        delta_time = h_r - h_l

        if delta_time < 1e-9:
            spike = 1000 * (0.02 * (4 / x - 24)) ** 0.25
            li = np.searchsorted(base_corners, h_l, side="left")
            ri = np.searchsorted(base_corners, h_l, side="right")
            if ri > li:
                P_step[li:ri] += spike
            continue

        li = np.searchsorted(base_corners, h_l, side="left")
        ri = np.searchsorted(base_corners, h_r, side="left")
        if ri <= li:
            continue

        delta = 0.001 * delta_time
        b_val = stream_booster(delta)
        base_inc = (0.08 * x ** -1 * (1 - 24 * x ** -1 * (x / 6) ** 2)) ** 0.25

        if delta < 2 * x / 3:
            inc = delta ** -1 * (0.08 * x ** -1 * (1 - 24 * x ** -1 * (delta - x / 2) ** 2)) ** 0.25 * max(b_val, 1)
        else:
            inc = delta ** -1 * base_inc * max(b_val, 1)

        seg_anchor = anchor[li:ri]
        P_step[li:ri] += np.minimum(inc * seg_anchor, np.maximum(inc, inc * 2 - 10))

    return smooth_on_corners(base_corners, P_step, window=500, scale=0.001, mode="sum")


def compute_Abar(K, T, x, note_seq_by_column, active_columns, delta_ks, A_corners, base_corners):
    dks = {k: np.zeros(len(base_corners)) for k in range(K - 1)}
    for i in range(len(base_corners)):
        cols = active_columns[i]
        for j in range(len(cols) - 1):
            k0, k1 = cols[j], cols[j + 1]
            dks[k0][i] = abs(delta_ks[k0][i] - delta_ks[k1][i]) + 0.4 * max(
                0, max(delta_ks[k0][i], delta_ks[k1][i]) - 0.11
            )

    A_step = np.ones(len(A_corners))
    bc_idx = np.clip(np.searchsorted(base_corners, A_corners), 0, len(base_corners) - 1)

    for i in range(len(A_corners)):
        idx = bc_idx[i]
        cols = active_columns[idx]
        for j in range(len(cols) - 1):
            k0, k1 = cols[j], cols[j + 1]
            d_val = dks[k0][idx]
            dk0, dk1 = delta_ks[k0][idx], delta_ks[k1][idx]
            if d_val < 0.02:
                A_step[i] *= min(0.75 + 0.5 * max(dk0, dk1), 1)
            elif d_val < 0.07:
                A_step[i] *= min(0.65 + 5 * d_val + 0.5 * max(dk0, dk1), 1)

    return smooth_on_corners(A_corners, A_step, window=250, mode="avg")


def compute_C_and_Ks(K, T, note_seq, key_usage, base_corners):
    note_hit_times = np.array(sorted(n[1] for n in note_seq), dtype=float)
    lo = np.searchsorted(note_hit_times, base_corners - 500, side="left")
    hi = np.searchsorted(note_hit_times, base_corners + 500, side="left")
    C_step = (hi - lo).astype(float)
    Ks_step = np.maximum(
        np.stack([key_usage[k] for k in range(K)], axis=0).sum(axis=0), 1
    ).astype(float)
    return C_step, Ks_step


# Dan level mapping (from daniel.py)
DAN_MEANS = {
    "Alpha": 6.562,
    "Beta": 6.957,
    "Gamma": 7.459,
    "Delta": 7.939,
    "Epsilon": 9.095,
    "Zeta": 9.473,
    "Eta": 10.162,
    "Theta": 10.782,
}
ORDER = list(DAN_MEANS.keys())
DAN_ORDER_START = 11


def _precompute_dan_boundaries():
    means = [DAN_MEANS[d] for d in ORDER]
    boundaries = []
    for i in range(len(ORDER)):
        mean = means[i]
        lower = (means[i - 1] + mean) / 2 if i > 0 else mean - ((means[1] + mean) / 2 - mean)
        upper = (mean + means[i + 1]) / 2 if i < len(means) - 1 else mean + (mean - means[i - 1]) / 2
        boundaries.append((lower, upper))
    return boundaries


_DAN_BOUNDARIES = _precompute_dan_boundaries()


def get_dan_from_diff(diff):
    if diff < _DAN_BOUNDARIES[0][0]:
        return f"<{ORDER[0]} Low", None
    if diff >= _DAN_BOUNDARIES[-1][1]:
        return "? ? ? ? ?", None

    for i, dan in enumerate(ORDER):
        lower, upper = _DAN_BOUNDARIES[i]
        if lower <= diff < upper:
            t = max(0.0, min((diff - lower) / (upper - lower), 1.0))
            numeric = round(DAN_ORDER_START + i + t, 2)
            if t < 1 / 3:
                label = f"{dan} Low"
            elif t < 2 / 3:
                label = f"{dan} Mid"
            else:
                label = f"{dan} High"
            return label, numeric

    return "? ? ? ? ?", None


def calculate(file_path, mod="NM"):
    x, K, T, note_seq, note_seq_by_column = preprocess_file(file_path, mod)
    all_corners, base_corners, A_corners = get_corners(T, note_seq)

    key_usage = get_key_usage(K, T, note_seq, base_corners)
    active_columns = [[k for k in range(K) if key_usage[k][i]] for i in range(len(base_corners))]
    key_usage_400 = get_key_usage_400(K, T, note_seq, base_corners)
    anchor = compute_anchor(K, key_usage_400, base_corners)

    delta_ks, Jbar = compute_Jbar(K, T, x, note_seq_by_column, base_corners)
    Jbar = np.interp(all_corners, base_corners, Jbar)

    Xbar = compute_Xbar(K, T, x, note_seq_by_column, active_columns, base_corners)
    Xbar = np.interp(all_corners, base_corners, Xbar)

    Pbar = compute_Pbar(K, T, x, note_seq, anchor, base_corners)
    Pbar = np.interp(all_corners, base_corners, Pbar)

    Abar = compute_Abar(K, T, x, note_seq_by_column, active_columns, delta_ks, A_corners, base_corners)
    Abar = np.interp(all_corners, A_corners, Abar)

    C_step, Ks_step = compute_C_and_Ks(K, T, note_seq, key_usage, base_corners)
    C_arr = np.interp(all_corners, base_corners, C_step)
    # Step interp for Ks
    indices = np.searchsorted(base_corners, all_corners, side="right") - 1
    indices = np.clip(indices, 0, len(Ks_step) - 1)
    Ks_arr = Ks_step[indices]

    S_all = (
        (0.4 * (Abar ** (3 / Ks_arr) * np.minimum(Jbar, 8 + 0.85 * Jbar)) ** 1.5) +
        (0.6 * (Abar ** (2 / 3) * (0.8 * Pbar)) ** 1.5)
    ) ** (2 / 3)
    T_all = (Abar ** (3 / Ks_arr) * Xbar) / (Xbar + S_all + 1)
    D_all = 2.7 * (S_all ** 0.5) * (T_all ** 1.5) + S_all * 0.27

    gaps = np.empty_like(all_corners, dtype=float)
    gaps[0] = (all_corners[1] - all_corners[0]) / 2.0
    gaps[-1] = (all_corners[-1] - all_corners[-2]) / 2.0
    gaps[1:-1] = (all_corners[2:] - all_corners[:-2]) / 2.0

    effective_weights = C_arr * gaps
    sorted_indices = np.argsort(D_all)
    D_sorted = D_all[sorted_indices]
    w_sorted = effective_weights[sorted_indices]

    cum_weights = np.cumsum(w_sorted)
    total_weight = cum_weights[-1]
    if not math.isfinite(total_weight) or total_weight <= 0:
        return 0, "N/A", None

    norm_cum_weights = cum_weights / total_weight

    target_percentiles = np.array([0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815])
    indices = np.searchsorted(norm_cum_weights, target_percentiles, side="left")

    percentile_93 = np.mean(D_sorted[indices[:4]])
    percentile_83 = np.mean(D_sorted[indices[4:8]])
    weighted_mean = (np.sum(D_sorted ** 5 * w_sorted) / np.sum(w_sorted)) ** 0.2

    SR = 0.88 * percentile_93 * 0.25 + 0.94 * percentile_83 * 0.2 + weighted_mean * 0.55
    total_notes = len(note_seq)
    SR *= total_notes / (total_notes + 60)
    SR = rescale_high(SR) * 0.975

    label, numeric = get_dan_from_diff(SR)

    return SR, label, numeric


if __name__ == "__main__":
    import time

    print("=" * 60)
    print("  Daniel (Original by TheBagelOfMan)")
    print("  Beatmap: Once Forgotten, Nothing Remains (MWC4K 2025 GF TB)")
    print("=" * 60)

    start = time.time()
    sr, label, numeric = calculate("5732935.osu")
    elapsed = time.time() - start

    print()
    print(f"  Calculation time: {elapsed:.2f}s")
    print(f"  Star Rating: {sr:.4f}")
    print(f"  Dan Level: {label}")
    if numeric is not None:
        print(f"  Numeric Dan: {numeric:.2f}")
    print(f"  OD: 9 (fixed by Daniel)")
    print("=" * 60)
