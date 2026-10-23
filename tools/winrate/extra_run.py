"""the honest 1h / 4h engines on the 83 extra coins (into <dir>x/), the 127's check split untouched"""
import os, sys, time, importlib, multiprocessing as mp
mod = sys.argv[1]
E = importlib.import_module(mod)
E.OUT = E.OUT + "x"
os.makedirs(E.OUT, exist_ok=True)
syms = [s.strip() for s in open("new_coins.txt") if s.strip() and os.path.exists(f"data/1h/{s.strip()}.csv")]
if __name__ == "__main__":
    with mp.Pool(4) as p:
        for k, r in enumerate(p.imap_unordered(E.run, syms)):
            print(k, r, flush=True)
