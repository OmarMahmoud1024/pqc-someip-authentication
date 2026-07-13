"""
pq_crypto.py

Track A, Objectives 1-2 of the R3 design document:
  - The PQ-Signature Option TLV format (Length + Type 0x50 + Reserved + AlgID + Signature),
    kept faithful to the design document even though the current testbed transports it as a
    companion datagram rather than literally inside someipy's native SD Options Array
    (see secure_daemon.py / camera_service.py for why, and README_R3.md for the full explanation).
  - The canonical "signed scope" byte encoding: ServiceID, InstanceID, MajorVersion, TTL,
    Endpoint IP, Endpoint Port, Counter (Section 6/7 of the design doc). This is the exact
    byte string that gets Falcon-512 signed and later re-derived+verified. Signer and verifier
    MUST build this identically or nothing will ever verify.

IMPORTANT BUG FOUND IN EXISTING R2 CODE:
  pqcrypto's verify() signature is verify(public_key, message, signature) -- NOT
  verify(public_key, signature, message). crypto_test.py and pqc_benchmark.py from R2 both
  call verify(public_key, signature, message), which silently returns False on every call
  (it does not raise -- it just always fails). This means the "verify" timings reported in
  the R1/R2 material were timing an always-failing call, not a genuine verification. This
  module uses the correct argument order throughout. Worth fixing in the R2 scripts too.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass

from pqcrypto.sign.falcon_512 import generate_keypair as _falcon_generate_keypair
from pqcrypto.sign.falcon_512 import sign as _falcon_sign
from pqcrypto.sign.falcon_512 import verify as _falcon_verify

# ---------------------------------------------------------------------------
# Algorithm identifiers (AlgID field of the PQ-Signature Option, design doc §5)
# ---------------------------------------------------------------------------
ALG_ID_FALCON_512 = 0x01

# Project-local SOME/IP-SD option type for the (not-yet-embedded) PQ-Signature Option.
# See design doc §5.1 -- not officially reserved by AUTOSAR, documented here as a
# project-local convention.
PQ_SIGNATURE_OPTION_TYPE = 0x50

# Magic bytes identifying our companion "PQ-Auth" datagram on the wire (see
# secure_daemon.py). Chosen so it can never collide with a real SOME/IP header: a real
# SOME/IP message's first two bytes are a Service ID, and 0xFFFF/SD's Method ID is 0x8100;
# "PQA1" as raw bytes does not parse as a plausible SOME/IP header and is rejected by
# someipy's own is_sd_message() check, so the daemon harmlessly ignores it by default.
COMPANION_MAGIC = b"PQA1"


# ---------------------------------------------------------------------------
# Falcon-512 wrappers (correct argument order)
# ---------------------------------------------------------------------------
def generate_keypair() -> tuple[bytes, bytes]:
    """Returns (public_key, secret_key)."""
    return _falcon_generate_keypair()


def sign(secret_key: bytes, message: bytes) -> bytes:
    return _falcon_sign(secret_key, message)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Correct argument order: (public_key, message, signature)."""
    try:
        return bool(_falcon_verify(public_key, message, signature))
    except Exception:
        # Some pqcrypto backends raise on a malformed/invalid signature instead of
        # returning False. Either way, "not valid" means reject.
        return False


# ---------------------------------------------------------------------------
# Signed scope (design doc §6): the exact bytes that get signed.
# ServiceID(2) + InstanceID(2) + MajorVersion(1) + TTL(3) + IPv4(4) + Port(2) + Counter(4)
# = 18 bytes, all big-endian, matching SOME/IP's own network-byte-order convention.
# ---------------------------------------------------------------------------
def build_signed_scope(
    service_id: int,
    instance_id: int,
    major_version: int,
    ttl: int,
    endpoint_ip: str,
    endpoint_port: int,
    counter: int,
) -> bytes:
    ip_int = int(ipaddress.IPv4Address(endpoint_ip))
    ttl_high = (ttl >> 16) & 0xFF
    ttl_low = ttl & 0xFFFF
    return struct.pack(
        ">HHBBHIHI",
        service_id,
        instance_id,
        major_version,
        ttl_high,
        ttl_low,
        ip_int,
        endpoint_port,
        counter,
    )


