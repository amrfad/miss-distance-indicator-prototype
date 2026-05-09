#!/usr/bin/env python3
"""
Migrate PyQt6 imports to PySide6.
Run this script from project root.
"""

import os
import re
from pathlib import Path

# Mapping import lama → baru
IMPORT_MAP = {
    r'from PyQt6\.QtWidgets': 'from PySide6.QtWidgets',
    r'from PyQt6\.QtCore': 'from PySide6.QtCore',
    r'from PyQt6\.QtGui': 'from PySide6.QtGui',
    r'from PyQt6\.QtMultimedia': 'from PySide6.QtMultimedia',
    r'from PyQt6\.QtNetwork': 'from PySide6.QtNetwork',
}

# Signal/Slot replacements
REPLACEMENTS = [
    (r'pyqtSignal\(', r'Signal('),
    (r'pyqtSlot\(', r'Slot('),
    # Handle case with no arguments
    (r'pyqtSignal\)', r'Signal()'),
    (r'pyqtSlot\)', r'Slot()'),
]

# File extensions to process
EXTENSIONS = ('.py', '.pyw')


def migrate_file(filepath: Path) -> bool:
    """Migrate a single Python file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Replace imports
    for pattern, replacement in IMPORT_MAP.items():
        content = re.sub(pattern, replacement, content)
    
    # Replace signals/slots
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def main():
    # Directory to scan (current directory)
    root_dir = Path.cwd()
    
    # Also scan darat/ui directory
    target_dirs = [root_dir / "darat" / "ui"]
    
    modified_files = []
    
    for target_dir in target_dirs:
        if not target_dir.exists():
            print(f"Directory not found: {target_dir}")
            continue
        
        for filepath in target_dir.rglob('*'):
            if filepath.suffix in EXTENSIONS:
                if migrate_file(filepath):
                    modified_files.append(str(filepath))
                    print(f"✅ Migrated: {filepath}")
    
    print(f"\n{'='*50}")
    print(f"Migration complete! {len(modified_files)} files modified.")
    
    if modified_files:
        print("\nFiles modified:")
        for f in modified_files:
            print(f"  - {f}")
    
    print("\n⚠️  Remember to:")
    print("  1. Uninstall PyQt6: pip uninstall PyQt6")
    print("  2. Install PySide6: pip install PySide6")
    print("  3. Update requirements.txt: PySide6>=6.5.0")

if __name__ == "__main__":
    main()