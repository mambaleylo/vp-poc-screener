import numpy as np
from cas_loss import show, F, SD
SDf = SD.astype(float); b1 = SDf * F("b_r1") > -0.5
for nm, kw in (("сейчас", {}), ("BTC 1ч против < 0.5%", dict(mask=b1)),
               ("1/2 на +0.5R, до 3", dict(part_r=0.5, part_f=0.5, cap=3)), ("1/3 на +0.5R, до 4", dict(part_r=0.5, cap=4)),
               ("1/2 на +0.5R + BTC 1ч", dict(part_r=0.5, part_f=0.5, mask=b1)), ("1/3 на +0.7R, до 3 + BTC 1ч", dict(cap=3, mask=b1)),
               ("1/3 на +0.6R", dict(part_r=0.6)), ("1/2 на +0.7R", dict(part_f=0.5)), ("1/2 на +0.6R, тейк 3R", dict(part_r=0.6, part_f=0.5, take_r=3.0))):
    show(nm, kw)
