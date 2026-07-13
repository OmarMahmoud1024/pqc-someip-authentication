# R3 — Falcon-512 Implementation and Testing

The third phase of this research: the phase in which the Falcon-512 decision made at the end of R2 is actually designed, built, and tested end to end, rather than only estimated on paper.

## What's in this folder

- **`report/`** — three documents:
  - `R3_Design_Falcon512_SOMEIP_SD.docx/.pdf` — the architecture and design document written before implementation started, covering the pivot rationale, the new message format, and the experimental plan.
  - `R3_Report_Omar_Mahmoud.docx/.pdf` — the final report, written in the same style as the R1 and R2 reports, presenting the design, the implementation, and the real, measured results.
  - `R3_Development_Process_Narrative.docx` — a step-by-step account of how the solution was actually built: the research behind each decision, the sources used, the debugging process, and the two findings (a gap in the `someipy` library and a pre-existing bug in the R2 codebase) that only showed up through live testing.
- **`code/`** — the working implementation:
  - `pq_crypto.py` — Falcon-512 signing/verification, the signed-data format, and the message wire format.
  - `trust_store.py` — tracks known public keys and the last-accepted (address, counter) per service, implementing the "Last-Valid-In-Wins" rule.
  - `setup_keys.py` — one-time script to generate a keypair and initial trust store.
  - `secure_daemon.py` — the gateway: patches the `someipy` daemon at runtime to check Service Discovery messages and frame delivery against the trust store.
  - `camera_service.py`, `attacker_service.py`, `dashboard_client.py` — the ECU simulation scripts, extended from R2 to sign messages, attempt replay attacks, and measure results.
  - `run_r3_experiments.py` — orchestrates the full experiment suite (baseline latency, flood attack, replay attack) end to end.
- **`figures/`** — the diagrams and charts used in the final report, generated directly from real experimental data (not hand-drawn).
- **`data/`** — curated results: measured packet sizes, ten baseline latency measurements, and before/after attack success rates.
- **`validation_scripts/`** — internal test drivers used to validate the system while it was being built. Not part of the core deliverable, but kept here for transparency.
- **`report_generation/`** — the scripts used to generate the figures (`make_figures.py`) and the report documents themselves (`build_r3_report.js`, `build_process_doc.js`, `build_doc.js`), using `matplotlib` and the `docx` npm package.

## Headline results

- Malicious-frame ratio: **66% → 0%** across every attacker speed tested, against the same routing-hijack attack used in R2.
- A new replay attack (stealing a real, validly-signed message and re-broadcasting it with a different address) was also rejected in every trial.
- Measured packet size: 653–686 bytes on the wire, comfortably inside a single automotive Ethernet packet.
- Authenticated connection time: under 14 milliseconds across ten runs, well inside the 50-millisecond safety limit.

See `report/R3_Report_Omar_Mahmoud.pdf` for full details, and `report/R3_Development_Process_Narrative.docx` for how and why each decision was made.
