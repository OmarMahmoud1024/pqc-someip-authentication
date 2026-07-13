"""
camera_service.py -- R3 version (modified from the R2 script)

Changes from R2:
  - Loads the Camera's Falcon-512 secret key (generated once by setup_keys.py) and, at
    boot, signs its own (ServiceID, InstanceID, MajorVersion, TTL, Endpoint IP, Endpoint
    Port, Counter) scope exactly once (design doc §8/§11: "sign-once-per-boot-session" --
    the expensive signing operation is amortized across the whole session instead of
    being redone on every 10ms cyclic frame).
  - Broadcasts that single signed "PQ-Auth" companion message directly onto the SD
    multicast group a few times at startup (mirroring the real SD Initial
    Wait/Repetition burst), so secure_daemon.py's companion listener can pick it up and
    vouch for this camera's endpoint before its normal OfferService broadcasts arrive,
    and then keeps re-transmitting that SAME already-signed message every couple of
    seconds for as long as the camera runs. This does not re-sign anything (still one
    Falcon-512 signing operation per boot session, per §11) -- it only re-announces the
    existing signed blob, the same way the real OfferService itself is re-broadcast
    every cyclic_offer_delay_ms without recomputing anything. This matters in practice:
    without a periodic re-announcement, a verifier (or, as tested here, an attacker)
    that wasn't already listening at the exact moment of the initial boot burst would
    never see a companion message at all.
  - Everything else (the actual SOME/IP service, event loop, video frame cadence) is
    byte-for-byte the same as R2's camera_service.py.
"""

import asyncio
import socket
import time

from someipy import ServiceBuilder, connect_to_someipy_daemon, ServerServiceInstance, EventGroup, Event, TransportLayerProtocol

from pq_crypto import build_and_sign_companion_message

SERVICE_ID = 0x1234
INSTANCE_ID = 0x0001
MAJOR_VERSION = 1
TTL = 5
ENDPOINT_IP = "127.0.0.1"
ENDPOINT_PORT = 30509

SD_ADDRESS = "224.224.224.245"
SD_PORT = 30490

CAMERA_SK_FILENAME = "camera_falcon_sk.bin"


def load_secret_key() -> bytes:
    with open(CAMERA_SK_FILENAME, "rb") as f:
        return f.read()


def broadcast_companion_auth(payload: bytes, repeats: int = 5, spacing_s: float = 0.05):
    """Sends the signed PQ-Auth companion datagram directly onto the SD multicast
    group a few times, mirroring the real Initial Wait/Repetition burst so the
    message survives the occasional dropped multicast packet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    # Explicitly select the outgoing interface for the multicast send. Without this,
    # environments with no default route configured (some sandboxes/minimal containers
    # -- loopback-only networking) fail with "OSError: Network is unreachable" even
    # though the multicast group itself is on loopback.
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ENDPOINT_IP))
    for _ in range(repeats):
        sock.sendto(payload, (SD_ADDRESS, SD_PORT))
        time.sleep(spacing_s)
    sock.close()


async def start_camera_service():
    print("[*] Connecting to the vehicle SOME/IP Gateway (Daemon)...")
    someipy_daemon = await connect_to_someipy_daemon()

    service_id = SERVICE_ID
    instance_id = INSTANCE_ID

    # 1. Define the "Video Feed" Event
    video_event = Event(id=0x8000, protocol=TransportLayerProtocol.UDP)
    video_eventgroup = EventGroup(id=0x4000, events=[video_event])

    service = (
        ServiceBuilder()
        .with_service_id(service_id)
        .with_major_version(MAJOR_VERSION)
        .with_eventgroup(video_eventgroup) # Attach the video feed to the service
        .build()
    )

    camera_service = ServerServiceInstance(
        daemon=someipy_daemon,
        service=service,
        instance_id=instance_id,
        endpoint_ip=ENDPOINT_IP,
        endpoint_port=ENDPOINT_PORT,
        ttl=TTL,
        cyclic_offer_delay_ms=1000
    )

    # --- R3 addition: sign once per boot session, then broadcast the companion
    # PQ-Auth message before/alongside the real (unauthenticated-at-the-option-level)
    # OfferService broadcasts start. Wall-clock seconds is used as the Counter: it is
    # naturally monotonic across both cyclic broadcasts and daemon/camera restarts,
    # which is what Last-Valid-In-Wins (design doc §7) needs.
    secret_key = load_secret_key()
    counter = int(time.time())
    companion_msg = build_and_sign_companion_message(
        secret_key=secret_key,
        service_id=service_id,
        instance_id=instance_id,
        major_version=MAJOR_VERSION,
        ttl=TTL,
        endpoint_ip=ENDPOINT_IP,
        endpoint_port=ENDPOINT_PORT,
        counter=counter,
    )
    print(
        f"[*] Signed PQ-Auth companion message (Falcon-512, counter={counter}, "
        f"signature {len(companion_msg.option.signature)} bytes, option "
        f"{companion_msg.option.on_wire_size} bytes on the wire). Broadcasting..."
    )
    broadcast_companion_auth(companion_msg.to_buffer())

    async def periodic_companion_reannounce(payload: bytes, interval_s: float = 2.0):
        # Re-transmits the same already-signed companion message on a timer. No new
        # signature is ever computed here -- see the module docstring.
        while True:
            await asyncio.sleep(interval_s)
            broadcast_companion_auth(payload, repeats=1, spacing_s=0.0)

    reannounce_task = asyncio.create_task(
        periodic_companion_reannounce(companion_msg.to_buffer())
    )

    print(f"[*] Camera ECU starting... Offering Service {hex(service_id)}")
    await camera_service.start_offer()

    try:
        # Loop: Send a "Video Frame" every 10 milliseconds
        while True:
            await asyncio.sleep(0.01)
            camera_service.send_event(0x4000, 0x8000, b'VIDEO_FRAME')
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        reannounce_task.cancel()
        print("\n[*] Shutting down Camera service.")
        await camera_service.stop_offer()
        await someipy_daemon.disconnect_from_daemon()

if __name__ == "__main__":
    try:
        asyncio.run(start_camera_service())
    except KeyboardInterrupt:
        pass
