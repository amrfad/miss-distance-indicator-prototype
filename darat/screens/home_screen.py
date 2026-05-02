"""
Home Screen
Layar pembuka dengan navigasi ke halaman utama aplikasi.
"""

from tkinter import LEFT, ttk


class HomeScreen:
    """Halaman awal dengan 3 tombol navigasi."""

    def __init__(self, app):
        """
        Args:
            app: Instance EventGUI (koordinator utama)
        """
        self.app = app

    def build(self):
        """Bangun widget di app.main_frame."""
        app = self.app
        frame = app.main_frame

        ttk.Label(
            frame, text="COMMAND APPLICATION", font=("Arial", 24, "bold")
        ).pack(pady=50)

        ttk.Label(
            frame, text="WELCOME TO COMMAND APPLICATION!", font=("Arial", 16)
        ).pack(pady=20)

        nav_frame = ttk.Frame(frame)
        nav_frame.pack(pady=50)

        ttk.Button(
            nav_frame,
            text="Go to command page",
            command=app.show_command,
            width=20,
        ).pack(side=LEFT, padx=10)

        ttk.Button(
            nav_frame,
            text="Visualize Results",
            command=app.show_visualize,
            width=20,
        ).pack(side=LEFT, padx=10)

        ttk.Button(
            nav_frame,
            text="Exit",
            command=app.on_closing,
            width=20,
        ).pack(side=LEFT, padx=10)
