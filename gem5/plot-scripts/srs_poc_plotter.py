import pandas as pd
import matplotlib.pyplot as plt
import warnings

import sys
if len(sys.argv) > 2:
    file_name = sys.argv[1]
    figure_name = sys.argv[2]
else:
    print("Usage: python srs_poc_plotter.py <input_file_name> <figure_name>")
    sys.exit(1)

warnings.filterwarnings("ignore")

df_bits = pd.DataFrame(columns=['index', 'SWAPs', 'Bit'])
it = 0

with open(file_name, 'r') as f:
    for line in f:
        if "[RECV] Received" in line:
            try:
                bit = int(line.split("Received: ")[1].split("(")[0].strip())
                num_swaps = int(line.split("(")[1].split(" ")[0].strip())
                df_bits = pd.concat([df_bits, pd.DataFrame([{'index': it, 'SWAPs': num_swaps, 'Bit': bit}])], ignore_index=True)
                it += 1
            except (IndexError, ValueError):
                continue

df = df_bits.copy()
fig, ax = plt.subplots(figsize=(9, 3.6))
plt.rcParams.update({'font.size': 14})

for i, value in enumerate(df["Bit"]):
    color = "sandybrown" if value == 0 else "cornflowerblue"
    ax.axvspan(i - 0.5, i + 0.5, color=color, alpha=0.3, label="0" if value == 0 else "1")

ax.plot(df["index"], df["SWAPs"], marker="o", color="black", label="SWAPs")

xticks_positions = [(i - 1) + 0.5 for i in range(0, len(df) + 1, 8)]
ax.set_xticks(xticks_positions)
ax.set_xticklabels([str(int(pos + 0.5)) for pos in xticks_positions], fontsize=12)

ax.set_xlabel("Transmission Window", fontsize=14)
ax.set_ylabel("Number of Swaps\nMeasured by the Receiver", fontsize=14)

for i in range(0, len(df) + 1, 8):
    ax.axvline((i - 1) + 0.5, color="black", linewidth=1)

# Annotate each byte as its ASCII character (MICRO)
message_str = "MICRO"
for char_idx, ch in enumerate(message_str):
    if char_idx < len(xticks_positions) - 1:
        x_pos = (xticks_positions[char_idx] + xticks_positions[char_idx + 1]) / 2
        ax.text(x_pos, -0.5, f"({ch})", ha='center', va='top', fontsize=16, color='red')

ax.axhline(0.5, color="gray", linewidth=2, linestyle="--")

handles, labels = ax.get_legend_handles_labels()
by_label = dict(zip(labels, handles))
by_label.pop("SWAPs")
legend_labels = ["Bit Value"] + list(by_label.keys())
legend_handles = [plt.Line2D([0], [0], color="none")] + list(by_label.values())
ax.legend(
    legend_handles,
    legend_labels,
    loc='upper center',
    fontsize=12,
    ncol=len(legend_labels),
    framealpha=1,
    bbox_to_anchor=(0.5, 1.2),
    edgecolor="black",
    borderpad=0.3,
    fancybox=False,
    labelspacing=0.5,
)
plt.xlim(-1, len(df))
plt.tight_layout()
plt.savefig(figure_name, bbox_inches='tight', dpi=300)
