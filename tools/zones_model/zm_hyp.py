import sys, numpy as np
ARGS = sys.argv[1:]
import zm_h as Z
q = float(ARGS[0]); d = Z.d
L0 = "G_0.75_R4.0"
def run(nm, mask=None, lab=L0):
    Z.line(nm, Z.replay(Z.cand(q, mask), lab), q)
print(f"== q {q}")
run("сейчас: буфер 0.75, тейк 4R")
run("только лонги", Z.SIDE > 0); run("только шорты", Z.SIDE < 0)
for tf in sorted(set(d.tf.astype(str).values)):
    run(f"только график {tf}", d.tf.astype(str).values == tf)
run("BTC 24ч по сделке > -4%", d.s_b24.values > -4)
run("BTC по сделке относительно EMA50 > 0", d.s_b_ema50.values > 0)
run("монета по тренду (EMA200 по сделке > 0)", d.s_ema200.values > 0)
for lab in ("G_0.75_R3.0", "G_0.75_R6.0", "G_1.0_R4.0", "G_1.0_R3.0", "G_1.5_R3.0", "G_1.5_R2.0", "G_2.0_R2.0"):
    run(f"выход {lab}", lab=lab)
