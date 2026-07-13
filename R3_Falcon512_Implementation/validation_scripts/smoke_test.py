"""
smoke_test.py -- validation-only driver (not part of the deliverable).

Runs the secure daemon, camera, and one dashboard baseline check as three asyncio tasks
inside a SINGLE process/event loop (rather than three OS processes), purely so this can
be exercised inside a sandboxed shell that does not tolerate detached background
processes. The real deliverable (run_r3_experiments.py) still uses separate processes,
matching R2's own auto_lab.py structure, since that's how the student's own machine
will run it.
"""
import asyncio
import time

import secure_daemon as sd  # noqa: F401 (import applies the monkeypatches + starts nothing yet)
from someipy import ServiceBuilder, connect_to_someipy_daemon, ServerServiceInstance, ClientServiceInstance, EventGroup, Event, TransportLayerProtocol
from pq_crypto import build_and_sign_companion_message
import socket

SERVICE_ID = 0x1234
INSTANCE_ID = 0x0001


async def run_camera():
    daemon = await connect_to_someipy_daemon()
    video_event = Event(id=0x8000, protocol=TransportLayerProtocol.UDP)
    video_eventgroup = EventGroup(id=0x4000, events=[video_event])
    service = ServiceBuilder().with_service_id(SERVICE_ID).with_major_version(1).with_eventgroup(video_eventgroup).build()
    camera_service = ServerServiceInstance(
        daemon=daemon, service=service, instance_id=INSTANCE_ID,
        endpoint_ip="127.0.0.1", endpoint_port=30509, ttl=5, cyclic_offer_delay_ms=1000,
    )

    with open("camera_falcon_sk.bin", "rb") as f:
        secret_key = f.read()
    counter = int(time.time())
    companion_msg = build_and_sign_companion_message(
        secret_key, SERVICE_ID, INSTANCE_ID, 1, 5, "127.0.0.1", 30509, counter
    )
    print(f"[camera] signed companion message, sig={len(companion_msg.option.signature)}B, counter={counter}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    for _ in range(5):
        sock.sendto(companion_msg.to_buffer(), ("224.224.224.245", 30490))
        await asyncio.sleep(0.05)
    sock.close()

    print("[camera] starting offer")
    await camera_service.start_offer()

    for _ in range(300):
        await asyncio.sleep(0.01)
        camera_service.send_event(0x4000, 0x8000, b"VIDEO_FRAME")


async def run_dashboard_baseline():
    daemon = await connect_to_someipy_daemon()
    video_event = Event(id=0x8000, protocol=TransportLayerProtocol.UDP)
    video_eventgroup = EventGroup(id=0x4000, events=[video_event])
    service = ServiceBuilder().with_service_id(SERVICE_ID).with_major_version(1).with_eventgroup(video_eventgroup).build()
    client = ClientServiceInstance(daemon=daemon, service=service, instance_id=INSTANCE_ID, endpoint_ip="127.0.0.1", endpoint_port=30510)

    start_time = time.time()
    done = asyncio.Event()
    result = {}

    def on_frame(event_id, payload):
        if not done.is_set():
            result["latency_ms"] = (time.time() - start_time) * 1000
            result["payload"] = payload
            done.set()

    client.register_callback(on_frame)
    client.subscribe_eventgroup(video_eventgroup, 5)

    try:
        await asyncio.wait_for(done.wait(), timeout=10)
        print(f"[dashboard] got frame {result['payload']} after {result['latency_ms']:.2f} ms")
    except asyncio.TimeoutError:
        print("[dashboard] TIMED OUT waiting for a frame")


async def main():
    daemon_task = asyncio.create_task(sd._daemon_mod.async_main())
    await asyncio.sleep(2)
    camera_task = asyncio.create_task(run_camera())
    await asyncio.sleep(2)
    await run_dashboard_baseline()
    await asyncio.sleep(0.5)
    camera_task.cancel()
    daemon_task.cancel()
    try:
        await camera_task
    except asyncio.CancelledError:
        pass
    try:
        await daemon_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
