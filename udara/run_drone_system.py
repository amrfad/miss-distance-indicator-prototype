#!/usr/bin/env python3
"""
Entry point untuk menjalankan Drone Audio Detection System
Gunakan file ini untuk start aplikasi
"""

from drone_system.main import main
from drone_system.network_setup import init_network

if __name__ == "__main__":
    print("[INIT] Mempersiapkan Automasi Jaringan Udara/Drone...")
    init_network()
    main()
