import re

with open("tpot-analyzer/scripts/verify_veil_cv.py", "r") as f:
    content = f.read()

# Replace cg import with compute_ppr import
content = content.replace("from scipy.sparse.linalg import cg", "from src.propagation.engine import compute_ppr")

# Modify main() to pass adj instead of laplacian
content = content.replace("laplacian = sp.diags(degrees, format=\"csr\") - sym", "")
content = content.replace(
    "memberships, labeled_mask, snc = propagate_fold(\n            laplacian, degrees, node_ids, train_seeds, archive_weights,\n            community_ids, eligibility,\n        )",
    "memberships, labeled_mask, snc = propagate_fold(\n            adj, degrees, node_ids, train_seeds, archive_weights,\n            community_ids, eligibility,\n        )"
)
# Note: the exact formatting in the file might be slightly different.
