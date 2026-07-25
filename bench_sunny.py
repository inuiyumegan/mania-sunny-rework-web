import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import time, sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sunny
import sunny_fast
import lookup

beatmap = "5732935.osu"

print("=" * 60)
print("  Benchmark: sunny vs sunny_fast")
print("=" * 60)

print("\n--- sunny (original) ---")
t0 = time.time()
r_orig = sunny.calculate(beatmap)
t1 = time.time()
d_orig = lookup.sunny_diff(r_orig['star'], r_orig['ln_ratio'], r_orig['column_count'])
print(f"  Time: {t1-t0:.2f}s  SR={r_orig['star']:.4f}  {d_orig}")

print("\n--- sunny_fast (optimized) ---")
t0 = time.time()
r_fast = sunny_fast.calculate(beatmap)
t1 = time.time()
d_fast = lookup.sunny_diff(r_fast['star'], r_fast['ln_ratio'], r_fast['column_count'])
print(f"  Time: {t1-t0:.2f}s  SR={r_fast['star']:.4f}  {d_fast}")

print(f"\n  Speedup:       {(time.time() - t0) / (time.time() - t0) if False else 'see above'}")
print(f"  Orig SR:       {r_orig['star']:.6f}")
print(f"  Fast SR:       {r_fast['star']:.6f}")
print(f"  SR Delta:      {abs(r_fast['star']-r_orig['star']):.6f}")
