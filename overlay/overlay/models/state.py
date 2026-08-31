# State class for managing iRacing connection state and configuration

import json
import logging # Import logging module
from iracing.data_processor import get_drivers_data

logger = logging.getLogger("iracing-timing") # Initialize logger

class State:
    """
    Class to manage the state of the connection with iRacing and application configuration.
    """
    # Session type constants
    SESSION_PRACTICE = "PRACTICE"
    SESSION_QUALIFY = "QUALIFY"
    SESSION_RACE = "RACE"
    SESSION_GRIDDING = "GRIDDING"
    SESSION_UNKNOWN = "UNKNOWN"
    
    def __init__(self):
        self.ir_connected = False
        self.last_session_info_update = -1
        self.session_data = None
        self.current_session_type = self.SESSION_UNKNOWN
        self.is_race_finished = False
        self.is_checkered_flag = False  # True when SessionState = 5 (checkered waving)
        self.finished_cars = set()      # Set of carIdx that have individually crossed the finish line
        self.checkered_laps = {}        # Snapshot of CarIdxLap when checkered dropped
        self.frozen_gaps = {}           # Last gap value before a car finished {carIdx: gap_string}
        self.frozen_intervals = {}      # Last interval value before a car finished {carIdx: interval_string}
        self.frozen_positions = {}      # Position when car crossed the finish line {carIdx: position_int}
        self.focused_driver_details = None # Stores details of the focused driver {carIdx, userName, carNumber, teamName}
        self.focused_driver_enabled = False # Controls whether focused driver functionality is active
        self.session_time = 0.0 # Current iRacing session time (seconds), updated each tick
        self.last_known_tire_compounds = {} # Stores the last known tire compound for each carIdx
        self.pit_stop_counts = {} # Stores the pit stop count for each carIdx
        self.last_lap_dist_pct = {} # Stores the last lap_dist_pct for pit entry detection
        self.pit_entry_pct = -1.0 # Stores the pit entry percentage
        self.car_in_pits = {} # Stores whether each car is currently in pits
        self.last_pit_state = {} # Stores the last known pit state for each car
        self.pit_entry_times = {} # Stores the session time when each car entered pits
        self.last_pit_duration = {} # Stores the duration (in seconds) of the last pit stop for each car
        self.last_pit_lap = {} # Stores the lap number when each car last pitted
        self.last_surface_state = {} # Stores last CarIdxTrackSurface for pit box transition detection
        self.pit_box_entry_times = {} # Stores session time when car entered pit stall (TrackSurface == 1)
        self.last_pit_box_duration = {} # Stores duration of last pit box (stationary) stop
        self.on_out_lap = {} # {carIdx: True} when car is on an out lap (exited pits, hasn't crossed S/F yet)
        self.driver_lap_times = {}      # {carIdx: [lap_time_seconds, ...]} — for consistency scoring
        self.driver_laps_complete = {}  # {carIdx: int} — last known lapsComplete to detect new completed laps
        self.history_saved = False      # True once session results have been written to race_history.json
        self.green_flag_time = None # Session time when green flag dropped (SessionState -> 4)
        self.qualify_grid_order = {} # {carIdx: position} from qualifying ResultsPositions
        # --- MINISECTOR REFERENCE-POINT TIMING ---
        NUM_MINISECTORS = 25
        self.minisector_pcts = [i / NUM_MINISECTORS for i in range(NUM_MINISECTORS)]
        self.crossing_times = {}      # {car_idx: {minisector_idx: session_time}}
        self.last_car_minisector = {}  # {car_idx: last_pct}

        # --- SECTORES POR VUELTA ---
        self.track_sectors = []
        self.sector_data = {}
        self.current_session_num = -1  # <--- AÑADIR ESTA VARIABLE
        # --- NUEVO: TIENES QUE AÑADIR ESTAS DOS LÍNEAS ---
        self.session_best_sectors = {}  # Récords absolutos (Morados)
        self.driver_best_sectors = {}   # Récords personales (Verdes)
        # Initialize with None - will be set by ConfigManager
        self.driver_name_format = None
        self.active_columns = None
        self.show_focused_driver_team_logo = True # New config for focused driver team logo visibility
        self.overlay_window_enabled = True # Controls whether the PyQt5 overlay window is launched
        self.focused_driver_battle_mode_enabled = True # Controls the P1/P2 duel/train card vs. solo focused driver card
        
        # These are fixed and don't change
        self.timing_columns = [
            "position", "teamLogo", "brands", "carNumber", "userName", "tireCompound", "bestLapTime",
            "lastLapTime", "interval", "gap", "positionsGained", "pitstops", "lastPitTime", "lastPitBoxTime", "lastPitLap", "lapsComplete", "onPitRoad","lastSector","sectors","performanceScore"
        ]
        
        # Column presets for different session types
        # Session-specific column presets
        self.practice_columns = [
            "position", "carNumber", "userName", "bestLapTime", "gap", "onPitRoad"
        ]
        
        self.qualifying_columns = [
            "position", "carNumber", "userName", "bestLapTime", "gap", "onPitRoad","lastSector"
        ]
        
        self.race_columns = [
            "position", "carNumber", "userName", "interval", "gap", "bestLapTime", "onPitRoad"
        ]
        
        self.results_columns = [
            "position", "carNumber", "userName", "lapsComplete", "bestLapTime", "interval", "gap", "onPitRoad"
        ]

        # WebSocket connections
        self.websockets = []

    def reset_session_data(self):
        """
        Reinicia los datos acumulados al cambiar de sesión.
        """
        logger.info("Reseteando datos de sectores y récords por cambio de sesión.")

        # Reset minisector timing
        self.crossing_times = {}
        self.last_car_minisector = {}

        # Borrar récords absolutos (Morados)
        self.session_best_sectors = {}

        # Borrar récords personales (Verdes)
        self.driver_best_sectors = {}

        # Borrar datos de visualización (Cajitas del overlay)
        # Opcional: Borrar todo sector_data forzará a reinicializar cada coche
        self.sector_data = {}

        # Opcional: Si quieres resetear pitstops también
        self.pit_stop_counts = {}

        # Opcional: Resetear estados de pit
        self.last_pit_state = {}

        # Reset performance score tracking
        self.driver_lap_times = {}
        self.driver_laps_complete = {}
        self.history_saved = False

        # Reset pit timing data
        self.pit_entry_times = {}
        self.last_pit_duration = {}
        self.last_pit_lap = {}
        self.last_surface_state = {}
        self.pit_box_entry_times = {}
        self.last_pit_box_duration = {}
        self.on_out_lap = {}

        # Reset per-car finish tracking
        self.is_checkered_flag = False
        self.is_race_finished = False
        self.finished_cars = set()
        self.checkered_laps = {}
        self.frozen_gaps = {}
        self.frozen_intervals = {}
        self.frozen_positions = {}
        self.green_flag_time = None
        self.qualify_grid_order = {}

    def update_session_type(self, session_type_str):
        """
        Update the current session type based on the string from iRacing.
        
        Args:
            session_type_str (str): Session type string from iRacing
        """
        if not session_type_str:
            return
            
        session_type_upper = session_type_str.upper()
        
        if "PRACTICE" in session_type_upper:
            self.current_session_type = self.SESSION_PRACTICE
        elif "QUALIFY" in session_type_upper:
            self.current_session_type = self.SESSION_QUALIFY
        elif "RACE" in session_type_upper:
            # Check if it's gridding or actual race
            if "GRID" in session_type_upper:
                self.current_session_type = self.SESSION_GRIDDING
            else:
                self.current_session_type = self.SESSION_RACE
        else:
            self.current_session_type = self.SESSION_UNKNOWN
        
        # The active_columns should not be set here, as it overwrites user preferences.
        # It will be handled by ConfigManager to load from file or apply defaults if no file config exists.
            
    def is_time_based_session(self):
        """
        Check if the current session is time-based (practice or qualifying).
        
        Returns:
            bool: True if the session is practice or qualifying, False otherwise
        """
        return self.current_session_type in [self.SESSION_PRACTICE, self.SESSION_QUALIFY]

    def add_websocket(self, ws):
        """
        Add a WebSocket connection to the list.
        """
        self.websockets.append(ws)

    def remove_websocket(self, ws):
        """
        Remove a WebSocket connection from the list.
        """
        if ws in self.websockets:
            self.websockets.remove(ws)

    def broadcast_data(self):
        """
        Send the current session data to all connected WebSocket clients.

        Runs regardless of whether iRacing is connected: config changes (e.g. column
        order saved from /config or /controls) must reach the browser even without
        an active session, since the WebSocket push is the only channel timing.js
        listens on for those updates.
        """
        # session_data is the full dict from client.py (has "drivers" key + session info)
        # when connected; empty/None otherwise.
        sd = self.session_data if isinstance(self.session_data, dict) else {}
        drivers_list = sd.get("drivers", []) if sd else []

        # Prepare data to send, including session data and focused driver
        data_to_send = {
            "drivers": drivers_list,
            "focusedDriver": self.focused_driver_details,
            "sessionName": sd.get("sessionName", "Unknown Session"),
            "sessionTimeRemaining": sd.get("sessionTimeRemaining", 0),
            "sessionLapsTotal": sd.get("sessionLapsTotal", 0),
            "sessionLapsRemaining": sd.get("sessionLapsRemaining", 0),
            "sessionType": self.current_session_type,
            "trackName": sd.get("trackName", "Unknown Track"),
            "trackConfig": sd.get("trackConfig", ""),
            "timestamp": sd.get("timestamp", self.last_session_info_update),
            "sessionBestSectors": self.session_best_sectors,
            "sessionTime": self.session_time,
            "sessionFlags": sd.get("sessionFlags", 0),
            "config": {
                "showFocusedDriverTeamLogo": self.show_focused_driver_team_logo,
                "activeColumns": self.active_columns,
                "focusedDriverEnabled": self.focused_driver_enabled,
                "focusedDriverBattleMode": self.focused_driver_battle_mode_enabled
            }
        }

        logger.debug(f"Broadcasting data via WebSocket. Config: {data_to_send['config']}")
        message = json.dumps(data_to_send)

        # Use a copy of the list for safe iteration if removing items
        sockets_to_remove = []
        for ws in list(self.websockets):
            try:
                ws.send(message)
            except Exception as e:
                print(f"Error broadcasting to WebSocket: {e}. Removing socket.")
                # Mark socket for removal instead of modifying list during iteration
                sockets_to_remove.append(ws)

        # Remove disconnected sockets
        for ws in sockets_to_remove:
            self.remove_websocket(ws)

        return data_to_send # Return the data that was broadcasted
