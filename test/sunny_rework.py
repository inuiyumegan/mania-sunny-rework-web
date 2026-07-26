"""
Sunny Rework PP Calculator for osu!mania.
Port of the vernonlim/osu "author-port" branch algorithm.

Usage:
    python sunny_rework.py <beatmap.osu> [accuracy] [--mods MODS]
                             [--perfect N] [--great N] [--good N]
                             [--ok N] [--meh N] [--miss N]

    If no judgment counts are given, accuracy assumes all non-miss hits
    are regular 300s (Great), with the remaining being misses.

Examples:
    python sunny_rework.py map.osu 0.90
    python sunny_rework.py map.osu 0.95 --mods DT
    python sunny_rework.py map.osu --perfect 1000 --great 500 --miss 10
"""

import argparse
import math
import sys
import os

from mcalculator import Note, SRParams, MACalculator


# ============= Beatmap Parser =============

def parse_osu_file(filepath: str) -> dict:
    """Parse a .osu beatmap file and return relevant data."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Beatmap file not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    sections = {}
    current_section = None
    current_lines = []

    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            if current_section is not None:
                sections[current_section] = current_lines
            current_section = line[1:-1]
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)

    if current_section is not None:
        sections[current_section] = current_lines

    # Parse metadata
    def get_section(name):
        return sections.get(name, [])

    # Parse General
    general = {}
    for line in get_section('General'):
        if ':' in line:
            key, val = line.split(':', 1)
            general[key.strip()] = val.strip()

    mode = int(general.get('Mode', '0'))

    # Parse Difficulty
    difficulty = {}
    for line in get_section('Difficulty'):
        if ':' in line:
            key, val = line.split(':', 1)
            try:
                difficulty[key.strip()] = float(val.strip())
            except ValueError:
                pass

    # Parse TimingPoints (for red lines / uninherited timing points)
    timing_points = []
    for line in get_section('TimingPoints'):
        parts = line.split(',')
        if len(parts) >= 2:
            time = float(parts[0])
            beat_length = float(parts[1])
            meter = int(parts[2]) if len(parts) > 2 else 4
            # uninherited if beat_length > 0
            timing_points.append({
                'time': time,
                'beat_length': beat_length,
                'meter': meter,
                'uninherited': beat_length > 0
            })

    # Parse HitObjects
    hit_objects = []
    for line in get_section('HitObjects'):
        parts = line.split(',')
        if len(parts) >= 5:
            x = int(parts[0])
            y = int(parts[1])
            time = int(parts[2])
            hit_type = int(parts[3])
            obj = {
                'x': x,
                'y': y,
                'time': time,
                'type': hit_type,
                'end_time': None,
                'column': 0
            }
            # Check for hold note (type 128)
            if hit_type & 128:
                extras = parts[5].split(':') if len(parts) > 5 else ['0']
                obj['end_time'] = int(extras[0])
            hit_objects.append(obj)

    # Determine key count from CircleSize (mania mode)
    cs = difficulty.get('CircleSize', 4)
    if mode == 3:  # mania
        key_count = int(cs) if cs >= 1 else 4
    else:
        key_count = 4  # default for converted maps

    # Assign columns to notes based on x position
    for obj in hit_objects:
        column_width = 512.0 / key_count
        col = int(obj['x'] / column_width)
        if col >= key_count:
            col = key_count - 1
        obj['column'] = col

    return {
        'mode': mode,
        'key_count': key_count,
        'od': difficulty.get('OverallDifficulty', 5),
        'hp': difficulty.get('HPDrainRate', 5),
        'cs': difficulty.get('CircleSize', key_count),
        'ar': difficulty.get('ApproachRate', 5),
        'timing_points': timing_points,
        'hit_objects': hit_objects,
        'total_objects': len(hit_objects),
    }


# ============= Difficulty Calculation (SunnySkill equivalent) =============

def calculate_difficulty(hit_objects, key_count, od, mods_str=''):
    """Calculate difficulty attributes from hit objects."""
    if not hit_objects:
        return {'sr': 0, 'variety': 0, 'acc_scalar': 0, 'total_notes': 0}

    # Parse mods
    mods_upper = mods_str.upper().replace(' ', '')
    has_dt = 'DT' in mods_upper or 'NC' in mods_upper
    has_ht = 'HT' in mods_upper
    has_hr = 'HR' in mods_upper
    has_ez = 'EZ' in mods_upper
    contains_cl = 'CL' in mods_upper

    # Calculate clock rate from mods
    clock_rate = 1.0
    if has_dt:
        clock_rate = 1.5
    elif has_ht:
        clock_rate = 0.75

    # Calculate great hit window (matching ManiaDifficultyCalculator.getHitWindow300)
    od_original = od
    if mode_guess(key_count) == 3:  # mania mode
        anti_od = min(10.0, max(0, 10.0 - od_original))
        great_hit_window = 34 + 3 * anti_od
    else:
        if round(od_original) > 4:
            great_hit_window = 34
        else:
            great_hit_window = 47

    # applyModAdjustments: multiply by clock_rate first, then HR/EZ, then round
    great_hit_window *= clock_rate
    great_hit_window += 1e-6  # ensure correct rounding

    if has_hr:
        great_hit_window /= 1.4
    elif has_ez:
        great_hit_window *= 1.4

    great_hit_window = (int(great_hit_window) + 0.5) / clock_rate

    # Calculate x parameter (derived from hit window)
    x = 0.3 * (great_hit_window / 500.0) ** 0.5
    x = min(x, 0.6 * (x - 0.09) + 0.09)

    # Build Note objects
    note_seq = []
    note_seq_by_column = [[] for _ in range(key_count)]

    for obj in hit_objects:
        col = obj['column']
        head = obj['time']
        tail = obj.get('end_time', -1) if obj.get('end_time') is not None else -1

        note = Note(column=col, head=head, tail=tail)
        note_seq.append(note)
        note_seq_by_column[col].append(note)

    if not note_seq:
        return {'sr': 0, 'variety': 0, 'acc_scalar': 0, 'total_notes': 0}

    # Calculate
    sr_params = MACalculator.calculate(
        note_seq, note_seq_by_column, key_count, x, contains_cl)
    variety = MACalculator.variety(note_seq, note_seq_by_column)

    acc_scalar = 0.5 * sr_params.spikiness + 0.5 * sr_params.switches
    total_notes = len(hit_objects)

    return {
        'sr': sr_params.sr,
        'variety': variety,
        'acc_scalar': acc_scalar,
        'total_notes': total_notes,
        'spikiness': sr_params.spikiness,
        'switches': sr_params.switches,
    }


def mode_guess(key_count):
    """Guess if this is osu!mania based on key_count."""
    return 3  # Always treat as mania for our purposes


# ============= Performance Calculator =============

def calculate_performance(diff_attrs: dict, accuracy: float,
                          mods_str: str = '', counts_provided: bool = False,
                          perfect_count: int = 0, great_count: int = 0,
                          good_count: int = 0, ok_count: int = 0,
                          meh_count: int = 0, miss_count: int = 0) -> dict:
    """
    Calculate PP from difficulty attributes and accuracy.
    Port of ManiaPerformanceCalculator.cs
    """
    sr = diff_attrs['sr']
    acc = max(0.0, min(1.0, accuracy))
    total_notes = diff_attrs['total_notes']

    mods_upper = mods_str.upper().replace(' ', '')

    # Compute total hits if not specified
    has_counts = counts_provided and \
        (perfect_count + great_count + good_count + ok_count + meh_count + miss_count) > 0
    if has_counts:
        total_hits = perfect_count + great_count + good_count + ok_count + meh_count + miss_count
    else:
        total_hits = total_notes

    # Custom accuracy (weighted by hit value / 305)
    # The website uses the accuracy value directly as custom_acc in the proportion formula
    if has_counts and total_hits > 0:
        custom_acc = (perfect_count * 305 + great_count * 300 + good_count * 200 +
                      ok_count * 100 + meh_count * 50) / (total_hits * 305)
    else:
        custom_acc = acc

    # Mod multiplier
    multiplier = 1.0
    if 'NF' in mods_upper:
        multiplier *= 0.75
    if 'EZ' in mods_upper:
        multiplier *= 0.90

    # Compute difficulty value
    difficulty_value = compute_difficulty_value(sr, custom_acc)

    # Variety multiplier
    variety_mult = variety_multiplier(diff_attrs['variety'])

    # Accuracy multiplier
    acc_mult = acc_multiplier(custom_acc, diff_attrs['acc_scalar'])

    # Length multiplier
    length_mult = length_multiplier(total_notes, sr)

    # Total PP
    total_value = (difficulty_value * multiplier * variety_mult *
                   acc_mult * length_mult)

    return {
        'difficulty': difficulty_value,
        'variety_multiplier': variety_mult,
        'acc_multiplier': acc_mult,
        'length_multiplier': length_mult,
        'multiplier': multiplier,
        'total': total_value,
        'star_rating': sr,
    }


def compute_difficulty_value(sr, acc):
    """Compute the base difficulty-to-PP conversion."""
    # proportion based on accuracy (only if acc > 0.80)
    if acc > 0.80:
        proportion = 4.5 * (acc - 0.8) / ((100 * (1 - acc) + (0.9 ** 20)) ** 0.05)
    else:
        proportion = 0

    difficulty_value = 9.8 * (max(sr - 0.15, 0.05) ** 2.2) * proportion
    return difficulty_value


def variety_multiplier(variety):
    """Sigmoid-based variety multiplier."""
    floor = 0.945
    cap = 1.055
    L = cap - floor
    v0 = 3.25
    k = 3

    sigmoid_variety = floor + L / (1 + math.exp(-k * (variety - v0)))
    return sigmoid_variety


def acc_multiplier(acc, acc_scalar):
    """Accuracy multiplier with sigmoid scaler."""
    sigmoid_scaler = 0.87 + 0.26 / (1.0 + math.exp(-20 * (acc_scalar - 1)))
    return sigmoid_scaler * (2 * (acc ** 20) - 1) + 2 - 2 * (acc ** 20)


def length_multiplier(total_notes, star_rating):
    """Length multiplier based on total notes and star rating."""
    return 1.1 / (1.0 + math.sqrt(star_rating / (2 * total_notes)))


# ============= Main Entry Point =============

def calculate_pp(beatmap_path: str, accuracy: float = 0.90,
                 mods: str = '', counts_provided: bool = False, **kwargs) -> dict:
    """
    Calculate PP for a beatmap.

    Args:
        beatmap_path: Path to .osu file
        accuracy: Overall accuracy (0.0 to 1.0)
        mods: Mod string (e.g. 'DT', 'HR', 'NF')
        counts_provided: Whether judgment counts are given
        **kwargs: Optional overrides for hit counts

    Returns:
        Dict with PP and component breakdown
    """
    # Parse beatmap
    bm = parse_osu_file(beatmap_path)

    if bm['mode'] != 3:
        print(f"Warning: Beatmap mode is {bm['mode']}, not osu!mania. "
              f"Treating as mania with {bm['key_count']} keys.")

    # Calculate difficulty
    diff_attrs = calculate_difficulty(
        bm['hit_objects'], bm['key_count'], bm['od'], mods)

    # Calculate performance
    perf = calculate_performance(
        diff_attrs, accuracy, mods, counts_provided=counts_provided,
        perfect_count=kwargs.get('perfect', 0),
        great_count=kwargs.get('great', 0),
        good_count=kwargs.get('good', 0),
        ok_count=kwargs.get('ok', 0),
        meh_count=kwargs.get('meh', 0),
        miss_count=kwargs.get('miss', 0),
    )

    return {
        'pp': perf['total'],
        'star_rating': round(perf['star_rating'], 4),
        'difficulty_value': round(perf['difficulty'], 2),
        'variety_multiplier': round(perf['variety_multiplier'], 4),
        'acc_multiplier': round(perf['acc_multiplier'], 4),
        'length_multiplier': round(perf['length_multiplier'], 4),
        'mod_multiplier': round(perf['multiplier'], 4),
        'total_notes': diff_attrs['total_notes'],
        'variety': round(diff_attrs['variety'], 4),
        'acc_scalar': round(diff_attrs['acc_scalar'], 4),
        'spikiness': round(diff_attrs.get('spikiness', 0), 4),
        'switches': round(diff_attrs.get('switches', 0), 4),
        'key_count': bm['key_count'],
        'od': bm['od'],
    }


def print_result(result: dict):
    """Pretty print calculation result."""
    print()
    print("=" * 50)
    print(f"  PP: {result['pp']:.2f}")
    print("=" * 50)
    print(f"  Star Rating:      {result['star_rating']:.2f}★")
    print(f"  Key Count:        {result['key_count']}K")
    print(f"  OD:               {result['od']:.1f}")
    print(f"  Total Notes:      {result['total_notes']}")
    print(f"  Variety:          {result['variety']:.3f}")
    print(f"  Acc Scalar:       {result['acc_scalar']:.3f}")
    print(f"  Spikiness:        {result['spikiness']:.3f}")
    print(f"  Switches:         {result['switches']:.3f}")
    print("-" * 50)
    print(f"  Difficulty Value: {result['difficulty_value']:.2f}")
    print(f"  Variety Multi:    {result['variety_multiplier']:.4f}")
    print(f"  Acc Multi:        {result['acc_multiplier']:.4f}")
    print(f"  Length Multi:     {result['length_multiplier']:.4f}")
    print(f"  Mod Multi:        {result['mod_multiplier']:.4f}")
    print("-" * 50)
    print(f"  PP = {result['difficulty_value']:.2f}"
          f" × {result['variety_multiplier']:.4f}"
          f" × {result['acc_multiplier']:.4f}"
          f" × {result['length_multiplier']:.4f}"
          f" × {result['mod_multiplier']:.4f}"
          f" = {result['pp']:.2f}")
    print("=" * 50)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Sunny Rework PP Calculator for osu!mania",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sunny_rework.py map.osu 0.90
  python sunny_rework.py map.osu 0.95 --mods DT
  python sunny_rework.py map.osu --perfect 1000 --great 500 --miss 10
        """
    )
    parser.add_argument("beatmap", metavar="BEATMAP", help="Path to .osu beatmap file")
    parser.add_argument(
        "accuracy", nargs='?', type=float, default=None,
        help="Overall accuracy (0.0-1.0). Ignored if judgment counts given."
    )
    parser.add_argument("--mods", default="", help="Mod string, e.g. 'DT', 'HRDT', 'NF'")
    parser.add_argument("--perfect", type=int, default=0, help="Number of MAX (Rainbow 300)")
    parser.add_argument("--great", type=int, default=0, help="Number of 300s (Great)")
    parser.add_argument("--good", type=int, default=0, help="Number of 200s (Good)")
    parser.add_argument("--ok", type=int, default=0, help="Number of 100s (Ok)")
    parser.add_argument("--meh", type=int, default=0, help="Number of 50s (Meh)")
    parser.add_argument("--miss", type=int, default=0, help="Number of misses")

    args = parser.parse_args()

    beatmap_path = args.beatmap
    mods = args.mods

    if not os.path.exists(beatmap_path):
        print(f"Error: Beatmap file not found: {beatmap_path}")
        sys.exit(1)

    # Determine accuracy and counts
    counts_provided = any([
        args.perfect > 0, args.great > 0, args.good > 0,
        args.ok > 0, args.meh > 0, args.miss > 0
    ])

    if counts_provided:
        total_given = (args.perfect + args.great + args.good +
                       args.ok + args.meh + args.miss)
        if total_given == 0:
            print("Error: No hit counts provided.")
            sys.exit(1)
        # Calculate effective accuracy from counts (displayed accuracy)
        acc = (args.perfect * 300 + args.great * 300 + args.good * 200 +
               args.ok * 100 + args.meh * 50) / (total_given * 300)
    elif args.accuracy is not None:
        acc = max(0.0, min(1.0, args.accuracy))
    else:
        acc = 0.90  # default

    print(f"Calculating PP for: {beatmap_path}")
    print(f"Accuracy: {acc * 100:.1f}%")
    if mods:
        print(f"Mods: {mods}")
    if counts_provided:
        print(f"Judgments: {args.perfect}MAX {args.great}GREAT "
              f"{args.good}GOOD {args.ok}OK {args.meh}MEH {args.miss}MISS")

    result = calculate_pp(
        beatmap_path, acc, mods,
        perfect=args.perfect,
        great=args.great,
        good=args.good,
        ok=args.ok,
        meh=args.meh,
        miss=args.miss,
        counts_provided=counts_provided,
    )
    print_result(result)


if __name__ == '__main__':
    main()
