"""robustness of the one idea better on both sets: tighten the exit channel after +X R (neighbours of +5R -> 15)"""
import sys, numpy as np
ARGS = sys.argv[1:]
import rb_h as B, rb_sim2 as S2
M = B.BOT if ARGS[0] == "bot" else B.CHECK
print(f"== {ARGS[0]}")
for nm, kw in (("сейчас", {}), ("+4R -> 15", {"tight_r": 4.0, "ne2": 15}), ("+5R -> 15", {"tight_r": 5.0, "ne2": 15}), ("+6R -> 15", {"tight_r": 6.0, "ne2": 15}),
               ("+8R -> 15", {"tight_r": 8.0, "ne2": 15}), ("+8R -> 10", {"tight_r": 8.0, "ne2": 10})):
    R, H = S2.outcomes(M, **kw); tr = B.replay(M, R, H); B.line(nm, tr, R, H)
