"""v0.99.724 — «📤 Сделки в GitHub»: the money fields cut (the repository is public), the gzip'ed file on the branch
lab-data (created from main's head the first time, updated by its sha later, never main), the token chmod 600, the errors
in words; the page's button with no page errors"""
import os, json, gzip, base64, tempfile, time, threading
from common import V
D = tempfile.mkdtemp(); res = {}
V.GITHUB_CREDENTIALS_FILE = os.path.join(D, "gh.json")
V.DLM_STATE_FILE = os.path.join(D, "vp_dlm_state.json"); V.PRX_STATE_FILE = os.path.join(D, "vp_prx_state.json")
V.SMC_STATE_FILE = os.path.join(D, "vp_smc_state.json"); V.EMX_STATE_FILE = os.path.join(D, "vp_emx_state.json"); V.BNO_FILE = os.path.join(D, "vp_bn_others.json")
V.HTF_STATE_FILE = os.path.join(D, "vp_htf_state.json")   # v0.99.736 — 📏 HTF in the export
json.dump({"trades": [{"symbol": "SOL_USDT", "fam": "pdl", "entry": 150.0, "sl": 147.0, "r": 1.2, "real": {"status": "FILLED", "size": 3, "margin": 40.0}}], "armed": []}, open(V.HTF_STATE_FILE, "w"))
json.dump({"orders": [{"symbol": "BTC_USDT", "lv": 100.0, "real": {"status": "LIMIT", "id": "7", "size": 12, "price": 100.0, "risk": 4.5, "lev": 10}}],
           "trades": [{"symbol": "BTC_USDT", "entry": 100.0, "sl": 98.0, "pnl_r": 0.55, "pnl": 3.21, "risk_pct": 4.5, "balance_after": 512.3, "why": "маржа $29.53 превышает доступный баланс $1.62", "note": "5 USDT мало",
                       "real": {"status": "FILLED", "price": 100.01, "size": 12, "risk": 4.5, "margin": 50.0}}], "scan": {}}, open(V.DLM_STATE_FILE, "w"))
json.dump({"pos": {"ETHUSDT": {"mode": "smc", "qty": 0.5, "entry": 2000.0, "risk": 3.0, "margin": 100.0, "sl_px": 1950.0, "notional": 1000}}}, open(V.BNO_FILE, "w"))
V.log_error("binance algo STOP_MARKET ZKUSDT: Binance -4509: test reason — the order endpoint")
V.log_error("telegram: HTTPSConnectionPool url: /bot123456789:AAHk3jsd8f7sdf8sd7f8sd7f8sdf7sd8f7s/sendMessage timeout; GET /fapi/v2/account?timestamp=1&signature=abcdef0123456789")
V.log_error("free margin $12.50 too low")
dat = V.lab_export_build(); s = json.dumps(dat, ensure_ascii=False)
res["errors exported, secrets / money cut"] = "Binance -4509: test reason" in s and "AAHk3" not in s and "abcdef0123456789" not in s and "12.50" not in s
res["money cut"] = all(k not in s for k in ('"size"', '"risk"', '"margin"', '"balance_after"', '"pnl"', '"qty"', '"notional"'))
res["prices / R kept"] = '"pnl_r": 0.55' in s and '"risk_pct": 4.5' in s and '"sl_px": 1950.0' in s and '"price": 100.01' in s and '"lev": 10' in s
res["money in texts cut"] = "29.53" not in s and "1.62" not in s and "5 USDT" not in s and "маржа $… превышает доступный баланс $…" in s and "BTC_USDT" in s
res["coin keys kept"] = '"ETHUSDT"' in s and '"BTC_USDT"' in s
res["missing files skipped"] = set(dat["files"]) == {"vp_dlm_state.json", "vp_htf_state.json", "vp_bn_others.json"}
res["📏 HTF exported, money cut"] = dat["files"]["vp_htf_state.json"]["trades"][0]["r"] == 1.2 and "margin" not in json.dumps(dat["files"]["vp_htf_state.json"])
try: V.lab_upload(); res["no token -> error"] = False
except RuntimeError as e: res["no token -> error"] = "токена" in str(e)
V.save_github_token("ghp_test")
res["token chmod 600"] = oct(os.stat(V.GITHUB_CREDENTIALS_FILE).st_mode & 0o777) == "0o600" and V.github_token() == "ghp_test"
class R:
    def __init__(s, c, j=None): s.status_code, s._j, s.text = c, j or {}, json.dumps(j or {})
    def json(s): return s._j
