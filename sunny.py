import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import math
import bisect
import numpy as np
from collections import defaultdict

import parser as _parser_mod

# crossMatrix[K] = K+1 coefficients for K-key mode
# 1K: [0.075, 0.075], 2K: [0.125, 0.05, 0.125], ...
CROSS_MATRIX = {
    1: [0.075, 0.075],
    2: [0.125, 0.05, 0.125],
    3: [0.125, 0.125, 0.125, 0.125],
    4: [0.175, 0.25, 0.05, 0.25, 0.175],
    5: [0.175, 0.25, 0.175, 0.175, 0.25, 0.175],
    6: [0.225, 0.35, 0.25, 0.05, 0.25, 0.35, 0.225],
    7: [0.225, 0.35, 0.25, 0.225, 0.225, 0.25, 0.35, 0.225],
    8: [0.275, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.275],
    9: [0.275, 0.45, 0.35, 0.25, 0.275, 0.275, 0.25, 0.35, 0.45, 0.275],
    10: [0.325, 0.55, 0.45, 0.35, 0.25, 0.05, 0.25, 0.35, 0.45, 0.55, 0.325],
}


def _cumulative_sum(x, f):
    F = np.zeros(len(x))
    F[1:] = np.cumsum(f[:-1] * np.diff(x))
    return F


def _smooth_on_corners(x, f, window, scale=1.0, mode="sum"):
    x = np.asarray(x, dtype=float)
    f = np.asarray(f, dtype=float)
    F = _cumulative_sum(x, f)
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


def _rescale_high(sr):
    if sr <= 9:
        return sr
    return 9 + (sr - 9) / 1.2


def _bisect_left(arr, target):
    return bisect.bisect_left(arr, target)


def _bisect_right(arr, target):
    return bisect.bisect_right(arr, target)


# ============================================================
# Sunny-specific: LN helpers
# ============================================================

def _ln_bodies_count_sparse(ln_seq, T):
    diff = defaultdict(float)
    for _, h, t in ln_seq:
        t0 = min(h + 60, t)
        t1 = min(h + 120, t)
        diff[t0] += 1.3
        diff[t1] += -1.3 + 1.0
        diff[t] -= 1.0

    points = sorted(set([0, T]) | set(diff.keys()))
    values = []
    cumsum = [0.0]
    curr = 0.0
    for i in range(len(points) - 1):
        if points[i] in diff:
            curr += diff[points[i]]
        v = min(curr, 2.5 + 0.5 * curr)
        values.append(v)
        cumsum.append(cumsum[-1] + (points[i + 1] - points[i]) * v)
    return {"points": points, "cumsum": cumsum, "values": values}


def _ln_sum(a, b, ln_rep):
    pts, cs, vals = ln_rep["points"], ln_rep["cumsum"], ln_rep["values"]
    i = _bisect_right(pts, a) - 1
    j = _bisect_right(pts, b) - 1
    if i == j:
        return (b - a) * vals[i]
    return (pts[i + 1] - a) * vals[i] + (cs[j] - cs[i + 1]) + (b - pts[j]) * vals[j]


def _find_next_note_in_column(note, times, note_seq_by_column):
    k, h = note[0], note[1]
    idx = _bisect_left(times, h)
    nxt = note_seq_by_column[k][idx + 1] if idx + 1 < len(note_seq_by_column[k]) else [0, 10**9, 10**9]
    return nxt


# ============================================================
# Sunny: preprocess
# ============================================================

