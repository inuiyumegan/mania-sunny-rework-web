import os; os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import time, sys
sys.dont_write_bytecode = True
sys.path.insert(0, r"D:\00\todo\web_sunny_rework\sunny-rework-extension")

import sunny

t0 = time.time()
r = sunny.calculate("5732935.osu")
elapsed = time.time() - t0
print(f"Total: {elapsed:.2f}s, SR={r['star']:.4f}")
