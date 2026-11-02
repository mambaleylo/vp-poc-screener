# 🧱 SMC lab from scratch (v0.99.770 round)

Run from a copy of this folder outside git (e.g. `/home/user/smclab`, with `cp -r tools/winrate/lv` there): the events are big.

1. `run_smc.sh` — the levels' events of the 127 bot + 83 check coins on the clean 2020- candles (`/home/user/ema211/data/1h`:
   `tools/ema_model/data/1h` + the 83 coins by `tools/zones_model/dl.py`, both filled by `fill_gaps.py`) -> `lv2/`; the yearly
   walk-forward scores (`smc_sel.py` via `sc.py`: Neuro's data not needed) -> `smc_sc.npz`; `smc_repro.py` (corr 0.976).
2. `run_smc2.sh` — the events at ANY touch (`LV_TOUCH=0 lv_engine.py` -> `lv2_t0/`, build it first) scored by the deployed
   recipe (`smc_sc_t0.py`) and the rule variants (`smc_var.py` -> `<LABSTORE>/wf/smc_var_*.json`). `LV_D1H` must be the
   candles the events were built on (the bar indices).
3. Money: `MOD=smc ALLSUF=_clr money_ema.py K STEP bot base …`.
