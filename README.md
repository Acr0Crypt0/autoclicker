Here is a professional, clean `README.md` file tailored for your GitHub repository. You can copy and paste this directly into a file named `README.md` in your project folder.

```markdown
# 🚀 Secure Multi-Position Auto-Clicker

A feature-rich, highly customizable, and secure auto-clicker built in **Python** utilizing **Tkinter**, **PyAutoGUI**, **Pynput**, and **Pystray**. Designed with robust concurrency controls, a multi-position sequence queue, up to 24-hour custom delays, and system tray integration.

---

## ✨ Features

* **Multi-Position Sequence Queue:** Add as many click coordinates $(X, Y)$ as you need, and the app will execute them sequentially.
* **Custom Delays (Up to 24 Hours):** Set individual step delays (in seconds, minutes, or hours) and a separate loop cooldown timer between cycles.
* **Live Progress & Countdown:** Displays active step progress (`Step 1/3`) and real-time countdowns (`HH:MM:SS left`) during long pauses.
* **3-Layer Emergency Security:**
  1. **Global Hotkeys:** Press `F6` to Start/Stop and `ESC` to instantly halt execution from anywhere.
  2. **Corner Fail-Safe:** Slam your mouse cursor into any of the 4 screen corners to abort instantly (polled every 50ms, even during multi-hour waits).
  3. **Windows Anti-Sleep:** Automatically prevents your PC from going to sleep during long execution sequences.
* **System Tray / Icon Bar Support:** Minimize the app to your system tray for silent background operation.
* **JSON Preset Management:** Save and load your multi-position click sequences and loop settings effortlessly.

---

## 🛠️ Prerequisites & Installation

Make sure you have **Python 3.8+** installed on your system.

1. **Clone or download this repository**, then open your terminal (or Git Bash) inside the project folder.
2. **Install the required libraries:**
   ```bash
   pip install pyautogui pynput pystray Pillow

```

---

## 🚀 Running the Application

* **Standard Run (with terminal output):**
```bash
python autoclicker.py

```


* **Silent Background Run (Windows):**
Rename the file extension to `.pyw` or run via `pythonw`:
```bash
pythonw autoclicker.py

```



---

## 📦 Building a Standalone `.exe` (Windows)

If you want to package this into a single executable file without needing Python installed on target machines:

1. Install PyInstaller:
```bash
pip install pyinstaller

```


2. Build the executable:
```bash
python -m PyInstaller --noconsole --onefile --collect-submodules pynput --collect-submodules pystray --name "SecureAutoClicker" autoclicker.py

```


3. Find your finished executable inside the **`dist/`** folder!

---

## 🎮 How to Use

1. **Add Click Steps:** Type your target $X$ and $Y$ coordinates manually, or use the **Record Pos & Add (3s)** button to hover your mouse over a target and capture it automatically.
2. **Configure Delays:** Select whether your delay is in **seconds**, **minutes**, or **hours** (supports up to 24 hours).
3. **Loop Settings:** Enable continuous looping and optionally set a separate delay timer between cycles.
4. **Start / Stop:** Press **`F6`** at any time to start or stop the click sequence.
5. **Emergency Stop:** Press **`ESC`** or flick your mouse cursor violently into any screen corner.

---

## 🛡️ License

This project is open-source and available under the [MIT License](https://www.google.com/search?q=LICENSE).

```

<FollowUp label="Need a license file or a CONTRIBUTING.md template for your repo?" query="How do I add a standard MIT License file and a CONTRIBUTING.md guide to my GitHub repository?"/>

```
