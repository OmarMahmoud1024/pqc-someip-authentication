"""
dashboard_client.py -- R3 version

Unchanged in behavior from R2's dashboard_client.py: it does not need to know anything
about PQ-Signature verification, because that gate now lives in secure_daemon.py. The
Dashboard only ever gets subscribed to whichever endpoint the daemon (now gated) hands
it -- if the gate is working, that's never the attacker's endpoint. Only the log
filename changed (R2_DATA.txt -> R3_DATA.txt) so R2 and R3 results don't overwrite
each other.
"""

import asyncio
import time
import sys
from someipy import ServiceBuilder, connect_to_someipy_daemon, ClientServiceInstance, EventGroup, Event, TransportLayerProtocol

mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
attack_delay = sys.argv[2] if len(sys.argv) > 2 else "100"
# Optional 3rd arg overrides how many frames to sample in "attack" mode (default matches
# R2's methodology of 10000; a smaller number is useful for quick smoke tests).
frames_override = int(sys.argv[3]) if len(sys.argv) > 3 else None

async def start_dashboard_client():
    someipy_daemon = await connect_to_someipy_daemon()
    service_id = 0x1234

    video_event = Event(id=0x8000, protocol=TransportLayerProtocol.UDP)
    video_eventgroup = EventGroup(id=0x4000, events=[video_event])
    service = ServiceBuilder().with_service_id(service_id).with_major_version(1).with_eventgroup(video_eventgroup).build()

    dashboard_client = ClientServiceInstance(daemon=someipy_daemon, service=service, instance_id=0x0001, endpoint_ip="127.0.0.1", endpoint_port=30510)

    start_time = time.time()
    completion_event = asyncio.Event()

    frame_count = 0
    good_frames = 0
    bad_frames = 0

    TOTAL_FRAMES = frames_override if frames_override else 10000

    def on_video_frame_received(event_id: int, payload: bytes) -> None:
        nonlocal frame_count, good_frames, bad_frames

        if mode == "baseline":
            latency = (time.time() - start_time) * 1000
            with open("R3_DATA.txt", "a") as f:
                f.write(f"Baseline Latency: {latency:.2f} ms\n")
            print(f"[*] Baseline Logged: {latency:.2f} ms")
            completion_event.set()

        elif mode == "attack":
            frame_count += 1
            if b'VIDEO_FRAME' in payload:
                good_frames += 1
            else:
                bad_frames += 1

            if frame_count >= TOTAL_FRAMES:
                ratio = (bad_frames / TOTAL_FRAMES) * 100
                with open("R3_DATA.txt", "a") as f:
                    f.write(f"Attack (Delay {attack_delay}ms) -> Good: {good_frames}, Malware: {bad_frames} | Malware Ratio: {ratio:.1f}%\n")
                print(f"[*] Attack Logged: {ratio:.1f}% Malware")
                completion_event.set()

    dashboard_client.register_callback(on_video_frame_received)
    dashboard_client.subscribe_eventgroup(video_eventgroup, 5)

    await completion_event.wait()
    await someipy_daemon.disconnect_from_daemon()

if __name__ == "__main__":
    asyncio.run(start_dashboard_client())
