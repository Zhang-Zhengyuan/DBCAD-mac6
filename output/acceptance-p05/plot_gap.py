"""Draw the measured X projection of the two CADWorld candidates."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


HERE = Path(__file__).resolve().parent
measured = json.loads((HERE / "freecad_measurements.json").read_text())["assemblies"]
graded = json.loads((HERE / "assembly_results.json").read_text())["candidates"]
fig, axes = plt.subplots(1, 2, figsize=(7.1, 1.68), layout="constrained")
for ax, key in zip(axes, ("resaved_5mm", "resaved_8mm")):
    gap = measured[key]["face_distance_mm"]
    right = 10 + gap  # the grounded upstream box spans X = 0..10 mm
    ax.add_patch(Rectangle((0, 0), 10, 2.5, facecolor="#45667a"))
    ax.add_patch(Rectangle((right, 0), 5, 2.5, facecolor="#739d99"))
    ax.vlines([10, right], 0, 4.5, color="#45545d", linewidth=.8)
    ax.annotate("", xy=(10, 3.9), xytext=(right, 3.9),
                arrowprops=dict(arrowstyle="<->", color="#253945", shrinkA=0, shrinkB=0))
    ax.text(10 + gap / 2, 5, f"{gap:g} mm", ha="center", fontsize=11, color="#172e3b")
    ax.set(xticks=[0, 10, right, right + 5], yticks=[], xlim=(-1, 24), ylim=(-1.6, 7.5),
           xlabel="X (mm)")
    ax.set_title(f'CADWorld score   {graded[key]["score"]:.0f} / 1', fontsize=10)
    for side in ("top", "left", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#86929a")
    ax.tick_params(axis="x", labelsize=8, length=3, colors="#395365")
fig.savefig(HERE / "gap-comparison.png", dpi=200, facecolor="white")
plt.close(fig)
