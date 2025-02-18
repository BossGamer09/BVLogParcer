import os
import sys
import time
import threading
import psutil
import tkinter as tk
from tkinter import messagebox, scrolledtext
from PIL import Image, ImageTk
import pystray
from pystray import MenuItem as item
import re

SC_LOG_LOCATION = None
monitor_thread = None
monitoring = False

# Helper function to handle resource paths dynamically
def get_resource_path(filename):
    if getattr(sys, 'frozen', False):  # If the app is frozen (PyInstaller)
        # PyInstaller creates a temp folder in _MEIPASS, where bundled files are extracted
        base_path = sys._MEIPASS
    else:
        # If running in development mode, use the current directory
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, 'resources', filename)

# Function to check if a process is running
def check_if_process_running(process_name):
    for proc in psutil.process_iter(['name', 'exe']):
        if process_name.lower() in proc.info['name'].lower():
            return proc.info['exe']
    return None

# Function to find the Game.log file
def find_game_log(directory):
    game_log_path = os.path.join(directory, 'Game.log')
    if os.path.exists(game_log_path):
        return game_log_path
    parent_directory = os.path.dirname(directory)
    game_log_path = os.path.join(parent_directory, 'Game.log')
    if os.path.exists(game_log_path):
        return game_log_path
    return None

# Function to set the SC_LOG_LOCATION
def set_sc_log_location():
    global SC_LOG_LOCATION
    rsi_launcher_path = check_if_process_running("RSI Launcher")
    if not rsi_launcher_path:
        update_status("RSI Launcher not running.")
        return None

    sc_launcher_path = check_if_process_running("StarCitizen")
    if not sc_launcher_path:
        update_status("Star Citizen Launcher not running.")
        return None

    star_citizen_dir = os.path.dirname(sc_launcher_path)
    log_path = find_game_log(star_citizen_dir)
    if log_path:
        SC_LOG_LOCATION = log_path
        os.environ['SC_LOG_LOCATION'] = log_path
        update_status(f"Game.log found: {log_path}")
        return log_path
    else:
        update_status("Game.log not found.")
        return None

# Function to parse log lines for specific events
def parse_kill_line(line):
    # Define patterns for the events to match
    vehicle_destroy_pattern = r"Vehicle '([^']+)'.*destroy level (\d+).*caused by '([^']+)'"
    actor_death_pattern = r"CActor::Kill: '([^']+)'.*killed by '([^']+)'.*using '([^']+)'"
    jump_drive_pattern = r"Changing state to (Idle|Active).*state to (Idle|Active)"
    
    # Check for vehicle destruction
    vehicle_match = re.search(vehicle_destroy_pattern, line)
    if vehicle_match:
        vehicle = vehicle_match.group(1)
        destroy_level = vehicle_match.group(2)
        caused_by = vehicle_match.group(3)
        highlight_log(f"Vehicle Destruction: {vehicle} destroyed at level {destroy_level} by {caused_by}", 'red')
        return

    # Check for actor death
    actor_death_match = re.search(actor_death_pattern, line)
    if actor_death_match:
        actor = actor_death_match.group(1)
        killed_by = actor_death_match.group(2)
        weapon = actor_death_match.group(3)
        highlight_log(f"Actor Death: {actor} killed by {killed_by} using {weapon}", 'blue')
        return

    # Check for jump drive state change
    jump_drive_match = re.search(jump_drive_pattern, line)
    if jump_drive_match:
        state_change = jump_drive_match.group(1)
        new_state = jump_drive_match.group(2)
        highlight_log(f"Jump Drive State Change: State changed to {new_state}", 'green')
        return

    # If no match, just log normally
    update_status(f"Log: {line.strip()}")

# Function to highlight specific log messages
def highlight_log(message, color):
    status_text.config(state=tk.NORMAL)
    status_text.insert(tk.END, message + "\n", color)
    status_text.config(state=tk.DISABLED)
    status_text.yview(tk.END)

# Function to tail the Game.log file and parse the lines
def tail_log(log_file_location):
    global monitoring
    with open(log_file_location, "r") as log_file:
        log_file.seek(0, os.SEEK_END)
        while monitoring:
            line = log_file.readline()
            if line:
                parse_kill_line(line)
            else:
                time.sleep(1)

