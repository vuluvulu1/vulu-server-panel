"""Release imzasının doğrulanması (ECDSA P-256 + SHA-256).

Panel güncellemeleri vulu'nun release anahtarıyla imzalanır (vulu Launcher'la aynı anahtar). İmza,
.NET'in varsayılan biçimindedir: r || s, her biri 32 bayt. Doğrulama yalnızca açık veriyle yapıldığı için
saf Python yeterli; ek paket gerekmez."""
import base64
import hashlib

# vulu release açık anahtarı (SubjectPublicKeyInfo, base64). vulu-launcher'daki Shared/Releases.cs ile aynı.
RELEASE_PUBLIC_KEY = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE3TeeU2nXv6fbTkri3BObKy19SbNBbWMMqC+D7e4JSDC8jiGZU62lz7Nvk1tZcKSQAh3Bx08rEv7wBW4XbTrxzQ=="

# NIST P-256
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
_SPKI_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0] and (p[1] + q[1]) % _P == 0:
        return None
    if p == q:
        lam = (3 * p[0] * p[0] + _A) * pow(2 * p[1], -1, _P) % _P
    else:
        lam = (q[1] - p[1]) * pow(q[0] - p[0], -1, _P) % _P
    x = (lam * lam - p[0] - q[0]) % _P
    return x, (lam * (p[0] - x) - p[1]) % _P


def _mul(k, p):
    out = None
    while k:
        if k & 1:
            out = _add(out, p)
        p = _add(p, p)
        k >>= 1
    return out


def _public_point(spki_b64: str):
    der = base64.b64decode(spki_b64)
    if len(der) != len(_SPKI_PREFIX) + 65 or not der.startswith(_SPKI_PREFIX) or der[len(_SPKI_PREFIX)] != 4:
        raise ValueError("unsupported public key")
    raw = der[len(_SPKI_PREFIX) + 1:]
    q = int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    if (q[1] * q[1] - (q[0] ** 3 + _A * q[0] + _B)) % _P:
        raise ValueError("point not on curve")
    return q


def verify(data: bytes, signature_b64: str, public_key_b64: str = RELEASE_PUBLIC_KEY) -> bool:
    """data'nın imzası geçerliyse True."""
    try:
        sig = base64.b64decode(signature_b64.strip(), validate=True)
        q = _public_point(public_key_b64)
    except (ValueError, TypeError):
        return False
    if len(sig) != 64:
        return False
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    e = int.from_bytes(hashlib.sha256(data).digest(), "big")
    w = pow(s, -1, _N)
    point = _add(_mul(e * w % _N, _G), _mul(r * w % _N, q))
    return point is not None and point[0] % _N == r
