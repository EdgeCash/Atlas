"""Owner-only tools. What they produce is published only inside the owner
page's ciphertext (`atlas/owner/page.py`, sealed by `atlas/owner/crypto.py`),
never on the public site.

They sit outside `atlas/live` on purpose: the live tracker must never
reason about money (`tests/test_live.py`), and it does not - these read its
committed record and never write to it.
"""
