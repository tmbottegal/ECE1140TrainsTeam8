""" 
 This is the Train Controller Run Program

 Launch the demo UI
"""
from __future__ import annotations
import sys

from PyQt6.QtWidgets import QApplication

# Relative import if used as a package, else absolute for VS Code run
try:
    from .TrainControllerFrontend import TrainControllerFrontend
    from .TrainControllerUI import TrainControllerUI
except Exception:
    from TrainControllerFrontend import TrainControllerFrontend
    from TrainControllerUI import TrainControllerUI


def main() -> None:
    app = QApplication(sys.argv)

    frontend = TrainControllerFrontend(train_id="Blue-01")
    ui = TrainControllerUI(frontend)
    ui.resize(980, 700)
    ui.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
