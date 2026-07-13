"""
setup_keys.py

Run this ONCE before the R3 experiments (mirrors design doc §10: keys are provisioned
out of band, at "manufacturing time", not sent over SOME/IP-SD).

Generates one Falcon-512 keypair for the Camera ECU (service_id 0x1234):
  - camera_falcon_sk.bin  -> the Camera's secret key (only camera_service.py reads this)
  - trust_store.json      -> service_id -> public_key, read by secure_daemon.py

If you later add a real backup camera / second signer for the failover test, generate a
second keypair the same way and register it under the same service_id with a distinct
instance_id if your trust-store design needs per-instance keys (this testbed uses one key
per service_id, which is enough for the R2/R3 experiments -- see README_R3.md).
"""

from pq_crypto import generate_keypair
from trust_store import TrustStore

SERVICE_ID_CAMERA = 0x1234

CAMERA_SK_FILENAME = "camera_falcon_sk.bin"
CAMERA_PK_FILENAME = "camera_falcon_pk.bin"  # kept for reference / inspection only


def main():
    public_key, secret_key = generate_keypair()

    with open(CAMERA_SK_FILENAME, "wb") as f:
        f.write(secret_key)
    with open(CAMERA_PK_FILENAME, "wb") as f:
        f.write(public_key)

    store = TrustStore()
    store.register(SERVICE_ID_CAMERA, public_key)
    store.save()

    print(f"[*] Generated Falcon-512 keypair for service 0x{SERVICE_ID_CAMERA:04x}")
    print(f"[*] Public key size: {len(public_key)} bytes, secret key size: {len(secret_key)} bytes")
    print(f"[*] Wrote {CAMERA_SK_FILENAME}, {CAMERA_PK_FILENAME}, trust_store.json")


if __name__ == "__main__":
    main()
