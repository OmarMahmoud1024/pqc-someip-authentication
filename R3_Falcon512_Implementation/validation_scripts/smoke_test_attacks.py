"""
smoke_test_attacks.py -- validation-only driver (not part of the deliverable).
Runs the flood attack and the substitution attack against the secure daemon, each with
a short frame count (via dashboard_client.py's optional 3rd arg) so this finishes fast.
"""
import subprocess
import sys
import time
import os

FRAMES = "80"  # small number so a smoke test finishes quickly; real runs use 10000


def clean():
    os.system("pkill -9 -f someipyd 2>/dev/null")
    os.system("pkill -9 -f secure_daemon 2>/dev/null")
    os.system("pkill -9 -f camera_service 2>/dev/null")
    os.system("pkill -9 -f attacker_service 2>/dev/null")
    if os.path.exists("/tmp/someipyd.sock"):
        os.remove("/tmp/someipyd.sock")
    time.sleep(1)


def run_attack(mode, delay="50"):
    clean()
    print(f"\n########## ATTACK MODE = {mode} ##########", flush=True)
    daemon_log = open(f"secure_daemon_{mode}.log", "w")
    daemon_proc = subprocess.Popen(["python3", "-u", "secure_daemon.py"], stdout=daemon_log, stderr=subprocess.STDOUT)
    time.sleep(2)

    camera_log = open(f"camera_{mode}.log", "w")
    camera_proc = subprocess.Popen(["python3", "-u", "camera_service.py"], stdout=camera_log, stderr=subprocess.STDOUT)
    time.sleep(2)

    attacker_log = open(f"attacker_{mode}.log", "w")
    attacker_proc = subprocess.Popen(
        ["python3", "-u", "attacker_service.py", mode, delay], stdout=attacker_log, stderr=subprocess.STDOUT
    )
    time.sleep(2)

    try:
        result = subprocess.run(
            ["python3", "-u", "dashboard_client.py", "attack", delay, FRAMES],
            capture_output=True, text=True, timeout=20,
        )
        print("dashboard stdout tail:", result.stdout.strip().splitlines()[-3:], flush=True)
    except subprocess.TimeoutExpired:
        print("dashboard TIMED OUT (no attacker frames arriving is actually a GOOD sign here"
              " if 0 malicious frames were the goal, but 80 GOOD frames should still arrive"
              " from the legit camera -- investigate if this times out)", flush=True)

    for p in (attacker_proc, camera_proc, daemon_proc):
        p.kill()
    for p in (attacker_proc, camera_proc, daemon_proc):
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    daemon_log.close(); camera_log.close(); attacker_log.close()

    print(f"--- secure_daemon_{mode}.log (gate decisions) ---", flush=True)
    for line in open(f"secure_daemon_{mode}.log").read().splitlines():
        if "DROPPED" in line or "ACCEPTED" in line or "REJECTED" in line or "Stale" in line:
            print(line, flush=True)


run_attack("flood", "50")
run_attack("substitution", "50")
print("\nSMOKE TEST (ATTACKS) DONE", flush=True)
