"""
trust_store.py

The trust store (Service ID -> public key,
design doc §10) plus the "Last-Valid-In-Wins" state (design doc §7): the highest Counter
seen so far in a *validly signed* message per (service_id, instance_id), and the endpoint
that counter was bound to.

Public keys are provisioned out of band (a local JSON file here, standing in for R3's
"primary model": manufacturing-time provisioning, design doc §10) -- never sent over the
SOME/IP-SD multicast group itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

TRUST_STORE_FILENAME = "trust_store.json"


@dataclass
class LastValidState:
    counter: int
    endpoint_ip: str
    endpoint_port: int


class TrustStore:
    """service_id -> public_key (bytes), plus the Last-Valid-In-Wins tracking state."""

    def __init__(self):
        self._public_keys: Dict[int, bytes] = {}
        self._last_valid: Dict[Tuple[int, int], LastValidState] = {}

    # -- provisioning (out of band, at "manufacturing time") -----------------
    def register(self, service_id: int, public_key: bytes) -> None:
        self._public_keys[service_id] = public_key

    def get_public_key(self, service_id: int) -> Optional[bytes]:
        return self._public_keys.get(service_id)

    def is_protected(self, service_id: int) -> bool:
        return service_id in self._public_keys

    # -- Last-Valid-In-Wins (design doc §7) -----------------------------------
    def current_trusted_endpoint(
        self, service_id: int, instance_id: int
    ) -> Optional[Tuple[str, int]]:
        state = self._last_valid.get((service_id, instance_id))
        if state is None:
            return None
        return (state.endpoint_ip, state.endpoint_port)

    def try_update(
        self,
        service_id: int,
        instance_id: int,
        counter: int,
        endpoint_ip: str,
        endpoint_port: int,
    ) -> bool:
        """Only updates (and returns True) if counter is strictly greater than the last
        accepted counter for this (service_id, instance_id) -- this is what turns a stale
        replay of an old-but-validly-signed message into a no-op instead of a downgrade."""
        key = (service_id, instance_id)
        current = self._last_valid.get(key)
        if current is not None and counter <= current.counter:
            return False
        self._last_valid[key] = LastValidState(
            counter=counter, endpoint_ip=endpoint_ip, endpoint_port=endpoint_port
        )
        return True

    # -- persistence -----------------------------------------------------------
    def save(self, path: str = TRUST_STORE_FILENAME) -> None:
        data = {
            str(service_id): public_key.hex()
            for service_id, public_key in self._public_keys.items()
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str = TRUST_STORE_FILENAME) -> "TrustStore":
        store = cls()
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            for service_id_str, public_key_hex in data.items():
                store.register(int(service_id_str), bytes.fromhex(public_key_hex))
        return store
