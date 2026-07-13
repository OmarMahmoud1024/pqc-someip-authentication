import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, Rectangle
import numpy as np

plt.rcParams["font.family"] = "DejaVu Sans"

# ---------------------------------------------------------------------------
# Figure 1: Sequence diagram of the authenticated Offer flow
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 6))
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis("off")

actors = [("Camera ECU", 1.2), ("Gateway (someipyd +\nPQ-Auth Listener)", 5.0), ("Dashboard ECU", 8.8)]
for name, x in actors:
    ax.add_patch(Rectangle((x - 1.1, 9.0), 2.2, 0.8, fill=True, facecolor="#DDEBF7", edgecolor="black"))
    ax.text(x, 9.4, name, ha="center", va="center", fontsize=9, fontweight="bold")
    ax.plot([x, x], [0.3, 9.0], color="black", linestyle="--", linewidth=0.8)

def arrow(y, x1, x2, label, style="-|>", color="black", label_dy=0.18):
    a = FancyArrowPatch((x1, y), (x2, y), arrowstyle=style, mutation_scale=14, color=color, linewidth=1.4)
    ax.add_patch(a)
    ax.text((x1 + x2) / 2, y + label_dy, label, ha="center", va="bottom", fontsize=7.6)

y = 8.3
ax.text(1.2, y + 0.35, "sign once per boot\n(Falcon-512)", ha="center", fontsize=7.2, style="italic", color="#555")
y -= 0.9
arrow(y, 1.2, 5.0, "PQ-Auth companion (Falcon-512 sig over\nServiceID+InstanceID+Endpoint+Counter)")
y -= 0.75
ax.text(5.0, y + 0.3, "verify signature; if valid & counter fresh:\ntrusted_endpoint[service] = camera endpoint", ha="center", fontsize=7.0, style="italic", color="#555")
y -= 0.95
arrow(y, 1.2, 5.0, "OfferService (cyclic, unchanged wire format)")
y -= 0.75
ax.text(5.0, y + 0.3, "endpoint == trusted_endpoint ?\nyes -> accept   /   no -> DROP", ha="center", fontsize=7.0, style="italic", color="#555")
y -= 0.95
arrow(y, 5.0, 8.8, "SubscribeEventGroupAck (endpoint)")
y -= 0.9
arrow(y, 1.2, 5.0, "SendEventRequest (VIDEO_FRAME,\nsrc_endpoint=camera)")
y -= 0.75
ax.text(5.0, y + 0.3, "src_endpoint == trusted_endpoint ?\nyes -> forward   /   no -> DROP", ha="center", fontsize=7.0, style="italic", color="#555")
y -= 0.95
arrow(y, 5.0, 8.8, "VIDEO_FRAME payload")

ax.set_title("Figure 1: Authenticated SOME/IP-SD Offer and Event-Delivery Sequence", fontsize=10, pad=14)
plt.tight_layout()
plt.savefig("fig1_sequence.png", dpi=200)
plt.close()

# ---------------------------------------------------------------------------
# Figure 2: PQ-Auth companion message / PQ-Signature Option wire format
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.set_xlim(0, 10)
ax.set_ylim(0, 4)
ax.axis("off")

fields = [
    ("Magic\n'PQA1'\n4B", 1.0),
    ("ServiceID\n2B", 0.55),
    ("InstanceID\n2B", 0.55),
    ("MajorVer\n1B", 0.4),
    ("TTL\n3B", 0.5),
    ("Endpoint\nIPv4  4B", 0.7),
    ("Port\n2B", 0.5),
    ("Counter\n4B", 0.6),
]
x = 0.3
h = 1.2
y0 = 2.2
for label, w in fields:
    ax.add_patch(Rectangle((x, y0), w, h, facecolor="#DDEBF7", edgecolor="black"))
    ax.text(x + w / 2, y0 + h / 2, label, ha="center", va="center", fontsize=6.6)
    x += w

# PQ-Signature Option starts here
opt_x0 = x
opt_fields = [("Length\n2B", 0.65), ("Type\n=0x50\n1B", 0.7), ("Reserved\n1B", 0.65), ("AlgID\n1B", 0.55), ("Falcon-512 Signature\n(~653-666 bytes, variable)", 2.35)]
for label, w in opt_fields:
    ax.add_patch(Rectangle((x, y0), w, h, facecolor="#FCE4D6", edgecolor="black"))
    ax.text(x + w / 2, y0 + h / 2, label, ha="center", va="center", fontsize=6.3)
    x += w

ax.annotate("", xy=(0.3, y0 - 0.15), xytext=(opt_x0, y0 - 0.15),
            arrowprops=dict(arrowstyle="-", color="black"))
ax.text((0.3 + opt_x0) / 2, y0 - 0.5, "Companion message\nheader (this project's transport)", ha="center", fontsize=6.8)

