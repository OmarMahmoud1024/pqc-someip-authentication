"""
secure_daemon.py

Implements the someipyd integration and the verification / trust store /
Last-Valid-In-Wins gate described in the R3 design document.

WHY THIS FILE EXISTS INSTEAD OF PATCHING someipy DIRECTLY:
Investigating the installed someipy 2.1.2 package showed that the actual periodic
OfferService broadcast is built and re-sent BY THE DAEMON ITSELF on a timer
(SomeipDaemon.offer_timer_callback -> create_offer_service_message), not by
camera_service.py. someipy also has its own closed set of SD Option types
(SdOptionOnWireType in _sd/deserialization/sd_deserialization.py) that does not know
about a new option type 0x50 -- teaching it to survive an unrecognized option safely
and to serialize a brand new option type on the *send* side would mean patching the
enum, the (de)serializer, and OfferServiceEntry across several internal files, all of
it inside a third-party package.

Instead, this file:
  1. Runs a second, independent multicast listener (companion_auth_listener) that
     receives our own "PQ-Auth" companion datagrams (pq_crypto.CompanionAuthMessage,
     sent by camera_service.py) on the SAME multicast group someipyd already listens
     on (224.224.224.245:30490), verifies the Falcon-512 signature, and if valid AND
     the Counter is fresh (Last-Valid-In-Wins, design doc §7), records the endpoint
     that companion message vouches for.
  2. Monkeypatches SomeipDaemon.datagram_received_mcast (the real daemon's own
     entry point for every incoming SD packet) so that, for any OfferService entry
     whose Service ID is in our trust store, the entry is only allowed through to the
     real daemon's routing logic (which is what actually redirects the Dashboard's
     subscription -- see design doc §8/§9) if its endpoint matches the one most
     recently vouched for by a valid companion message. Unknown/untrusted endpoints
     are dropped before they ever reach _handle_offered_service, i.e. before the
     Dashboard can be told to subscribe to them.

This still enforces every property from the design document (endpoint binding closes
the substitution gap in §6, the counter check gives Last-Valid-In-Wins in §7) --
what changed is the wire mechanics (a correlated companion datagram instead of a
single datagram with an embedded TLV option), which is called out explicitly in
README_R3.md as a pragmatic implementation choice, not a change in the security
properties being tested.

Run this INSTEAD OF the bare `someipyd` command:
    python3 secure_daemon.py
"""

import asyncio
import logging
import socket
import sys

import someipy.someipyd as _daemon_mod
from someipy._internal.utils import create_rcv_multicast_socket

from pq_crypto import CompanionAuthMessage, verify_companion_message
from trust_store import TrustStore

SD_ADDRESS = "224.224.224.245"
SD_PORT = 30490
INTERFACE = "127.0.0.1"

logger = logging.getLogger("secure_daemon")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TRUST_STORE = TrustStore.load()


# ---------------------------------------------------------------------------
# 1. Companion PQ-Auth listener
# ---------------------------------------------------------------------------
class CompanionAuthProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        if not data.startswith(b"PQA1"):
            return
        try:
            msg = CompanionAuthMessage.from_buffer(data)
        except Exception as exc:
            logger.warning(f"Malformed PQ-Auth companion message from {addr}: {exc}")
            return

        public_key = TRUST_STORE.get_public_key(msg.service_id)
        if public_key is None:
            logger.info(
                f"PQ-Auth for unknown/unprotected service 0x{msg.service_id:04x}, ignoring"
            )
            return

        if not verify_companion_message(public_key, msg):
            logger.warning(
                f"REJECTED forged/invalid PQ-Auth for service 0x{msg.service_id:04x} "
                f"instance 0x{msg.instance_id:04x} claiming endpoint "
                f"{msg.endpoint_ip}:{msg.endpoint_port} (signature did not verify)"
            )
            return

        updated = TRUST_STORE.try_update(
            msg.service_id,
            msg.instance_id,
            msg.counter,
            msg.endpoint_ip,
            msg.endpoint_port,
        )
        if updated:
            logger.info(
                f"ACCEPTED PQ-Auth: service 0x{msg.service_id:04x} instance "
                f"0x{msg.instance_id:04x} now trusted at {msg.endpoint_ip}:"
                f"{msg.endpoint_port} (counter={msg.counter})"
            )
        else:
            logger.info(
                f"Stale/replayed PQ-Auth for service 0x{msg.service_id:04x} "
                f"(counter={msg.counter} not newer than last accepted), ignored"
            )


async def start_companion_listener():
    loop = asyncio.get_running_loop()
    sock = create_rcv_multicast_socket(SD_ADDRESS, SD_PORT, INTERFACE)
    await loop.create_datagram_endpoint(lambda: CompanionAuthProtocol(), sock=sock)
    logger.info(
        f"PQ-Auth companion listener joined {SD_ADDRESS}:{SD_PORT} "
        f"(protected services: {list(TRUST_STORE._public_keys.keys())})"
    )


