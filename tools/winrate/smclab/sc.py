# smc_sel.py without the Neuro lab's data: lv_wf imports nx_h only for pain (the growth bootstrap, not the scores)
import sys, types, runpy
sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
runpy.run_path("/home/user/vp-poc-screener/tools/new_ind/smc_sel.py", run_name="__main__")
