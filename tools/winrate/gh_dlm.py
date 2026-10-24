"""GitHub indicator states at the entries of the whole honest ⚡ pool (the money sim's PC), saved for splits / money tests"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
exec(open("gh_states.py").read().split("rows = []")[0])
out = []
for p in PC:
    s = dname(p[5]["sym"]); 
    if not s: out.append(None); continue
    c = coin(s); te = float(p[0]); side = int(p[5]["s"]); r = {"R": float(p[2]), "te": te, "sym": p[5]["sym"], "d": side,
                                                              "y": int(np.datetime64(int(te), "s").astype("datetime64[Y]").astype(int) + 1970)}
    ok = True
    for tf in ("4h", "1d"):
        et, st_ = c[tf]; k = np.searchsorted(et, te, side="right") - 1
        if k < 60: ok = False; break
        for nm, v in st_.items():
            x = float(v[k]); r[f"{nm}_{tf}"] = x * side if nm in SIGNED or nm == "td" else x
    if not ok: out.append(None); continue
    for tf in ("4h", "1d"):
        w, iw = r.pop(f"wvf_{tf}"), r.pop(f"iwvf_{tf}"); r[f"vix_{tf}"] = w if side > 0 else iw
        r3 = r.pop(f"rsi3_{tf}"); r[f"rsi3_{tf}"] = r3 if side > 0 else 100 - r3
    out.append(r)
json.dump(out, open("gh_dlm.json", "w"))
print(len(PC), sum(1 for r in out if r))
