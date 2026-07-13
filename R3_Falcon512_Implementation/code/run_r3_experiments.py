"""
run_r3_experiments.py

Track A, Objective 7 of the R3 design document: re-runs the R2 experiments against the
now-authenticated gateway (secure_daemon.py instead of bare someipyd), plus the new
endpoint-substitution attack test. Mirrors R2's auto_lab.py structure so results stay
directly comparable.

Usage:
    python3 setup_keys.py        # once, before the first run
    python3 run_r3_experiments.py
"""

import subprocess
import sys
import time
import os

# Allow overriding the per-attack frame count for quick smoke tests, e.g.:
#   python3 run_r3_experiments.py 200
FRAMES = sys.argv[1] if len(sys.argv) > 1 else None


def clean_environment():
    os.system("pkill -f someipyd")
    os.system("pkill -f secure_daemon.py")
    os.system("pkill -f camera_service.py")
    os.system("pkill -f attacker_service.py")
    os.system("pkill -f dashboard_client.py")
    time.sleep(1)


def dashboard_args(mode, delay=None):
    args = ["python3", "dashboard_client.py", mode]
    if delay is not None:
        args.append(str(delay))
    if FRAMES:
        if delay is None:
            args.append("100")  # placeholder positional, unused in baseline mode
        args.append(FRAMES)
    return args


print("=== STARTING AUTOMATED R3 LAB (AUTHENTICATED SOME/IP-SD) ===")

if not os.path.exists("camera_falcon_sk.bin") or not os.path.exists("trust_store.json"):
    print("[!] Run `python3 setup_keys.py` first.")
    sys.exit(1)

with open("R3_DATA.txt", "w") as f:
    f.write("=== MASTER'S THESIS R3 AUTOMATED DATA (AUTHENTICATED GATEWAY) ===\n\n")

# ---------------------------------------------------------------------------
# EXPERIMENT 1: Baseline latency, now with signing + verification in the loop
# ---------------------------------------------------------------------------
clean_environment()
print("\n[*] Booting secure gateway & Camera for Exp 1 (Baseline, authenticated)...")
with open("R3_DATA.txt", "a") as f:
    f.write("--- EXP 1: BASELINE LATENCY, AUTHENTICATED (10 RUNS) ---\n")

subprocess.Popen(["python3", "secure_daemon.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
subprocess.Popen(["python3", "camera_service.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)  # let the PQ-Auth companion burst land before the dashboard subscribes

print("[*] Collecting baseline latency data points...")
for i in range(10):
    subprocess.run(dashboard_args("baseline"))
    time.sleep(0.5)

# ---------------------------------------------------------------------------
# EXPERIMENT 2: Original flood hijack, now against the gated daemon
# ---------------------------------------------------------------------------
clean_environment()
print("\n[*] Booting secure gateway & Camera for Exp 2 (Flood attack, authenticated)...")
with open("R3_DATA.txt", "a") as f:
    f.write("\n--- EXP 2: FLOOD HIJACK vs AUTHENTICATED GATEWAY ---\n")

subprocess.Popen(["python3", "secure_daemon.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
subprocess.Popen(["python3", "camera_service.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)

delays = [1000, 100, 10]
for delay in delays:
    print(f"[*] Simulating FLOOD attack with Spam Delay = {delay}ms...")
    attacker = subprocess.Popen(["python3", "attacker_service.py", "flood", str(delay)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(dashboard_args("attack", delay))
    attacker.terminate()
    time.sleep(1)

# ---------------------------------------------------------------------------
# EXPERIMENT 3: Endpoint-substitution replay attack (design doc §6)
# ---------------------------------------------------------------------------
clean_environment()
print("\n[*] Booting secure gateway & Camera for Exp 3 (Substitution attack, authenticated)...")
with open("R3_DATA.txt", "a") as f:
    f.write("\n--- EXP 3: ENDPOINT-SUBSTITUTION REPLAY vs AUTHENTICATED GATEWAY ---\n")

subprocess.Popen(["python3", "secure_daemon.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
subprocess.Popen(["python3", "camera_service.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)

for delay in [100, 10]:
    print(f"[*] Simulating SUBSTITUTION attack with Spam Delay = {delay}ms...")
    attacker = subprocess.Popen(["python3", "attacker_service.py", "substitution", str(delay)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(dashboard_args("attack", delay))
    attacker.terminate()
    time.sleep(1)

clean_environment()
print("\n=== ALL R3 EXPERIMENTS COMPLETE ===")
print("Check R3_DATA.txt and secure_daemon's console log (ACCEPTED/DROPPED lines) for details.")
