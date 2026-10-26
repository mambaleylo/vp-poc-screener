exec(open("htf_lab7.py").read().split('print("== монеты"')[0])
run("BOTH99K24 обе ≥0.99 + стоп по дню", save=True, both=(0.99, False), kh=24)
run("ORB99K24 бот ИЛИ обе ≥0.99 + стоп по дню", save=True, both=(0.99, True), kh=24)
run("ORB99 бот ИЛИ обе ≥0.99", save=True, both=(0.99, True))
