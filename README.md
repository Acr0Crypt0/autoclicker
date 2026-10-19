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