def _preprocess(file_path, speed_rate=1.0, od_flag=None):
    p = _parser_mod.OsuFileParser(file_path)
    p.parse()

    od = p.od
    if od_flag == "HR":
        od = 6.462 + 0.715 * od
    elif od_flag == "EZ":
        od = -20.761 + 2.566 * od
    elif od_flag is not None:
        od = float(od_flag)

    time_scale = 1.0 / speed_rate if speed_rate != 0 else 1.0

    note_seq = p.get_note_seq_with_tails(time_scale)

    x = 0.3 * math.sqrt((64.5 - math.ceil(od * 3)) / 500)
    x = min(x, 0.6 * (x - 0.09) + 0.09)

    K = p.column_count
    note_seq_by_column = p.get_note_seq_by_column(note_seq, K)
    ln_seq = [n for n in note_seq if n[2] >= 0]
    tail_seq = sorted(ln_seq, key=lambda n: n[2])

    T = max((max((n[1] for n in note_seq), default=0),
             max((n[2] for n in note_seq), default=0))) + 1

    return {
        "x": x, "K": K, "T": T,
        "note_seq": note_seq,
        "note_seq_by_column": note_seq_by_column,
        "ln_seq": ln_seq, "tail_seq": tail_seq,
        "ln_ratio": p.ln_ratio, "column_count": K,
        "total_notes": p.total_notes, "ln_count": p.ln_count,
        "od_original": p.od,
    }


# ============================================================
# Sunny: corners
# ============================================================

def _get_corners(T, note_seq):
    corners_base = set()
    for _, h, t in note_seq:
        corners_base.update([h, h + 501, h - 499, h + 1])
        if t >= 0:
            corners_base.update([t, t + 501, t - 499, t + 1])
    corners_base.update([0, T])
    base = sorted(s for s in corners_base if 0 <= s <= T)

    corners_a = set()
    for _, h, t in note_seq:
        corners_a.update([h, h + 1000, h - 1000])
        if t >= 0:
            corners_a.update([t, t + 1000, t - 1000])
    corners_a.update([0, T])
    a_corners = sorted(s for s in corners_a if 0 <= s <= T)

    all_crnrs = sorted(set(base) | set(a_corners))
    return np.array(all_crnrs, float), np.array(base, float), np.array(a_corners, float)


# ============================================================
# Sunny: key usage
# ============================================================

def _get_key_usage(K, T, note_seq, base_corners):
    ku = np.zeros((K, len(base_corners)), dtype=bool)
    for k, h, t in note_seq:
        start = max(h - 150, 0)
        end = min(t + 150, T - 1) if t >= 0 else min(h + 150, T - 1)
        li = np.searchsorted(base_corners, start, side="left")
        ri = np.searchsorted(base_corners, end, side="left")
        if ri > li:
            ku[k, li:ri] = True
    return ku


def _get_key_usage_400(K, T, note_seq, base_corners):
    ku400 = np.zeros((K, len(base_corners)), dtype=float)
    for k, h, t in note_seq:
        start = max(h, 0)
        end = t if t >= 0 else h
        end = min(end, T - 1)

        left_400 = np.searchsorted(base_corners, start - 400, "left")
        left = np.searchsorted(base_corners, start, "left")
        right = np.searchsorted(base_corners, end, "left")
        right_400 = np.searchsorted(base_corners, end + 400, "left")

        duration = max(1, end - start)
        ku400[k, left:right] += 3.75 + min(duration, 1500) / 150.0

        for idx in range(left_400, left):
            ku400[k, idx] += 3.75 - (3.75 / 400**2) * (base_corners[idx] - start)**2
        for idx in range(right, right_400):
            ku400[k, idx] += 3.75 - (3.75 / 400**2) * (abs(base_corners[idx] - end))**2
    return ku400


# ============================================================
# Sunny: strain components
# ============================================================

def _compute_anchor(K, ku400, base_corners):
    counts = np.sort(ku400.T, axis=1)[:, ::-1]
    nz_mask = counts > 0
    n_nz = nz_mask.sum(axis=1)
    c0, c1 = counts[:, :-1], counts[:, 1:]
    safe_c0 = np.where(c0 > 0, c0, 1.0)
    ratio = np.where(c0 > 0, c1 / safe_c0, 0.0)
    weight = 1 - 4 * (0.5 - ratio)**2
    pair_valid = nz_mask[:, :-1] & nz_mask[:, 1:]
    walk = np.sum(np.where(pair_valid, c0 * weight, 0.0), axis=1)
    max_walk = np.sum(np.where(pair_valid, c0, 0.0), axis=1)
    raw = np.where(n_nz > 1, walk / np.maximum(max_walk, 1e-9), 0.0)
    return 1 + np.minimum(raw - 0.18, 5 * (raw - 0.22)**3)


