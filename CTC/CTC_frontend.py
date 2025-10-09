#CTC frontend code 
# CTC/CTC_frontend.py
import sys
from PyQt6 import QtWidgets   # or: from PySide6 import QtWidgets
from CTC_tb_ui import CTCWindow

def main():
    print("=== CTC Fronxtend: launching UI ===")
    app = QtWidgets.QApplication(sys.argv)
    win = CTCWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
