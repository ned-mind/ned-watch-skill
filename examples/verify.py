"""Check a callback from Ned before you trust it. Works with any web framework: pass the headers and the raw body."""
import hashlib, hmac, time


def verify(signing_secret: str, headers: dict, raw_body: bytes, max_age_s: int = 300) -> bool:
    h = {k.lower(): v for k, v in headers.items()}
    ts, sig = h.get("x-ned-timestamp", ""), h.get("x-ned-signature", "")
    if not ts.isdigit() or abs(time.time() - int(ts)) > max_age_s:
        return False
    want = hmac.new(signing_secret.encode(), ts.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)


if __name__ == "__main__":                        # self-test
    secret, body, ts = "whs_example", b'{"event":"fire","watch_id":"w_x"}', str(int(time.time()))
    good = {"X-Ned-Timestamp": ts, "X-Ned-Signature": hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()}
    assert verify(secret, good, body) and not verify(secret, good, body + b" ") and not verify("whs_other", good, body)
    print("verify.py ok")
