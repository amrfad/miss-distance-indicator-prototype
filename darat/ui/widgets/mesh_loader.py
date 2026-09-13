# darat/ui/widgets/mesh_loader.py
"""
MeshLoader — Parser for loading, scaling, and pre-computing geometry metadata for the aircraft mesh.
Reads plane.ply, centers it, scales it, maps coordinates, and pre-calculates face normals,
material categories (canopy, wings, fuselage, exhaust), and centroids for high-performance 3D shading.
"""

import math
import os
import struct
from functools import lru_cache


def _calc_normal(pts: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Calculate normalized normal vector using 3-point cross product."""
    if len(pts) < 3:
        return (0.0, 0.0, 1.0)
    p0, p1, p2 = pts[0], pts[1], pts[2]
    v1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    v2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    nx = v1[1] * v2[2] - v1[2] * v2[1]
    ny = v1[2] * v2[0] - v1[0] * v2[2]
    nz = v1[0] * v2[1] - v1[1] * v2[0]
    length = math.hypot(nx, ny, nz)
    if length > 1e-8:
        return (nx / length, ny / length, nz / length)
    return (0.0, 0.0, 1.0)


def _classify_face(cx: float, cy: float, cz: float) -> str:
    """Classify face into procedural tactical material type."""
    # Canopy glass: upper front dorsal area
    if 0.15 < cy < 0.75 and cz > 0.05 and abs(cx) < 0.22:
        return "canopy"
    # Wing panels: outer lateral wingspan
    elif abs(cx) > 0.40:
        return "wings"
    # Engine exhaust / rear nozzle
    elif cy < -0.85:
        return "exhaust"
    # Main fuselage composite skin
    return "fuselage"


@lru_cache(maxsize=1)
def load_plane_mesh() -> tuple[
    list[tuple[float, float, float]],
    list[tuple[int, ...]],
    list[tuple[float, float, float]],
    list[str],
    list[tuple[float, float, float]],
]:
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
    normals : list of tuple (float, float, float)
        Normalized face normal vectors (nx, ny, nz).
    face_types : list of str
        Category string: 'canopy', 'wings', 'exhaust', or 'fuselage'.
    centroids : list of tuple (float, float, float)
        Pre-calculated center of each face (cx, cy, cz).
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ply_path = os.path.normpath(os.path.join(current_dir, "..", "..", "assets", "plane.ply"))

    # Fallback delta wing model in case file is missing or corrupted
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
    fallback_normals = [
        _calc_normal([fallback_vertices[i] for i in face])
        for face in fallback_faces
    ]
    fallback_types = ["wings", "wings", "canopy"]
    fallback_centroids = [
        (
            sum(fallback_vertices[i][0] for i in face) / len(face),
            sum(fallback_vertices[i][1] for i in face) / len(face),
            sum(fallback_vertices[i][2] for i in face) / len(face),
        )
        for face in fallback_faces
    ]

    if not os.path.exists(ply_path):
        print(f"Warning: plane.ply not found at {ply_path}. Using fallback delta wing.")
        return fallback_vertices, fallback_faces, fallback_normals, fallback_types, fallback_centroids

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
            # xw = -z_s (East-West)
            # yw = -x_s (North-South)
            # zw = y_s (Altitude)
            transformed_vertices = []
            for x, y, z in vertices:
                x_c = (x - cx) * scale
                y_c = (y - cy) * scale
                z_c = (z - cz) * scale
                transformed_vertices.append((-z_c, -x_c, y_c))

            # Pre-compute face normals, centroids, and material classification
            normals = []
            centroids = []
            face_types = []

            for face in faces:
                pts = [transformed_vertices[idx] for idx in face]
                k = len(pts)
                fcx = sum(p[0] for p in pts) / k
                fcy = sum(p[1] for p in pts) / k
                fcz = sum(p[2] for p in pts) / k
                centroids.append((fcx, fcy, fcz))
                normals.append(_calc_normal(pts))
                face_types.append(_classify_face(fcx, fcy, fcz))

            return transformed_vertices, faces, normals, face_types, centroids

    except Exception as e:
        print(f"Error loading plane.ply: {e}. Using fallback delta wing.")
        return fallback_vertices, fallback_faces, fallback_normals, fallback_types, fallback_centroids
