import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import math
import numpy as np

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
    x, f = np.asarray(x, float), np.asarray(f, float)
    F = _cumulative_sum(x, f)
    a, b = np.clip(x - window, x[0], x[-1]), np.clip(x + window, x[0], x[-1])

    def _query(q):
        i = np.clip(np.searchsorted(x, q) - 1, 0, len(x) - 2)
        return F[i] + f[i] * (q - x[i])

    val = _query(b) - _query(a)
    if mode == "avg":
        return np.where(b - a > 0, val / (b - a), 0.0)
    return scale * val


def _rescale_high(sr):
    return sr if sr <= 9 else 9 + (sr - 9) / 1.2


# ============================================================
# Daniel: preprocess
# ============================================================

def _preprocess(file_path, mod="NM"):
    p = _parser_mod.OsuFileParser(file_path)
    p.parse()

    od = 9

    if mod == "DT":
        time_scale = 2.0 / 3.0
    elif mod == "HT":
        time_scale = 4.0 / 3.0
    else:
        time_scale = 1.0

    note_seq = p.get_note_seq_taps_only(time_scale)

    x = 0.3 * ((64.5 - math.ceil(od * 3)) / 500)**0.5
    x = min(x, 0.6 * (x - 0.09) + 0.09)

    K = p.column_count
    nbc = p.get_note_seq_by_column(note_seq, K)
    T = max(n[1] for n in note_seq) + 1 if note_seq else 0

    return {
        "x": x, "K": K, "T": T,
        "note_seq": note_seq, "note_seq_by_column": nbc,
        "ln_ratio": p.ln_ratio, "column_count": K,
        "total_notes": p.total_notes, "ln_count": p.ln_count,
        "od": od,
    }


# ============================================================
# Daniel: corners
# ============================================================

def _get_corners(T, note_seq):
    cb = {0, T}
    ca = {0, T}
    for _, h in note_seq:
        cb.update([h, h + 501, h - 499, h + 1])
        ca.update([h, h + 1000, h - 1000])
    base = sorted(s for s in cb if 0 <= s <= T)
    a = sorted(s for s in ca if 0 <= s <= T)
    return (
        np.array(sorted(set(base) | set(a)), float),
        np.array(base, float),
        np.array(a, float),
    )


# ============================================================
# Daniel: key usage
# ============================================================

def _get_key_usage(K, T, note_seq, base_corners):
    ku = np.zeros((K, len(base_corners)), dtype=bool)
    for k, h in note_seq:
        start, end = max(h - 150, 0), min(h + 150, T - 1)
        li, ri = np.searchsorted(base_corners, start, "left"), np.searchsorted(base_corners, end, "left")
        if ri > li:
            ku[k, li:ri] = True
    return ku


def _get_key_usage_400(K, note_seq, base_corners):
    ku400 = np.zeros((K, len(base_corners)))
    for k, h in note_seq:
        li = np.searchsorted(base_corners, h - 400, "left")
        ri = np.searchsorted(base_corners, h + 400, "left")
        mid = np.searchsorted(base_corners, h, "left")
        ku400[k, mid] += 3.75
        if li < mid:
            rng = np.arange(li, mid)
            ku400[k, rng] += 3.75 - 3.75 / 400**2 * (base_corners[rng] - h)**2
        if mid + 1 < ri:
            rng = np.arange(mid + 1, ri)
            ku400[k, rng] += 3.75 - 3.75 / 400**2 * (base_corners[rng] - h)**2
    return ku400


# ============================================================
# Daniel: strain components
# ============================================================

def _compute_anchor(K, ku400, base_corners):
    counts = np.sort(ku400.T, axis=1)[:, ::-1]
    nz = counts > 0
    n_nz = nz.sum(axis=1)
    c0, c1 = counts[:, :-1], counts[:, 1:]
    safe = np.where(c0 > 0, c0, 1.0)
    ratio = np.where(c0 > 0, c1 / safe, 0.0)
    weight = 1 - 4 * (0.5 - ratio)**2
    pv = nz[:, :-1] & nz[:, 1:]
    walk = np.sum(np.where(pv, c0 * weight, 0), axis=1)
    mw = np.sum(np.where(pv, c0, 0), axis=1)
    raw = np.where(n_nz > 1, walk / np.maximum(mw, 1e-9), 0.0)
    return 1 + np.minimum(raw - 0.18, 5 * (raw - 0.22)**3)


