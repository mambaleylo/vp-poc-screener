"""the models retrained on the v0.99.690 exit's labels (s27_mix.py) vs the deployed (s26), both traded with that exit;
the pool as the bot trades it, money at 20 x 4%, by year, fixed starts, the last 12 months, unseen coins"""
exec(open("tkext3.py").read().split("for lab, EVx in")[0].replace('EVA = events(', 'EVA_ = (').replace('EVB = events(', 'EVB_ = ('))
UN4 = None
for nm, f4, f2 in (("развёрнутые модели (s26)", "s26_s23_4h_w1_0.npz", "s26_s21h2_d2_1.npz"), ("переобученные на новый выход (s27)", "s27_s23_4h_w1.npz", "s27_s21h2_d2.npz")):
    for q in (0.99, 0.985, 0.995):
        EV = events("s23_4h", 2, f4, "s23_engine", 4, "wick", 1.0, q) + events("s21h2", 0, f2, "s21h2_engine", 2, "close", 2.0, q)
        show(f"{nm} q{q}", 0.4, 1.0)
