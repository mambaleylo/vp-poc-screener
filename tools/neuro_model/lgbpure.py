"""LightGBM model -> compact JSON and a pure-Python predictor (the bot runs on a phone without numpy)."""
import json

def export(booster, feats):
    dm = booster.dump_model()
    trees = []
    def conv(n):
        if "leaf_value" in n:
            return round(n["leaf_value"], 7)
        assert n["decision_type"] == "<=", n["decision_type"]
        return [n["split_feature"], round(float(n["threshold"]), 7), 1 if n.get("default_left", True) else 0,
                conv(n["left_child"]), conv(n["right_child"])]
    for t in dm["tree_info"]:
        trees.append(conv(t["tree_structure"]))
    return {"feats": feats, "trees": trees}

def predict(m, x):
    s = 0.0
    for t in m["trees"]:
        while isinstance(t, list):
            v = x[t[0]]
            t = t[3] if (v <= t[1] if v == v else t[2]) else t[4]
        s += t
    return s