def _compute_Jbar(K, x, nbc, base_corners):
    def jn(delta):
        return 1 - 7e-5 * (0.15 + abs(delta - 0.08))**(-4)

    J_ks = np.zeros((K, len(base_corners)))
    d_ks = np.full((K, len(base_corners)), 1e9)

    for k in range(K):
        notes = nbc[k]
        for i in range(len(notes) - 1):
            s, e = notes[i][1], notes[i + 1][1]
            li, ri = np.searchsorted(base_corners, s, "left"), np.searchsorted(base_corners, e, "left")
            if ri <= li:
                continue
            d = 0.001 * (e - s)
            v = d**-1 * (d + 0.11 * x**0.25)**-1 * jn(d)
            J_ks[k, li:ri] = v
            d_ks[k, li:ri] = d

    Jbar_ks = np.zeros((K, len(base_corners)))
    for k in range(K):
        Jbar_ks[k] = _smooth_on_corners(base_corners, J_ks[k], 500, 0.001, "sum")

    w = 1.0 / d_ks
    return d_ks, (np.sum(np.maximum(Jbar_ks, 0)**5 * w, axis=0) / np.maximum(np.sum(w, axis=0), 1e-9))**0.2


def _compute_Xbar(K, x, nbc, active, base_corners):
    cross = CROSS_MATRIX.get(K, [1.0 / (K + 1)] * (K + 1))
    X_ks = {k: np.zeros(len(base_corners)) for k in range(K + 1)}
    fc = {k: np.zeros(len(base_corners)) for k in range(K + 1)}

    for k in range(K + 1):
        if k == 0:
            notes = list(nbc[0])
        elif k == K:
            notes = list(nbc[K - 1])
        else:
            notes = sorted(list(nbc[k - 1]) + list(nbc[k]), key=lambda n: n[1])

        for i in range(1, len(notes)):
            s, e = notes[i - 1][1], notes[i][1]
            if e <= s:
                continue
            li, ri = np.searchsorted(base_corners, s, "left"), np.searchsorted(base_corners, e, "left")
            if ri <= li:
                continue
            d = 0.001 * (e - s)
            val = 0.16 * max(x, d)**-2

            la = active[li] if li < len(active) else set()
            ra = active[min(ri, len(active) - 1)]
            if (k - 1 not in la and k - 1 not in ra) or (k not in la and k not in ra):
                val *= 1 - cross[k]

            X_ks[k][li:ri] = val
            fc[k][li:ri] = max(0, 0.4 * max(d, 0.06, 0.75 * x)**-2 - 80)

    Xb = np.zeros(len(base_corners))
    for i in range(len(base_corners)):
        s1 = sum(X_ks[k][i] * cross[k] for k in range(K + 1))
        s2 = sum(np.sqrt(max(fc[k][i] * cross[k] * fc[k + 1][i] * cross[k + 1], 0)) for k in range(K))
        Xb[i] = s1 + s2
    return _smooth_on_corners(base_corners, Xb, 500, 0.001, "sum")


def _compute_Pbar(x, note_seq, anchor, base_corners):
    def sb(delta):
        bpm = np.clip(7.5 / delta, 0, 420)
        p = 0.10 / (1 + np.exp(-0.06 * (bpm - 175)))
        s = np.where((bpm >= 200) & (bpm <= 350), 0.30 * (1 - np.exp(-0.02 * (bpm - 200))), 0.0)
        return 1 + p + s

    Ps = np.zeros(len(base_corners))
    for i in range(len(note_seq) - 1):
        hl, hr = note_seq[i][1], note_seq[i + 1][1]
        dt = hr - hl
        if dt < 1e-9:
            spike = 1000 * (0.02 * (4 / x - 24))**0.25
            li, ri = np.searchsorted(base_corners, hl, "left"), np.searchsorted(base_corners, hl, "right")
            if ri > li:
                Ps[li:ri] += spike
            continue
        li, ri = np.searchsorted(base_corners, hl, "left"), np.searchsorted(base_corners, hr, "left")
        if ri <= li:
            continue
        d = 0.001 * dt
        bv = sb(d)
        base_inc = (0.08 * x**-1 * (1 - 24 * x**-1 * (x / 6)**2))**0.25
        if d < 2 * x / 3:
            inc = d**-1 * (0.08 * x**-1 * (1 - 24 * x**-1 * (d - x / 2)**2))**0.25 * max(bv, 1)
        else:
            inc = d**-1 * base_inc * max(bv, 1)
        sa = anchor[li:ri]
        Ps[li:ri] += np.minimum(inc * sa, np.maximum(inc, inc * 2 - 10))
    return _smooth_on_corners(base_corners, Ps, 500, 0.001, "sum")


