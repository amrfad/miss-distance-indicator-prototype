import matplotlib.pyplot as plt
import re


def parse_results_file(filename):
    """Parse file hasil _results.txt dan ekstrak koordinat"""
    events = []
    mic_positions = {}

    with open(filename, "r", encoding="utf-8") as f:
        section = None
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                if "MICROPHONE" in line:
                    section = "mic"
                elif "EVENT" in line:
                    section = "event"
                continue

            if "=" not in line:
                continue

            # Parse microphone positions
            if section == "mic" and line.startswith("mic"):
                match = re.match(
                    r"(mic\d+)\s*=\s*\[([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\]", line
                )
                if match:
                    mic_name = match.group(1)
                    x = float(match.group(2))
                    y = float(match.group(3))
                    z = float(match.group(4))
                    mic_positions[mic_name] = (x, y, z)

            # Parse event positions
            elif line.startswith("e"):
                # Format: e1 = [x, y, z] atau e1 = FAILED
                match = re.match(
                    r"e(\d+)\s*=\s*\[([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\]", line
                )
                if match:
                    event_num = int(match.group(1))
                    x = float(match.group(2))
                    y = float(match.group(3))
                    z = float(match.group(4))
                    events.append(
                        {
                            "event_number": event_num,
                            "x": x,
                            "y": y,
                            "z": z,
                            "valid": True,
                        }
                    )
                elif "FAILED" in line:
                    match = re.match(r"e(\d+)\s*=\s*FAILED", line)
                    if match:
                        event_num = int(match.group(1))
                        events.append({"event_number": event_num, "valid": False})

    return events, mic_positions


