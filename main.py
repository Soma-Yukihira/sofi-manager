"""
main.py - point d'entree du SELFBOT MANAGER.
Lance l'interface graphique premium black & gold.
"""

# Apply any update fetched on the previous run BEFORE importing the GUI,
# so the new code is what gets loaded. No-op on non-git installs.
from updater import apply_pending_on_startup
apply_pending_on_startup()

from gui import run

if __name__ == "__main__":
    run()
