import re
import os
import ast
import sys
import time
import json
import psutil
import pystray
import requests
import threading
import tkinter as tk
from PIL import Image, ImageTk
from pystray import MenuItem as item
from tkinter import messagebox, scrolledtext

# Global variables
show_parsed_only = True
debug_mode = False
last_log = {}
contested_elevator_tracking = {}  # Dictionary to track carriages
elevator_door_states = {}  # Dictionary to track door open/close state
elevator_states = {}
SC_LOG_LOCATION = None 
monitor_thread = None 
monitoring = True
# URL for dynamic zone mappings
zone_mappings_url = "https://raw.githubusercontent.com/BossGamer09/BVLogParcer/refs/heads/main/zone_mappings.json"

# Initialize zone_mappings dictionary
zone_mappings = {}
# Global variables
icon_positions = {
    "TransitDungeon_Exfil": (380, 169, "green"),
    "TransitDungeonRewardRoom": (249, 241, "yellow"),
    "TransitDungeonSideEntrance": (533, 77, "red"),
    "TransitDungeonMainEntrance": (729, 272, "red"),
    "TransitDungeonMaintenance_1": (554, 151, "orange"),
    "TransitDungeonMaintenance_2": (656, 291, "orange"),
}

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

# Function to handle contested zone elevator log parsing and icon updates for all elevators
def parse_contested_zone_elevator(line):
    global last_log, elevator_door_states  # Use the global last_log and elevator_door_states

    # Check for TransitCarriageStartTransit or TransitCarriageFinishTransit before processing
    if "TransitCarriageStartTransit" in line or "TransitCarriageFinishTransit" in line:
        # Handle door state changes for all elevators
        if "Opened:" in line or "Closed:" in line:
            match = re.search(r"TransitManager_TransitDungeon([^\s]+)", line)
            if match:
                manager_id = match.group(1)

                # First "Opened:" state for any elevator (side, main, maintenance, or reward room)
                if "Opened:" in line:
                    if manager_id not in elevator_door_states:  # First "Opened" state for this elevator
                        elevator_door_states[manager_id] = 'opened'
                        print(f"Event: {manager_id} Opened for the first time")
                        highlight_log(f"🚪 **Elevator Opened**: {manager_id}", 'yellow')
                        flash_icon("TransitDungeon_Exfil", icon_positions)

                elif "Closed:" in line:
                    if manager_id in elevator_door_states and elevator_door_states[manager_id] != 'closed':
                        elevator_door_states[manager_id] = 'closed'
                        print(f"Event: {manager_id} Closed")
                        highlight_log(f"🚪 **Elevator Closed**: {manager_id}", 'yellow')
                        flash_icon("TransitDungeonRewardRoom", icon_positions)

        # Handle exiting the contested zone (Exfil event)
        if "TransitDungeonExfil" in line:
            print("Event: TransitDungeonExfil")  # Debug: print event name
            highlight_log(f"🚪 **Exit Notice**: Someone has exited the Contested Zone (CZ)", 'red')
            flash_icon("TransitDungeon_Exfil", icon_positions)

        # Handle loot room (Reward Room) events
        if "TransitDungeonRewardRoom_" in line:
            print("Event: TransitDungeonRewardRoom")  # Debug: print event name
            highlight_log(f"💎 **Loot Room Alert**: Someone is in a Loot Room", 'yellow')
            flash_icon("TransitDungeonRewardRoom", icon_positions)

        # Handle each elevator type using simple if statements
        if "TransitDungeonSideEntrance" in line:
            print("Event: TransitDungeonSideEntrance")  # Debug: print event name
            highlight_log(f"🚪 **Side Entrance Alert**: Someone is at the Side Entrance", 'red')
            flash_icon("TransitDungeonSideEntrance", icon_positions)

        if "TransitDungeonMainEntrance" in line:
            print("Event: TransitDungeonMainEntrance")  # Debug: print event name
            highlight_log(f"🚪 **Main Entrance Alert**: Someone is at the Main Entrance", 'red')
            flash_icon("TransitDungeonMainEntrance", icon_positions)

        if "TransitDungeonMaintenance" in line:
            print("Event: TransitDungeonMaintenance")  # Debug: print event name
            highlight_log(f"🚪 **Maintenance Alert**: Someone is at the Maintenance Entrance", 'orange')
            flash_icon("TransitDungeonMaintenance_1", icon_positions)
            flash_icon("TransitDungeonMaintenance_2", icon_positions)

        if "TransitDungeonRewardRoom" in line:
            print("Event: TransitDungeonRewardRoom")  # Debug: print event name
            highlight_log(f"💎 **Loot Room Alert**: Someone is in a Loot Room", 'yellow')
            flash_icon("TransitDungeonRewardRoom", icon_positions)

