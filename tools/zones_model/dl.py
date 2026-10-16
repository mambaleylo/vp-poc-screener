import os, sys, io, zipfile, urllib.request, concurrent.futures as cf, csv, json
B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines"
COINS = """BTC ETH BNB SOL XRP DOGE ADA AVAX LINK DOT TRX LTC BCH ATOM NEAR UNI ETC FIL APT ARB OP INJ SUI SEI TIA AAVE MKR LDO CRV SNX
COMP RUNE SAND MANA AXS GALA APE CHZ ENJ IMX FTM GRT ALGO XLM VET EOS XTZ THETA EGLD FLOW KAVA ZEC DASH NEO QTUM ICP STX HBAR WLD
1000PEPE 1000SHIB 1000FLOKI 1000BONK WIF ORDI TON JUP PYTH ENA ONDO RNDR RENDER FET AR TAO NOT PENDLE DYDX GMX BLUR JASMY ROSE ZIL 1INCH
SUSHI YFI LRC ZRX KSM ANKR CELO RSR TRB ENS MASK ARPA STORJ WOO C98 PEOPLE GMT ID MAGIC CFX ACH SSV XAI ALT MANTA STRK DYM BOME ETHFI
KAS AEVO W BB IO ZK POPCAT NEIRO EIGEN HMSTR CATI TURBO MEW BRETT""".split()
TF = sys.argv[1] if len(sys.argv) > 1 else "1h"
OUT = f"data/{TF}"
os.makedirs(OUT, exist_ok=True)
months = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
def get(sym, mo):
    url = f"{B}/{sym}/{TF}/{sym}-{TF}-{mo}.zip"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        rows = []
        for line in z.read(z.namelist()[0]).decode().splitlines():
            p = line.split(",")
            if not p[0].isdigit():
                continue
            rows.append((int(p[0]) // 1000, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[7])))
        return rows
    except Exception as e:
        return None
def coin(c):
    sym = c + "USDT"
    fn = f"{OUT}/{sym}.csv"
    if os.path.exists(fn):
        return c, -1
    allr = []
    with cf.ThreadPoolExecutor(8) as ex:
        for rows in ex.map(lambda mo: get(sym, mo), months):
            if rows:
                allr += rows
    if allr:
        allr.sort()
        with open(fn, "w") as f:
            f.write("\n".join(",".join(map(str, r)) for r in allr))
    return c, len(allr)
with cf.ThreadPoolExecutor(4) as ex:
    for c, n in ex.map(coin, COINS):
        print(c, n, flush=True)