def _compute_Abar(K, active, d_ks, A_corners, base_corners):
    dks = np.zeros((K - 1, len(base_corners)))
    for i in range(len(base_corners)):
        cols = sorted(active[i])
        for j in range(len(cols) - 1):
            k0, k1 = cols[j], cols[j + 1]
            dks[k0, i] = abs(d_ks[k0, i] - d_ks[k1, i]) + 0.4 * max(0, max(d_ks[k0, i], d_ks[k1, i]) - 0.11)

    As = np.ones(len(A_corners))
    bci = np.clip(np.searchsorted(base_corners, A_corners), 0, len(base_corners) - 1)
    for i in range(len(A_corners)):
        idx = bci[i]
        cols = sorted(active[idx])
        for j in range(len(cols) - 1):
            k0, k1 = cols[j], cols[j + 1]
            if k0 >= K - 1:
                continue
            dv = dks[k0, idx]
            dk0, dk1 = d_ks[k0, idx], d_ks[k1, idx]
            if dv < 0.02:
                As[i] *= min(0.75 + 0.5 * max(dk0, dk1), 1)
            elif dv < 0.07:
                As[i] *= min(0.65 + 5 * dv + 0.5 * max(dk0, dk1), 1)
    return _smooth_on_corners(A_corners, As, 250, 1.0, "avg")


def _compute_C_and_Ks(K, note_seq, key_usage, base_corners):
    nht = np.array(sorted(n[1] for n in note_seq), float)
    lo = np.searchsorted(nht, base_corners - 500, "left")
    hi = np.searchsorted(nht, base_corners + 500, "left")
    Cs = (hi - lo).astype(float)
    Kss = np.maximum(key_usage.sum(axis=0), 1).astype(float)
    return Cs, Kss


# ============================================================
# Daniel: main calculate
# ============================================================

def calculate(file_path, mod="NM"):
    pp = _preprocess(file_path, mod)
    if pp["K"] != 4:
        return {"error": "Only 4K supported", "star": 0, "est_diff": "N/A"}

    x, K, T = pp["x"], pp["K"], pp["T"]
    note_seq, nbc = pp["note_seq"], pp["note_seq_by_column"]

    all_corners, base_corners, A_corners = _get_corners(T, note_seq)

    key_usage = _get_key_usage(K, T, note_seq, base_corners)
    active = [set(k for k in range(K) if key_usage[k, i]) for i in range(len(base_corners))]
    ku400 = _get_key_usage_400(K, note_seq, base_corners)
    anchor = _compute_anchor(K, ku400, base_corners)

    d_ks, Jbar_b = _compute_Jbar(K, x, nbc, base_corners)
    Jbar = np.interp(all_corners, base_corners, Jbar_b)

    Xbar_b = _compute_Xbar(K, x, nbc, active, base_corners)
    Xbar = np.interp(all_corners, base_corners, Xbar_b)

    Pbar_b = _compute_Pbar(x, note_seq, anchor, base_corners)
    Pbar = np.interp(all_corners, base_corners, Pbar_b)

    Abar_b = _compute_Abar(K, active, d_ks, A_corners, base_corners)
    Abar = np.interp(all_corners, A_corners, Abar_b)

    Cs, Kss = _compute_C_and_Ks(K, note_seq, key_usage, base_corners)
    C_arr = np.interp(all_corners, base_corners, Cs)
    idx = np.clip(np.searchsorted(base_corners, all_corners, "right") - 1, 0, len(Kss) - 1)
    Ks_arr = Kss[idx]

    S_all = (
        0.4 * (Abar**(3 / Ks_arr) * np.minimum(Jbar, 8 + 0.85 * Jbar))**1.5 +
        0.6 * (Abar**(2 / 3) * (0.8 * Pbar))**1.5
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
    if cum_w[-1] <= 0:
        return {"star": 0, "ln_ratio": pp["ln_ratio"], "column_count": K, "total_notes": len(note_seq)}
    norm = cum_w / cum_w[-1]

    targets = np.array([0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815])
    i_pct = np.searchsorted(norm, targets, "left")
    p93 = np.mean(D_s[i_pct[:4]])
    p83 = np.mean(D_s[i_pct[4:8]])
    wm = (np.sum(D_s**5 * w_s) / np.sum(w_s))**0.2

    sr = 0.88 * p93 * 0.25 + 0.94 * p83 * 0.2 + wm * 0.55
    sr *= len(note_seq) / (len(note_seq) + 60)
    sr = _rescale_high(sr) * 0.975

    return {
        "star": sr,
        "ln_ratio": pp["ln_ratio"],
        "column_count": K,
        "total_notes": len(note_seq),
        "ln_count": pp["ln_count"],
        "od": 9,
        "x_factor": x,
    }