# Function to flash icons on the map for specific events
def flash_icon(event_name, icon_positions):
    """Flash the appropriate icon based on the event."""
    if icon_positions is not None and event_name in icon_positions:
        x, y, reset_color = icon_positions[event_name]
        icon = icons.get(event_name)
        if icon:
            def toggle_flash(count):
                # Toggle between white and the original color
                current_color = "white" if count % 2 == 0 else reset_color
                canvas.itemconfig(icon, fill=current_color)  # Ensure this is updating the right icon

                # Continue flashing for more cycles
                if count < 10:  # Flash 10 times
                    canvas.after(500, toggle_flash, count + 1)  # 500ms delay between flashes
                else:
                    # Reset to the original color after flashing
                    canvas.itemconfig(icon, fill=reset_color)
            # Start flashing (starting count = 0)
            toggle_flash(0)
        else:
            print(f"Warning: Icon for event '{event_name}' not found in icons.")  # Debugging line
    else:
        print(f"Warning: Icon for event '{event_name}' not found in icon_positions.")  # Debugging line
        
def fetch_zone_mappings():
    global zone_mappings  # Ensure it's modifying the global variable
    try:
        update_status("Fetching zone mappings from URL...")
        response = requests.get(zone_mappings_url)  # Only call this once

        if response.status_code == 200:
            print(f"Raw data from URL: {response.text}")  # Add this line to print the raw response
            zone_mappings = ast.literal_eval(response.text)

            # Debug: print the mappings to check if they are parsed correctly
            update_status(f"Successfully fetched zone mappings: {zone_mappings}")
        else:
            update_status(f"Error fetching zone mappings. Status Code: {response.status_code}")
    
    except Exception as e:
        update_status(f"Error loading zone mappings: {e}")


def parse_kill_line(line, flash_icon, icon_positions):
    global show_parsed_only
    global zone_mappings

    patterns = {
        "vehicle_destroy": r"Vehicle '([^']+)'.*destroy level (\d+).*caused by '([^']+)'",
        "actor_death": r"CActor::Kill: '([^']+)' \[([^\]]+)\] in zone '([^']+)' killed by '([^']+)' \[([^\]]+)\] using '([^']+)'",  
        "jump_drive": r"Changing state to (Idle|Active).*state to (Idle|Active)",
        "qt": r"Entity Trying To QT: '([^']+)",
    }

    parse_contested_zone_elevator(line)

    matched = False  
    for key, pattern in patterns.items():
        if match := re.search(pattern, line):
            matched = True
            if key == "actor_death":
                actor_name = match.group(1)
                actor_id = match.group(2)  # Actor ID captured from the log
                zone = match.group(3)  
                killer_name = match.group(4)
                killer_id = match.group(5)  # Killer ID captured from the log
                weapon = match.group(6)  # Weapon used in the death

                print(f"Captured kill: {actor_name} ({actor_id}) killed by {killer_name} ({killer_id}) with {weapon} in zone {zone}")
                
                # Ensure the zone name is mapped correctly
                zone_name = zone_mappings.get(zone, zone)  # Use zone from mapping or default to the zone itself
                print(f"Mapped zone: {zone_name}")  # Debug print for zone mapping
                
                highlight_log(f"💀 **Actor Death**: {actor_name} killed by {killer_name} using {weapon} in zone {zone_name}", 'purple')

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

    # Insert the message with the appropriate tag using after to schedule the update
    def insert_message():
        if tag:
            status_text.insert(tk.END, message + "\n", tag)
        else:
            status_text.insert(tk.END, message + "\n")  # Default, no color
        status_text.config(state=tk.DISABLED)
        status_text.yview(tk.END)

    status_text.after(0, insert_message)  # Schedule the update on the main thread