def _compute_Jbar(K, x, note_seq_by_column, base_corners):
    def jack_nerfer(delta):
        return 1 - 7e-5 * (0.15 + abs(delta - 0.08))**(-4)

    J_ks = np.zeros((K, len(base_corners)))
    delta_ks = np.full((K, len(base_corners)), 1e9)

    for k in range(K):
        notes = note_seq_by_column[k]
        for i in range(len(notes) - 1):
            start, end = notes[i][1], notes[i + 1][1]
            li = np.searchsorted(base_corners, start, "left")
            ri = np.searchsorted(base_corners, end, "left")
            if ri <= li:
                continue
            delta = 0.001 * (end - start)
            val = delta**-1 * (delta + 0.11 * x**0.25)**-1 * jack_nerfer(delta)
            J_ks[k, li:ri] = val
            delta_ks[k, li:ri] = delta

    Jbar_ks = np.zeros((K, len(base_corners)))
    for k in range(K):
        Jbar_ks[k] = _smooth_on_corners(base_corners, J_ks[k], 500, 0.001, "sum")

    weights = 1.0 / delta_ks
    num = np.sum(np.maximum(Jbar_ks, 0)**5 * weights, axis=0)
    den = np.sum(weights, axis=0)
    return delta_ks, (num / np.maximum(den, 1e-9))**0.2


def _compute_Xbar(K, x, note_seq_by_column, active_columns_set, base_corners):
    cross = CROSS_MATRIX.get(K, [1.0 / (K + 1)] * (K + 1))
    X_ks = {k: np.zeros(len(base_corners)) for k in range(K + 1)}
    fast_cross = {k: np.zeros(len(base_corners)) for k in range(K + 1)}

    for k in range(K + 1):
        if k == 0:
            notes_in_pair = note_seq_by_column[0]
        elif k == K:
            notes_in_pair = note_seq_by_column[K - 1]
        else:
            notes_in_pair = sorted(
                list(note_seq_by_column[k - 1]) + list(note_seq_by_column[k]),
                key=lambda n: n[1]
            )

        for i in range(1, len(notes_in_pair)):
            start, end = notes_in_pair[i - 1][1], notes_in_pair[i][1]
            if end <= start:
                continue
            li = np.searchsorted(base_corners, start, "left")
            ri = np.searchsorted(base_corners, end, "left")
            if ri <= li:
                continue

            delta = 0.001 * (end - start)
            val = 0.16 * max(x, delta)**-2

            la = active_columns_set[li] if li < len(active_columns_set) else set()
            ra = active_columns_set[min(ri, len(active_columns_set) - 1)]

            left_inactive = (k - 1 not in la and k - 1 not in ra)
            right_inactive = (k not in la and k not in ra)
            if left_inactive or right_inactive:
                val *= 1 - cross[k]

            X_ks[k][li:ri] = val
            fast_cross[k][li:ri] = max(0, 0.4 * max(delta, 0.06, 0.75 * x)**-2 - 80)

    X_base = np.zeros(len(base_corners))
    for i in range(len(base_corners)):
        s1 = sum(X_ks[k][i] * cross[k] for k in range(K + 1))
        s2 = sum(
            np.sqrt(max(fast_cross[k][i] * cross[k] * fast_cross[k + 1][i] * cross[k + 1], 0))
            for k in range(K)
        )
        X_base[i] = s1 + s2

    return _smooth_on_corners(base_corners, X_base, 500, 0.001, "sum")


