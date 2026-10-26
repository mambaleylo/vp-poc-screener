exec(open("cfl_lab.py").read().split('if __name__ == "__main__":')[0].replace("@njit(cache=True)", "@njit"))
run("B0 бот: q0.997, 1 dATR, 3R, 72ч")
for nm, kw in (("L лонги", dict(side=1)), ("L96 лонги, 96ч", dict(side=1, hold=96)), ("L96T4 лонги, 96ч, тейк 4R", dict(side=1, hold=96, take=4.0)),
               ("L96C20 лонги, 96ч, лимит 20", dict(side=1, hold=96, cap=20)), ("L96T4C20 + тейк 4R + лимит 20", dict(side=1, hold=96, take=4.0, cap=20)),
               ("L96Q995 лонги, 96ч, q0.995", dict(side=1, hold=96, q=0.995)), ("L96Q995C20 + лимит 20", dict(side=1, hold=96, q=0.995, cap=20)),
               ("L96D1 лонги, 96ч, вход через час", dict(side=1, hold=96, delay=1)), ("L120 лонги, 120ч", dict(side=1, hold=120))):
    run(nm, **kw)
