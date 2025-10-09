import sys
import os

# Ensure the directory is on the path to find local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ttkthemes import ThemedTk
from app_controller import OrchestratorGUI

# --- Uncaught Exception Hook for debugging ---
import traceback


def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
    """Logs unhandled exceptions, forcing a printout to the console."""
    print("\n\n!! CRITICAL UNCAUGHT EXCEPTION !!")
    print("-----------------------------------")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print("-----------------------------------")


sys.excepthook = log_uncaught_exceptions
# ----------------------------------------------


if __name__ == "__main__":
    try:
        # 1. Initialize the root GUI window with a theme
        root = ThemedTk(theme="equilux", themebg=True)

        # 2. Start the main controller class
        app = OrchestratorGUI(root)

        # 3. Start the Tkinter event loop
        root.mainloop()

    except Exception as e:
        print(f"FATAL ERROR during GUI initialization: {e}")
