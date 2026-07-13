"""
smoke_test_procs.py -- validation-only driver (not part of the deliverable), subprocess
version. Launches secure_daemon.py and camera_service.py as real child processes via
subprocess.Popen (so this driver process can reliably reap them), runs one dashboard
baseline check via subprocess.run with a timeout, then explicitly kills everything.
"""
import subprocess
import sys
import time
import os

os.system("pkill -9 -f someipyd 2>/dev/null")
os.system("pkill -9 -f secure_daemon 2>/dev/null")
os.system("pkill -9 -f camera_service 2>/dev/null")
if os.path.exists("/tmp/someipyd.sock"):
    os.remove("/tmp/someipyd.sock")
time.sleep(1)

daemon_log = open("secure_daemon.log", "w")
daemon_proc = subprocess.Popen(
    ["python3", "-u", "secure_daemon.py"], stdout=daemon_log, stderr=subprocess.STDOUT
)
print(f"daemon pid={daemon_proc.pid}", flush=True)
time.sleep(2)

camera_log = open("camera.log", "w")
camera_proc = subprocess.Popen(
    ["python3", "-u", "camera_service.py"], stdout=camera_log, stderr=subprocess.STDOUT
)
print(f"camera pid={camera_proc.pid}", flush=True)
time.sleep(2)

print("running dashboard baseline...", flush=True)
try:
    result = subprocess.run(
        ["python3", "-u", "dashboard_client.py", "baseline"],
        capture_output=True, text=True, timeout=10,
    )
    print("dashboard stdout:", result.stdout, flush=True)
    print("dashboard stderr:", result.stderr, flush=True)
except subprocess.TimeoutExpired as e:
    print("dashboard TIMED OUT:", e, flush=True)

print("killing daemon/camera...", flush=True)
camera_proc.kill()
daemon_proc.kill()
camera_proc.wait(timeout=5)
daemon_proc.wait(timeout=5)
daemon_log.close()
camera_log.close()

print("=== secure_daemon.log ===", flush=True)
print(open("secure_daemon.log").read(), flush=True)
print("=== camera.log ===", flush=True)
print(open("camera.log").read(), flush=True)
print("SMOKE TEST DONE", flush=True)
