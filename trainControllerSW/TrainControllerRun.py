""" 
 This is the Train Controller Run Program

 Launch the demo UI
"""

from __future__ import annotations

import sys
from PyQt6.QtWidgets import QApplication

try:
    from .TrainControllerFrontend import TrainControllerFrontend
    from .TrainControllerUI import TrainControllerUI
except Exception:
    from TrainControllerFrontend import TrainControllerFrontend  # type: ignore
    from TrainControllerUI import TrainControllerUI  # type: ignore

# Optional Train Model (if importable from PATH)
TM_BACKEND = None
TM_UI_CLS = None
try:
    from train_model_backend import TrainModelBackend as _TMBackend  # type: ignore
    from train_model_ui import TrainModelUI as _TMUI  # type: ignore
    TM_BACKEND = _TMBackend
    TM_UI_CLS = _TMUI
except Exception:
    pass


def main() -> None:
    app = QApplication(sys.argv)

    # Attach Train Model if available; otherwise None → demo mode
    tm = TM_BACKEND() if TM_BACKEND else None

    frontend = TrainControllerFrontend(train_id="Blue-01", train_model=tm)
    ui = TrainControllerUI(frontend)
    ui.resize(1020, 700)
    ui.show()

    # Optionally show the Train Model UI alongside, if present
    if tm and TM_UI_CLS:
        tm_ui = TM_UI_CLS(tm)  # type: ignore
        tm_ui.move(ui.x() + ui.width() + 10, ui.y())
        tm_ui.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()