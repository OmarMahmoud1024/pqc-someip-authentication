# Post-Quantum Authentication for SOME/IP Service Discovery

**Master's thesis research — Omar Mahmoud**

This repository contains the reports, source code, experimental data, and figures produced across the phases of a Master's thesis on securing **SOME/IP Service Discovery** (the automotive middleware protocol used by modern vehicle ECUs) against spoofing and routing-hijack attacks, using **Post-Quantum Cryptography (PQC)**.

## The problem

SOME/IP Service Discovery (SOME/IP-SD) lets ECUs (Electronic Control Units) in a vehicle advertise and find services — for example, a camera ECU offering a video feed that a dashboard ECU subscribes to — over multicast UDP, with no authentication of the sender. AUTOSAR's specification assumes the in-vehicle network is a closed, trusted environment. If an attacker gets access to that network (for example, through a compromised infotainment system), they can send forged "Offer" messages and hijack that routing, redirecting safety-relevant data (camera feeds, sensor data) to themselves.

Fixing this with standard post-quantum digital signatures runs into a second problem: the signature sizes standardized by NIST are, in most cases, too large to fit inside a single automotive Ethernet packet (~1,500 bytes), and the vehicle still has to boot and connect within strict timing budgets (typically 50 milliseconds for safety-critical systems like backup cameras).

## Research phases

| Phase | Focus | Status |
|---|---|---|
| **R1** | Literature review: identified the unauthenticated Service Discovery vulnerability and the post-quantum "packet size collision" problem; proposed an initial fragmentation-based fix using ML-DSA-44 (Dilithium-2). | Complete |
| **R2** | Built a working local testbed (someipy), proved the routing-hijack vulnerability empirically (~66% malicious-frame hijack rate), benchmarked ML-DSA-44 against Falcon-512, and concluded Falcon-512 should replace ML-DSA-44 because its signature is small enough to avoid the packet size problem entirely. | Complete |
| **R3** | Designed and implemented the Falcon-512 authentication scheme end to end: a new signed message format, a fix for a replay/endpoint-substitution attack, and a modified gateway that verifies signatures before trusting a route. Tested against real attacks. Malicious-frame ratio dropped from 66% to 0%. | Complete |
| **R4** | Planned: port this same authentication scheme onto physical Cortex-M4 automotive-class hardware (two NUCLEO-L4R5ZI boards) and re-measure timing with real embedded cycle counts. | Planned / next |

## Key results (R3)

- **Routing-hijack attack**: malicious-frame ratio dropped from **66% (unauthenticated) to 0% (authenticated)** across every attacker speed tested (10ms–1000ms cyclic offer delay).
- **New replay attack** (stealing a real, validly-signed message and re-broadcasting it with a different address): also rejected in every trial, because the signed data includes the sender's address and a counter, not just which service is being offered.
- **Packet size**: the signed message measured 653–686 bytes on the wire — comfortably inside the ~1,472-byte usable payload of a single automotive Ethernet packet, confirmed by direct measurement rather than only arithmetic.
- **Latency**: the authenticated system still connected in under 14 milliseconds across ten test runs, well inside the 50-millisecond safety budget.
- **A library-specific finding**: testing uncovered a gap in the `someipy` library itself, where a rogue program could inject a fake video frame directly, bypassing Service Discovery entirely, unless a second, independent check is added to the frame-delivery path (not just the routing-table path). This is documented in detail in the R3 report and process narrative.
- **A pre-existing bug fix**: found and corrected an argument-order bug in the R2 codebase's cryptographic verification calls, which had been silently invalidating its own "verify" timing benchmarks.

## Repository structure

```
R1_Literature_Review/            The original literature review report (PDF)
R2_Vulnerability_Proof_and_Algorithm_Benchmark/
  report/                        R2 report (docx + PDF)
  code/                          The R2 testbed: camera/attacker/dashboard scripts, benchmarks, DTLS comparison
  data/                          Raw benchmark and attack results from R2
  LAB_NOTES.md                   Informal working notes from R2
R3_Falcon512_Implementation/
  report/                        R3 design document, final report, and development process narrative (docx + PDF)
  code/                          The authenticated implementation: crypto module, trust store, gateway patch, ECU scripts
  figures/                       Diagrams and charts used in the R3 report (generated from real data)
  data/                          Curated experimental results from R3
  validation_scripts/            Internal test drivers used to validate the system end to end (not part of the core deliverable)
  report_generation/             Scripts used to generate the report figures and the report documents themselves
```

## How the R3 system works, briefly

1. The camera ECU signs its Service ID, Instance ID, network address, and a counter once per boot session, using a Falcon-512 private key.
2. It broadcasts this signed message (`code/camera_service.py`, format defined in `code/pq_crypto.py`) alongside its normal, unmodified Service Discovery broadcasts.
3. A modified gateway (`code/secure_daemon.py`) verifies the signature and only accepts a routing update if it is valid and fresher (higher counter) than the last one accepted — a rule called "Last-Valid-In-Wins", replacing SOME/IP's original "Last-In-Wins" rule.
4. A second, independent check is applied to the actual video-frame delivery path, not just Service Discovery, closing a gap that was only found through live testing (see `R3_Falcon512_Implementation/report/R3_Development_Process_Narrative.docx` for how this was discovered).
5. `code/attacker_service.py` implements both a naive flood attack (reused from R2) and a new endpoint-substitution replay attack, used to test the system.

## Reproducing the results

The code depends on:
- [`someipy`](https://github.com/chrizog/someipy) — the Python SOME/IP protocol library the testbed is built on.
- `pqcrypto` — Python bindings for the Falcon-512 and ML-DSA-44 reference implementations.

Typical flow: run `setup_keys.py` once to generate a keypair and trust store, then run `secure_daemon.py`, `camera_service.py`, and `dashboard_client.py`/`attacker_service.py` as separate processes (see `R3_Falcon512_Implementation/code/run_r3_experiments.py` for the full experiment orchestration used to produce the results in the R3 report).

Report documents were generated programmatically (see `report_generation/`) using the `docx` npm package and `matplotlib`, and verified by converting to PDF and visually inspecting every page before being finalized.

## Author

Omar Mahmoud
