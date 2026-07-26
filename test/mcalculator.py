"""
Port of MACalculator.cs from sunny rework (vernonlim/osu, author-port branch).
Calculates difficulty (star rating) for osu!mania beatmaps using a novel
physics-inspired continuous-time model instead of traditional strain decay.
"""

import math
import bisect


class Note:
    __slots__ = ('column', 'head', 'tail', 'column_index')

    def __init__(self, column: int, head: int, tail: int):
        self.column = column
        self.head = head
        self.tail = tail
        self.column_index = 0


class SRParams:
    __slots__ = ('sr', 'spikiness', 'switches')

    def __init__(self, sr=0.0, spikiness=0.0, switches=0.0):
        self.sr = sr
        self.spikiness = spikiness
        self.switches = switches


class MACalculator:
    """Static methods for computing difficulty rating from note sequences."""

    @staticmethod
    def calculate(note_seq, note_seq_by_column, key_count, x, contains_cl):
        """Main entry point. Returns SRParams with sr, spikiness, switches."""
        # Fixed tuning constants.
        lambda_n = 5
        lambda_1 = 0.11
        lambda_3 = 24.0
        lambda2 = 6.0
        lambda_4 = 0.8
        w0 = 0.4
        w1 = 2.7
        p1 = 1.5
        w2 = 0.27
        p0 = 1.0

        # --- Sort notes by head time, then by column ---
        note_seq.sort(key=lambda n: (n.head, n.column))

        # --- Group notes by column ---
        note_dict = {i: [] for i in range(key_count)}
        for note in note_seq:
            note_dict[note.column].append(note)

        for col_list in note_dict.values():
            for i, note in enumerate(col_list):
                note.column_index = i

        # --- Long notes ---
        ln_seq = [n for n in note_seq if n.tail >= 0]
        tail_seq = sorted(ln_seq, key=lambda n: n.tail)

        max_head = max(n.head for n in note_seq)
        non_negative_tails = [n.tail for n in note_seq if n.tail >= 0]
        max_tail = max(non_negative_tails) if non_negative_tails else 0
        T = max(max_head, max_tail) + 1

        # --- Determine Corner Times ---
        corners_base = set()
        for note in note_seq:
            corners_base.add(note.head)
            if note.tail >= 0:
                corners_base.add(note.tail)
        for s in list(corners_base):
            corners_base.add(s + 501)
            corners_base.add(s - 499)
            corners_base.add(s + 1)
        corners_base.add(0)
        corners_base.add(T)
        base_corners_list = sorted(s for s in corners_base if 0 <= s <= T)

        corners_a = set()
        for note in note_seq:
            corners_a.add(note.head)
            if note.tail >= 0:
                corners_a.add(note.tail)
        for s in list(corners_a):
            corners_a.add(s + 1000)
            corners_a.add(s - 1000)
        corners_a.add(0)
        corners_a.add(T)
        a_corners_list = sorted(s for s in corners_a if 0 <= s <= T)

        all_corners_set = set(base_corners_list) | set(a_corners_list)
        all_corners_list = sorted(all_corners_set)

        all_corners = [float(v) for v in all_corners_list]
        base_corners = [float(v) for v in base_corners_list]
        a_corners = [float(v) for v in a_corners_list]

        # --- Calculate KU (key usage) ---
        key_usage = {k: [False] * len(base_corners) for k in range(key_count)}

        for k in range(key_count):
            notes = note_seq_by_column[k]
            for note in notes:
                active_start = max(note.head - 150, 0)
                active_end = (note.head + 150) if note.tail < 0 else min(note.tail + 150, T - 1)
                start_idx = bisect.bisect_left(base_corners, float(active_start))
                idx = start_idx
                while idx < len(base_corners) and base_corners[idx] < active_end:
                    key_usage[k][idx] = True
                    idx += 1

        ku_s_cols = []
        for i in range(len(base_corners)):
            active = [k for k in range(key_count) if key_usage[k][i]]
            ku_s_cols.append(active)

        # Key usage 400 (weighted active time)
        key_usage_400 = {k: [0.0] * len(base_corners) for k in range(key_count)}

        for k in range(key_count):
            notes = note_seq_by_column[k]
            for note in notes:
                active_start = max(note.head, 0)
                active_end = note.head if note.tail < 0 else min(note.tail, T - 1)

                start400_idx = bisect.bisect_left(base_corners, float(active_start - 400))
                start_idx = bisect.bisect_left(base_corners, float(active_start))
                end400_idx = bisect.bisect_left(base_corners, float(active_end + 400))
                end_idx = bisect.bisect_left(base_corners, float(active_end))

                base_val = 3.75 + min(active_end - active_start, 1500) / 150.0

                for i in range(start_idx, end_idx):
                    if i < len(base_corners):
                        key_usage_400[k][i] += base_val

                for i in range(start400_idx, start_idx):
                    if i < len(base_corners):
                        t = base_corners[i] - active_start
                        key_usage_400[k][i] += 3.75 - 3.75 / (400 ** 2) * (t ** 2)

                for i in range(end_idx, end400_idx):
                    if i < len(base_corners):
                        t = abs(base_corners[i] - active_end)
                        key_usage_400[k][i] += 3.75 - 3.75 / (400 ** 2) * (t ** 2)

        # --- Anchor ---
        anchor = [0.0] * len(base_corners)
        for i in range(len(base_corners)):
            counts = [key_usage_400[k][i] for k in range(key_count)]
            counts.sort(reverse=True)
            non_zero = [c for c in counts if c > 0]
            if len(non_zero) > 1:
                walk = sum(non_zero[j] * (1 - 4 * (0.5 - non_zero[j + 1] / non_zero[j]) ** 2)
                           for j in range(len(non_zero) - 1))
                max_walk = sum(non_zero[:-1])
                anchor[i] = walk / max_walk if max_walk > 0 else 0
            else:
                anchor[i] = 0

        for i in range(len(anchor)):
            anchor[i] = 1 + min(anchor[i] - 0.18, 5 * (anchor[i] - 0.22) ** 3)

        # --- 2.3: Compute Jbar (jack difficulty) ---
        def jack_nerfer(delta):
            return 1 - 7e-5 * (0.15 + abs(delta - 0.08)) ** -4

        j_ks = {k: [0.0] * len(base_corners) for k in range(key_count)}
        delta_ks = {k: [1e9] * len(base_corners) for k in range(key_count)}

        for k in range(key_count):
            notes = note_seq_by_column[k]
            pointer = 0
            for i in range(len(notes) - 1):
                start = notes[i].head
                end = notes[i + 1].head
                delta = 0.001 * (end - start)
                val = (1.0 / delta) * (1.0 / (delta + lambda_1 * (x ** 0.25)))
                j_val = val * jack_nerfer(delta)

                while pointer < len(base_corners) and base_corners[pointer] < start:
                    pointer += 1
                while pointer < len(base_corners) and base_corners[pointer] < end:
                    j_ks[k][pointer] = j_val
                    delta_ks[k][pointer] = delta
                    pointer += 1

        # Smooth J per column
        jbar_ks = {k: MACalculator._smooth_on_corners(base_corners, j_ks[k], 500, 0.001, "sum")
                   for k in range(key_count)}

        # Aggregate across columns
        jbar_base = [0.0] * len(base_corners)
        for j in range(len(base_corners)):
            num = 0.0
            den = 0.0
            for k in range(key_count):
                v = max(jbar_ks[k][j], 0)
                w = 1.0 / delta_ks[k][j]
                num += (v ** lambda_n) * w
                den += w
            avg = num / max(1e-9, den)
            jbar_base[j] = avg ** (1.0 / lambda_n)

        jbar = MACalculator._interp_values(all_corners, base_corners, jbar_base)

        # --- 2.4: Compute Xbar (cross difficulty) ---
        cross_matrix = [
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

        x_ks = {k: [0.0] * len(base_corners) for k in range(key_count + 1)}
        fast_cross = [None] * (key_count + 1)
        for k in range(key_count + 1):
            fast_cross[k] = [0.0] * len(base_corners)

        for k in range(key_count + 1):
            if k == 0:
                notes_in_pair = note_seq_by_column[0]
            elif k == key_count:
                notes_in_pair = note_seq_by_column[key_count - 1]
            else:
                notes_in_pair = MACalculator._merge_sorted(
                    note_seq_by_column[k - 1], note_seq_by_column[k])

            pointer = 0
            for i in range(1, len(notes_in_pair)):
                start = notes_in_pair[i - 1].head
                end = notes_in_pair[i].head
                delta = 0.001 * (end - start)
                val = 0.16 * (max(x, delta) ** -2)

                while pointer < len(base_corners) and base_corners[pointer] < start:
                    pointer += 1
                pointer_start = pointer
                while pointer < len(base_corners) and base_corners[pointer] < end:
                    pointer += 1
                pointer_end = pointer

                cross_val = cross_matrix[key_count][k] if key_count < len(cross_matrix) else 0.4

                if pointer_start < len(ku_s_cols) and pointer_end <= len(ku_s_cols):
                    ks_start = ku_s_cols[min(pointer_start, len(ku_s_cols) - 1)]
                    ks_end = ku_s_cols[min(pointer_end - 1, len(ku_s_cols) - 1)] if pointer_end > 0 else []
                    left_not_present = (k - 1) not in ks_start and (k - 1) not in ks_end
                    key_not_present = k not in ks_start and k not in ks_end
                    if left_not_present or key_not_present:
                        val *= (1 - cross_val)

                for p in range(pointer_start, pointer_end):
                    if p < len(x_ks[k]):
                        x_ks[k][p] = val
                        fast_cross[k][p] = max(0, 0.4 * (max(max(delta, 0.06), 0.75 * x) ** -2) - 80)

        # Combine X_ks
        x_base = [0.0] * len(base_corners)
        for i in range(len(base_corners)):
            sum1 = 0.0
            for k in range(key_count + 1):
                cross_val = cross_matrix[key_count][k] if key_count < len(cross_matrix) else 0.4
                sum1 += x_ks[k][i] * cross_val

            sum2 = 0.0
            for k in range(key_count):
                cross_val = cross_matrix[key_count][k] if key_count < len(cross_matrix) else 0.4
                cross_val_next = cross_matrix[key_count][k + 1] if key_count < len(cross_matrix) else 0.4
                sum2 += math.sqrt(fast_cross[k][i] * cross_val *
                                  fast_cross[k + 1][i] * cross_val_next)

            x_base[i] = sum1 + sum2

        xbar_base = MACalculator._smooth_on_corners(base_corners, x_base, 500, 0.001, "sum")
        xbar = MACalculator._interp_values(all_corners, base_corners, xbar_base)

        # --- 2.5: Compute Pbar (physical/stream difficulty) ---
        ln_bodies = [0.0] * T
        for note in ln_seq:
            h = note.head
            t = note.tail
            t0 = min(h + 60, t)
            t1 = min(h + 120, t)
            for i in range(t0, t1):
                ln_bodies[i] += 1.3
            for i in range(t1, t):
                ln_bodies[i] += 1.0

        for i in range(len(ln_bodies)):
            ln_bodies[i] = min(ln_bodies[i], 2.5 + 0.5 * ln_bodies[i])

        cumsum_ln = [0.0] * (T + 1)
        for i in range(1, T + 1):
            cumsum_ln[i] = cumsum_ln[i - 1] + ln_bodies[i - 1]

        def ln_sum(a, b):
            return cumsum_ln[b] - cumsum_ln[a]

        def stream_booster(delta):
            val = 7.5 / delta
            if 160 < val < 360:
                return 1 + 1.7e-7 * (val - 160) * ((val - 360) ** 2)
            return 1.0

        p_step = [0.0] * len(base_corners)
        pointer_p = 0
        for i in range(len(note_seq) - 1):
            h_l = note_seq[i].head
            h_r = note_seq[i + 1].head
            delta_time = h_r - h_l

            if delta_time < 1e-9:
                idx = bisect.bisect_left(base_corners, float(h_l))
                if idx < len(base_corners) and abs(base_corners[idx] - h_l) < 1e-9:
                    spike = 1000 * (0.02 * (4.0 / x - lambda_3)) ** 0.25
                    p_step[idx] += spike
                continue

            delta = 0.001 * delta_time
            v = 1 + lambda2 * 0.001 * ln_sum(h_l, h_r)
            b_val = stream_booster(delta)
            if delta < 2 * x / 3:
                inc = (1.0 / delta) * (0.08 * (1.0 / x) *
                      (1 - lambda_3 * (1.0 / x) * ((delta - x / 2) ** 2))) ** 0.25 * max(b_val, v)
            else:
                inc = (1.0 / delta) * (0.08 * (1.0 / x) *
                      (1 - lambda_3 * (1.0 / x) * ((x / 6) ** 2))) ** 0.25 * max(b_val, v)

            while pointer_p < len(base_corners) and base_corners[pointer_p] < h_l:
                pointer_p += 1
            while pointer_p < len(base_corners) and base_corners[pointer_p] < h_r:
                p_step[pointer_p] += min(inc * anchor[pointer_p], max(inc, inc * 2 - 10))
                pointer_p += 1

        pbar_base = MACalculator._smooth_on_corners(base_corners, p_step, 500, 0.001, "sum")
        pbar = MACalculator._interp_values(all_corners, base_corners, pbar_base)

        # --- 2.6: Compute Abar (agility/anchor difficulty) ---
        dks = {k: [0.0] * len(base_corners) for k in range(key_count - 1)}
        for i in range(len(base_corners)):
            cols = ku_s_cols[i]
            for j in range(len(cols) - 1):
                k0 = cols[j]
                k1 = cols[j + 1]
                dks[k0][i] = abs(delta_ks[k0][i] - delta_ks[k1][i]) + \
                    0.4 * max(0, max(delta_ks[k0][i], delta_ks[k1][i]) - 0.11)

        a_step = [1.0] * len(a_corners)
        for i in range(len(a_corners)):
            s = a_corners[i]
            idx = bisect.bisect_left(base_corners, s)
            if idx >= len(base_corners):
                idx = len(base_corners) - 1
            cols = ku_s_cols[idx]
            for j in range(len(cols) - 1):
                k0 = cols[j]
                k1 = cols[j + 1]
                d_val = dks[k0][idx]
                if d_val < 0.02:
                    a_step[i] *= min(0.75 + 0.5 * max(delta_ks[k0][idx], delta_ks[k1][idx]), 1)
                elif d_val < 0.07:
                    a_step[i] *= min(0.65 + 5 * d_val + 0.5 * max(delta_ks[k0][idx], delta_ks[k1][idx]), 1)

        abar_a = MACalculator._smooth_on_corners(a_corners, a_step, 250, 1.0, "avg")
        abar = MACalculator._interp_values(all_corners, a_corners, abar_a)

        # --- 2.7: Compute Rbar (release difficulty) ---
        r_base = [0.0] * len(base_corners)
        i_list = [0.0] * len(tail_seq)

        for note_idx in range(len(tail_seq)):
            current_note = tail_seq[note_idx]
            next_note_index = current_note.column_index + 1
            next_note_exists = next_note_index < len(note_seq_by_column[current_note.column])
            next_note = note_seq_by_column[current_note.column][next_note_index] if next_note_exists else None

            current_i = 0.001 * abs(current_note.tail - current_note.head - 80.0) / x

            if next_note is None:
                i_list[note_idx] = 2 / (2 + math.exp(-5 * (current_i - 0.75)))
            else:
                next_i = 0.001 * abs(next_note.head - current_note.tail - 80.0) / x
                i_list[note_idx] = 2 / (2 + math.exp(-5 * (current_i - 0.75)) +
                                        math.exp(-5 * (next_i - 0.75)))

        previous_idx_start = 0
        for i in range(len(tail_seq) - 1):
            note = tail_seq[i]
            next_note = tail_seq[i + 1]
            start_time = note.tail
            end_time = next_note.tail

            idx_start = -1
            for j in range(previous_idx_start, len(base_corners)):
                if base_corners[j] >= start_time:
                    idx_start = j
                    previous_idx_start = j
                    break

            if idx_start == -1:
                continue

            delta_r = 0.001 * (next_note.tail - note.tail)

            j = idx_start
            while j < len(base_corners) and base_corners[j] < end_time:
                r_base[j] = 0.08 * (delta_r ** -0.5) * (1.0 / x) * \
                    (1 + lambda_4 * (i_list[i] + i_list[i + 1]))
                j += 1

        rbar_base = MACalculator._smooth_on_corners(base_corners, r_base, 500, 0.001, "sum")
        rbar = MACalculator._interp_values(all_corners, base_corners, rbar_base)

        # --- Section 3: Compute C and Ks ---
        note_hit_times = sorted(n.head for n in note_seq)
        note_hit_times_v2 = sorted(
            list(n.head for n in note_seq) +
            list(n.tail for n in note_seq if n.tail >= 0)
        )

        c_step = [0.0] * len(base_corners)
        c_step_v2 = [0.0] * len(base_corners)
        for i in range(len(base_corners)):
            s = base_corners[i]
            cnt_low = bisect.bisect_left(note_hit_times, int(s - 500))
            cnt_high = bisect.bisect_left(note_hit_times, int(s + 500))
            c_step[i] = float(cnt_high - cnt_low)

            cnt_low_v2 = bisect.bisect_left(note_hit_times_v2, int(s - 500))
            cnt_high_v2 = bisect.bisect_left(note_hit_times_v2, int(s + 500))
            c_step_v2[i] = float(cnt_high_v2 - cnt_low_v2)

        c_arr = MACalculator._step_interp(all_corners, base_corners, c_step)
        c_arr_v2 = MACalculator._step_interp(all_corners, base_corners, c_step_v2)

        ks_step = [0.0] * len(base_corners)
        for i in range(len(base_corners)):
            cnt_active = sum(1 for k in range(key_count) if key_usage[k][i])
            ks_step[i] = float(max(cnt_active, 1))

        ks_arr = MACalculator._step_interp(all_corners, base_corners, ks_step)

        # --- Final Computations: S, T, D ---
        N = len(all_corners)
        d_all = [0.0] * N
        for i in range(N):
            a_val = abar[i]
            j_val = jbar[i]
            x_val = xbar[i]
            p_val = pbar[i]
            r_val = rbar[i]
            c_val = c_arr[i]
            ks_val = ks_arr[i]

            term1 = ((a_val ** (3.0 / ks_val)) * min(j_val, 8 + 0.85 * j_val)) ** 1.5
            term2 = ((a_val ** (2.0 / 3.0)) * (0.8 * p_val + r_val * 35.0 / (c_val + 8))) ** 1.5
            s_val = (w0 * term1 + (1 - w0) * term2) ** (2.0 / 3.0)
            t_val = ((a_val ** (3.0 / ks_val)) * x_val) / (x_val + s_val + 1)
            d_all[i] = w1 * (s_val ** 0.5) * (t_val ** p1) + s_val * w2

        # --- Weighted-Percentile ---
        gaps = [0.0] * N
        if N == 1:
            gaps[0] = 0
        else:
            gaps[0] = (all_corners[1] - all_corners[0]) / 2.0
            gaps[N - 1] = (all_corners[N - 1] - all_corners[N - 2]) / 2.0
            for i in range(1, N - 1):
                gaps[i] = (all_corners[i + 1] - all_corners[i - 1]) / 2.0

        effective_weights = [0.0] * N
        for i in range(N):
            effective_weights[i] = c_arr[i] * gaps[i] if contains_cl else c_arr_v2[i] * gaps[i]

        corner_data = []
        for i in range(N):
            corner_data.append({
                'time': all_corners[i],
                'jbar': jbar[i],
                'xbar': xbar[i],
                'pbar': pbar[i],
                'abar': abar[i],
                'rbar': rbar[i],
                'c': c_arr[i],
                'ks': ks_arr[i],
                'd': d_all[i],
                'weight': effective_weights[i]
            })

        sorted_data = sorted(corner_data, key=lambda cd: cd['d'])
        d_sorted = [cd['d'] for cd in sorted_data]

        cum_weights = []
        sum_w = 0.0
        for cd in sorted_data:
            sum_w += cd['weight']
            cum_weights.append(sum_w)
        total_weight = sum_w
        norm_cum_weights = [cw / total_weight for cw in cum_weights] if total_weight > 0 else [0.0] * len(cum_weights)

        target_percentiles = [0.945, 0.935, 0.925, 0.915, 0.845, 0.835, 0.825, 0.815]
        indices = []
        for tp in target_percentiles:
            idx = next((j for j, cw in enumerate(norm_cum_weights) if cw >= tp), len(sorted_data) - 1)
            indices.append(idx)

        if len(indices) >= 8:
            percentile93 = sum(sorted_data[indices[i]]['d'] for i in range(4)) / 4.0
            percentile83 = sum(sorted_data[indices[i]]['d'] for i in range(4, 8)) / 4.0
        else:
            percentile93 = sum(cd['d'] for cd in sorted_data) / len(sorted_data)
            percentile83 = percentile93

        num_weighted = sum((cd['d'] ** lambda_n) * cd['weight'] for cd in sorted_data)
        den_weighted = sum(cd['weight'] for cd in sorted_data)
        weighted_mean = (num_weighted / den_weighted) ** (1.0 / lambda_n) if den_weighted > 0 else 0

        sr = (0.88 * percentile93) * 0.25 + (0.94 * percentile83) * 0.2 + weighted_mean * 0.55
        sr = (sr ** p0) / (8 ** p0) * 8

        # Length weighting
        total_notes = len(note_seq) + 0.5 * sum(
            min(ln.tail - ln.head, 1000) / 200.0 for ln in ln_seq)
        sr *= total_notes / (total_notes + 60)

        sr = MACalculator._rescale_high(sr)
        sr *= 0.975

        # Spikiness
        variance_sum_top = 0.0
        variance_sum_bottom = den_weighted
        for i in range(len(d_sorted)):
            diff = (d_sorted[i] ** 8) - (weighted_mean ** 8)
            variance_sum_top += (diff ** 2) * sorted_data[i]['weight']

        weighted_variance = (variance_sum_top / variance_sum_bottom) ** (1.0 / 8.0) if variance_sum_bottom > 0 else 0
        spikiness = math.sqrt(weighted_variance) / weighted_mean if weighted_mean > 0 else 0
        switches = MACalculator._switches(note_seq, tail_seq, all_corners, ks_arr, d_all)

        return SRParams(sr=sr, spikiness=spikiness, switches=switches)

    @staticmethod
    def variety(note_seq, note_seq_by_column):
        """Compute variety measure from head gaps and tail gaps."""
        tail_seq = sorted(note_seq, key=lambda n: n.tail)

        head_gaps = [note_seq[i + 1].head - note_seq[i].head
                     for i in range(len(note_seq) - 1)]
        tail_gaps = [tail_seq[i + 1].tail - tail_seq[i].tail
                     for i in range(len(tail_seq) - 1)]

        head_variety = MACalculator._rao_quadratic_entropy_log(head_gaps)
        tail_variety = MACalculator._rao_quadratic_entropy_log(tail_gaps)

        head_gaps_new = []
        for col_notes in note_seq_by_column:
            for i in range(len(col_notes) - 1):
                head_gaps_new.append(col_notes[i + 1].head - col_notes[i].head)

        col_variety = 2.5 * MACalculator._rao_quadratic_entropy_log(head_gaps_new, 2)

        return 0.5 * head_variety + 0.11 * tail_variety + 0.45 * col_variety

    # ---- Helper methods ----

    @staticmethod
    def _rescale_high(sr):
        if sr <= 9:
            return sr
        return 9 + (sr - 9) * (1.0 / 1.2)

    @staticmethod
    def _cumulative_sum(x, f):
        n = len(x)
        F = [0.0] * n
        for i in range(1, n):
            F[i] = F[i - 1] + f[i - 1] * (x[i] - x[i - 1])
        return F

    @staticmethod
    def _query_cumsum(q, x, F, f):
        if q <= x[0]:
            return 0.0
        if q >= x[-1]:
            return F[-1]
        idx = bisect.bisect_left(x, q)
        i = idx - 1
        return F[i] + f[i] * (q - x[i])

    @staticmethod
    def _smooth_on_corners(x, f, window, scale, mode):
        n = len(f)
        F = MACalculator._cumulative_sum(x, f)
        g = [0.0] * n
        for i in range(n):
            s = x[i]
            a = max(s - window, x[0])
            b = min(s + window, x[-1])
            val = MACalculator._query_cumsum(b, x, F, f) - MACalculator._query_cumsum(a, x, F, f)
            if mode == "avg":
                g[i] = val / (b - a) if (b - a) > 0 else 0.0
            else:
                g[i] = scale * val
        return g

    @staticmethod
    def _interp_values(new_x, old_x, old_vals):
        n = len(new_x)
        new_vals = [0.0] * n
        for i in range(n):
            x_val = new_x[i]
            if x_val <= old_x[0]:
                new_vals[i] = old_vals[0]
            elif x_val >= old_x[-1]:
                new_vals[i] = old_vals[-1]
            else:
                idx = bisect.bisect_left(old_x, x_val)
                j = idx - 1
                t = (x_val - old_x[j]) / (old_x[j + 1] - old_x[j])
                new_vals[i] = old_vals[j] + t * (old_vals[j + 1] - old_vals[j])
        return new_vals

    @staticmethod
    def _step_interp(new_x, old_x, old_vals):
        new_vals = [0.0] * len(new_x)
        for i in range(len(new_x)):
            x_val = new_x[i]
            idx = bisect.bisect_left(old_x, x_val)
            idx = idx - 1
            if idx < 0:
                idx = 0
            if idx >= len(old_vals):
                idx = len(old_vals) - 1
            new_vals[i] = old_vals[idx]
        return new_vals

    @staticmethod
    def _merge_sorted(list1, list2):
        merged = []
        i = j = 0
        while i < len(list1) and j < len(list2):
            if list1[i].head <= list2[j].head:
                merged.append(list1[i])
                i += 1
            else:
                merged.append(list2[j])
                j += 1
        merged.extend(list1[i:])
        merged.extend(list2[j:])
        return merged

    @staticmethod
    def _rao_quadratic_entropy_log(values, log_iterations=1):
        if not values:
            return 0.0

        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1

        total = len(values)
        unique = list(counts.keys())
        p = [counts[v] / total for v in unique]

        def distance_func(x, y, log_iter):
            acc = float(abs(x - y))
            for _ in range(log_iter):
                acc = math.log(1 + acc)
            return acc

        q = 0.0
        for i in range(len(unique)):
            for j in range(len(unique)):
                q += p[i] * p[j] * distance_func(unique[i], unique[j], log_iterations)

        return q

    @staticmethod
    def _switches(note_seq, tail_seq, all_corners, ks_arr, weights):
        """Compute the switch measure."""
        heads = [n.head for n in note_seq]
        idx_list = [bisect.bisect_left(all_corners, float(h)) for h in heads]

        ks_at_note = [ks_arr[i] for i in idx_list[:-1]]
        weights_at_note = [weights[i] for i in idx_list[:-1]]

        head_gaps = [float(heads[i + 1] - heads[i]) for i in range(len(heads) - 1)]
        num_head_gaps = len(head_gaps)

        avgs = []
        for i in range(num_head_gaps):
            start = max(0, i - 50)
            end = min(i + 50, num_head_gaps - 1)
            s = sum(head_gaps[j] for j in range(start, end + 1))
            cnt = end - start + 1
            avgs.append(s / cnt)

        signature_head = 0.0
        for i in range(num_head_gaps):
            if avgs[i] > 0:
                signature_head += math.sqrt((head_gaps[i] / avgs[i] / num_head_gaps) * weights_at_note[i]) * \
                    (ks_at_note[i] ** 0.25)

        sum_ref_head = sum((head_gaps[i] / avgs[i]) * weights_at_note[i]
                           for i in range(num_head_gaps) if avgs[i] > 0)
        ref_signature_head = math.sqrt(sum_ref_head)

        tails = [n.tail for n in tail_seq]
        idx_list_tails = [bisect.bisect_left(all_corners, float(t)) for t in tails]
        ks_at_tail = [ks_arr[i] for i in idx_list_tails[:-1]]
        weights_at_tail = [weights[i] for i in idx_list_tails[:-1]]

        tail_gaps = [float(tails[i + 1] - tails[i]) for i in range(len(tails) - 1)]

        signature_tail = 0.0
        ref_signature_tail = 0.0
        if tails and tails[-1] > tails[0] and tail_gaps:
            num_tail_gaps = len(tail_gaps)
            avgs_tail = []
            for i in range(num_tail_gaps):
                start = max(0, i - 50)
                end = min(i + 50, num_tail_gaps - 1)
                s = sum(tail_gaps[j] for j in range(start, end + 1))
                cnt = end - start + 1
                avgs_tail.append(s / cnt)

            for i in range(num_tail_gaps):
                if avgs_tail[i] > 0:
                    signature_tail += math.sqrt((tail_gaps[i] / avgs_tail[i] / num_tail_gaps)
                                                 * weights_at_tail[i]) * (ks_at_tail[i] ** 0.25)

            sum_ref_tail = sum((tail_gaps[i] / avgs_tail[i]) * weights_at_tail[i]
                               for i in range(num_tail_gaps) if avgs_tail[i] > 0)
            ref_signature_tail = math.sqrt(sum_ref_tail)

        numerator = signature_head * num_head_gaps + signature_tail * len(tail_gaps)
        denominator = ref_signature_head * num_head_gaps + ref_signature_tail * len(tail_gaps)
        switches = numerator / denominator if denominator > 0 else 0.5

        return switches / 2.0 + 0.5
