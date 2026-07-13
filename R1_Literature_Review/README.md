# R1 — Literature Review

The first phase of this research. Identifies that SOME/IP Service Discovery broadcasts unauthenticated multicast messages, and that the natural fix — attaching a NIST post-quantum signature to each message — collides with the automotive Ethernet MTU, since post-quantum signatures are substantially larger than a standard ~1,500-byte Ethernet packet.

Proposes an initial solution: fragmenting an ML-DSA-44 (Dilithium-2) signature across two SOME/IP-SD messages (an Offer and its Repetition, sent about 10ms apart), and outlines a plan to prototype this using the `someipy` Python library in the following phase.

See `R1_Report_Omar_Mahmoud.pdf` for the full report, including the literature review of prior SOME/IP security work and the state of the art on post-quantum algorithms for constrained automotive hardware.
