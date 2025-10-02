from typing import Any
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QPushButton,
    QTableWidget,
    QHeaderView,
    QLineEdit,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy,
    QComboBox,
    QLabel,
)
import sys

def main() -> None:
    #Setup

    app: Any = QApplication(sys.argv)
    mw = QMainWindow()
    mw.setWindowTitle("Track Controller Module")
    central = QWidget()
    mw.setCentralWidget(central)

    # Table
    table_layout = QVBoxLayout(central)
    table_layout.setContentsMargins(8, 8, 8, 8)

    #Dropdown Text
    top_row = QHBoxLayout()
    dropdown_text: QLabel = QLabel("Track: Blue Line")
    font_droptext = dropdown_text.font()
    font_droptext.setPointSize(max(14, font_droptext.pointSize()+6))
    font_droptext.setBold(True)
    dropdown_text.setFont(font_droptext)
    top_row.addWidget(dropdown_text)

    #Track Picker Dropdown
    top_row.addStretch()
    track_picker: QComboBox = QComboBox()
    track_picker.addItems(["Blue Line", "Green Line", "Red Line"])
    track_picker.setCurrentIndex(0)
    track_picker.setFixedHeight(32)
    track_picker.setFixedWidth(160)
    font_drop: QFont = track_picker.font()
    font_drop.setPointSize(max(12, font_drop.pointSize()+4))
    track_picker.setFont(font_drop)
    track_picker.currentTextChanged.connect(lambda text: dropdown_text.setText(f"Track: {text}"))
    top_row.addWidget(track_picker)
    table_layout.addLayout(top_row)

    #Table_Other Setup
    table_other = QTableWidget()
    table_other.setColumnCount(3)
    table_other.setRowCount(4)
    table_other.setHorizontalHeaderLabels([
        "Light",
        "Switch",
        "Crossing",
    ])
    table_other.setMaximumHeight(160)
    table_other.setMaximumWidth(300)
    table_other.verticalHeader().setVisible(False)
    pergatory = QHBoxLayout()
    pergatory.addWidget(table_other)
    pergatory.addStretch()
    table_layout.addLayout(pergatory)

    #Table_Main Setup
    table_main = QTableWidget()
    table_main.setColumnCount(6)
    table_main.setHorizontalHeaderLabels([
        "Block",
        "Suggested Speed",
        "Suggested Authority",
        "Occupancy",
        "Commanded Speed",
        "Commanded Authority"
    ])
    table_main.setRowCount(15)

    #Table_Main other stuff
    table_layout.addStretch()
    table_layout.addWidget(table_main)
    header: QHeaderView = table_main.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table_main.verticalHeader().setVisible(False)
    table_main.setMaximumHeight(240)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
    table_main.setColumnWidth(0, 120)

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
    font_text: QFont = filename_box.font()
    font_text.setPointSize(max(12, font_text.pointSize()+4))
    filename_box.setFont(font_text)

    #Filename Box other stuff
    filename_box.setFixedHeight(bigboi.height()*2)
    bottom_row.addWidget(filename_box)
    bottom_row.addStretch()
    table_layout.addLayout(bottom_row)
    
    #Manual Override Button
    override_button: QPushButton = QPushButton("Manual Override")
    override_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    override_button.setFixedHeight(bigboi.height()*2)
    override_button.setFixedWidth(220)
    bottom_row.addWidget(override_button)
    bottom_row.addStretch()
    #DOES NOTHING RN

    table_layout.addLayout(bottom_row)

    #Window Size
    mw.resize(800, 600)
    mw.show()
    sys.exit(app.exec())

#how it runs
if __name__ == "__main__":
    main()