# darat/ui/widgets/mesh_loader.py
"""
MeshLoader — Parser for loading and scaling the aircraft mesh.
Reads plane.ply, centers it, scales it, maps coordinates, and caches results.
"""

import os
import struct
from functools import lru_cache

@lru_cache(maxsize=1)
def load_plane_mesh() -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    """
    Loads plane.ply, centers it, scales it to 3.19 meters wingspan,
    and maps coordinates to the widget coordinate system (rotated 180 degrees to face positive Y / North):
    - xw = -z_s (wingspan along X-axis / East-West)
    - yw = -x_s (length along Y-axis / North-South)
    - zw = y_s (height along Z-axis / Altitude)

    Returns
    -------
    vertices : list of tuple (float, float, float)
        List of pre-scaled 3D coordinates (xw, yw, zw) for each vertex.
    faces : list of tuple (int, ...)
        List of tuples of vertex indices defining each polygon face.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ply_path = os.path.normpath(os.path.join(current_dir, "..", "..", "assets", "plane.ply"))

    # Fallback delta wing model in case file is missing or corrupted
    # Coordinates in widget system: (xw, yw, zw)
    # Nose (0, 1.5, 0), Tail base (0, -1.0, 0), Left wingtip (-1.6, -0.5, 0), Right wingtip (1.6, -0.5, 0), Tail fin top (0, -1.0, 0.5)
    fallback_vertices = [
        (0.0, 1.5, 0.0),      # 0: Nose
        (0.0, -1.0, 0.0),     # 1: Tail base
        (-1.6, -0.5, 0.0),    # 2: Left wingtip
        (1.6, -0.5, 0.0),     # 3: Right wingtip
        (0.0, -1.0, 0.5),     # 4: Tail fin top
    ]
    fallback_faces = [
        (0, 2, 1),  # Left wing
        (0, 1, 3),  # Right wing
        (1, 4, 0),  # Vertical tail fin
    ]

    if not os.path.exists(ply_path):
        print(f"Warning: plane.ply not found at {ply_path}. Using fallback delta wing.")
        return fallback_vertices, fallback_faces

    try:
        with open(ply_path, "rb") as f:
            num_vertices = 0
            num_faces = 0
            header_ended = False

            while not header_ended:
                line = f.readline().decode("ascii", errors="ignore").strip()
                if not line:
                    break
                if line.startswith("element vertex"):
                    num_vertices = int(line.split()[-1])
                elif line.startswith("element face"):
                    num_faces = int(line.split()[-1])
                elif line == "end_header":
                    header_ended = True

            if num_vertices == 0 or num_faces == 0:
                raise ValueError("Invalid PLY header metadata.")

            # Parse vertices: format <fffBBBBff (24 bytes)
            # x, y, z (floats), r, g, b, a (uchars), s, t (floats)
            vertices = []
            for _ in range(num_vertices):
                data = f.read(24)
                if len(data) < 24:
                    raise ValueError("Unexpected end of vertex data.")
                val = struct.unpack("<fffBBBBff", data)
                vertices.append((val[0], val[1], val[2]))

            # Parse faces
            faces = []
            for _ in range(num_faces):
                count_bytes = f.read(1)
                if not count_bytes:
                    raise ValueError("Unexpected end of face data (count byte).")
                count = count_bytes[0]
                indices_data = f.read(4 * count)
                if len(indices_data) < 4 * count:
                    raise ValueError("Unexpected end of face data (indices).")
                indices = struct.unpack(f"<{count}I", indices_data)
                faces.append(indices)

            # Center and scale to 3.19 meters wingspan
            xs = [v[0] for v in vertices]
            ys = [v[1] for v in vertices]
            zs = [v[2] for v in vertices]

            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
            cz = (min(zs) + max(zs)) / 2.0

            # Z is wingspan in original model coordinates
            wingspan = max(zs) - min(zs)
            scale = 3.19 / wingspan if wingspan > 0 else 1.0

            # Transform and map to widget coordinate system:
            # xw = z_s (East-West)
            # yw = x_s (North-South)
            # zw = y_s (Altitude)
            transformed_vertices = []
            for x, y, z in vertices:
                x_c = (x - cx) * scale
                y_c = (y - cy) * scale
                z_c = (z - cz) * scale
                transformed_vertices.append((-z_c, -x_c, y_c))

            return transformed_vertices, faces

    except Exception as e:
        print(f"Error loading plane.ply: {e}. Using fallback delta wing.")
        return fallback_vertices, fallback_faces