# Function to tail the Game.log file and parse the lines
def tail_log(log_file_location, flash_icon, icon_positions):
    global monitoring
    with open(log_file_location, "r") as log_file:
        log_file.seek(0, os.SEEK_END)  # Start reading from the end of the file
        while monitoring:
            line = log_file.readline()  # Read new line from log file
            if line:
                parse_kill_line(line, flash_icon, icon_positions)  # Parse kill log lines
            else:
                time.sleep(1)  # Wait for new lines in the log file

# Function to start monitoring the Game.log file
def start_monitoring(flash_icon=None, icon_positions=None):
    global monitoring, monitor_thread

    # Display connecting message
    update_status("Connecting to fetch zone mappings...")

    if monitoring:
        return

    # Start the zone mapping fetch operation
    fetch_zone_mappings()  # Fetch zone mappings

    if not zone_mappings:  # Check if zone mappings were successfully fetched
        update_status("Error: Zone mappings could not be loaded.")
        return

    # Zone mappings fetched successfully, proceed with log monitoring
    log_file = set_sc_log_location()  # This will now return the log path
    if log_file:
        monitoring = True
        monitor_thread = threading.Thread(target=tail_log, args=(log_file, flash_icon, icon_positions), daemon=True)
        monitor_thread.start()
        update_status("Monitoring started.")
        
        # Enable the buttons once everything is set up
        start_button.config(state=tk.DISABLED)  # Disable the Start button once monitoring starts
        stop_button.config(state=tk.NORMAL)     # Enable the Stop button
    else:
        messagebox.showerror("Error", "Game.log not found.")

# Function to stop monitoring
def stop_monitoring():
    global monitoring
    monitoring = False
    update_status("Monitoring stopped.")
    
    # Disable stop button and re-enable start button
    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)

# Function to update the status in the GUI
def update_status(message):
    """Update status text in the GUI."""
    def insert_status():
        status_text.config(state=tk.NORMAL)
        status_text.insert(tk.END, message + "\n")
        status_text.config(state=tk.DISABLED)
        status_text.yview(tk.END)

    status_text.after(0, insert_status)  # Use after to ensure thread-safety

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

def handle_checkmate():
    """Handle the action when the Checkmate button is clicked."""
    update_status("🎮 **Checkmate Selected**: Opening Checkmate window.")
    
    global checkmate_window, canvas, icons, map_photo
    checkmate_window = tk.Toplevel(root)
    checkmate_window.title("Checkmate View")
    checkmate_window.geometry("800x600")  # Fixed size
    checkmate_window.configure(bg="#1e1e1e")
    checkmate_window.resizable(False, False)  # Lock the window size to prevent resizing

    # Load the map image
    map_image_path = get_resource_path("Star_Citizen_Contested_Zones_Checkmate_Map.jpg")
    print(f"Loading image from: {map_image_path}")
    map_image = Image.open(map_image_path).resize((800, 600), Image.Resampling.LANCZOS)
    map_photo = ImageTk.PhotoImage(map_image)

    # Create canvas and draw image
    canvas = tk.Canvas(checkmate_window, width=800, height=600)
    canvas.pack(fill=tk.BOTH, expand=True)

    # Use create_image to add the image to the canvas
    canvas.create_image(400, 300, anchor=tk.CENTER, image=map_photo)  # Center the image

    # Draw the icons on the canvas at fixed positions
    icons = {}
    for name, (x, y, color) in icon_positions.items():
        icons[name] = canvas.create_oval(x-10, y-10, x+10, y+10, fill=color, outline="white", width=2)

    update_status("🗺️ **Map Loaded**: Icons are now active.")
    
    # Pass the required arguments when calling start_monitoring
    start_monitoring(flash_icon)  # Now it correctly receives `flash_icon`

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

# Button to open the Checkmate map
checkmate_button = tk.Button(root, text="Open Checkmate Map", command=handle_checkmate, bg="#4CAF50", fg="white")
checkmate_button.pack(pady=5)

# Toggle between parsed or full log
toggle_button = tk.Button(root, text="Toggle Parsed Log", command=toggle_parsed_only, bg="#6200EE", fg="white")
toggle_button.pack(pady=5)

root.protocol("WM_DELETE_WINDOW", on_closing)  # Ensure we handle the window close event
root.mainloop()