def _compute_Pbar(x, note_seq, ln_rep, anchor, base_corners):
    def stream_booster(delta):
        expr = 7.5 / delta
        if 160 < expr < 360:
            return 1 + 1.7e-7 * (expr - 160) * (expr - 360)**2
        return 1.0

    P_step = np.zeros(len(base_corners))

    for i in range(len(note_seq) - 1):
        h_l, h_r = note_seq[i][1], note_seq[i + 1][1]
        dt = h_r - h_l

        if dt < 1e-9:
            spike = 1000 * (0.02 * (4 / x - 24))**0.25
            li = np.searchsorted(base_corners, h_l, "left")
            ri = np.searchsorted(base_corners, h_l, "right")
            if ri > li:
                P_step[li:ri] += spike
            continue

        li = np.searchsorted(base_corners, h_l, "left")
        ri = np.searchsorted(base_corners, h_r, "left")
        if ri <= li:
            continue

        delta = 0.001 * dt
        v = 1 + 6 * 0.001 * _ln_sum(h_l, h_r, ln_rep)
        b_val = stream_booster(delta)

        if delta < 2 * x / 3:
            inner = 0.08 * x**-1 * (1 - 24 * x**-1 * (delta - x / 2)**2)
            inc = delta**-1 * max(inner, 0)**0.25 * max(b_val, v)
        else:
            inner = 0.08 * x**-1 * (1 - 24 * x**-1 * (x / 6)**2)
            inc = delta**-1 * max(inner, 0)**0.25 * max(b_val, v)

        seg_anchor = anchor[li:ri]
        P_step[li:ri] += np.minimum(inc * seg_anchor, np.maximum(inc, inc * 2 - 10))

    return _smooth_on_corners(base_corners, P_step, 500, 0.001, "sum")


def _compute_Abar(K, active_columns_set, delta_ks, A_corners, base_corners):
    dks = np.zeros((K - 1, len(base_corners)))
    for i in range(len(base_corners)):
        cols = sorted(active_columns_set[i])
        for j in range(len(cols) - 1):
            k0, k1 = cols[j], cols[j + 1]
            dks[k0, i] = abs(delta_ks[k0, i] - delta_ks[k1, i]) + 0.4 * max(0, max(delta_ks[k0, i], delta_ks[k1, i]) - 0.11)

    A_step = np.ones(len(A_corners))
    bc_idx = np.clip(np.searchsorted(base_corners, A_corners), 0, len(base_corners) - 1)

    for i in range(len(A_corners)):
        idx = bc_idx[i]
        cols = sorted(active_columns_set[idx])
        for j in range(len(cols) - 1):
            k0, k1 = cols[j], cols[j + 1]
            d_val = dks[k0, idx]
            dk0, dk1 = delta_ks[k0, idx], delta_ks[k1, idx]
            if d_val < 0.02:
                A_step[i] *= min(0.75 + 0.5 * max(dk0, dk1), 1)
            elif d_val < 0.07:
                A_step[i] *= min(0.65 + 5 * d_val + 0.5 * max(dk0, dk1), 1)

    return _smooth_on_corners(A_corners, A_step, 250, 1.0, "avg")


def _compute_Rbar(K, x, note_seq_by_column, tail_seq, base_corners):
    R_step = np.zeros(len(base_corners))

    times_by_column = {}
    for k in range(K):
        times_by_column[k] = [n[1] for n in note_seq_by_column[k]]

    I_list = []
    for k, h_i, t_i in tail_seq:
        _, h_j, _ = _find_next_note_in_column([k, h_i, t_i], times_by_column[k], note_seq_by_column)
        I_h = 0.001 * abs(t_i - h_i - 80) / x
        I_t = 0.001 * abs(h_j - t_i - 80) / x
        I_list.append(2 / (2 + math.exp(-5 * (I_h - 0.75)) + math.exp(-5 * (I_t - 0.75))))

    for i in range(len(tail_seq) - 1):
        t_start, t_end = tail_seq[i][2], tail_seq[i + 1][2]
        li = np.searchsorted(base_corners, t_start, "left")
        ri = np.searchsorted(base_corners, t_end, "left")
        if ri <= li:
            continue
        delta_r = 0.001 * (t_end - t_start)
        r_val = 0.08 * delta_r**-0.5 * x**-1 * (1 + 0.8 * (I_list[i] + I_list[i + 1]))
        R_step[li:ri] = r_val

    return _smooth_on_corners(base_corners, R_step, 500, 0.001, "sum")


def _compute_C_and_Ks(K, note_seq, key_usage, base_corners):
    note_hit_times = np.array(sorted(n[1] for n in note_seq), float)
    lo = np.searchsorted(note_hit_times, base_corners - 500, "left")
    hi = np.searchsorted(note_hit_times, base_corners + 500, "left")
    C_step = (hi - lo).astype(float)
    Ks_step = np.maximum(key_usage.sum(axis=0), 1).astype(float)
    return C_step, Ks_step


