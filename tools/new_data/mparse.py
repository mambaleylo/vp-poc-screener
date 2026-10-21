import re, sys
for mod in sys.argv[1:]:
    sets, cur, yrs = [], None, None
    for ln in open(f"mt_{mod}.log"):
        if ln.startswith("=== "): cur = {"name": ln.strip(), "rows": {}}; sets.append(cur); continue
        if ln.strip().startswith("годы"): yrs = ln.split("годы")[1].strip(); continue
        m = re.match(r"(.{46}) +(\d+) +[\d.]+/нед ([+-][\d.]+)R WR +(\d+)%.*\| +(?:([\d.]+)%: x([\d.]+)|—)", ln)
        if m and cur is not None:
            cur["rows"][m.group(1).strip()] = (int(m.group(2)), float(m.group(3)), float(m.group(6) or 0), yrs)
    if len(sets) < 2: print(mod, "мало наборов", len(sets)); continue
    a, b = sets[0]["rows"], sets[1]["rows"]; ba, bb = a["сейчас"], b["сейчас"]
    print(f"\n#### {mod}: база {ba[1]:+.3f}R x{ba[2]:.0f} ({ba[0]}) | {bb[1]:+.3f}R x{bb[2]:.0f} ({bb[0]})")
    for k in a:
        if k == "сейчас" or k not in b: continue
        x, y = a[k], b[k]
        if x[1] > ba[1] and y[1] > bb[1] and x[2] > ba[2] and y[2] > bb[2]:
            print(f"  {k:36s} бот {x[1]:+.3f}R x{x[2]:.0f} ({x[0]}) [{x[3]}] | пров {y[1]:+.3f}R x{y[2]:.0f} ({y[0]}) [{y[3]}]")
