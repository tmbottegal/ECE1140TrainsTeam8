## Team 8 Train Control System
- Timothy Bottegal
- Grace Keywork
- Johann Traum
- Sara Keriakes
- Andrew White
- Jay Fu

---

## System Requirements

### Minimum Requirements
- **Operating System**: Windows 10 or Windows 11
- **Python**: Version 3.12 or higher
    - **PyQt6**
    - **pytest** (for test files)
---

## Step-by-Step Installation Guide

### Step 1: Install Python 3.12+

1. **Download Python**:
   - Go to [https://www.python.org/downloads/](https://www.python.org/downloads/)
   - Click "Download Python 3.13.x" (or latest version)

2. **Run the Python Installer**:
   - Check "Add Python to PATH" during installation
   - Click "Install Now"
   - Wait for installation to complete

3. **Verify Python Installation**:
   - Open Command Prompt (Win + R, type `cmd`, press Enter)
   - Type: `python --version`
   - Should display: `Python 3.12.x` or higher

### Step 2: Download the Project

1. **Option A: Download ZIP**:
   - Go to the project repository
   - Click "Code" → "Download ZIP"
   - Extract to `C:\Users\[YourUsername]\Desktop\ECE1140TrainsTeam8`

2. **Option B: Git Clone** (if Git is installed):
   ```cmd
   git clone [repository-url] C:\Users\[YourUsername]\Desktop\ECE1140TrainsTeam8
   ```

### Step 3: Install Dependencies

1. **Navigate to Project Directory**:
   ```cmd
   cd C:\Users\[YourUsername]\Desktop\ECE1140TrainsTeam8
   ```

2. **Install PyQt6 and pytest**:
   ```cmd
   pip install PyQt6
   ```
   ```cmd
   pip install pytest
   ```

3. **Verify Installation**:
   ```cmd
   python -c "import PyQt6; print('PyQt6 installed')"
   ```
   ```cmd
   python -c "import pytest; print('pytest installed')"
   ```

## Running the Application

### Main Application Launch
   ```cmd
   python main.py
   ```
## Troubleshooting

### Common Issues

**Issue**: `'python' is not recognized as an internal or external command`
- **Solution**: Python is not in your PATH. Reinstall Python and check "Add Python to PATH"

**Issue**: `No module named 'PyQt6'`
- **Solution**: Install PyQt6: `pip install PyQt6`

**Issue**: `No module named 'pytest'`
- **Solution**: Install pytest: `pip install pytest`

**Issue**: `FileNotFoundError: [Errno 2] No such file or directory: 'green_line.csv'`
- **Solution**: Make sure you are running from the project root directory, as all files are designed to be run from there

**Issue**: Application crashes on startup
- **Solution**: 
  1. Check Python version: `python --version` (must be 3.12+)
  2. Reinstall PyQt6: `pip uninstall PyQt6` then `pip install PyQt6`
  3. Run from correct directory


