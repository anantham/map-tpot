import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import norm
import time

def compute_ppr(adj: sp.csr_matrix, seeds: np.ndarray, alpha: float = 0.15, max_iter: int = 100, tol: float = 1e-6):
    n = adj.shape[0]
    
    # Out-degrees
    out_degrees = np.array(adj.sum(axis=1)).flatten()
    # To avoid division by zero
    out_degrees[out_degrees == 0] = 1.0
    
    # Transition matrix P (row stochastic)
    # P_ij = A_ij / d_i
    inv_D = sp.diags(1.0 / out_degrees)
    P = inv_D @ adj
    
    # Transpose for power iteration: x_{k+1} = (1-alpha) P^T x_k + alpha * v
    PT = P.T.tocsr()
    
    v = np.zeros(n)
    v[seeds] = 1.0
    if v.sum() > 0:
        v /= v.sum()
    else:
        v = np.ones(n) / n
        
    x = v.copy()
    
    for i in range(max_iter):
        x_next = (1 - alpha) * (PT @ x) + alpha * v
        diff = np.linalg.norm(x_next - x, ord=1)
        x = x_next
        if diff < tol:
            # print(f"Converged in {i+1} iterations")
            break
            
    return x