calls = []; store = {}
def fake(method, url, headers=None, timeout=None, json=None, params=None):
    calls.append((method, url.split("/repos/")[1], (json or {}).get("branch"), (params or {}).get("ref")))
    assert headers["Authorization"] == "Bearer ghp_test"
    if url.endswith("/branches/lab-data"): return R(200 if "branch" in store else 404)
    if url.endswith("/git/ref/heads/main"): return R(200, {"object": {"sha": "abc"}})
    if url.endswith("/git/refs"): store["branch"] = json["sha"]; return R(201)
    if "/contents/" in url and method == "GET": return R(200, {"sha": store["sha"]}) if "sha" in store else R(404)
    if "/contents/" in url and method == "PUT":
        if "sha" in store and json.get("sha") != store["sha"]: return R(409)
        store["file"] = json["content"]; store["sha"] = "s%d" % len(calls); return R(201)
    return R(500)
V.requests.request = fake
a = V.lab_upload()
res["1st: branch from main, file put on lab-data"] = store.get("branch") == "abc" and all(c[2] in (None, "lab-data") for c in calls) and not any(c[2] == "main" for c in calls)
got = json.loads(gzip.decompress(base64.b64decode(store["file"])))
res["the file = the sanitized export"] = got["files"]["vp_dlm_state.json"]["trades"][0]["pnl_r"] == 0.55 and "size" not in json.dumps(got)
res["counts"] = a["n"] == {"vp_dlm_state.json": 1, "vp_htf_state.json": 1, "vp_bn_others.json": 1} and a["url"].endswith("/blob/lab-data/lab/vp_lab.json.gz")
n0 = len(calls); V.lab_upload()
res["2nd: no new branch, update by sha"] = not any(c[1].endswith("/git/refs") for c in calls[n0:]) and store["sha"].startswith("s")
V.requests.request = lambda *x, **k: R(401)
try: V.lab_upload(); res["401 in words"] = False
except RuntimeError as e: res["401 in words"] = "не принял токен" in str(e)
V.requests.request = lambda *x, **k: R(403)
try: V.lab_upload(); res["403 in words"] = False
except RuntimeError as e: res["403 in words"] = "нет права записи" in str(e)
c = V.app.test_client()
res["api status"] = c.get("/api/lab").get_json()["token"] is True
res["token only from this phone"] = c.post("/api/lab/token", json={"token": "x"}, environ_base={"REMOTE_ADDR": "100.64.1.2"}).status_code in (403,)
r = c.post("/api/lab/token", json={"token": ""}, environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_json()
res["empty token -> removed"] = r["ok"] and r["token"] is False and not os.path.exists(V.GITHUB_CREDENTIALS_FILE)
res["gitignored"] = "vp_github_credentials.json" in open(os.path.join(os.path.dirname(V.__file__), ".gitignore")).read()
threading.Thread(target=lambda: V.app.run(port=5113, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs, dlg = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dlg.append(d.message), d.dismiss()))
    pg.goto("http://127.0.0.1:5113/"); pg.wait_for_timeout(3000)
    pg.evaluate("labUploadUi()"); pg.wait_for_timeout(1500)
    res["page: no errors, the token dialog"] = not errs and bool(dlg) and "Fine-grained" in dlg[0] and "Contents: Read and write" in dlg[0]
    b.close()
print(" · ".join(f"{k} {v}" for k, v in res.items())); print("ALL OK" if all(res.values()) else "FAILED")
