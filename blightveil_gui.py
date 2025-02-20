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

# Global variables
show_parsed_only = True
contested_elevator_tracking = {}  # Dictionary to track carriages
elevator_door_states = {}  # Dictionary to track door open/close state
SC_LOG_LOCATION = None 
monitor_thread = None 
monitoring = False 

# Helper function to handle resource paths dynamically
def get_resource_path(filename):
    base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    return os.path.join(base_path, 'resources', filename)

# Function to check if a process is running
def check_if_process_running(process_name):
    return next((proc.info['exe'] for proc in psutil.process_iter(['name', 'exe']) 
                 if process_name.lower() in proc.info['name'].lower()), None)

# Function to find the Game.log file
def find_game_log(directory):
    for path in [os.path.join(directory, 'Game.log'), os.path.join(os.path.dirname(directory), 'Game.log')]:
        if os.path.exists(path):
            return path
    return None

# Function to set the SC_LOG_LOCATION
def set_sc_log_location():
    global SC_LOG_LOCATION
    rsi_launcher_path = check_if_process_running("RSI Launcher")
    if not rsi_launcher_path:
        update_status("RSI Launcher not running.")
        print("RSI Launcher not found.")
        return None

    sc_launcher_path = check_if_process_running("StarCitizen")
    if not sc_launcher_path:
        update_status("Star Citizen Launcher not running.")
        print("Star Citizen Launcher not found.")
        return None

    log_path = find_game_log(os.path.dirname(sc_launcher_path))
    if log_path:
        SC_LOG_LOCATION = log_path
        os.environ['SC_LOG_LOCATION'] = log_path
        update_status(f"Game.log found: {log_path}")
        print(f"Game.log found at: {log_path}")
        return log_path  # Return the log path here
    else:
        update_status("Game.log not found.")
        print("Game.log not found in expected locations.")
        return None  # Ensure we return None if not found

# Function to parse log lines for specific events
def parse_kill_line(line):
    global show_parsed_only

    # Patterns to match different events in the log
    patterns = {
        "vehicle_destroy": r"Vehicle '([^']+)'.*destroy level (\d+).*caused by '([^']+)'",
        "actor_death": r"CActor::Kill: '([^']+)'.*killed by '([^']+)'.*using '([^']+)'",
        "jump_drive": r"Changing state to (Idle|Active).*state to (Idle|Active)",
        "qt": r"Entity Trying To QT: '([^']+)",
        "transit_manager": r"\[ECarriageDoors\] : Reconciled Doors for carriage (\d+) with manager (TransitManager_[\w\d_-]+)",  # Capture manager names
        "door_state": r"Elevator Door (Opened|Closed)"  # Simplified pattern for door state
    }

    matched = False  # Track if we found a match

    for key, pattern in patterns.items():
        if match := re.search(pattern, line):
            matched = True
            if key == "vehicle_destroy":
                highlight_log(f"🚗 **Vehicle Destroyed**: {match.group(1)} at level {match.group(2)} by {match.group(3)}", 'red')

            elif key == "actor_death":
                if "PU_Human" in match.group(1) and "PU_Human" in match.group(2):
                    return  # Ignore this death
                highlight_log(f"💀 **Actor Death**: {match.group(1)} killed by {match.group(2)} using {match.group(3)}", 'purple')

            elif key == "jump_drive":
                highlight_log(f"🚀 **Jump Drive State Change**: Now {match.group(2)}", 'green')

            elif key == "qt":
                highlight_log(f"⚡ **Entity Trying To QT**: {match.group(1)}", 'purple')

            elif key == "transit_manager":
                carriage_id, manager_name = match.groups()

                # Alert for any transit manager containing 'Dungeon' in its name
                if 'Dungeon' in manager_name:
                    highlight_log(f"⚠️ **CONTESTED ZONE ELEVATORS** ⚠️\n🚨 Carriage {carriage_id} using {manager_name} 🚨", 'orange')

            elif key == "door_state":
                door_state = match.group(1)  # Capture Opened or Closed state

                # Log door state changes directly
                if door_state == "Opened":
                    highlight_log(f"🚪 **Elevator Opened**", 'yellow')
                elif door_state == "Closed":
                    highlight_log(f"🚪 **Elevator Closed**", 'yellow')

            break  # Exit loop after first match

    if not matched and not show_parsed_only:
        update_status(f"Log: {line.strip()}")

# Function to toggle between showing parsed events or full log
def toggle_parsed_only():
    global show_parsed_only
    show_parsed_only = not show_parsed_only
    update_status("🔥 Switched to **PARSED EVENTS ONLY** 🔥" if show_parsed_only else "📜 Showing **FULL LOG** again.")

def setup_highlight_tags():
    colors = {
        'red': 'Vehicle Destruction',
        'purple1': 'Actor Death',
        'green': 'Jump Drive State Change',
        'purple2': 'Entity Trying To QT',
        'orange': 'Contested Zone Elevator',
        'yellow': 'Elevator Door State'
    }
    for tag, description in colors.items():
        status_text.tag_configure(tag, foreground=tag)  # Tag name and color

def highlight_log(message, color):
    """Highlight log messages with different colors."""
    status_text.config(state=tk.NORMAL)
    
    # Map the color to the tag name (which was defined earlier)
    if color == 'red':
        tag = 'red'
    elif color == 'purple':
        tag = 'purple1'  # Choose 'purple1' or 'purple2' based on your logic
    elif color == 'green':
        tag = 'green'
    elif color == 'orange':
        tag = 'orange'
    elif color == 'yellow':
        tag = 'yellow'
    else:
        tag = None  # No tag if color is not recognized

    # Insert the message with the appropriate tag
    if tag:
        status_text.insert(tk.END, message + "\n", tag)
    else:
        status_text.insert(tk.END, message + "\n")  # Default, no color

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
    log_file = set_sc_log_location()  # This will now return the log path
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
    """Update status text in the GUI."""
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
    image = Image.open(ico_path)
    tray_icon = pystray.Icon("BlightVeil", image, menu=(item('Open', lambda: root.deiconify()), item('Exit', exit_app)))
    threading.Thread(target=tray_icon.run, daemon=True).start()

# Store a reference to the banner image
banner_image = None  # Initialize a variable to hold the banner image
if banner_path:
    banner = Image.open(banner_path).resize((480, 100), Image.LANCZOS)
    banner_image = ImageTk.PhotoImage(banner)  # Store the PhotoImage reference
    label_banner = tk.Label(root, image=banner_image, bg="#1e1e1e")
    label_banner.pack()

# Scrolled text box for displaying log messages
status_text = scrolledtext.ScrolledText(root, height=8, wrap=tk.WORD, fg="white", bg="#252526", state=tk.DISABLED)
status_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

# Set up text highlighting for different log types
setup_highlight_tags()  # <-- Make sure to call this function to set up the tags

# Buttons to start and stop monitoring
start_button = tk.Button(root, text="Start Monitoring", command=start_monitoring, bg="#0078D4", fg="white")
start_button.pack(pady=5)
stop_button = tk.Button(root, text="Stop Monitoring", command=stop_monitoring, bg="#D32F2F", fg="white")
stop_button.pack(pady=5)

# Toggle between parsed or full log
toggle_button = tk.Button(root, text="Toggle Parsed Log", command=toggle_parsed_only, bg="#6200EE", fg="white")
toggle_button.pack(pady=5)

root.protocol("WM_DELETE_WINDOW", on_closing)  # Ensure we handle the window close event
root.mainloop()

