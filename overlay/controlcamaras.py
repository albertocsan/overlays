import customtkinter as ctk
from tkinter import ttk
import tkinter as tk
from tkinter import messagebox
import irsdk
import threading
import time
import math
import json
import os

from license_info import LICENSE_TEXT, BUILD_ID

# --- Configuration & Constants ---
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

RSEARCH_MODE_TO_END = 1
RSEARCH_MODE_PREV_LAP = 4
RSEARCH_MODE_NEXT_LAP = 5
REFRESH_RATE_MS = 50
LAYOUT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "director_layout.json")

class ModernIRacingApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window Setup
        self.title(f"iRacing Director - Modern UI  |  {LICENSE_TEXT}  [{BUILD_ID}]")
        self.geometry("1200x700")
        self.minsize(1000, 600)
        
        # iRacing SDK
        self.ir = irsdk.IRSDK()
        
        # State Variables
        self.is_collecting_data = False
        self.drivers_data = []
        self.cameras = []
        self.car_idx_to_name = {}

        # Freeze UI updates during window move/resize
        self._ui_frozen = False
        self._freeze_after_id = None
        self.bind("<Configure>", self._on_configure)
        
        # Telemetry State
        self.last_positions_race = {}
        self.last_lap_dist_pct = {}
        self.pit_entry_pct = -1.0
        self.is_qualifying_session = False
        self.last_laps_completed = {}
        self.personal_best_laps = {}
        self.compound_map = {0: 'Dry', 1: 'Wet'}

        # Sector tracking for qualifying
        self.track_sectors = []
        self.sector_data = {}
        self.session_best_sectors = {}
        self.driver_best_sectors = {}

        # Pit stop tracking
        self.last_pit_state = {}
        self.pit_entry_times = {}
        self.pit_stop_counts = {}
        self.last_pit_duration = {}
        # Pit box (stationary) tracking — CarIdxTrackSurface == 1
        self.last_surface_state = {}      # {car_idx: track_surface} for transition detection
        self.pit_box_entry_times = {}     # {car_idx: session_time} when car entered pit stall
        self.last_pit_box_duration = {}   # {car_idx: seconds} duration of last pit box stop

        # Event tracking
        self.last_session_state = -1
        self.last_track_surfaces = {}
        self.last_flag_state = "normal"  # "normal" | "yellow" | "sc"
        self.overtake_cooldowns = {}     # {frozenset({carA, carB}): session_time} cooldown per pair
        self.car_stopped_since = {}      # {car_idx: session_time} when car first went below stop threshold
        self.car_stopped_reported = {}   # {car_idx: bool} whether stopped event was already fired this stop
        self.green_flag_time = None      # session_time when green flag dropped (for standing-start grace period)
        self.replay_delay = 3.0  # Default 3 seconds

        # Minisector reference-point timing system
        NUM_MINISECTORS = 25
        self.minisector_pcts = [i / NUM_MINISECTORS for i in range(NUM_MINISECTORS)]
        self.crossing_times = {}      # {car_idx: {minisector_idx: session_time}}
        self.last_car_minisector = {}  # {car_idx: last_pct} to detect crossings

        # --- Layout Construction ---
        self._setup_layout()
        self._apply_treeview_style()

        # Load saved layout (geometry + sash positions)
        self._load_layout()

        # Initial Check
        self.check_connection_static()

    def _setup_layout(self):
        """Builds a 3-pane resizable layout using PanedWindow"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        self.header_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew")

        self.title_label = ctk.CTkLabel(self.header_frame, text="iRacing Director // Live Timing", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(side="left", padx=20, pady=10)

        self.status_indicator = ctk.CTkLabel(self.header_frame, text="⚫ Disconnected", text_color="gray", font=ctk.CTkFont(size=14))
        self.status_indicator.pack(side="right", padx=20)

        self.save_layout_btn = ctk.CTkButton(self.header_frame, text="Save Layout", width=100, height=28,
                                              font=ctk.CTkFont(size=11), command=self._save_layout)
        self.save_layout_btn.pack(side="right", padx=(0, 10))

        self.next_car_btn = ctk.CTkButton(self.header_frame, text="Car Ahead ▶", width=90, height=28,
                                           font=ctk.CTkFont(size=11), command=lambda: self._switch_to_adjacent_car(1))
        self.next_car_btn.pack(side="right", padx=(0, 5))

        self.prev_car_btn = ctk.CTkButton(self.header_frame, text="◀ Car Behind", width=90, height=28,
                                           font=ctk.CTkFont(size=11), command=lambda: self._switch_to_adjacent_car(-1))
        self.prev_car_btn.pack(side="right", padx=(0, 5))

        # --- Resizable PanedWindow ---
        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6, sashrelief=tk.RAISED,
                                     bg="#333333", opaqueresize=False)
        self.paned.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))

        # --- Pane 1: Drivers ---
        self.driver_frame = ctk.CTkFrame(self.paned, corner_radius=10)

        ctk.CTkLabel(self.driver_frame, text="Drivers (Positional)", font=ctk.CTkFont(weight="bold")).pack(pady=5)

        # Treeview with horizontal scrollbar
        driver_tree_frame = ctk.CTkFrame(self.driver_frame, fg_color="transparent")
        driver_tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.driver_tree_xscroll = ttk.Scrollbar(driver_tree_frame, orient="horizontal")
        self.driver_tree = ttk.Treeview(driver_tree_frame, columns=("Pos", "Num", "Name", "Tire"), show="headings",
                                         selectmode="browse", xscrollcommand=self.driver_tree_xscroll.set)
        self.driver_tree_xscroll.config(command=self.driver_tree.xview)
        self._configure_race_columns()

        self.driver_tree.pack(fill="both", expand=True, side="top")
        self.driver_tree_xscroll.pack(fill="x", side="bottom")

        # Double-click on a driver to switch camera focus to them
        self.driver_tree.bind('<Double-1>', self._on_driver_double_click)

        # Add driver pane — default width is ~200 (half of previous ~400)
        self.paned.add(self.driver_frame, minsize=150, width=200)

        # --- Pane 2: Cameras & Controls ---
        self.center_frame = ctk.CTkFrame(self.paned, corner_radius=10)

        # Camera Buttons Scrollable Area
        self.camera_scroll = ctk.CTkScrollableFrame(self.center_frame, label_text="Cameras", label_font=ctk.CTkFont(weight="bold"))
        self.camera_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Configure grid for 2 columns of buttons
        self.camera_scroll.grid_columnconfigure(0, weight=1)
        self.camera_scroll.grid_columnconfigure(1, weight=1)

        # Replay Controls Container
        self.controls_frame = ctk.CTkFrame(self.center_frame, fg_color="transparent")
        self.controls_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(self.controls_frame, text="Replay Control", font=ctk.CTkFont(size=12)).pack(pady=(0,5))

        # Grid for buttons
        btn_grid = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        btn_grid.pack(fill="x")

        # Replay Buttons
        self.btn_rewind = ctk.CTkButton(btn_grid, text="<<", width=40, command=lambda: self.set_replay_speed(-4))
        self.btn_rewind.grid(row=0, column=0, padx=2, pady=2)

        self.btn_prev = ctk.CTkButton(btn_grid, text="< Lap", width=50, command=lambda: self.seek_lap(RSEARCH_MODE_PREV_LAP))
        self.btn_prev.grid(row=0, column=1, padx=2, pady=2)

        self.btn_slow = ctk.CTkButton(btn_grid, text="Slow", width=50, command=lambda: self.set_replay_speed(0.5))
        self.btn_slow.grid(row=0, column=2, padx=2, pady=2)

        self.btn_play = ctk.CTkButton(btn_grid, text="Play", width=50, fg_color="#2CC985", text_color="white", command=lambda: self.set_replay_speed(1))
        self.btn_play.grid(row=0, column=3, padx=2, pady=2)

        self.btn_next = ctk.CTkButton(btn_grid, text="Lap >", width=50, command=lambda: self.seek_lap(RSEARCH_MODE_NEXT_LAP))
        self.btn_next.grid(row=0, column=4, padx=2, pady=2)

        self.btn_ff = ctk.CTkButton(btn_grid, text=">>", width=40, command=lambda: self.set_replay_speed(4))
        self.btn_ff.grid(row=0, column=5, padx=2, pady=2)

        self.btn_live = ctk.CTkButton(self.controls_frame, text="JUMP TO LIVE", fg_color="#C92C2C", hover_color="#8a1e1e", command=self.go_to_live)
        self.btn_live.pack(fill="x", pady=(5,0))

        # Replay Delay Control
        delay_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        delay_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkLabel(delay_frame, text="Replay Delay:", font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 5))
        self.delay_slider = ctk.CTkSlider(delay_frame, from_=0, to=10, number_of_steps=20, command=self._update_delay)
        self.delay_slider.set(3.0)
        self.delay_slider.pack(side="left", fill="x", expand=True, padx=5)

        self.delay_label = ctk.CTkLabel(delay_frame, text="3.0s", width=40)
        self.delay_label.pack(side="left")

        # Track Map Canvas
        self.track_map_frame = ctk.CTkFrame(self.center_frame)
        self.track_map_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(self.track_map_frame, text="Track Map", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(5, 0))

        self.track_canvas = tk.Canvas(self.track_map_frame, bg="#2b2b2b", highlightthickness=0, width=200, height=200)
        self.track_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        self.track_canvas.bind('<Button-1>', self._on_track_map_click)

        # Main Toggle
        self.toggle_btn = ctk.CTkButton(self.center_frame, text="START TELEMETRY", height=40, font=ctk.CTkFont(weight="bold"), command=self.toggle_data_collection)
        self.toggle_btn.pack(fill="x", padx=10, pady=20)

        # Add center pane
        self.paned.add(self.center_frame, minsize=250, width=350)

        # --- Pane 3: Event Logs ---
        self.log_frame = ctk.CTkFrame(self.paned, corner_radius=10)

        ctk.CTkLabel(self.log_frame, text="Live Event Log", font=ctk.CTkFont(weight="bold")).pack(pady=5)

        # Treeview with horizontal scrollbar
        log_tree_frame = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.log_tree_xscroll = ttk.Scrollbar(log_tree_frame, orient="horizontal")
        self.log_tree = ttk.Treeview(log_tree_frame, columns=("Time", "Event"), show="headings",
                                      selectmode="browse", xscrollcommand=self.log_tree_xscroll.set)
        self.log_tree_xscroll.config(command=self.log_tree.xview)
        self.log_tree.heading("Time", text="Session Time")
        self.log_tree.heading("Event", text="Description")
        self.log_tree.column("Time", width=100, anchor="center")
        self.log_tree.column("Event", width=400, anchor="w")

        self.log_tree.pack(fill="both", expand=True, side="top")
        self.log_tree_xscroll.pack(fill="x", side="bottom")
        self.log_tree.bind('<Double-1>', self.jump_to_log_event)

        # Add log pane — gets the remaining space
        self.paned.add(self.log_frame, minsize=200)

    def _configure_race_columns(self):
        """Configure columns for race sessions"""
        self.driver_tree["columns"] = ("Pos", "Num", "Name", "Gap", "Int", "Tire", "Pits", "PitLane", "PitBox")
        self.driver_tree.heading("Pos", text="P")
        self.driver_tree.heading("Num", text="#")
        self.driver_tree.heading("Name", text="Driver")
        self.driver_tree.heading("Gap", text="Gap")
        self.driver_tree.heading("Int", text="Int")
        self.driver_tree.heading("Tire", text="Tire")
        self.driver_tree.heading("Pits", text="Pits")
        self.driver_tree.heading("PitLane", text="Lane")
        self.driver_tree.heading("PitBox", text="Box")

        self.driver_tree.column("Pos", width=30, anchor="center")
        self.driver_tree.column("Num", width=40, anchor="center")
        self.driver_tree.column("Name", width=110, anchor="w")
        self.driver_tree.column("Gap", width=65, anchor="e")
        self.driver_tree.column("Int", width=60, anchor="e")
        self.driver_tree.column("Tire", width=40, anchor="center")
        self.driver_tree.column("Pits", width=35, anchor="center")
        self.driver_tree.column("PitLane", width=55, anchor="e")
        self.driver_tree.column("PitBox", width=55, anchor="e")

    def _configure_qualifying_columns(self):
        """Configure columns for qualifying sessions"""
        self.driver_tree["columns"] = ("Pos", "Num", "Name", "Gap", "Lap", "S1", "S2", "S3", "Pits", "PitLane", "PitBox")
        self.driver_tree.heading("Pos", text="P")
        self.driver_tree.heading("Num", text="#")
        self.driver_tree.heading("Name", text="Driver")
        self.driver_tree.heading("Gap", text="Gap")
        self.driver_tree.heading("Lap", text="Lap")
        self.driver_tree.heading("S1", text="S1")
        self.driver_tree.heading("S2", text="S2")
        self.driver_tree.heading("S3", text="S3")
        self.driver_tree.heading("Pits", text="Pits")
        self.driver_tree.heading("PitLane", text="Lane")
        self.driver_tree.heading("PitBox", text="Box")

        self.driver_tree.column("Pos", width=30, anchor="center")
        self.driver_tree.column("Num", width=40, anchor="center")
        self.driver_tree.column("Name", width=150, anchor="w")
        self.driver_tree.column("Gap", width=80, anchor="e")
        self.driver_tree.column("Lap", width=60, anchor="center")
        self.driver_tree.column("S1", width=35, anchor="center")
        self.driver_tree.column("S2", width=35, anchor="center")
        self.driver_tree.column("S3", width=35, anchor="center")
        self.driver_tree.column("Pits", width=35, anchor="center")
        self.driver_tree.column("PitLane", width=55, anchor="e")
        self.driver_tree.column("PitBox", width=55, anchor="e")

    def _apply_treeview_style(self):
            """Forces Tkinter Treeview to match CustomTkinter Dark Theme and adds Faded style"""
            style = ttk.Style()
            style.theme_use("default")
            
            # Configure Treeview colors
            style.configure("Treeview", 
                            background="#2b2b2b", 
                            foreground="white", 
                            fieldbackground="#2b2b2b", 
                            borderwidth=0,
                            font=("Segoe UI", 10))
            
            style.map('Treeview', background=[('selected', '#1f538d')])
            
            # Configure Header
            style.configure("Treeview.Heading", 
                            background="#3a3a3a", 
                            foreground="white", 
                            relief="flat",
                            font=("Segoe UI", 10, "bold"))
            
            style.map("Treeview.Heading", background=[('active', '#4a4a4a')])

            # --- NEW: Define the 'faded' tag style here ---
            # We don't use style.configure for row tags, we use tag_configure in the widget,
            # but we can set up the selection map here if needed.
            # (The actual color definition happens in _update_driver_tree)

    # --- Logic Core (Adapted from previous version) ---
    
    def check_connection_static(self):
        if self.ir.startup():
            self.status_indicator.configure(text="🟢 Connected", text_color="#2CC985")
            self.ir.freeze_var_buffer_latest()
            # CALL THE NEW BUTTON GENERATOR
            self._update_camera_buttons()
        else:
            self.status_indicator.configure(text="⚫ Disconnected (Waiting...)", text_color="gray")

    def switch_camera_by_group_id(self, group_num):
        """Switches the camera for the currently selected driver"""
        # 1. Check if a driver is selected in the Treeview
        sel = self.driver_tree.selection()
        if not sel:
            # Optional: Select the leader (P1) if no one is selected?
            # For now, just warn
            print("Select a driver first!")
            return
        
        try:
            # 2. Get CarIdx from the selected row's tags
            tags = self.driver_tree.item(sel[0], 'tags')
            if not tags: return
            car_idx = int(tags[0])
            
            # 3. Find the Driver's info to get the Car Number
            # We look in our self.drivers_data cache
            driver_info = next((d for d in self.drivers_data if d['CarIdx'] == car_idx), None)
            
            if driver_info:
                print(f"Switching {driver_info['Name']} (#{driver_info['Num']}) to Camera Group {group_num}")
                self.ir.cam_switch_num(driver_info['Num'], group_num, 0)
                
        except Exception as e:
            print(f"Camera Switch Error: {e}")

    def _switch_to_adjacent_car(self, direction):
        """Switch focus to the car physically ahead (+1) or behind (-1) on track."""
        if not self.ir.is_connected:
            return
        try:
            focused_idx = self.ir['CamCarIdx']
            dist_pcts = self.ir['CarIdxLapDistPct']
            track_surfaces = self.ir['CarIdxTrackSurface']

            if dist_pcts is None:
                return

            # Build list of (lap_dist_pct, car_idx) for cars actually on track
            cars_on_track = []
            for car_idx in range(len(dist_pcts)):
                pct = dist_pcts[car_idx]
                if pct < 0:
                    continue
                # Skip cars not in world
                if track_surfaces and car_idx < len(track_surfaces) and track_surfaces[car_idx] in [-1, 0]:
                    continue
                cars_on_track.append((pct, car_idx))

            if not cars_on_track:
                return

            # Sort by physical position on track (0.0 → 1.0, ascending)
            cars_on_track.sort(key=lambda x: x[0])

            # Find the focused car in the sorted list
            focused_index = None
            for i, (_, car_idx) in enumerate(cars_on_track):
                if car_idx == focused_idx:
                    focused_index = i
                    break

            if focused_index is None:
                return

            # Sorted ascending by pct: index+1 = car ahead, index-1 = car behind
            # direction +1 = car ahead, direction -1 = car behind
            target_index = (focused_index + direction) % len(cars_on_track)
            target_car_idx = cars_on_track[target_index][1]

            # Find driver info for the target car
            driver_info = next((d for d in self.drivers_data if d['CarIdx'] == target_car_idx), None)
            if not driver_info:
                # Fallback: look in DriverInfo directly
                for d in self.ir['DriverInfo']['Drivers']:
                    if d['CarIdx'] == target_car_idx:
                        driver_info = {'Num': d['CarNumber'], 'Name': d['UserName']}
                        break

            if driver_info:
                current_group = self.ir['CamGroupNumber']
                label = "ahead" if direction == 1 else "behind"
                print(f"Switching to car {label}: #{driver_info['Num']} {driver_info['Name']}")
                self.ir.cam_switch_num(driver_info['Num'], current_group, 0)

        except Exception as e:
            print(f"Adjacent car switch error: {e}")

    def _on_driver_double_click(self, event):
        """Switch camera focus to the double-clicked driver, keeping the current camera group."""
        sel = self.driver_tree.selection()
        if not sel:
            return

        try:
            tags = self.driver_tree.item(sel[0], 'tags')
            if not tags:
                return
            car_idx = int(tags[0])

            driver_info = next((d for d in self.drivers_data if d['CarIdx'] == car_idx), None)
            if not driver_info:
                return

            # Get the current camera group so we keep the same angle
            current_group = 0
            try:
                current_group = self.ir['CamGroupNumber']
            except:
                pass

            print(f"Focusing on {driver_info['Name']} (#{driver_info['Num']}) - Camera Group {current_group}")
            self.ir.cam_switch_num(driver_info['Num'], current_group, 0)
        except Exception as e:
            print(f"Focus driver error: {e}")

    def _update_camera_buttons(self):
        """Generates buttons for each camera group in the scrollable frame"""
        try:
            current_groups = self.ir['CameraInfo']['Groups']
            
            # Check if camera list actually changed to avoid rebuilding buttons constantly
            current_group_names = [g['GroupName'] for g in current_groups]
            stored_group_names = [g['GroupName'] for g in self.cameras]
            
            if current_group_names == stored_group_names:
                return # No change, skip

            self.cameras = current_groups
            
            # Clear existing buttons
            for widget in self.camera_scroll.winfo_children():
                widget.destroy()
            self.camera_scroll.update_idletasks()  # Force canvas to repaint cleared area

            # Camera display name aliases (GroupName → label shown in UI)
            _CAM_ALIASES = {
                'Nose':     'Salp. Fuera',
                'Roll Bar': 'Piloto',
                'Gearbox':  'Ala Tras',
            }

            # Create new buttons
            for i, cam in enumerate(self.cameras):
                cam_name = _CAM_ALIASES.get(cam['GroupName'], cam['GroupName'])
                grp_num = cam['GroupNum']

                # We use a lambda with default arg (n=grp_num) to capture the value loop-safely
                btn = ctk.CTkButton(
                    self.camera_scroll,
                    text=cam_name,
                    height=30,
                    fg_color="#3a3a3a",
                    hover_color="#1f538d",
                    command=lambda n=grp_num: self.switch_camera_by_group_id(n)
                )
                
                # Arrange in 2 columns
                row = i // 2
                col = i % 2
                btn.grid(row=row, column=col, padx=3, pady=3, sticky="ew")

            self.camera_scroll.update_idletasks()  # Force scroll region recalc after adding buttons

        except Exception as e:
            print(f"Error updating cameras: {e}")

    def _on_configure(self, event):
        """Freeze UI-heavy updates while window is being moved/resized."""
        if event.widget is self:
            self._ui_frozen = True
            if self._freeze_after_id:
                self.after_cancel(self._freeze_after_id)
            self._freeze_after_id = self.after(200, self._unfreeze_ui)

    def _unfreeze_ui(self):
        self._ui_frozen = False
        self._freeze_after_id = None

    def master_loop(self):
        if not self.is_collecting_data: return

        if not self.ir.is_connected:
            if self.ir.startup():
                self.status_indicator.configure(text="🟢 Connected", text_color="#2CC985")
            else:
                self.status_indicator.configure(text="🔴 Reconnecting...", text_color="#C92C2C")
                self.after(2000, self.master_loop)
                return

        self.ir.freeze_var_buffer_latest()

        # Update minisector crossing times every tick (for gap calculation)
        self._update_minisector_crossings()

        # Track pit stops for all session types
        self._track_pit_stops()

        # Update sectors for qualifying/practice
        if self.is_qualifying_session:
            self._update_sector_times()

        # Skip UI-heavy work while window is being moved/resized
        if not self._ui_frozen:
            self._process_drivers_and_positions()
            self._log_events_logic()
            self._draw_track_map()

        self.after(REFRESH_RATE_MS, self.master_loop)

    def _process_drivers_and_positions(self):
        try:
            # Check session type and reconfigure columns if needed
            session_type = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]['SessionType']
            was_qualifying = self.is_qualifying_session
            self.is_qualifying_session = "Qualify" in session_type or "Practice" in session_type

            # Reconfigure columns if session type changed
            if was_qualifying != self.is_qualifying_session:
                if self.is_qualifying_session:
                    self._configure_qualifying_columns()
                    self._init_sectors()
                else:
                    self._configure_race_columns()

            # 1. Fetch Basic Info
            driver_info_list = self.ir['DriverInfo']['Drivers']
            positions = self.ir['CarIdxPosition']
            tire_compounds = self.ir['CarIdxTireCompound']

            # 2. Fetch Data required for your logic
            on_pit_road_arr = self.ir['CarIdxOnPitRoad']
            track_surface_arr = self.ir['CarIdxTrackSurface']

            # 3. Fetch data for virtual positions and qualifying
            lap_arr = self.ir['CarIdxLap']
            lap_dist_pct_arr = self.ir['CarIdxLapDistPct']

            current_data = []

            for d in driver_info_list:
                car_idx = d['CarIdx']

                # Skip if not a real driver
                if d.get('UserID', 0) <= 0:
                    continue

                # --- POSITION LOGIC ---
                pos = positions[car_idx] if car_idx < len(positions) else 999
                if pos <= 0: pos = 999

                # --- TIRE LOGIC ---
                tire_idx = tire_compounds[car_idx] if car_idx < len(tire_compounds) else 0
                tire_str = self.compound_map.get(tire_idx, "Dry")

                # --- PIT / ABANDONED LOGIC ---
                current_on_pit_road = False
                if car_idx < len(on_pit_road_arr):
                    current_on_pit_road = on_pit_road_arr[car_idx]

                car_abandoned = False
                if car_idx < len(track_surface_arr):
                    track_surface = track_surface_arr[car_idx]
                    car_abandoned = track_surface in [-1, 0]

                is_faded = current_on_pit_road or car_abandoned

                # --- LAP AND PROGRESS DATA ---
                current_lap = lap_arr[car_idx] if car_idx < len(lap_arr) else 0
                lap_progress = lap_dist_pct_arr[car_idx] if car_idx < len(lap_dist_pct_arr) else 0

                # Track position for race sorting
                track_position = (current_lap * 100) + lap_progress

                entry = {
                    'CarIdx': car_idx,
                    'Num': d['CarNumber'],
                    'Name': d['UserName'],
                    'Pos': pos,
                    'Tire': tire_str,
                    'IsFaded': is_faded,
                    'CurrentLap': current_lap,
                    'LapProgress': lap_progress,
                    'TrackPosition': track_position,
                    'PitStops': self.pit_stop_counts.get(car_idx, 0),
                    'LastPitTime': self.last_pit_duration.get(car_idx, None),
                    'LastPitBoxTime': self.last_pit_box_duration.get(car_idx, None)
                }

                # Add qualifying-specific data
                if self.is_qualifying_session:
                    entry.update(self._get_qualifying_data(car_idx))

                current_data.append(entry)
                self.car_idx_to_name[car_idx] = f"#{d['CarNumber']} {d['UserName']}"

            # Sort based on session type
            if self.is_qualifying_session:
                # Sort by best lap time
                current_data.sort(key=lambda x: x.get('BestLapSeconds', 999999))
                # Assign positions
                for idx, driver in enumerate(current_data):
                    driver['Pos'] = idx + 1
            else:
                # RACE: Sort by virtual track position (lap + progress)
                current_data.sort(key=lambda x: x['TrackPosition'], reverse=True)
                # Assign virtual positions
                for idx, driver in enumerate(current_data):
                    driver['Pos'] = idx + 1

                # Calculate estimated gaps to leader
                self._calculate_race_gaps(current_data)

            self.drivers_data = current_data

            self._update_driver_tree()
        except Exception as e:
            print(f"Data error: {e}")

    def _update_minisector_crossings(self):
        """Record the session time when each car crosses each minisector reference point."""
        try:
            dist_pcts = self.ir['CarIdxLapDistPct']
            session_time = self.ir['SessionTime']
            car_laps = self.ir['CarIdxLap']

            if not dist_pcts or not car_laps:
                return

            for car_idx, current_pct in enumerate(dist_pcts):
                if current_pct < 0:  # Car not on track
                    continue

                last_pct = self.last_car_minisector.get(car_idx, -1.0)

                # Initialize crossing data for this car
                if car_idx not in self.crossing_times:
                    self.crossing_times[car_idx] = {}

                # Check each minisector boundary
                for ms_idx, ms_pct in enumerate(self.minisector_pcts):
                    # Detect forward crossing of this boundary
                    if last_pct < ms_pct <= current_pct:
                        self.crossing_times[car_idx][ms_idx] = session_time
                    # Handle lap wrap-around (crossing start/finish, minisector 0)
                    elif ms_idx == 0 and current_pct < 0.05 and last_pct > 0.95:
                        self.crossing_times[car_idx][0] = session_time

                self.last_car_minisector[car_idx] = current_pct

        except Exception as e:
            print(f"Minisector update error: {e}")

    def _get_gap_at_reference_point(self, car_a_idx, car_b_idx):
        """
        Calculate the time gap between two cars at the most recent common
        reference point that car_b has crossed.
        Returns gap in seconds (positive = car_b is behind car_a), or None.
        """
        times_a = self.crossing_times.get(car_a_idx)
        times_b = self.crossing_times.get(car_b_idx)

        if not times_a or not times_b:
            return None

        # Find the most recent minisector that car_b has crossed,
        # where car_a also has a recorded time
        best_gap = None
        best_ms_time_b = -1  # Track the most recent crossing by car_b

        for ms_idx in times_b:
            if ms_idx in times_a:
                time_b = times_b[ms_idx]
                time_a = times_a[ms_idx]
                # Use the most recently crossed sector by car_b
                if time_b > best_ms_time_b:
                    best_ms_time_b = time_b
                    best_gap = time_b - time_a

        return best_gap

    def _calculate_race_gaps(self, drivers_list):
        """Calculate gap to leader and interval to car ahead using minisector reference points."""
        if not drivers_list or len(drivers_list) == 0:
            return

        try:
            leader = drivers_list[0]
            leader_idx = leader['CarIdx']
            leader_track_pos = leader['TrackPosition']

            for i, driver in enumerate(drivers_list):
                if driver['Pos'] == 1:
                    driver['EstGap'] = "Leader"
                    driver['Interval'] = "-"
                    continue

                car_idx = driver['CarIdx']

                # Check lapped cars first
                position_diff = leader_track_pos - driver['TrackPosition']
                if position_diff >= 100:
                    laps_down = int(position_diff / 100)
                    driver['EstGap'] = f"+{laps_down}L"
                    driver['Interval'] = f"+{laps_down}L"
                    continue

                # Gap to leader (reference point)
                gap_to_leader = self._get_gap_at_reference_point(leader_idx, car_idx)
                if gap_to_leader is not None and gap_to_leader > 0:
                    driver['EstGap'] = f"+{gap_to_leader:.1f}s"
                else:
                    driver['EstGap'] = "-"

                # Interval to car directly ahead (reference point)
                car_ahead_idx = drivers_list[i - 1]['CarIdx']
                gap_to_ahead = self._get_gap_at_reference_point(car_ahead_idx, car_idx)
                if gap_to_ahead is not None and gap_to_ahead > 0:
                    driver['Interval'] = f"+{gap_to_ahead:.1f}s"
                else:
                    driver['Interval'] = "-"

        except Exception as e:
            print(f"Gap calculation error: {e}")
            for driver in drivers_list:
                if driver['Pos'] == 1:
                    driver['EstGap'] = "Leader"
                    driver['Interval'] = "-"
                else:
                    driver['EstGap'] = "-"
                    driver['Interval'] = "-"

    def _init_sectors(self):
        """Initialize sector tracking for qualifying"""
        if self.track_sectors:
            return

        try:
            split_info = self.ir['SessionInfo'].get('SplitTimeInfo')
            use_virtual = True

            # Try to load official sectors
            if split_info and 'Sectors' in split_info:
                sectors = split_info.get('Sectors', [])
                if sectors:
                    use_virtual = False
                    ordered = sorted(sectors, key=lambda s: s['SectorStartPct'])
                    self.track_sectors = [
                        {
                            "index": s['SectorNum'],
                            "start": s['SectorStartPct'],
                            "name": s.get('SectorName', f"S{s['SectorNum']}")
                        }
                        for s in ordered
                    ]

            # Fallback: Generate virtual sectors
            if use_virtual:
                self.track_sectors = [
                    {"index": 1, "start": 0.3333, "name": "S1"},
                    {"index": 2, "start": 0.6666, "name": "S2"}
                ]
        except Exception as e:
            print(f"Sector init error: {e}")

    def _get_qualifying_data(self, car_idx):
        """Get qualifying-specific data for a driver"""
        qual_data = {
            'Gap': '-',
            'LapDisplay': '-',
            'S1': '○',
            'S2': '○',
            'S3': '○',
            'BestLapSeconds': 999999
        }

        try:
            session_num = self.ir['SessionNum']
            results = self.ir['SessionInfo']['Sessions'][session_num].get('ResultsPositions', [])

            for result in results:
                if result and result.get('CarIdx') == car_idx:
                    # Best lap time
                    best_time = result.get('FastestTime', -1)
                    if best_time > 0:
                        qual_data['BestLapSeconds'] = best_time

                    # Current lap progress
                    lap_arr = self.ir['CarIdxLap']
                    lap_dist_pct_arr = self.ir['CarIdxLapDistPct']

                    if car_idx < len(lap_arr) and car_idx < len(lap_dist_pct_arr):
                        current_lap = lap_arr[car_idx]
                        lap_progress = lap_dist_pct_arr[car_idx]

                        # Format as "2.56" for lap 2, 56% complete
                        if current_lap > 0:
                            lap_decimal = current_lap + lap_progress
                            qual_data['LapDisplay'] = f"{lap_decimal:.2f}"

                    # Sector colors (simplified - using last 3 sectors crossed)
                    if car_idx in self.sector_data:
                        status_list = self.sector_data[car_idx].get("current_lap_sector_status", [0, 0, 0])
                        qual_data['S1'] = self._sector_to_symbol(status_list[0] if len(status_list) > 0 else 0)
                        qual_data['S2'] = self._sector_to_symbol(status_list[1] if len(status_list) > 1 else 0)
                        qual_data['S3'] = self._sector_to_symbol(status_list[2] if len(status_list) > 2 else 0)

                    break

        except Exception as e:
            print(f"Qualifying data error: {e}")

        return qual_data

    def _update_delay(self, value):
        """Update replay delay from slider"""
        self.replay_delay = float(value)
        self.delay_label.configure(text=f"{value:.1f}s")

    def _draw_track_map(self):
        """Draw circular track map with car positions.
        Static elements (track oval, S/F line) are cached and only redrawn on resize.
        Car dots are redrawn every tick using the 'car_dot' tag.
        """
        try:
            width = self.track_canvas.winfo_width()
            height = self.track_canvas.winfo_height()

            if width < 50 or height < 50:
                return

            center_x = width / 2
            center_y = height / 2
            radius = min(width, height) / 2 - 25

            # Only redraw static elements if canvas size changed
            last_size = getattr(self, '_track_map_last_size', (0, 0))
            if (width, height) != last_size:
                self._track_map_last_size = (width, height)
                self.track_canvas.delete("all")

                # Track circle
                self.track_canvas.create_oval(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    outline="#3a3a3a", width=12, tags="static"
                )
                self.track_canvas.create_oval(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    outline="#4a4a4a", width=6, tags="static"
                )

                # Start/finish line
                self.track_canvas.create_line(
                    center_x, center_y - radius - 12,
                    center_x, center_y - radius + 12,
                    fill="#ffffff", width=3, tags="static"
                )
                self.track_canvas.create_text(
                    center_x, center_y - radius - 18,
                    text="S/F", fill="#888888", font=("Arial", 7), tags="static"
                )
            else:
                # Only clear car dots, keep static elements
                self.track_canvas.delete("car_dot")

            if not self.drivers_data:
                return

            focused_car_idx = -1
            try:
                focused_car_idx = self.ir['CamCarIdx']
            except:
                pass

            for driver in self.drivers_data:
                car_idx = driver.get('CarIdx', -1)
                lap_progress = driver.get('LapProgress', 0)

                if lap_progress < 0:
                    continue

                angle = lap_progress * 2 * math.pi - math.pi / 2
                car_x = center_x + radius * math.cos(angle)
                car_y = center_y + radius * math.sin(angle)

                is_focused = (car_idx == focused_car_idx)
                if is_focused:
                    color = "#FF4444"
                elif driver['Pos'] == 1:
                    color = "#FFD700"
                elif driver['Pos'] <= 3:
                    color = "#00b4c8"
                elif driver.get('IsFaded', False):
                    color = "#555555"
                else:
                    color = "#cccccc"

                if is_focused:
                    dot_size = 7
                elif driver['Pos'] == 1:
                    dot_size = 6
                elif driver['Pos'] <= 3:
                    dot_size = 5
                else:
                    dot_size = 4

                car_tag = f"car_{car_idx}"

                self.track_canvas.create_oval(
                    car_x - dot_size, car_y - dot_size,
                    car_x + dot_size, car_y + dot_size,
                    fill=color, outline="#1a1a1a", width=1,
                    tags=(car_tag, "car_dot")
                )

                if driver['Pos'] <= 5 or is_focused:
                    label_r = radius + 16
                    label_x = center_x + label_r * math.cos(angle)
                    label_y = center_y + label_r * math.sin(angle)
                    self.track_canvas.create_text(
                        label_x, label_y,
                        text=driver['Num'],
                        fill=color,
                        font=("Arial", 8, "bold"),
                        tags=(car_tag, "car_dot")
                    )

        except Exception as e:
            print(f"Track map error: {e}")

    def _on_track_map_click(self, event):
        """Focus camera on the car whose dot was clicked on the track map."""
        items = self.track_canvas.find_overlapping(event.x - 8, event.y - 8, event.x + 8, event.y + 8)
        for item_id in items:
            tags = self.track_canvas.gettags(item_id)
            for tag in tags:
                if tag.startswith("car_"):
                    car_idx = int(tag.split("_")[1])
                    driver_info = next((d for d in self.drivers_data if d['CarIdx'] == car_idx), None)
                    if driver_info:
                        current_group = 0
                        try:
                            current_group = self.ir['CamGroupNumber']
                        except:
                            pass
                        print(f"Map click: focusing on {driver_info['Name']} (#{driver_info['Num']})")
                        self.ir.cam_switch_num(driver_info['Num'], current_group, 0)
                    return

    def _sector_to_symbol(self, status):
        """Convert sector status to symbol with color indicator"""
        if status == 0: return '-'      # Pending
        elif status == 1: return '●'    # Gray (no improvement)
        elif status == 2: return 'PB'   # Green (personal best)
        elif status == 3: return 'SB'   # Purple (session best)
        return '-'

    def _track_pit_stops(self):
        """Track pit stops - count, pit lane duration, and pit box (stationary) duration"""
        try:
            on_pit_road_arr = self.ir['CarIdxOnPitRoad']
            session_time = self.ir['SessionTime']
            session_num = self.ir['SessionNum']
            track_surface_arr = self.ir['CarIdxTrackSurface']

            for car_idx in range(len(on_pit_road_arr)):
                current_on_pit_road = on_pit_road_arr[car_idx]

                # Get track surface for this car
                track_surface = -1
                if car_idx < len(track_surface_arr):
                    track_surface = track_surface_arr[car_idx]

                # Skip abandoned/not-in-world cars
                if track_surface in [-1, 0]:
                    continue

                # --- Pit lane tracking (CarIdxOnPitRoad) ---
                last_pit_state = self.last_pit_state.get(car_idx, False)

                if current_on_pit_road and not last_pit_state:
                    self.pit_entry_times[car_idx] = session_time
                    self.pit_stop_counts[car_idx] = self.pit_stop_counts.get(car_idx, 0) + 1
                    self.log_event(session_time, session_num, "pit_enter", car_idx=car_idx)
                elif not current_on_pit_road and last_pit_state:
                    if car_idx in self.pit_entry_times:
                        pit_duration = session_time - self.pit_entry_times[car_idx]
                        self.last_pit_duration[car_idx] = pit_duration
                        self.log_event(session_time, session_num, "pit_exit", car_idx=car_idx, pit_duration=pit_duration)

                self.last_pit_state[car_idx] = current_on_pit_road

                # --- Pit box tracking (CarIdxTrackSurface == 1 = InPitStall) ---
                last_surface = self.last_surface_state.get(car_idx, -1)
                in_pit_stall = (track_surface == 1)
                was_in_pit_stall = (last_surface == 1)

                if in_pit_stall and not was_in_pit_stall:
                    # Car just entered pit box
                    self.pit_box_entry_times[car_idx] = session_time
                elif not in_pit_stall and was_in_pit_stall:
                    # Car just left pit box
                    if car_idx in self.pit_box_entry_times:
                        box_duration = session_time - self.pit_box_entry_times[car_idx]
                        self.last_pit_box_duration[car_idx] = box_duration

                self.last_surface_state[car_idx] = track_surface

        except Exception as e:
            print(f"Pit tracking error: {e}")

    def _update_sector_times(self):
        """Update sector times for qualifying (simplified version)"""
        if not self.track_sectors:
            return

        try:
            dist_pcts = self.ir['CarIdxLapDistPct']
            car_laps = self.ir['CarIdxLap']
            session_time = self.ir['SessionTime']

            if not dist_pcts or not car_laps:
                return

            for car_idx, lap_progress in enumerate(dist_pcts):
                if car_idx >= len(car_laps):
                    continue

                current_lap = car_laps[car_idx]

                # Initialize car sector state if needed
                if car_idx not in self.sector_data:
                    self.sector_data[car_idx] = {
                        "lastLap": -1,
                        "lastPct": 0.0,
                        "last_boundary_time": None,
                        "current_lap_sector_status": [0, 0, 0]
                    }

                    if car_idx not in self.driver_best_sectors:
                        self.driver_best_sectors[car_idx] = {}

                car_sector_state = self.sector_data[car_idx]

                # Check for lap change
                if car_sector_state["lastLap"] != current_lap:
                    # New lap - reset sector status
                    car_sector_state["last_boundary_time"] = session_time
                    car_sector_state["lastLap"] = current_lap
                    car_sector_state["lastPct"] = 0.0
                    car_sector_state["current_lap_sector_status"] = [0, 0, 0]

                # Check sector crossings
                for idx, sector in enumerate(self.track_sectors):
                    if lap_progress >= sector["start"] and car_sector_state["lastPct"] < sector["start"]:
                        last_bound = car_sector_state["last_boundary_time"]

                        if last_bound is not None:
                            split_time = session_time - last_bound

                            if split_time > 0.1:
                                # Process sector color
                                status_code = 1  # Default: Gray

                                # Check personal best
                                pbs = self.driver_best_sectors[car_idx]
                                current_pb = pbs.get(idx)

                                if current_pb is None or split_time <= current_pb:
                                    pbs[idx] = split_time
                                    status_code = 2  # Green

                                # Check session best
                                overall_best = self.session_best_sectors.get(idx)

                                if overall_best is None or split_time < overall_best:
                                    self.session_best_sectors[idx] = split_time
                                    status_code = 3  # Purple

                                # Update status
                                car_sector_state["current_lap_sector_status"][idx] = status_code

                        car_sector_state["last_boundary_time"] = session_time

                car_sector_state["lastPct"] = lap_progress

        except Exception as e:
            print(f"Sector update error: {e}")

    def _update_driver_tree(self):
        # Store selection to restore it
        selected_item = self.driver_tree.selection()
        selected_car_idx = None

        if selected_item:
            try:
                tags = self.driver_tree.item(selected_item[0], 'tags')
                if tags: selected_car_idx = int(tags[0])
            except: pass

        # Clear Tree
        for item in self.driver_tree.get_children():
            self.driver_tree.delete(item)

        # Refill based on session type
        new_selection_id = None

        # Calculate gap for qualifying
        leader_best_time = None
        if self.is_qualifying_session and self.drivers_data:
            leader_best_time = self.drivers_data[0].get('BestLapSeconds', 999999)

        for d in self.drivers_data:
            pos_str = str(d['Pos']) if d['Pos'] < 900 else "-"

            # Base tag is the CarIdx
            row_tags = [str(d['CarIdx'])]

            if d['IsFaded']:
                row_tags.append("faded")

            # Prepare pit data (shared by all session types)
            pit_count = d.get('PitStops', 0)
            last_pit_time = d.get('LastPitTime', None)
            last_pit_box_time = d.get('LastPitBoxTime', None)
            pit_lane_str = f"{last_pit_time:.1f}s" if last_pit_time and last_pit_time > 0 else "-"
            pit_box_str = f"{last_pit_box_time:.1f}s" if last_pit_box_time and last_pit_box_time > 0 else "-"

            # Prepare values based on session type
            if self.is_qualifying_session:
                # Calculate gap
                gap_str = "Leader" if d['Pos'] == 1 else "-"
                if d['Pos'] > 1 and leader_best_time and d['BestLapSeconds'] < 999999:
                    gap_seconds = d['BestLapSeconds'] - leader_best_time
                    gap_str = f"+{gap_seconds:.3f}"

                values = (
                    pos_str,
                    d['Num'],
                    d['Name'],
                    gap_str,
                    d.get('LapDisplay', '-'),
                    d.get('S1', '○'),
                    d.get('S2', '○'),
                    d.get('S3', '○'),
                    str(pit_count),
                    pit_lane_str,
                    pit_box_str
                )
            else:
                # Race mode
                est_gap = d.get('EstGap', '-')
                interval = d.get('Interval', '-')

                values = (
                    pos_str,
                    d['Num'],
                    d['Name'],
                    est_gap,
                    interval,
                    d['Tire'],
                    str(pit_count),
                    pit_lane_str,
                    pit_box_str
                )

            # Insert item
            item_id = self.driver_tree.insert("", "end", values=values, tags=tuple(row_tags))

            # --- HIGHLIGHTING LOGIC ---
            self.driver_tree.tag_configure("faded", foreground="#808080")

            # Color sector symbols in qualifying
            if self.is_qualifying_session:
                car_idx = d['CarIdx']
                if car_idx in self.sector_data:
                    status_list = self.sector_data[car_idx].get("current_lap_sector_status", [0, 0, 0])
                    # Visual indication is done via the text symbols (PB, SB, etc.)
                    pass

            if not self.is_qualifying_session and "Wet" in d.get('Tire', ''):
                unique_bg_tag = f"row_{d['CarIdx']}_wet"
                self.driver_tree.item(item_id, tags=tuple(row_tags + [unique_bg_tag]))
                self.driver_tree.tag_configure(unique_bg_tag, background="#1E3A4C")

            # Restore Selection
            if selected_car_idx is not None and d['CarIdx'] == selected_car_idx:
                new_selection_id = item_id

        # Restore Selection UI
        if new_selection_id:
            self.driver_tree.selection_set(new_selection_id)
            self.driver_tree.see(new_selection_id)

    # --- Interaction Logic ---
    
    def switch_to_selected_driver(self, event=None):
        sel = self.driver_tree.selection()
        cam_sel_idx = self.camera_list.curselection()
        
        if not sel or not cam_sel_idx: return
        
        try:
            # Get CarIdx from tag
            tags = self.driver_tree.item(sel[0], 'tags')
            car_idx = int(tags[0])
            
            # Get Camera
            grp_num = self.cameras[cam_sel_idx[0]]['GroupNum']
            
            # Send command
            driver_info = next((d for d in self.drivers_data if d['CarIdx'] == car_idx), None)
            if driver_info:
                self.ir.cam_switch_num(driver_info['Num'], grp_num, 0)
        except Exception as e:
            print(f"Switch error: {e}")

    def toggle_data_collection(self):
        self.is_collecting_data = not self.is_collecting_data
        if self.is_collecting_data:
            if not self.ir.startup():
                messagebox.showerror("iRacing Not Found", "Please start iRacing first.")
                self.is_collecting_data = False
                return

            # Reset pit stop tracking
            self.last_pit_state = {}
            self.pit_entry_times = {}
            self.pit_stop_counts = {}
            self.last_pit_duration = {}
            self.last_surface_state = {}
            self.pit_box_entry_times = {}
            self.last_pit_box_duration = {}

            # Reset event tracking
            self.last_session_state = -1
            self.last_track_surfaces = {}
            self.last_flag_state = "normal"
            self.overtake_cooldowns = {}
            self.car_stopped_since = {}
            self.car_stopped_reported = {}
            self.green_flag_time = None

            # Reset minisector timing
            self.crossing_times = {}
            self.last_car_minisector = {}

            self.toggle_btn.configure(text="STOP TELEMETRY", fg_color="#C92C2C")
            self._get_pit_lane_markers()
            self.master_loop()
        else:
            self.toggle_btn.configure(text="START TELEMETRY", fg_color="#1f538d")

    # --- Event Logic (Identical to previous logic, just targeting modern tree) ---
    def _log_events_logic(self):
        try:
            self._check_session_type()
            if self.is_qualifying_session: self._log_qualifying_events()
            else: self._log_race_events()
        except: pass

    def _log_race_events(self):
        session_time = self.ir['SessionTime']
        session_num = self.ir['SessionNum']

        # Track session state changes (green flag start of race)
        current_session_state = self.ir['SessionState']
        if self.last_session_state != current_session_state:
            # Session states: 0=invalid, 1=get in car, 2=warmup, 3=parade laps, 4=racing, 5=checkered, 6=cool down
            if current_session_state == 4 and self.last_session_state in [2, 3]:
                self.log_event(session_time, session_num, "green_flag")
                self.green_flag_time = session_time
            self.last_session_state = current_session_state

        # Track live flag changes via SessionFlags bitmask
        flags = int(self.ir['SessionFlags'] or 0)
        FLAG_CAUTION        = 0x4000
        FLAG_CAUTION_WAVING = 0x8000
        FLAG_YELLOW         = 0x0008
        is_sc     = bool(flags & (FLAG_CAUTION | FLAG_CAUTION_WAVING))
        is_yellow = not is_sc and bool(flags & FLAG_YELLOW)
        new_flag_state = "sc" if is_sc else ("yellow" if is_yellow else "normal")

        if new_flag_state != self.last_flag_state:
            if new_flag_state == "sc":
                self.log_event(session_time, session_num, "safety_car_out")
            elif new_flag_state == "yellow":
                self.log_event(session_time, session_num, "yellow_flag")
            elif new_flag_state == "normal":
                if self.last_flag_state == "sc":
                    self.log_event(session_time, session_num, "safety_car_in")
                else:
                    self.log_event(session_time, session_num, "green_flag_resume")
            self.last_flag_state = new_flag_state

        # Track overtakes using virtual positions
        current_positions = {d['Pos']: d['CarIdx'] for d in self.drivers_data if d['Pos'] < 900}
        laps = self.ir['CarIdxLap']

        _OVERTAKE_COOLDOWN = 6.0  # seconds — suppress re-overtakes between the same pair
        if self.last_positions_race:
            for pos, new_car_idx in current_positions.items():
                old_car_idx = self.last_positions_race.get(pos)
                if old_car_idx is not None and new_car_idx != old_car_idx:
                    # Verify they're on the same lap (avoid lap-down confusion)
                    if new_car_idx < len(laps) and old_car_idx < len(laps):
                        if laps[new_car_idx] == laps[old_car_idx]:
                            pair = frozenset({new_car_idx, old_car_idx})
                            last_time = self.overtake_cooldowns.get(pair, 0.0)
                            if session_time - last_time >= _OVERTAKE_COOLDOWN:
                                self.overtake_cooldowns[pair] = session_time
                                self.log_event(session_time, session_num, "overtake",
                                              new_driver_idx=new_car_idx, old_driver_idx=old_car_idx, position=pos)
        self.last_positions_race = current_positions

        # Track off-track incidents
        track_surface_arr = self.ir['CarIdxTrackSurface']
        for d in self.drivers_data:
            c_idx = d['CarIdx']
            if c_idx >= len(track_surface_arr):
                continue

            current_surface = track_surface_arr[c_idx]
            last_surface = self.last_track_surfaces.get(c_idx, 1)

            # Surface types: -1=not in world, 0=undefined, 1=asphalt, 2=rumble strip, 3=grass, 4=dirt, 5=gravel
            # Detect when going from asphalt (1) to off-track (3, 4, 5)
            if last_surface == 1 and current_surface in [3, 4, 5]:
                self.log_event(session_time, session_num, "offtrack", car_idx=c_idx)

            self.last_track_surfaces[c_idx] = current_surface

        # Track stopped on track / crashes
        _STOP_SPEED_MS   = 2.0   # m/s (~7 km/h) — below this = stopped
        _MOVING_SPEED_MS = 8.0   # m/s (~29 km/h) — above this = back racing (hysteresis)
        _STOP_DURATION   = 4.0   # seconds before firing the event
        _GREEN_GRACE     = 5.0   # seconds after green flag to ignore stops (standing start)

        speed_arr  = self.ir['CarIdxSpeed']
        on_pit_arr = self.ir['CarIdxOnPitRoad']

        in_green_grace = (self.green_flag_time is not None and
                          session_time - self.green_flag_time < _GREEN_GRACE)

        if in_green_grace:
            self.car_stopped_since.clear()
            self.car_stopped_reported.clear()

        if speed_arr and on_pit_arr and not in_green_grace:
            for d in self.drivers_data:
                c_idx = d['CarIdx']
                if c_idx >= len(speed_arr) or c_idx >= len(on_pit_arr):
                    continue

                speed   = speed_arr[c_idx] or 0.0
                on_pit  = on_pit_arr[c_idx]
                surface = track_surface_arr[c_idx] if c_idx < len(track_surface_arr) else -1

                # Ignore: on pit road, not in world, or already off-track (handled separately)
                if on_pit or surface == -1 or surface in [3, 4, 5]:
                    self.car_stopped_since.pop(c_idx, None)
                    self.car_stopped_reported.pop(c_idx, None)
                    continue

                if speed < _STOP_SPEED_MS:
                    if c_idx not in self.car_stopped_since:
                        self.car_stopped_since[c_idx] = session_time
                    elif not self.car_stopped_reported.get(c_idx, False):
                        stopped_for = session_time - self.car_stopped_since[c_idx]
                        if stopped_for >= _STOP_DURATION:
                            self.log_event(session_time, session_num, "stopped_on_track", car_idx=c_idx)
                            self.car_stopped_reported[c_idx] = True
                elif speed >= _MOVING_SPEED_MS:
                    # Car is back at racing speed — reset state
                    self.car_stopped_since.pop(c_idx, None)
                    self.car_stopped_reported.pop(c_idx, None)

    def _log_qualifying_events(self):
        session_time = self.ir['SessionTime']
        session_num = self.ir['SessionNum']
        laps_completed = self.ir['CarIdxLapsCompleted']
        try:
            results = self.ir['SessionInfo']['Sessions'][session_num]['ResultsPositions']
            for result in results:
                if not result or 'CarIdx' not in result: continue
                car_idx = result['CarIdx']
                last_time = result.get('LastTime', -1)
                current_completed = laps_completed[car_idx] if car_idx < len(laps_completed) else 0
                prev_completed = self.last_laps_completed.get(car_idx, 0)
                if current_completed > prev_completed and last_time > 0:
                    best_time = self.personal_best_laps.get(car_idx, 99999.0)
                    if last_time < best_time:
                        self.personal_best_laps[car_idx] = last_time
                        self.log_event(session_time, session_num, "qualify_lap_improved", car_idx=car_idx, lap_time=last_time)
                self.last_laps_completed[car_idx] = current_completed
        except: pass

    def log_event(self, session_time, session_num, event_type, **kwargs):
        try:
            event_desc = ""
            involved_car_idx = -1

            if event_type == "overtake":
                d_new = self.car_idx_to_name.get(kwargs['new_driver_idx'], "Unknown")
                d_old = self.car_idx_to_name.get(kwargs['old_driver_idx'], "Unknown")
                event_desc = f"🏁 Overtake: {d_new} P{kwargs['position']} (passed {d_old})"
                involved_car_idx = kwargs['new_driver_idx']

            elif event_type == "pit_enter":
                d_name = self.car_idx_to_name.get(kwargs['car_idx'], "Unknown")
                event_desc = f"🔧 Pit Entry: {d_name}"
                involved_car_idx = kwargs['car_idx']

            elif event_type == "pit_exit":
                d_name = self.car_idx_to_name.get(kwargs['car_idx'], "Unknown")
                pit_duration = kwargs.get('pit_duration', 0)
                event_desc = f"🏎️ Pit Exit: {d_name} ({pit_duration:.1f}s)"
                involved_car_idx = kwargs['car_idx']

            elif event_type == "offtrack":
                d_name = self.car_idx_to_name.get(kwargs['car_idx'], "Unknown")
                event_desc = f"⚠️ Off Track: {d_name}"
                involved_car_idx = kwargs['car_idx']

            elif event_type == "stopped_on_track":
                d_name = self.car_idx_to_name.get(kwargs['car_idx'], "Unknown")
                event_desc = f"🛑 Stopped on Track: {d_name}"
                involved_car_idx = kwargs['car_idx']

            elif event_type == "green_flag":
                event_desc = "🟢 GREEN FLAG - Racing Started!"
                involved_car_idx = -1

            elif event_type == "green_flag_resume":
                event_desc = "🟢 GREEN FLAG - Racing Resumed"
                involved_car_idx = -1

            elif event_type == "yellow_flag":
                event_desc = "🟡 YELLOW FLAG - Caution"
                involved_car_idx = -1

            elif event_type == "safety_car_out":
                event_desc = "🚗 SAFETY CAR DEPLOYED"
                involved_car_idx = -1

            elif event_type == "safety_car_in":
                event_desc = "🚗 SAFETY CAR IN"
                involved_car_idx = -1

            elif event_type == "qualify_lap_improved":
                d_name = self.car_idx_to_name.get(kwargs['car_idx'], "Unknown")
                mins, secs = divmod(kwargs['lap_time'], 60)
                time_str = f"{int(mins)}:{secs:06.3f}"
                event_desc = f"⏱️ PB: {d_name} - {time_str}"
                involved_car_idx = kwargs['car_idx']

            if event_desc:
                mins, secs = divmod(session_time, 60)
                time_str = f"{int(mins):02}:{secs:05.2f}"
                tag_data = f"{session_num},{session_time},{involved_car_idx}"

                # Insert at end
                self.log_tree.insert("", "end", values=(time_str, event_desc), tags=(tag_data,))
                self.log_tree.yview_moveto(1)
        except Exception as e:
            print(f"Log event error: {e}")

    def jump_to_log_event(self, event=None):
        sel = self.log_tree.selection()
        if not sel: return

        try:
            # 1. Parse data from the tag
            tag = self.log_tree.item(sel[0], "tags")[0]
            sess_num, time_s, car_idx = tag.split(',')

            car_idx = int(car_idx)

            # 2. Apply configurable delay (go back X seconds before the event)
            event_time = float(time_s)
            rewind_time = max(0, event_time - self.replay_delay)  # Don't go negative
            timestamp_ms = int(rewind_time * 1000)

            # 3. Execute Replay Seek (Session Number + Milliseconds)
            self.ir.replay_search_session_time(int(sess_num), timestamp_ms)

            # 4. Switch Camera Focus to the car involved (if applicable)
            if car_idx >= 0:  # -1 means no specific car (e.g., green flag)
                driver_info = next((d for d in self.drivers_data if d['CarIdx'] == car_idx), None)

                if driver_info:
                    # Find a good replay camera (look for "TV1", "TV Mixed", or "Chopper")
                    target_cam_group = 1

                    if self.cameras:
                        # Try to find a group with "TV" in the name
                        tv_cam = next((c for c in self.cameras if "TV" in c['GroupName']), None)
                        if tv_cam:
                            target_cam_group = tv_cam['GroupNum']

                    # Send Camera Switch Command
                    self.ir.cam_switch_num(driver_info['Num'], target_cam_group, 0)
                    print(f"Replay: Jumping to {rewind_time:.1f}s (event at {event_time:.1f}s, delay: {self.replay_delay}s) for Car #{driver_info['Num']}")
            else:
                print(f"Replay: Jumping to {rewind_time:.1f}s (event at {event_time:.1f}s, delay: {self.replay_delay}s)")

        except Exception as e:
            print(f"Jump error: {e}")

    # --- Layout Persistence ---
    def _save_layout(self):
        """Save current window geometry and pane sash positions to a JSON file."""
        try:
            self.update_idletasks()
            sash_positions = []
            for i in range(len(self.paned.panes()) - 1):
                sash_positions.append(self.paned.sash_coord(i)[0])

            config = {
                "geometry": self.geometry(),
                "sash_positions": sash_positions
            }
            with open(LAYOUT_CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
            print(f"Layout saved to {LAYOUT_CONFIG_FILE}")
        except Exception as e:
            print(f"Error saving layout: {e}")

    def _load_layout(self):
        """Load saved layout config and apply after the window is rendered."""
        if not os.path.exists(LAYOUT_CONFIG_FILE):
            return
        try:
            with open(LAYOUT_CONFIG_FILE, "r") as f:
                config = json.load(f)

            if "geometry" in config:
                self.geometry(config["geometry"])

            # Defer sash restore until paned is fully rendered
            if "sash_positions" in config:
                self._pending_sash_positions = config["sash_positions"]
                self.after(100, self._apply_sash_positions)
        except Exception as e:
            print(f"Error loading layout: {e}")

    def _apply_sash_positions(self):
        """Apply saved sash positions once the PanedWindow has been drawn."""
        try:
            positions = getattr(self, "_pending_sash_positions", None)
            if not positions:
                return
            self.update_idletasks()
            for i, x in enumerate(positions):
                if i < len(self.paned.panes()) - 1:
                    self.paned.sash_place(i, x, 0)
            del self._pending_sash_positions
        except Exception as e:
            print(f"Error restoring sash positions: {e}")

    # --- Helpers ---
    def set_replay_speed(self, speed):
        if self.ir.is_connected: self.ir.replay_set_play_speed(speed, 0)

    def seek_lap(self, mode):
        if self.ir.is_connected: self.ir.replay_search(mode)

    def go_to_live(self):
        if self.ir.is_connected: self.ir.replay_search(RSEARCH_MODE_TO_END)

    def _get_pit_lane_markers(self):
        try:
            split_time_info = self.ir['SessionInfo'].get('SplitTimeInfo', {})
            sectors = split_time_info.get('Sectors', [])
            for sector in sectors:
                if sector['SectorName'] == 'Pit Entry':
                    self.pit_entry_pct = sector['SectorStartPct']
                    break
        except: pass

    def _check_session_type(self):
        try:
            session_type = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]['SessionType']
            self.is_qualifying_session = "Qualify" in session_type
        except: pass

def main():
    app = ModernIRacingApp()
    app.mainloop()

if __name__ == "__main__":
    main()