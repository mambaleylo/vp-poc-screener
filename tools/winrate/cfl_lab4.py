"""🔄 lab round 4: the close stop's grid (the close TF, the soft stop, the emergency stop, the take, the hold) + the entry an
hour later; R in the soft stop's units (the bot sizes on it; the emergency stop -> the worst trade)"""
import numpy as np
exec(open("cfl_lab3.py").read().rsplit('if __name__ == "__main__":', 1)[0])
src3 = open("cfl_lab3.py").read()
DEL = {"d": 0}
_run3 = run3
import re
# the entry an hour later: jE + delay (the walk and the busy time from the signal)
exec(src3.split("OUT = {}")[1].rsplit('if __name__ == "__main__":', 1)[0].replace("def run3(", "def run4(").replace("jE = int(J[i]) + 1", "jE = int(J[i]) + 1 + DEL['d']")
     .replace("end = t + int(K[i]) * 3600", "end = t + (int(K[i]) + DEL['d']) * 3600"))
if __name__ == "__main__":
    run4("B: 1 dATR, 4R, 96ч")
    for ctf in (24, 12, 8, 4):
        print(f"== закрытие {ctf}ч")
        for sk in (0.5, 0.6, 0.75, 0.9):
            for hd in (1.5, 2.0, 2.5):
                if hd <= sk: continue
                run4(f"{ctf}ч мягкий {sk} авар {hd} тейк 4R", sk=sk, hard=hd, ctf=ctf)
                if ctf in (24, 4): run4(f"{ctf}ч мягкий {sk} авар {hd} тейк 4 dATR", sk=sk, hard=hd, ctf=ctf, take=4.0 / sk)
    print("== держим / тейк на 24ч 0.75 / 2")
    for hold in (72, 120, 144):
        run4(f"24ч 0.75/2, 4R, {hold}ч", sk=0.75, hard=2.0, ctf=24, hold=hold)
    for tk in (3.0, 5.0, 6.0, 0.0):
        run4(f"24ч 0.75/2, тейк {tk or 'нет'}", sk=0.75, hard=2.0, ctf=24, take=tk)
    print("== вход через час (устойчивость)")
    DEL["d"] = 1
    run4("B через час", ); run4("24ч 0.75/2 4R через час", sk=0.75, hard=2.0, ctf=24); run4("4ч 0.75/2 4R через час", sk=0.75, hard=2.0, ctf=4)
    DEL["d"] = 2
    run4("24ч 0.75/2 4R через 2ч", sk=0.75, hard=2.0, ctf=24)
