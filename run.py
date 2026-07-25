import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import sys
import os
sys.dont_write_bytecode = True

import time

import sunny_fast as sunny
import daniel
import lookup


def main():
    beatmap_file = "5732935.osu"
    if len(sys.argv) > 1:
        beatmap_file = sys.argv[1]

    if not os.path.exists(beatmap_file):
        print(f"Error: '{beatmap_file}' not found")
        sys.exit(1)

    print("=" * 62)
    print("  sunny-rework-extension")
    print("  Sunny Rework + Daniel (TheBagelOfMan) Difficulty Calculator")
    print("=" * 62)

    # --- Sunny ---
    print("\n>>> Sunny Rework Algorithm")
    t0 = time.time()
    sr = sunny.calculate(beatmap_file)
    t1 = time.time()
    diff = lookup.sunny_diff(sr["star"], sr["ln_ratio"], sr["column_count"])
    print(f"  Time:         {t1 - t0:.2f}s")
    print(f"  Star Rating:  {sr['star']:.4f}")
    print(f"  Difficulty:   {diff}")
    print(f"  LN Ratio:     {sr['ln_ratio']:.3f} ({sr['ln_count']}/{sr['total_notes']} LN)")
    print(f"  OD:           {sr['od']} (beatmap)")
    print(f"  Keys:         {sr['column_count']}K")

    # --- Daniel ---
    print("\n>>> Daniel Algorithm (TheBagelOfMan)")
    t0 = time.time()
    dr = daniel.calculate(beatmap_file)
    t1 = time.time()
    label, numeric = lookup.daniel_diff(dr["star"])
    print(f"  Time:         {t1 - t0:.2f}s")
    print(f"  Star Rating:  {dr['star']:.4f}")
    print(f"  Dan Level:    {label}")
    if numeric is not None:
        print(f"  Numeric Dan:  {numeric:.2f}")
    print(f"  LN Ratio:     {dr['ln_ratio']:.3f} ({dr['ln_count']}/{dr['total_notes']} LN)")
    print(f"  OD:           9 (fixed)")
    print(f"  Keys:         {dr['column_count']}K")

    print("\n" + "=" * 62)


if __name__ == "__main__":
    main()
