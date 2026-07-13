"""
final_validation_run.py -- validation-only driver (not part of the deliverable).
Mirrors run_r3_experiments.py's actual experiment structure (10 baseline runs, then
flood attacks at 3 delays, then substitution attacks at 2 delays) but writes to
R3_DATA_FINAL.txt and uses a smaller per-attack frame count so it completes within this
sandbox's constraints. This is the run whose numbers get quoted back to the user.
"""
import subprocess
import time
import os

DATA_FILE = "R3_DATA_FINAL.txt"
FRAMES = "150"


def clean():
    os.system("pkill -9 -f someipyd 2>/dev/null")
    os.system("pkill -9 -f secure_daemon 2>/dev/null")
    os.system("pkill -9 -f camera_service 2>/dev/null")
    os.system("pkill -9 -f attacker_service 2>/dev/null")
    if os.path.exists("/tmp/someipyd.sock"):
        os.remove("/tmp/someipyd.sock")
    time.sleep(1)


def start_daemon_and_camera():
    clean()
    daemon_proc = subprocess.Popen(
        ["python3", "-u", "secure_daemon.py"],
        stdout=open("final_daemon.log", "a"), stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    camera_proc = subprocess.Popen(
        ["python3", "-u", "camera_service.py"],
        stdout=open("final_camera.log", "a"), stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    return daemon_proc, camera_proc


def stop(*procs):
    for p in procs:
        p.kill()
    for p in procs:
        try:
            p.wait(timeout=5)
        except Exception:
            pass


with open(DATA_FILE, "w") as f:
    f.write("=== MASTER'S THESIS R3 VALIDATED DATA (AUTHENTICATED GATEWAY) ===\n\n")

# EXP 1: baseline latency, 10 runs, authenticated gateway
daemon_proc, camera_proc = start_daemon_and_camera()
with open(DATA_FILE, "a") as f:
    f.write("--- EXP 1: BASELINE LATENCY, AUTHENTICATED (10 RUNS) ---\n")
print("Running 10 baseline latency samples...", flush=True)
for i in range(10):
    result = subprocess.run(
        ["python3", "-u", "dashboard_client.py", "baseline"],
        capture_output=True, text=True, timeout=10,
    )
    for line in result.stdout.splitlines():
        if "Baseline Latency" in line:
            with open(DATA_FILE, "a") as f:
                f.write(line.strip() + "\n")
    time.sleep(0.3)
stop(daemon_proc, camera_proc)

# EXP 2: flood hijack at three delays
with open(DATA_FILE, "a") as f:
    f.write("\n--- EXP 2: FLOOD HIJACK vs AUTHENTICATED GATEWAY ---\n")
for delay in [1000, 100, 10]:
    daemon_proc, camera_proc = start_daemon_and_camera()
    attacker_proc = subprocess.Popen(
        ["python3", "-u", "attacker_service.py", "flood", str(delay)],
        stdout=open("final_attacker.log", "a"), stderr=subprocess.STDOUT,
    )
    time.sleep(1)
    print(f"Running flood attack, delay={delay}ms...", flush=True)
    try:
        result = subprocess.run(
            ["python3", "-u", "dashboard_client.py", "attack", str(delay), FRAMES],
            capture_output=True, text=True, timeout=25,
        )
        for line in result.stdout.splitlines():
            if "Attack (" in line:
                with open(DATA_FILE, "a") as f:
                    f.write(line.strip() + "\n")
    except subprocess.TimeoutExpired:
        with open(DATA_FILE, "a") as f:
            f.write(f"Attack (Delay {delay}ms) -> TIMED OUT\n")
    stop(attacker_proc, camera_proc, daemon_proc)

# EXP 3: endpoint-substitution replay at two delays
with open(DATA_FILE, "a") as f:
    f.write("\n--- EXP 3: ENDPOINT-SUBSTITUTION REPLAY vs AUTHENTICATED GATEWAY ---\n")
for delay in [100, 10]:
    daemon_proc, camera_proc = start_daemon_and_camera()
    attacker_proc = subprocess.Popen(
        ["python3", "-u", "attacker_service.py", "substitution", str(delay)],
        stdout=open("final_attacker.log", "a"), stderr=subprocess.STDOUT,
    )
    time.sleep(1)
    print(f"Running substitution attack, delay={delay}ms...", flush=True)
    try:
        result = subprocess.run(
            ["python3", "-u", "dashboard_client.py", "attack", str(delay), FRAMES],
            capture_output=True, text=True, timeout=25,
        )
        for line in result.stdout.splitlines():
            if "Attack (" in line:
                with open(DATA_FILE, "a") as f:
                    f.write(line.strip() + "\n")
    except subprocess.TimeoutExpired:
        with open(DATA_FILE, "a") as f:
            f.write(f"Attack (Delay {delay}ms) -> TIMED OUT\n")
    stop(attacker_proc, camera_proc, daemon_proc)

clean()
print("FINAL VALIDATION RUN DONE", flush=True)
with open(DATA_FILE) as f:
    print(f.read(), flush=True)
