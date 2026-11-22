"""Print a locust *_stats.csv as one line per endpoint:  python loadtest/summary.py .house/reports/load/real"""

import csv
import sys

for r in csv.DictReader(open(sys.argv[1] + "_stats.csv", encoding="utf-8")):
    print(f"{r['Name'][:28]:28} n={r['Request Count']:>6} err={r['Failure Count']:>4} p50={r['50%']:>6} "
          f"p95={r['95%']:>6} p99={r['99%']:>6} rps={float(r['Requests/s']):6.1f}")
