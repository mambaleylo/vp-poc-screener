"""the models retrained on the v0.99.690 exit's labels (s27) vs the deployed (s26), honest order (honest2.py: the touch's
1h bar, the nearer level first), 4h + 2h and 4h alone with the new take. usage: pool27h.py s26|s27"""
import sys; WHICH = sys.argv[1] if len(sys.argv) > 1 else "s27"
src = open("honest2.py").read()
pre = open("pool1h.py").read().split('print("4h fills')[0]
tk = open("tkext.py").read().split("\nroll = np.arange")[0]
if WHICH == "s27":
    tk = tk.replace('"s26_s23_4h_w1_0.npz"', '"s27_s23_4h_w1.npz"').replace('"s26_s21h2_d2_1.npz"', '"s27_s21h2_d2.npz"')
open("_tk_tmp.py", "w").write(tk)
pre = pre.replace('exec(open("tkext.py").read().split("\\nroll = np.arange")[0])', 'exec(open("_tk_tmp.py").read())')
src = src.replace('''exec(open("pool1h.py").read().split('print("4h fills')[0]''', "exec(" + repr(pre) + "")
src = src[:src.index('show("4ч одна, тейк 1 ATR')]
src += '''W4 = [v for v in EV_ALL if v["tfh"] == 4]
show(f"{WHICH}: 4ч + 2ч, новый тейк", EV_ALL, 0.4, 1.0)
show(f"{WHICH}: 4ч одна, новый тейк", W4, 0.4, 1.0)
'''
open(f"_pool27h_{WHICH}.py", "w").write(src)
exec(compile(src, f"_pool27h_{WHICH}.py", "exec"))