# ============================================================
# Sunny: main calculate
# ============================================================

def calculate(file_path, speed_rate=1.0, od_flag=None):
    pp = _preprocess(file_path, speed_rate, od_flag)
    x, K, T = pp["x"], pp["K"], pp["T"]
    note_seq = pp["note_seq"]
    nbc = pp["note_seq_by_column"]
    ln_seq = pp["ln_seq"]
    tail_seq = pp["tail_seq"]

    all_corners, base_corners, A_corners = _get_corners(T, note_seq)

    key_usage = _get_key_usage(K, T, note_seq, base_corners)
    active_columns_set = [set(k for k in range(K) if key_usage[k, i]) for i in range(len(base_corners))]

    ku400 = _get_key_usage_400(K, T, note_seq, base_corners)
    anchor = _compute_anchor(K, ku400, base_corners)

    delta_ks, Jbar_b = _compute_Jbar(K, x, nbc, base_corners)
    Jbar = np.interp(all_corners, base_corners, Jbar_b)

    Xbar_b = _compute_Xbar(K, x, nbc, active_columns_set, base_corners)
    Xbar = np.interp(all_corners, base_corners, Xbar_b)

    ln_rep = _ln_bodies_count_sparse(ln_seq, T)
    Pbar_b = _compute_Pbar(x, note_seq, ln_rep, anchor, base_corners)
    Pbar = np.interp(all_corners, base_corners, Pbar_b)

    Abar_b = _compute_Abar(K, active_columns_set, delta_ks, A_corners, base_corners)
    Abar = np.interp(all_corners, A_corners, Abar_b)

    Rbar_b = _compute_Rbar(K, x, nbc, tail_seq, base_corners)
    Rbar = np.interp(all_corners, base_corners, Rbar_b)

    C_step, Ks_step = _compute_C_and_Ks(K, note_seq, key_usage, base_corners)
    C_arr = np.interp(all_corners, base_corners, C_step)
    idx = np.clip(np.searchsorted(base_corners, all_corners, "right") - 1, 0, len(Ks_step) - 1)
    Ks_arr = Ks_step[idx]

    S_all = (
        0.4 * (Abar**(3 / Ks_arr) * np.minimum(Jbar, 8 + 0.85 * Jbar))**1.5 +
        0.6 * (Abar**(2 / 3) * (0.8 * Pbar + Rbar * 35 / (C_arr + 8)))**1.5
    )**(2 / 3)
    T_all = (Abar**(3 / Ks_arr) * Xbar) / (Xbar + S_all + 1)
    D_all = 2.7 * S_all**0.5 * T_all**1.5 + S_all * 0.27

    gaps = np.empty_like(all_corners)
    gaps[0] = (all_corners[1] - all_corners[0]) / 2
    gaps[-1] = (all_corners[-1] - all_corners[-2]) / 2
    gaps[1:-1] = (all_corners[2:] - all_corners[:-2]) / 2

    w_eff = C_arr * gaps
    order = np.argsort(D_all)
    D_s, w_s = D_all[order], w_eff[order]
    cum_w = np.cumsum(w_s)
    norm = cum_w / cum_w[-1]

    targets = np.array([0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815])
    idx_pct = np.searchsorted(norm, targets, "left")
    p93 = np.mean(D_s[idx_pct[:4]])
    p83 = np.mean(D_s[idx_pct[4:8]])
    wm = (np.sum(D_s**5 * w_s) / np.sum(w_s))**0.2

    sr = 0.88 * p93 * 0.25 + 0.94 * p83 * 0.2 + wm * 0.55

    ln_len = sum(min(t - h, 1000) / 200.0 for _, h, t in ln_seq)
    tn = len(note_seq) + 0.5 * ln_len
    sr *= tn / (tn + 60)
    sr = _rescale_high(sr) * 0.975

    return {
        "star": sr,
        "ln_ratio": pp["ln_ratio"],
        "column_count": pp["column_count"],
        "total_notes": pp["total_notes"],
        "ln_count": pp["ln_count"],
        "od": pp["od_original"],
        "x_factor": x,
    }