# ---------------------------------------------------------------------------
# 2. Monkeypatch the daemon's own multicast handler to gate on trusted endpoints
# ---------------------------------------------------------------------------
_original_datagram_received_mcast = _daemon_mod.SomeipDaemon.datagram_received_mcast


def _gated_datagram_received_mcast(self, data: bytes, addr):
    if _daemon_mod.is_sd_message(data):
        try:
            sd_message = _daemon_mod.deserialize_sd_message(
                data, addr[0], addr[1], multicast=True
            )
            for entry in sd_message.entries:
                if not isinstance(entry, _daemon_mod.OfferServiceEntry):
                    continue
                if not TRUST_STORE.is_protected(entry.service_id):
                    continue  # not a protected service: pass through unchanged

                if not entry.ip_v4_endpoints:
                    logger.warning(
                        f"DROPPED OfferService for protected service "
                        f"0x{entry.service_id:04x}: no IPv4 endpoint present"
                    )
                    return

                offered_ip = str(entry.ip_v4_endpoints[0].address)
                offered_port = entry.ip_v4_endpoints[0].port

                trusted = TRUST_STORE.current_trusted_endpoint(
                    entry.service_id, entry.instance_id
                )
                if trusted is None:
                    logger.warning(
                        f"DROPPED OfferService for protected service "
                        f"0x{entry.service_id:04x} claiming {offered_ip}:{offered_port}: "
                        f"no valid PQ-Auth has been seen yet for this service "
                        f"(default-deny, design doc §12 downgrade-attack defense)"
                    )
                    return

                if (offered_ip, offered_port) != trusted:
                    logger.warning(
                        f"DROPPED OfferService for protected service "
                        f"0x{entry.service_id:04x}: claims endpoint "
                        f"{offered_ip}:{offered_port} but the currently trusted "
                        f"endpoint (per valid PQ-Auth) is {trusted[0]}:{trusted[1]} "
                        f"-- this is exactly the endpoint-substitution/forgery attack "
                        f"design doc §6 closes"
                    )
                    return
        except Exception as exc:
            logger.debug(f"Gate check could not parse incoming SD message: {exc}")
            # Fall through to original handling rather than breaking unrelated traffic.

    return _original_datagram_received_mcast(self, data, addr)


_daemon_mod.SomeipDaemon.datagram_received_mcast = _gated_datagram_received_mcast


# ---------------------------------------------------------------------------
# 2b. IMPORTANT DISCOVERY while testing this against the real daemon: gating
# datagram_received_mcast alone is NOT sufficient. someipy's _handle_send_event_request
# forwards an event to every current subscriber of a (service_id, instance_id,
# eventgroup_id) the moment ANY locally-connected UDS client calls send_event() for it
# -- it never checks whether that client's claimed src_endpoint_ip/src_endpoint_port is
# the one currently trusted for that service. In other words: in someipy 2.1.2, a rogue
# ECU can inject events straight to existing subscribers over the daemon's local UDS
# API without ever having its OfferService accepted into the routing table at all. This
# is a different vulnerability than the SD-spoofing one R1/R2 analyzed, but it is the
# one that actually delivers R2's "malicious frame" payload to the Dashboard -- so the
# gate on datagram_received_mcast has to be paired with a gate here too.
# ---------------------------------------------------------------------------
_original_handle_send_event_request = _daemon_mod.SomeipDaemon._handle_send_event_request


def _gated_handle_send_event_request(self, message, writer_id: int):
    service_id = message.get("service_id")
    instance_id = message.get("instance_id")
    if TRUST_STORE.is_protected(service_id):
        trusted = TRUST_STORE.current_trusted_endpoint(service_id, instance_id)
        claimed = (message.get("src_endpoint_ip"), message.get("src_endpoint_port"))
        if trusted is None or claimed != trusted:
            logger.warning(
                f"DROPPED SendEventRequest for protected service 0x{service_id:04x}: "
                f"claims src endpoint {claimed} but the currently trusted endpoint is "
                f"{trusted} -- this is the actual payload-delivery path for the R2 "
                f"hijack in someipy 2.1.2's UDS event forwarding, not the SD Options"
            )
            return
    return _original_handle_send_event_request(self, message, writer_id)


_daemon_mod.SomeipDaemon._handle_send_event_request = _gated_handle_send_event_request


# ---------------------------------------------------------------------------
# 3. Also start the companion listener alongside the daemon's own SD listening
# ---------------------------------------------------------------------------
_original_start_sd_listening = _daemon_mod.SomeipDaemon.start_sd_listening


async def _start_sd_listening_with_companion(self):
    await _original_start_sd_listening(self)
    await start_companion_listener()


_daemon_mod.SomeipDaemon.start_sd_listening = _start_sd_listening_with_companion


if __name__ == "__main__":
    logger.info(
        f"Starting secure someipyd (PQ-Signature gating enabled) for services: "
        f"{[hex(s) for s in TRUST_STORE._public_keys.keys()]}"
    )
    sys.argv = [sys.argv[0]]  # someipyd's argparse doesn't expect our own args
    _daemon_mod.main()
