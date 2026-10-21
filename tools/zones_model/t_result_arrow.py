"""v0.99.677 — a result post (TradingView price-range label + arrow) is recognised without OCR.
Usage: python3 t_result_arrow.py BOT.py SCREENSHOT.jpg [SCREENSHOT2.jpg ...]
The label OCR is switched off (the phone's tesseract may not read it); each screenshot, also
halved and JPEG-squeezed, must come out as a result post with no zones."""
import sys, io, importlib.util
from PIL import Image
sp = importlib.util.spec_from_file_location("bot", sys.argv[1]); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
orig = m._zocr_tesseract
m._zocr_tesseract = lambda img, psm=6, *a, **k: "" if (psm == 7 and img.height < 400) else orig(img, psm, *a, **k)
bad = 0
for f in sys.argv[2:]:
    im = Image.open(f).convert("RGB")
    for sc, q in ((1.0, 90), (0.5, 40)):
        b = io.BytesIO(); im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS).save(b, "JPEG", quality=q)
        r = m.zones_recognize(b.getvalue())
        ok = r["result_post"] and not r["zones"]
        bad += not ok
        print(f, sc, q, "OK" if ok else "FAIL", r["result_post"], len(r["zones"]))
print("ALL OK" if not bad else f"{bad} FAILED")
sys.exit(1 if bad else 0)