ax.annotate("", xy=(opt_x0, y0 - 0.15), xytext=(x, y0 - 0.15),
            arrowprops=dict(arrowstyle="-", color="black"))
ax.text((opt_x0 + x) / 2, y0 - 0.5, "PQ-Signature Option (design doc §5 -- also valid\nas a future embedded SOME/IP-SD TLV option)", ha="center", fontsize=6.8)

ax.set_title("Figure 2: PQ-Auth Companion Message and PQ-Signature Option Format", fontsize=10, pad=10)
plt.tight_layout()
plt.savefig("fig2_wireformat.png", dpi=200)
plt.close()

# ---------------------------------------------------------------------------
# Figure 3: Gateway integration architecture
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.2))
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis("off")

def box(x, y, w, h, text, color="#DDEBF7", fontsize=8):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=color, edgecolor="black"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, wrap=True)

box(0.5, 6.6, 4.2, 2.6, "someipyd (unmodified core)\n• UDS server\n• routing table\n• offer_timer_callback", "#EFEFEF")
box(5.2, 7.6, 4.3, 1.4, "datagram_received_mcast()\n[monkeypatched: endpoint check]", "#FCE4D6")
box(5.2, 5.7, 4.3, 1.4, "_handle_send_event_request()\n[monkeypatched: src endpoint check]", "#FCE4D6")
box(0.5, 3.3, 4.2, 1.6, "PQ-Auth Companion Listener\n(new asyncio task, joins same\nmulticast group)", "#DDEBF7")
box(5.2, 3.3, 4.3, 1.6, "Trust Store\nservice_id -> public key\n(service_id,instance_id) -> last\nvalid counter + endpoint", "#DDEBF7")
box(2.5, 0.8, 5.0, 1.4, "secure_daemon.py\n(this project's entry point -- imports someipy.someipyd,\napplies the two monkeypatches above, then runs it)", "#E2EFDA")

for (x1, y1, x2, y2) in [
    (2.6, 6.6, 5.2, 8.3), (2.6, 6.6, 5.2, 6.4),
    (2.6, 3.3, 2.6, 4.9), (2.6, 3.3, 5.2, 4.9),
    (7.35, 5.7, 7.35, 4.9), (2.6, 3.3, 2.6, 6.6),
]:
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#555"))

ax.set_title("Figure 3: Gateway-Side Integration Architecture (secure_daemon.py)", fontsize=10, pad=10)
plt.tight_layout()
plt.savefig("fig3_architecture.png", dpi=200)
plt.close()

# ---------------------------------------------------------------------------
# Figure 4: Malicious frame ratio, before/after
# ---------------------------------------------------------------------------
labels = ["R2 baseline\n(unauthenticated,\nflood)", "R3 flood\n1000ms delay", "R3 flood\n100ms delay",
          "R3 flood\n10ms delay", "R3 substitution\n100ms delay", "R3 substitution\n10ms delay"]
values = [66.0, 0.0, 0.0, 0.0, 0.0, 0.0]
colors = ["#C00000", "#548235", "#548235", "#548235", "#548235", "#548235"]

fig, ax = plt.subplots(figsize=(9, 4.6))
bars = ax.bar(labels, values, color=colors)
for b, v in zip(bars, values):
    ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=9, fontweight="bold")
ax.set_ylabel("Malicious frames received by Dashboard (%)")
ax.set_ylim(0, 80)
ax.set_title("Figure 5: Malicious-Frame Ratio, Unauthenticated (R2) vs. Authenticated Gateway (R3)", fontsize=10)
plt.xticks(fontsize=8)
plt.tight_layout()
plt.savefig("fig5_ratio.png", dpi=200)
plt.close()

# ---------------------------------------------------------------------------
# Figure 5: Baseline latency, 10 runs
# ---------------------------------------------------------------------------
runs = list(range(1, 11))
latencies = [12.43, 1.50, 13.44, 1.84, 1.59, 8.59, 5.05, 1.39, 6.80, 3.85]

fig, ax = plt.subplots(figsize=(9, 4.2))
ax.bar(runs, latencies, color="#2E75B6")
ax.axhline(50, color="#C00000", linestyle="--", linewidth=1.3, label="50 ms automotive safety budget")
ax.set_xlabel("Run #")
ax.set_ylabel("Time to First Frame (ms)")
ax.set_xticks(runs)
ax.set_ylim(0, 55)
ax.legend(loc="upper right", fontsize=8)
ax.set_title("Figure 4: Baseline Time-to-First-Frame, Authenticated Gateway (10 runs)", fontsize=10)
plt.tight_layout()
plt.savefig("fig4_latency.png", dpi=200)
plt.close()

print("all figures written")