# Function to start monitoring the Game.log file
def start_monitoring():
    global monitoring, monitor_thread
    if monitoring:
        return
    log_file = set_sc_log_location()
    if log_file:
        monitoring = True
        monitor_thread = threading.Thread(target=tail_log, args=(log_file,), daemon=True)
        monitor_thread.start()
        update_status("Monitoring started.")
    else:
        messagebox.showerror("Error", "Game.log not found.")

# Function to stop monitoring
def stop_monitoring():
    global monitoring
    monitoring = False
    update_status("Monitoring stopped.")

# Function to update the status in the GUI
def update_status(message):
    status_text.config(state=tk.NORMAL)
    status_text.insert(tk.END, message + "\n")
    status_text.config(state=tk.DISABLED)
    status_text.yview(tk.END)

# Function to handle the closing of the application
def on_closing():
    stop_monitoring()  # Ensure the monitoring thread is stopped
    root.quit()        # Stop the Tkinter mainloop and exit the application
    sys.exit()         # Force an immediate exit

# Function to set up the system tray icon
def setup_tray():
    ico_path, _ = setup_resources()
    print("Resolved Icon Path:", ico_path)  # Debugging line
    if not ico_path:
        print("Icon file not found.")
        return
 
    image = Image.open(ico_path)
    menu = (item('Open', lambda: root.deiconify()), item('Exit', exit_app))
    tray_icon = pystray.Icon("BlightVeil", image, menu=menu)
    tray_icon.run()

# Function to exit the application
def exit_app():
    stop_monitoring()
    root.quit()

# Setup resources (icon and banner)
def setup_resources():
    ico_path = get_resource_path("BlightVeil.ico")
    banner_path = get_resource_path("BlightVeilBanner.png")

    if not os.path.exists(ico_path):
        print("Icon file not found:", ico_path)
    if not os.path.exists(banner_path):
        print("Banner image not found:", banner_path)

    return ico_path, banner_path

# Initialize GUI with dark mode
root = tk.Tk()
root.title("BlightVeil Log Parser")
root.geometry("500x350")
root.configure(bg="#1e1e1e")

# Setup icon and banner resources
ico_path, banner_path = setup_resources()

if ico_path:
    # Load icon for taskbar
    image = Image.open(ico_path)
    tray_icon = pystray.Icon("BlightVeil", image, menu=(item('Open', lambda: root.deiconify()), item('Exit', exit_app)))
    threading.Thread(target=tray_icon.run, daemon=True).start()

if banner_path:
    # Load banner image
    banner = Image.open(banner_path)
    banner = banner.resize((480, 100), Image.LANCZOS)
    banner_img = ImageTk.PhotoImage(banner)
    label_banner = tk.Label(root, image=banner_img, bg="#1e1e1e")
    label_banner.pack()

# Scrolled text box for displaying log messages
status_text = scrolledtext.ScrolledText(root, height=8, wrap=tk.WORD, fg="white", bg="#252526", state=tk.DISABLED)
status_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

# Set up text highlighting for different log types
def setup_highlight_tags():
    status_text.tag_configure('red', foreground='red')
    status_text.tag_configure('blue', foreground='blue')
    status_text.tag_configure('green', foreground='green')

setup_highlight_tags()  # Call this once in the setup

# Button styling
button_style = {"fg": "white", "bg": "#333333", "activebackground": "#444444", "bd": 2, "relief": "raised"}

# Start, Stop, and Exit buttons
start_button = tk.Button(root, text="Start Monitoring", command=start_monitoring, **button_style)
start_button.pack(pady=5)

stop_button = tk.Button(root, text="Stop Monitoring", command=stop_monitoring, **button_style)
stop_button.pack(pady=5)

exit_button = tk.Button(root, text="Exit", command=on_closing, **button_style)
exit_button.pack(pady=5)

# Close window by hiding (minimizing to tray) and stopping the background processes
root.protocol("WM_DELETE_WINDOW", on_closing)

# Start the system tray in a separate thread
threading.Thread(target=setup_tray, daemon=True).start()

# Run the Tkinter main loop
root.mainloop()

# PyInstaller Command:
# pyinstaller --onefile --noconsole --icon=resources/BlightVeil.ico --add-data "resources/BlightVeilBanner.png;resources" --add-data "resources/BlightVeil.ico;resources" blightveil_gui.py
