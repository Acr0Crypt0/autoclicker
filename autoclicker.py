import ctypes
import json
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pyautogui
from pynput import keyboard
from PIL import Image, ImageDraw

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
if not IS_MAC:
    import pystray

# Safety: slamming the mouse into any screen corner aborts the click loop.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.001

MIN_INTERVAL = 0.01
MAX_INTERVAL = 86400.0     # 24 hours in seconds (24 * 60 * 60)
CORNER_MARGIN = 5          # px; coordinates this close to a corner are rejected
FAILSAFE_POLL_SEC = 0.05   # how often to check corners during delays
UI_POLL_MS = 25            # how often the main thread drains the UI callback queue

UNIT_MULTIPLIERS = {
    "sec": 1.0,
    "min": 60.0,
    "hr": 3600.0,
}


def format_duration(seconds):
    """Format seconds into a readable string (e.g., 1h 30m 5s or 0.5s)."""
    if seconds < 60:
        return f"{seconds:g}s"
    total_sec = int(round(seconds))
    hrs, rem = divmod(total_sec, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if hrs:
        parts.append(f"{hrs}h")
    if mins:
        parts.append(f"{mins}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def format_countdown(seconds):
    """Format remaining seconds as HH:MM:SS for the live status bar."""
    total_sec = max(0, int(seconds))
    hrs, rem = divmod(total_sec, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Position Auto-Clicker (24h)")
        self.root.attributes("-topmost", True)

        self.ui_queue = queue.Queue()
        self.closing = False

        self.stop_event = None
        self.worker_thread = None

        self.tray_icon = None
        self.listener = None
        self.picking = False
        self.steps = []

        if IS_MAC:
            self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.build_ui()

        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth() + 16, self.root.winfo_reqheight() + 16)

        self.root.after(UI_POLL_MS, self._process_ui_queue)

        self.start_hotkey_listener()
        if not IS_MAC:
            self.init_system_tray()

    @property
    def running(self):
        return (
            self.worker_thread is not None
            and self.worker_thread.is_alive()
            and self.stop_event is not None
            and not self.stop_event.is_set()
        )

    @property
    def worker_busy(self):
        return self.worker_thread is not None and self.worker_thread.is_alive()

    # ---------------------------------------------------- Windows Anti-Sleep
    def _set_keep_awake(self, keep_awake):
        """Prevent Windows from sleeping during multi-hour delays."""
        if not IS_WIN:
            return
        try:
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            flags = (ES_CONTINUOUS | ES_SYSTEM_REQUIRED) if keep_awake else ES_CONTINUOUS
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception:
            pass

    # ---------------------------------------------------- Thread-Safe UI Queue
    def _schedule(self, fn):
        if not self.closing:
            self.ui_queue.put(fn)

    def _process_ui_queue(self):
        if self.closing:
            return
        while True:
            try:
                fn = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass
        if not self.closing:
            self.root.after(UI_POLL_MS, self._process_ui_queue)

    # ---------------------------------------------------------------- UI
    def build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # --- Add / Edit Step Section ---
        input_frame = ttk.LabelFrame(self.root, text="Add or Edit Click Step (Up to 24h)")
        input_frame.pack(fill="x", **pad)

        ttk.Label(input_frame, text="X:").grid(row=0, column=0, padx=(8, 2), pady=6, sticky="e")
        self.x_var = tk.StringVar(value="500")
        self.x_entry = ttk.Entry(input_frame, textvariable=self.x_var, width=6)
        self.x_entry.grid(row=0, column=1, padx=2, pady=6, sticky="w")

        ttk.Label(input_frame, text="Y:").grid(row=0, column=2, padx=(6, 2), pady=6, sticky="e")
        self.y_var = tk.StringVar(value="500")
        self.y_entry = ttk.Entry(input_frame, textvariable=self.y_var, width=6)
        self.y_entry.grid(row=0, column=3, padx=2, pady=6, sticky="w")

        ttk.Label(input_frame, text="Delay:").grid(row=0, column=4, padx=(6, 2), pady=6, sticky="e")
        self.delay_var = tk.StringVar(value="0.5")
        self.delay_entry = ttk.Entry(input_frame, textvariable=self.delay_var, width=6)
        self.delay_entry.grid(row=0, column=5, padx=2, pady=6, sticky="w")

        self.unit_var = tk.StringVar(value="sec")
        self.unit_combo = ttk.Combobox(
            input_frame, textvariable=self.unit_var, values=("sec", "min", "hr"), width=4, state="readonly"
        )
        self.unit_combo.grid(row=0, column=6, padx=(2, 8), pady=6, sticky="w")

        action_frame = ttk.Frame(input_frame)
        action_frame.grid(row=1, column=0, columnspan=7, pady=(2, 8))

        self.pick_btn = ttk.Button(
            action_frame, text="Record Pos & Add (3s)", command=self.pick_and_add_location
        )
        self.pick_btn.grid(row=0, column=0, padx=4)

        self.add_btn = ttk.Button(
            action_frame, text="Add Manual Step", command=self.add_manual_step
        )
        self.add_btn.grid(row=0, column=1, padx=4)

        self.update_btn = ttk.Button(
            action_frame, text="Update Selected", command=self.update_selected_step
        )
        self.update_btn.grid(row=0, column=2, padx=4)

        # --- Sequence List (Treeview) ---
        list_frame = ttk.LabelFrame(self.root, text="Click Sequence Queue")
        list_frame.pack(fill="both", expand=True, **pad)

        columns = ("step", "x", "y", "delay")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=5, selectmode="browse")
        self.tree.heading("step", text="#")
        self.tree.heading("x", text="X Pos")
        self.tree.heading("y", text="Y Pos")
        self.tree.heading("delay", text="Delay After")

        self.tree.column("step", width=40, anchor="center")
        self.tree.column("x", width=75, anchor="center")
        self.tree.column("y", width=75, anchor="center")
        self.tree.column("delay", width=110, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        scrollbar.pack(side="right", fill="y", padx=(0, 8), pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # --- Queue Management & File Buttons ---
        queue_btn_frame = ttk.Frame(self.root)
        queue_btn_frame.pack(fill="x", padx=12, pady=2)

        self.up_btn = ttk.Button(queue_btn_frame, text="▲ Move Up", width=10, command=lambda: self.move_step(-1))
        self.up_btn.pack(side="left", padx=2)

        self.down_btn = ttk.Button(queue_btn_frame, text="▼ Move Down", width=10, command=lambda: self.move_step(1))
        self.down_btn.pack(side="left", padx=2)

        self.del_btn = ttk.Button(queue_btn_frame, text="Remove", width=8, command=self.remove_selected_step)
        self.del_btn.pack(side="left", padx=2)

        self.clear_btn = ttk.Button(queue_btn_frame, text="Clear", width=7, command=self.clear_steps)
        self.clear_btn.pack(side="left", padx=2)

        self.save_btn = ttk.Button(queue_btn_frame, text="Save", width=8, command=self.save_preset)
        self.save_btn.pack(side="right", padx=2)

        self.load_btn = ttk.Button(queue_btn_frame, text="Load", width=8, command=self.load_preset)
        self.load_btn.pack(side="right", padx=2)

        # --- Loop Settings Section ---
        loop_frame = ttk.LabelFrame(self.root, text="Loop Settings")
        loop_frame.pack(fill="x", **pad)

        self.loop_var = tk.BooleanVar(value=True)
        self.loop_check = ttk.Checkbutton(
            loop_frame,
            text="Repeat sequence continuously",
            variable=self.loop_var,
            command=self.toggle_loop_inputs,
        )
        self.loop_check.grid(row=0, column=0, columnspan=3, padx=8, pady=(6, 2), sticky="w")

        ttk.Label(loop_frame, text="Delay Between Loops:").grid(row=1, column=0, padx=(8, 4), pady=(2, 8), sticky="w")
        self.loop_delay_var = tk.StringVar(value="0")
        self.loop_delay_entry = ttk.Entry(loop_frame, textvariable=self.loop_delay_var, width=8)
        self.loop_delay_entry.grid(row=1, column=1, padx=2, pady=(2, 8), sticky="w")

        self.loop_unit_var = tk.StringVar(value="sec")
        self.loop_unit_combo = ttk.Combobox(
            loop_frame, textvariable=self.loop_unit_var, values=("sec", "min", "hr"), width=4, state="readonly"
        )
        self.loop_unit_combo.grid(row=1, column=2, padx=(2, 8), pady=(2, 8), sticky="w")

        # --- Status & Main Controls ---
        self.status_label = ttk.Label(
            self.root, text="Status: STOPPED", foreground="#d9534f", font=("Segoe UI", 10, "bold")
        )
        self.status_label.pack(pady=6)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=4)

        self.toggle_btn = ttk.Button(btn_frame, text="Start / Stop (F6)", command=self.toggle_clicking)
        self.toggle_btn.grid(row=0, column=0, padx=6)

        if IS_MAC:
            ttk.Button(btn_frame, text="Quit", command=self.quit_app).grid(row=0, column=1, padx=6)
        else:
            ttk.Button(btn_frame, text="Minimize to Tray", command=self.hide_to_tray).grid(row=0, column=1, padx=6)

        ttk.Label(
            self.root,
            text="Fail-Safe: Slam mouse to any screen corner or press ESC to emergency stop.",
            font=("Segoe UI", 8), justify="center", foreground="gray",
        ).pack(padx=12, pady=(4, 10))

    def toggle_loop_inputs(self):
        if self.worker_busy:
            return
        enabled = self.loop_var.get()
        self.loop_delay_entry.config(state="normal" if enabled else "disabled")
        self.loop_unit_combo.config(state="readonly" if enabled else "disabled")

    # --------------------------------------------------- Presets (Save / Load)
    def save_preset(self):
        if self.worker_busy:
            return
        if not self.steps:
            messagebox.showwarning("Empty Queue", "Add at least one step before saving.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Preset", "*.json"), ("All Files", "*.*")],
            title="Save Click Sequence Preset"
        )
        if not file_path:
            return

        try:
            data = {
                "steps": self.steps,
                "loop_enabled": self.loop_var.get(),
                "loop_delay": self.loop_delay_var.get(),
                "loop_unit": self.loop_unit_var.get(),
            }
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
            messagebox.showinfo("Success", "Preset saved successfully!")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save file:\n{e}")

    def load_preset(self):
        if self.worker_busy:
            return

        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Preset", "*.json"), ("All Files", "*.*")],
            title="Load Click Sequence Preset"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            loaded_steps = data.get("steps", [])
            if not isinstance(loaded_steps, list):
                raise ValueError("Invalid preset file format.")

            self.steps = loaded_steps
            self.loop_var.set(data.get("loop_enabled", True))
            self.loop_delay_var.set(data.get("loop_delay", "0"))
            self.loop_unit_var.set(data.get("loop_unit", "sec"))

            self.refresh_tree()
            self.toggle_loop_inputs()
            messagebox.showinfo("Success", "Preset loaded successfully!")
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load file:\n{e}")

    # --------------------------------------------------- Step & Loop Validation
    def get_delay_in_seconds(self):
        try:
            raw_val = float(self.delay_var.get())
        except ValueError:
            raise ValueError("Please enter a valid number for Step Delay.")

        unit = self.unit_var.get()
        multiplier = UNIT_MULTIPLIERS.get(unit, 1.0)
        delay_sec = raw_val * multiplier

        if not (MIN_INTERVAL <= delay_sec <= MAX_INTERVAL):
            raise ValueError("Step Delay must be between 0.01 seconds and 24 hours (86,400s).")
        return delay_sec

    def get_loop_delay_in_seconds(self):
        if not self.loop_var.get():
            return 0.0
        try:
            raw_val = float(self.loop_delay_var.get())
        except ValueError:
            raise ValueError("Please enter a valid number for Delay Between Loops.")

        unit = self.loop_unit_var.get()
        multiplier = UNIT_MULTIPLIERS.get(unit, 1.0)
        loop_delay_sec = raw_val * multiplier

        if not (0.0 <= loop_delay_sec <= MAX_INTERVAL):
            raise ValueError("Delay Between Loops must be between 0 seconds and 24 hours (86,400s).")
        return loop_delay_sec

    def parse_step_inputs(self, custom_xy=None):
        delay = self.get_delay_in_seconds()

        if custom_xy is not None:
            x, y = custom_xy
        else:
            try:
                x, y = int(self.x_var.get()), int(self.y_var.get())
            except ValueError:
                raise ValueError("Please enter whole numbers for X and Y.")

        width, height = pyautogui.size()
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"Coordinates ({x}, {y}) must be inside primary screen (0-{width - 1}, 0-{height - 1}).")

        near_x = x < CORNER_MARGIN or x >= width - CORNER_MARGIN
        near_y = y < CORNER_MARGIN or y >= height - CORNER_MARGIN
        if near_x and near_y:
            raise ValueError(
                f"Position ({x}, {y}) is in a screen corner, which would trigger the emergency fail-safe."
            )

        return {"x": x, "y": y, "delay": delay}

    def refresh_tree(self, select_idx=None):
        self.tree.delete(*self.tree.get_children())
        for idx, step in enumerate(self.steps):
            self.tree.insert(
                "", "end", iid=str(idx),
                values=(idx + 1, step["x"], step["y"], format_duration(step["delay"]))
            )
        if select_idx is not None and 0 <= select_idx < len(self.steps):
            self.tree.selection_set(str(select_idx))

    def add_manual_step(self):
        if self.worker_busy:
            return
        try:
            step = self.parse_step_inputs()
        except ValueError as e:
            messagebox.showerror("Invalid Step", str(e))
            return
        self.steps.append(step)
        self.refresh_tree(len(self.steps) - 1)

    def update_selected_step(self):
        if self.worker_busy:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a Step", "Click a step in the list first to update it.")
            return
        idx = int(sel[0])
        try:
            step = self.parse_step_inputs()
        except ValueError as e:
            messagebox.showerror("Invalid Step", str(e))
            return
        self.steps[idx] = step
        self.refresh_tree(idx)

    def remove_selected_step(self):
        if self.worker_busy:
            return
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        del self.steps[idx]
        self.refresh_tree(min(idx, len(self.steps) - 1))

    def clear_steps(self):
        if self.worker_busy:
            return
        self.steps.clear()
        self.refresh_tree()

    def move_step(self, direction):
        if self.worker_busy:
            return
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        new_idx = idx + direction
        if 0 <= new_idx < len(self.steps):
            self.steps[idx], self.steps[new_idx] = self.steps[new_idx], self.steps[idx]
            self.refresh_tree(new_idx)

    def on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        step = self.steps[int(sel[0])]
        self.x_var.set(str(step["x"]))
        self.y_var.set(str(step["y"]))
        delay = step["delay"]
        if delay >= 3600 and delay % 3600 == 0:
            self.delay_var.set(f"{delay / 3600:g}")
            self.unit_var.set("hr")
        elif delay >= 60 and delay % 60 == 0:
            self.delay_var.set(f"{delay / 60:g}")
            self.unit_var.set("min")
        else:
            self.delay_var.set(f"{delay:g}")
            self.unit_var.set("sec")

    # ------------------------------------------------- Position Recording
    def pick_and_add_location(self):
        if self.picking or self.worker_busy:
            return
        try:
            self.get_delay_in_seconds()
        except ValueError as e:
            messagebox.showerror("Invalid Delay", str(e))
            return

        self.picking = True
        self.pick_btn.config(state="disabled")
        self._countdown(3)

    def _countdown(self, remaining):
        if remaining > 0:
            self.pick_btn.config(text=f"Move mouse... {remaining}s")
            self.root.after(1000, lambda: self._countdown(remaining - 1))
            return

        x, y = pyautogui.position()
        self.pick_btn.config(text="Record Pos & Add (3s)", state="normal")
        self.picking = False

        try:
            step = self.parse_step_inputs(custom_xy=(x, y))
            self.x_var.set(str(x))
            self.y_var.set(str(y))
            self.steps.append(step)
            self.refresh_tree(len(self.steps) - 1)
        except ValueError as e:
            messagebox.showerror("Invalid Position", str(e))

    # --------------------------------------------------------- Clicking Loop
    def set_inputs_state(self, state):
        for widget in (
            self.x_entry, self.y_entry, self.delay_entry,
            self.pick_btn, self.add_btn, self.update_btn,
            self.up_btn, self.down_btn, self.del_btn, self.clear_btn,
            self.save_btn, self.load_btn, self.loop_check
        ):
            widget.config(state=state)
        self.unit_combo.config(state="readonly" if state == "normal" else "disabled")

        if state == "normal":
            self.toggle_loop_inputs()
        else:
            self.loop_delay_entry.config(state="disabled")
            self.loop_unit_combo.config(state="disabled")

    def toggle_clicking(self):
        if self.running:
            self.stop_clicking()
        elif not self.worker_busy:
            self.start_clicking()

    def start_clicking(self):
        if self.worker_busy:
            return
        if not self.steps:
            messagebox.showwarning("Empty Queue", "Please add at least one click position to the sequence first.")
            return

        try:
            loop_delay = self.get_loop_delay_in_seconds()
        except ValueError as e:
            messagebox.showerror("Invalid Loop Delay", str(e))
            return

        steps_snapshot = [dict(s) for s in self.steps]
        loop_forever = self.loop_var.get()

        event = threading.Event()
        self.stop_event = event
        self.set_inputs_state("disabled")
        self._set_keep_awake(True)
        self.status_label.config(text="Status: RUNNING", foreground="#5cb85c")

        self.worker_thread = threading.Thread(
            target=self.click_loop,
            args=(event, steps_snapshot, loop_forever, loop_delay),
            daemon=True,
        )
        self.worker_thread.start()

    def stop_clicking(self):
        if self.stop_event is not None and not self.stop_event.is_set():
            self.stop_event.set()
            if self.worker_busy:
                self.status_label.config(text="Status: STOPPING...", foreground="#f0ad4e")

    def _wait_with_failsafe(self, event, delay, status_prefix):
        if delay <= 0:
            return event.is_set()

        deadline = time.monotonic() + delay
        last_shown_sec = None
        while True:
            pyautogui.failSafeCheck()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            if delay >= 1.0:
                rem_int = int(remaining) + 1
                if rem_int != last_shown_sec:
                    last_shown_sec = rem_int
                    countdown_str = format_countdown(rem_int)
                    self._schedule(
                        lambda p=status_prefix, c=countdown_str: self.status_label.config(
                            text=f"Status: RUNNING ({p} — {c} left)",
                            foreground="#5cb85c",
                        ) if (self.stop_event is event and not event.is_set()) else None
                    )

            if event.wait(min(remaining, FAILSAFE_POLL_SEC)):
                return True

    def click_loop(self, event, steps, loop_forever, loop_delay):
        error = None
        total = len(steps)
        try:
            while not event.is_set():
                for idx, step in enumerate(steps, start=1):
                    if event.is_set():
                        break
                    step_label = f"Step {idx}/{total}"
                    self._schedule(
                        lambda lbl=step_label: self.status_label.config(
                            text=f"Status: RUNNING ({lbl})", foreground="#5cb85c"
                        ) if (self.stop_event is event and not event.is_set()) else None
                    )
                    pyautogui.click(step["x"], step["y"])
                    if self._wait_with_failsafe(event, step["delay"], step_label):
                        break

                if not loop_forever or event.is_set():
                    break

                if loop_delay > 0:
                    self._schedule(
                        lambda: self.status_label.config(
                            text="Status: RUNNING (Loop Delay)", foreground="#5cb85c"
                        ) if (self.stop_event is event and not event.is_set()) else None
                    )
                    if self._wait_with_failsafe(event, loop_delay, "Loop Delay"):
                        break
        except pyautogui.FailSafeException:
            error = ("Emergency Stop", "Corner fail-safe triggered! Clicking stopped.", "info")
        except Exception as e:
            error = ("Clicker Error", f"Clicking stopped due to an error:\n{e}", "error")
        finally:
            event.set()
            self._schedule(lambda: self._on_loop_finished(event, error))

    def _on_loop_finished(self, event, error):
        if self.stop_event is event:
            self.stop_event = None
            self.worker_thread = None
            self._set_keep_awake(False)
            self.set_inputs_state("normal")
            self.status_label.config(text="Status: STOPPED", foreground="#d9534f")
        if error:
            title, msg, kind = error
            (messagebox.showinfo if kind == "info" else messagebox.showerror)(title, msg)

    # ---------------------------------------------------- Global Hotkeys
    def start_hotkey_listener(self):
        def on_press(key):
            if key == keyboard.Key.f6:
                self._schedule(self.toggle_clicking)
            elif key == keyboard.Key.esc and self.running:
                self._schedule(self.stop_clicking)

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    # ------------------------------------------------------ System Tray
    def create_tray_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 60, 60), fill=(33, 150, 243), outline=(255, 255, 255), width=4)
        draw.ellipse((22, 22, 42, 42), fill=(255, 255, 255))
        return img

    def init_system_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open Settings", self.show_from_tray, default=True),
            pystray.MenuItem("Start / Stop (F6)", lambda icon, item: self._schedule(self.toggle_clicking)),
            pystray.MenuItem("Quit Completely", self.quit_app),
        )
        self.tray_icon = pystray.Icon("auto_clicker", self.create_tray_image(), "Auto-Clicker (F6)", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.root.withdraw()

    def show_from_tray(self, icon=None, item=None):
        self._schedule(self.root.deiconify)

    def quit_app(self, icon=None, item=None):
        self.closing = True
        self._set_keep_awake(False)
        if self.stop_event is not None:
            self.stop_event.set()
        if self.listener:
            self.listener.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
