""" 
 This is the Train Controller Run Program

 Launch the demo UI
"""

from __future__ import annotations
import sys
from PyQt6.QtWidgets import QApplication
from TrainControllerFrontend import TrainControllerFrontend
from TrainControllerUI import TrainControllerUI

def main() -> None:
    app = QApplication(sys.argv)

    frontend = TrainControllerFrontend()
    ui = TrainControllerUI(frontend)
    ui.resize(760,360)
    ui.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()