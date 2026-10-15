"""Approver signatures (Ed25519) + local bridge token.

The app generates an Ed25519 key locally (iOS/visionOS Keychain), registers its public key once (trust on first use,
pinned in approvers.json), and signs every Approve/Decline payload. The bridge verifies the signature, runs WERIAM's
own principal CLI, and appends {payload, signature, public key, WERIAM entry hash} to a hash-chained side ledger
(signed_approvals.jsonl, same Ledger class as WERIAM). WERIAM's journal itself stays tamper-evident only; the side
ledger links each WERIAM principal_decision hash to a verifiable signature.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .adapter import Ledger

MAX_SKEW_S = 600


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def unb64(s: str) -> bytes:
    return base64.b64decode(s)


def key_id(pub_raw: bytes) -> str:
    return hashlib.sha256(pub_raw).hexdigest()[:16]


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def token(data: Path) -> str:
    p = Path(data) / "token"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(secrets.token_urlsafe(24))
        os.chmod(p, 0o600)
    return p.read_text().strip()


class Approvers:
    def __init__(self, data: Path):
        self.path = Path(data) / "approvers.json"
        self.keys = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.nonces_path = Path(data) / "nonces.json"
        self.nonces = set(json.loads(self.nonces_path.read_text())) if self.nonces_path.exists() else set()
        self.ledger = Ledger("signed_approvals", Path(data) / "signed_approvals.jsonl")

    def register(self, name: str, pub_b64: str) -> dict:
        raw = unb64(pub_b64)
        Ed25519PublicKey.from_public_bytes(raw)          # validates length/format
        kid = key_id(raw)
        if kid not in self.keys:
            if any(v["name"] == name for v in self.keys.values()):
                raise PermissionError(f"approver {name!r} already pinned to another key")
            self.keys[kid] = {"name": name, "pub": pub_b64, "registered_at": time.time()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.keys, indent=1, sort_keys=True))
        return {"key_id": kid, **self.keys[kid]}

    def verify(self, payload: dict, sig_b64: str, kid: str) -> dict:
        k = self.keys.get(kid)
        if k is None:
            raise PermissionError("unknown approver key (register first)")
        try:
            Ed25519PublicKey.from_public_bytes(unb64(k["pub"])).verify(unb64(sig_b64), canonical(payload))
        except (InvalidSignature, ValueError) as e:
            raise PermissionError("bad signature") from e
        if payload.get("by") != k["name"]:
            raise PermissionError("payload signer name does not match pinned key")
        if abs(time.time() - float(payload.get("ts", 0))) > MAX_SKEW_S:
            raise PermissionError("stale signature (ts)")
        n = str(payload.get("nonce", ""))
        if not n or n in self.nonces:
            raise PermissionError("nonce missing or replayed")
        self.nonces.add(n)
        self.nonces_path.write_text(json.dumps(sorted(self.nonces)))
        return k

    def record(self, payload: dict, sig_b64: str, kid: str, weriam_entry: dict | None) -> dict:
        return self.ledger.append("signed_decision", {
            "payload": payload, "signature": sig_b64, "key_id": kid, "pub": self.keys[kid]["pub"],
            "weriam_seq": weriam_entry["seq"] if weriam_entry else None,
            "weriam_hash": weriam_entry["hash"] if weriam_entry else None})

    def audit(self, journal_entries: list[dict]) -> dict:
        """Re-verify every signature and cross-check the linked WERIAM principal_decision entries."""
        ok, msg = self.ledger.verify()
        by_hash = {e["hash"]: e for e in journal_entries}
        bad = []
        for e in self.ledger.entries("signed_decision"):
            p = e["payload"]
            try:
                Ed25519PublicKey.from_public_bytes(unb64(p["pub"])).verify(unb64(p["signature"]), canonical(p["payload"]))
            except (InvalidSignature, ValueError):
                bad.append((e["seq"], "signature")); continue
            w = by_hash.get(p["weriam_hash"]) if p["weriam_hash"] else None
            if p["weriam_hash"] and (w is None or w["payload"]["request_id"] != p["payload"]["request_id"]):
                bad.append((e["seq"], "weriam link"))
        return {"ok": ok and not bad, "chain": msg, "signed": len(self.ledger.entries("signed_decision")), "bad": bad}


def dev_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Test/CLI helper: a fresh key and its raw public key (b64)."""
    k = Ed25519PrivateKey.generate()
    return k, b64(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def sign(k: Ed25519PrivateKey, payload: dict) -> str:
    return b64(k.sign(canonical(payload)))
