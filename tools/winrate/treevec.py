"""the bot's tree models (zm_tree_pred's nested lists: [feature, threshold, nan_left, left, right] / a leaf value) evaluated
vectorized over many rows: each tree flattened once, then all rows walk it together"""
import numpy as np
def flat(tree):
    F, T, NL, L, R, V = [], [], [], [], [], []
    def add(n):
        i = len(F); F.append(-1); T.append(0.0); NL.append(False); L.append(-1); R.append(-1); V.append(0.0)
        if isinstance(n, list):
            F[i] = int(n[0]); T[i] = float(n[1]); NL[i] = bool(n[2]); L[i] = add(n[3]); R[i] = add(n[4])
        else:
            V[i] = float(n)
        return i
    add(tree)
    return np.array(F), np.array(T), np.array(NL), np.array(L), np.array(R), np.array(V)
def predict(trees, X):
    """sum over the trees (zm_tree_pred's)"""
    X = np.asarray(X, float); out = np.zeros(len(X))
    for tr in trees:
        F, T, NL, L, R, V = tr if isinstance(tr, tuple) else flat(tr)
        idx = np.zeros(len(X), np.int64); act = F[idx] >= 0
        while act.any():
            a = np.flatnonzero(act); n = idx[a]; v = X[a, F[n]]
            go_left = np.where(np.isnan(v), NL[n], v <= T[n])
            idx[a] = np.where(go_left, L[n], R[n]); act[a] = F[idx[a]] >= 0
        out += V[idx]
    return out
def model_score(models, X):
    """the bot's score: the mean over the models of the sum over each one's trees"""
    return np.mean([predict([flat(t) for t in m], X) for m in models], axis=0)