# ---------------------------------------------------------------------------
# PQ-Signature Option TLV (design doc §5) -- encode/decode of the option itself,
# independent of how it is transported (embedded option vs. companion datagram).
# Length value = 1 (Reserved, already emitted by the common 4-byte option header) +
# 1 (AlgID) + len(signature), matching the real AUTOSAR/someipy convention where Length
# covers Reserved+payload but not the Type byte (verified against someipy's own
# SdOptionCommon / SD_IPV4ENDPOINT_OPTION_LENGTH_VALUE=9 encoding).
# ---------------------------------------------------------------------------
@dataclass
class PQSignatureOption:
    alg_id: int
    signature: bytes

    def to_buffer(self) -> bytes:
        length_value = 2 + len(self.signature)  # Reserved(1) + AlgID(1) + signature
        reserved_and_discardable = 0x00
        header = struct.pack(
            ">HBB", length_value, PQ_SIGNATURE_OPTION_TYPE, reserved_and_discardable
        )
        return header + struct.pack(">B", self.alg_id) + self.signature

    @classmethod
    def from_buffer(cls, buf: bytes) -> "PQSignatureOption":
        length_value, option_type, _reserved = struct.unpack(">HBB", buf[0:4])
        if option_type != PQ_SIGNATURE_OPTION_TYPE:
            raise ValueError(
                f"Not a PQ-Signature Option (type=0x{option_type:02x})"
            )
        alg_id = buf[4]
        sig_len = length_value - 2
        signature = buf[5 : 5 + sig_len]
        return cls(alg_id=alg_id, signature=signature)

    @property
    def on_wire_size(self) -> int:
        # 2 (Length field) + 1 (Type) + 1 (Reserved) + 1 (AlgID) + signature
        return 5 + len(self.signature)


# ---------------------------------------------------------------------------
# Companion "PQ-Auth" datagram (current testbed transport -- see secure_daemon.py).
# Wire format:
#   MAGIC(4) | ServiceID(2) | InstanceID(2) | MajorVersion(1) | TTL(3) |
#   IPv4(4) | Port(2) | Counter(4) | PQSignatureOption.to_buffer()
# ---------------------------------------------------------------------------
@dataclass
class CompanionAuthMessage:
    service_id: int
    instance_id: int
    major_version: int
    ttl: int
    endpoint_ip: str
    endpoint_port: int
    counter: int
    option: PQSignatureOption

    def signed_scope(self) -> bytes:
        return build_signed_scope(
            self.service_id,
            self.instance_id,
            self.major_version,
            self.ttl,
            self.endpoint_ip,
            self.endpoint_port,
            self.counter,
        )

    def to_buffer(self) -> bytes:
        ip_int = int(ipaddress.IPv4Address(self.endpoint_ip))
        ttl_high = (self.ttl >> 16) & 0xFF
        ttl_low = self.ttl & 0xFFFF
        header = COMPANION_MAGIC + struct.pack(
            ">HHBBHIHI",
            self.service_id,
            self.instance_id,
            self.major_version,
            ttl_high,
            ttl_low,
            ip_int,
            self.endpoint_port,
            self.counter,
        )
        return header + self.option.to_buffer()

    @classmethod
    def from_buffer(cls, buf: bytes) -> "CompanionAuthMessage":
        if buf[0:4] != COMPANION_MAGIC:
            raise ValueError("Not a PQ-Auth companion message")
        (
            service_id,
            instance_id,
            major_version,
            ttl_high,
            ttl_low,
            ip_int,
            port,
            counter,
        ) = struct.unpack(">HHBBHIHI", buf[4:22])
        ttl = (ttl_high << 16) | ttl_low
        ip_str = str(ipaddress.IPv4Address(ip_int))
        option = PQSignatureOption.from_buffer(buf[22:])
        return cls(
            service_id=service_id,
            instance_id=instance_id,
            major_version=major_version,
            ttl=ttl,
            endpoint_ip=ip_str,
            endpoint_port=port,
            counter=counter,
            option=option,
        )


def build_and_sign_companion_message(
    secret_key: bytes,
    service_id: int,
    instance_id: int,
    major_version: int,
    ttl: int,
    endpoint_ip: str,
    endpoint_port: int,
    counter: int,
) -> CompanionAuthMessage:
    scope = build_signed_scope(
        service_id, instance_id, major_version, ttl, endpoint_ip, endpoint_port, counter
    )
    signature = sign(secret_key, scope)
    option = PQSignatureOption(alg_id=ALG_ID_FALCON_512, signature=signature)
    return CompanionAuthMessage(
        service_id=service_id,
        instance_id=instance_id,
        major_version=major_version,
        ttl=ttl,
        endpoint_ip=endpoint_ip,
        endpoint_port=endpoint_port,
        counter=counter,
        option=option,
    )


def verify_companion_message(public_key: bytes, msg: "CompanionAuthMessage") -> bool:
    if msg.option.alg_id != ALG_ID_FALCON_512:
        return False
    return verify(public_key, msg.signed_scope(), msg.option.signature)
