# demo_ground/ssl/__init__.py
"""
Package SSL (Sound Source Localization) untuk demo_ground.
Mendukung solver 2D murni dan solver 3D yang diproyeksikan ke bidang 2D.
"""

from .ssl_dispatcher import solve_adaptive, SOLVER_CHOICES

__all__ = ["solve_adaptive", "SOLVER_CHOICES"]