def visualize_3d(events, filename, mic_positions=None):
    """Visualisasi koordinat 3D dari hasil TDOA"""
    # Filter hanya event yang valid
    valid_events = [e for e in events if e["valid"]]

    if not valid_events:
        print("Tidak ada event valid untuk divisualisasikan.")
        return None

    # Ekstrak koordinat
    x_coords = [e["x"] for e in valid_events]
    y_coords = [e["y"] for e in valid_events]
    z_coords = [e["z"] for e in valid_events]
    event_nums = [e["event_number"] for e in valid_events]

    # Buat figure
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")

    # Plot microphone positions jika tersedia
    if mic_positions:
        mic_x = [pos[0] for pos in mic_positions.values()]
        mic_y = [pos[1] for pos in mic_positions.values()]
        mic_z = [pos[2] for pos in mic_positions.values()]

        ax.scatter(
            mic_x,
            mic_y,
            mic_z,
            c="blue",
            marker="^",
            s=150,
            alpha=0.8,
            edgecolors="black",
            linewidths=2,
            label="Microphones",
        )

        # Label setiap mikrofon
        for mic_name, pos in mic_positions.items():
            ax.text(
                pos[0],
                pos[1],
                pos[2],
                f"  {mic_name}\n  ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})",
                fontsize=8,
                fontweight="bold",
                color="blue",
            )

    # Plot event points
    scatter = ax.scatter(
        x_coords,
        y_coords,
        z_coords,
        c=event_nums,
        cmap="viridis",
        s=100,
        alpha=0.6,
        edgecolors="black",
        label="Events",
    )

    # Label setiap titik dengan nomor event dan koordinat
    for i, (x, y, z, num) in enumerate(zip(x_coords, y_coords, z_coords, event_nums)):
        ax.text(
            x,
            y,
            z,
            f"  e{num}\n  ({x:.2f}, {y:.2f}, {z:.2f})",
            fontsize=8,
            fontweight="bold",
        )

    # Colorbar
    # cbar = plt.colorbar(scatter, ax=ax, pad=0.1)
    # cbar.set_label("Event Number", rotation=270, labelpad=15)

    # Labels dan title
    ax.set_xlabel("X (meters)", fontsize=11)
    ax.set_ylabel("Y (meters)", fontsize=11)
    ax.set_zlabel("Z (meters)", fontsize=11)
    ax.set_title(
        f"3D TDOA Position Estimation\n{filename}", fontsize=13, fontweight="bold"
    )

    # Grid
    ax.grid(True, alpha=0.3)

    # Add legend
    ax.legend(loc="upper right")

    # Info box
    info_text = f"Total Events: {len(events)}\n"
    info_text += f"Valid: {len(valid_events)}\n"
    info_text += f"Failed: {len(events) - len(valid_events)}"
    if mic_positions:
        info_text += f"\nMicrophones: {len(mic_positions)}"

    plt.figtext(
        0.02,
        0.98,
        info_text,
        fontsize=10,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    return fig


def visualize_2d_projections(events, filename, mic_positions=None):
    """Visualisasi proyeksi 2D (XY, XZ, YZ) dari hasil TDOA"""
    # Filter hanya event yang valid
    valid_events = [e for e in events if e["valid"]]

    if not valid_events:
        print("Tidak ada event valid untuk divisualisasikan.")
        return None

    # Ekstrak koordinat
    x_coords = [e["x"] for e in valid_events]
    y_coords = [e["y"] for e in valid_events]
    z_coords = [e["z"] for e in valid_events]
    event_nums = [e["event_number"] for e in valid_events]

    # Buat figure dengan 3 subplot
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # XY projection (Top View)
    axes[0].scatter(
        x_coords,
        y_coords,
        c=event_nums,
        cmap="viridis",
        s=100,
        alpha=0.6,
        edgecolors="black",
        label="Events",
    )

    # Plot microphones
    if mic_positions:
        mic_x = [pos[0] for pos in mic_positions.values()]
        mic_y = [pos[1] for pos in mic_positions.values()]
        axes[0].scatter(
            mic_x,
            mic_y,
            c="blue",
            marker="^",
            s=150,
            alpha=0.8,
            edgecolors="black",
            linewidths=2,
            label="Microphones",
        )
        for mic_name, pos in mic_positions.items():
            axes[0].text(
                pos[0],
                pos[1],
                f"  {mic_name}",
                fontsize=7,
                fontweight="bold",
                color="blue",
            )

    for x, y, num in zip(x_coords, y_coords, event_nums):
        axes[0].text(x, y, f"  e{num}", fontsize=8)
    axes[0].set_xlabel("X (meters)")
    axes[0].set_ylabel("Y (meters)")
    axes[0].set_title("XY Projection (Top View)")
    axes[0].grid(True, alpha=0.3)
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].legend(loc="best", fontsize=8)

    # XZ projection (Front View)
    axes[1].scatter(
        x_coords,
        z_coords,
        c=event_nums,
        cmap="viridis",
        s=100,
        alpha=0.6,
        edgecolors="black",
    )

    # Plot microphones
    if mic_positions:
        mic_x = [pos[0] for pos in mic_positions.values()]
        mic_z = [pos[2] for pos in mic_positions.values()]
        axes[1].scatter(
            mic_x,
            mic_z,
            c="blue",
            marker="^",
            s=150,
            alpha=0.8,
            edgecolors="black",
            linewidths=2,
            label="Microphones",
        )
        for mic_name, pos in mic_positions.items():
            axes[1].text(
                pos[0],
                pos[2],
                f"  {mic_name}",
                fontsize=7,
                fontweight="bold",
                color="blue",
            )

    for x, z, num in zip(x_coords, z_coords, event_nums):
        axes[1].text(x, z, f"  e{num}", fontsize=8)
    axes[1].set_xlabel("X (meters)")
    axes[1].set_ylabel("Z (meters)")
    axes[1].set_title("XZ Projection (Front View)")
    axes[1].grid(True, alpha=0.3)
    axes[1].set_aspect("equal", adjustable="box")

    # YZ projection (Side View)
    axes[2].scatter(
        y_coords,
        z_coords,
        c=event_nums,
        cmap="viridis",
        s=100,
        alpha=0.6,
        edgecolors="black",
    )

    # Plot microphones
    if mic_positions:
        mic_y = [pos[1] for pos in mic_positions.values()]
        mic_z = [pos[2] for pos in mic_positions.values()]
        axes[2].scatter(
            mic_y,
            mic_z,
            c="blue",
            marker="^",
            s=150,
            alpha=0.8,
            edgecolors="black",
            linewidths=2,
            label="Microphones",
        )
        for mic_name, pos in mic_positions.items():
            axes[2].text(
                pos[1],
                pos[2],
                f"  {mic_name}",
                fontsize=7,
                fontweight="bold",
                color="blue",
            )

    for y, z, num in zip(y_coords, z_coords, event_nums):
        axes[2].text(y, z, f"  e{num}", fontsize=8)
    axes[2].set_xlabel("Y (meters)")
    axes[2].set_ylabel("Z (meters)")
    axes[2].set_title("YZ Projection (Side View)")
    axes[2].grid(True, alpha=0.3)
    axes[2].set_aspect("equal", adjustable="box")

    # Add single info box at top center
    info_text = f"Total Events: {len(events)} | Valid: {len(valid_events)} | Failed: {len(events) - len(valid_events)}"
    if mic_positions:
        info_text += f" | Microphones: {len(mic_positions)}"
    fig.text(
        0.5,
        0.98,
        info_text,
        ha="center",
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    fig.suptitle(f"2D Projections - {filename}", fontsize=14, fontweight="bold", y=0.94)
    plt.tight_layout(rect=[0, 0, 1, 0.92])

    return fig


def main():
    """Main function untuk testing"""
    import glob

    # Cari file _results.txt
    result_files = sorted(glob.glob("*_results.txt"))

    if not result_files:
        print("Tidak ada file _results.txt ditemukan di direktori ini.")
        return

    print("File hasil yang tersedia:")
    for i, file in enumerate(result_files, 1):
        print(f"  {i}. {file}")

    choice = input("\nMasukkan nomor file yang akan divisualisasikan: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(result_files):
            filename = result_files[idx]
            events, mic_positions = parse_results_file(filename)

            print(f"\nMemproses {filename}...")
            print(f"Total events: {len(events)}")
            print(f"Valid events: {sum(1 for e in events if e['valid'])}")
            if mic_positions:
                print(f"Microphones: {len(mic_positions)}")

            # Tampilkan visualisasi
            fig1 = visualize_3d(events, filename, mic_positions)
            fig2 = visualize_2d_projections(events, filename)

            if fig1 or fig2:
                plt.show()
        else:
            print("Pilihan tidak valid.")
    except ValueError:
        print("Input harus berupa angka.")


if __name__ == "__main__":
    main()
