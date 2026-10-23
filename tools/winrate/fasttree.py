"""a compiled copy of the bot's zm_tree_pred (the same nodes, the same comparisons: v <= thr, NaN -> the node's flag)"""
import numpy as np
from numba import njit
_CACHE = {}
def flatten(trees):
    F, TH, NL, L, R, LEAF, roots = [], [], [], [], [], [], []
    def walk(t):
        k = len(F); F.append(-1); TH.append(0.0); NL.append(0); L.append(-1); R.append(-1); LEAF.append(0.0)
        if isinstance(t, list):
            F[k] = t[0]; TH[k] = t[1]; NL[k] = 1 if t[2] else 0
            l = walk(t[3]); r = walk(t[4]); L[k] = l; R[k] = r
        else:
            LEAF[k] = t
        return k
    for t in trees: roots.append(walk(t))
    return (np.array(F, np.int64), np.array(TH), np.array(NL, np.int64), np.array(L, np.int64), np.array(R, np.int64), np.array(LEAF), np.array(roots, np.int64))
@njit
def _pred(F, TH, NL, L, R, LEAF, roots, x):
    s = 0.0
    for r in roots:
        k = r
        while F[k] >= 0:
            v = x[F[k]]
            go = (v <= TH[k]) if v == v else (NL[k] == 1)
            k = L[k] if go else R[k]
        s += LEAF[k]
    return s
def fast_tree_pred(trees, x):
    key = id(trees)
    if key not in _CACHE: _CACHE[key] = (trees, flatten(trees))
    return _pred(*_CACHE[key][1], np.asarray(x, np.float64))
