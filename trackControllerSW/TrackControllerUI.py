from typing import Any
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy,
)
import sys

def main() -> None:
    app: Any = QApplication(sys.argv)
    mw = QMainWindow()
    mw.setWindowTitle("Track Controller Module")
    central = QWidget()
    mw.setCentralWidget(central)

    # Table
    table_layout = QVBoxLayout(central)
    table_layout.setContentsMargins(8, 8, 8, 8)

    # Table Setup
    table = QTableWidget()
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels([
        "Block",
        "Suggested Speed",
        "Suggested Authority",
        "Occupancy",
        "Commanded Speed",
        "Commanded Authority"
    ])
    table.setRowCount(15)

    #Table other stuff
    table_layout.addStretch()
    table_layout.addWidget(table)
    header: QHeaderView = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setMaximumHeight(240)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
    table.setColumnWidth(0, 120)

    #PLC Button
    bottom_row = QHBoxLayout()
    plc_button: QPushButton = QPushButton("PLC File Upload")
    plc_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    bigboi = plc_button.sizeHint()
    plc_button.setFixedSize(bigboi.width()*2, bigboi.height()*2)
    bottom_row.addWidget(plc_button)
    #DOES NOTHING RN

    #Filename Box(PLACEHOLDER)
    filename_box: QLineEdit = QLineEdit("File: ilovetrains.py")
    filename_box.setReadOnly(True)
    filename_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    filename_box.setFixedWidth(360)
    font: QFont = filename_box.font()
    font.setPointSize(max(12, font.pointSize()+4))
    filename_box.setFont(font)

    #Filename Box other stuff
    filename_box.setFixedHeight(bigboi.height()*2)
    bottom_row.addWidget(filename_box)
    bottom_row.addStretch()
    table_layout.addLayout(bottom_row)
    
    #Window Size
    mw.resize(800, 600)
    mw.show()
    sys.exit(app.exec())

#how it runs
if __name__ == "__main__":
    main()