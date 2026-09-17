import os
import random
from datetime import datetime, timedelta

rng = random.Random(7)
paths = ["/api/users", "/api/orders", "/api/payments", "/health", "/api/search"]
codes = ["E_DB_TIMEOUT", "E_UPSTREAM_502", "E_VALIDATION", "E_AUTH_EXPIRED", "E_RATE_LIMIT"]
t = datetime(2026, 3, 1, 12, 0, 0)
lines = []
for _ in range(4000):
    t += timedelta(milliseconds=rng.randint(5, 900))
    ts = t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    rid = f"{rng.getrandbits(32):08x}"
    path = rng.choice(paths)
    r = rng.random()
    if r < 0.78:
        msg = rng.choice(["ok", "cache hit", "no ERROR here", "served"])
        lines.append(
            f'{ts} INFO  request_id={rid} path={path} status=200 '
            f'latency_ms={rng.randint(2, 400)} msg="{msg}"'
        )
    elif r < 0.88:
        lines.append(
            f'{ts} WARN  request_id={rid} path={path} status=200 code=W_SLOW '
            f'latency_ms={rng.randint(800, 3000)} msg="slow request, ERROR budget at risk"'
        )
    elif r < 0.985:
        code = rng.choice(codes)
        lines.append(f'{ts} ERROR request_id={rid} path={path} status=500 code={code} msg="request failed"')
        if code == "E_DB_TIMEOUT":
            lines.append("    Traceback (most recent call last):")
            lines.append('      File "db/pool.py", line 88, in acquire')
            lines.append("    TimeoutError: ERROR acquiring connection code=E_POOL")
    else:
        lines.append(f'{ts} ERROR request_id={rid} path={path} status=500 msg="unhandled exception"')

os.makedirs("logs", exist_ok=True)
with open("logs/server.log", "w") as f:
    f.write("\n".join(lines) + "\n")
