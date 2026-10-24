"""⚡ hold bars of the chart: 32 (deployed) vs 24 / 40 / 48 / 64, the v0.99.704 exits and risk rules"""
exec(open("osc_take.py").read().split("run(\"v704: тейк 1.1 везде\"")[0])
def fh(hb):
    def f(e):
        T, O, H, L, C = h1c(e["sym"])
        return walk5(T, O, H, L, C, e["i1"], e["fbt"] + hb * e["tfh"] * 3600, e["s"], e["fill"], e["a"], 1.1, 2.0, 3.0, e["tfh"], 2.0)
    return f
for hb in (32, 24, 40, 48, 64):
    run(f"⚡ держать {hb} свечей", fh(hb))
