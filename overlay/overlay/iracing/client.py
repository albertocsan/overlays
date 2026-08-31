# iRacing client for connecting to the iRacing API and fetching data

import irsdk
import time
import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.state import State
from utils.formatting import format_lap_time
from iracing.camera_control import CameraFocusSystem

# Initialize logger
logger = logging.getLogger("iracing-timing")

class IRacingClient:
    """
    Client for connecting to iRacing and fetching session data.
    """
    # Class variable to keep track of instances
    __instances__ = []
    
    def __init__(self, state):
        """
        Initialize the iRacing client.
        
        Args:
            state (State): Application state object
        """
        self.ir = irsdk.IRSDK()
        self.state = state
        
        # Initialize camera focus system
        self.camera_focus = CameraFocusSystem(self.ir)
        
        # Add this instance to the list of instances
        IRacingClient.__instances__.append(self)

    def check_connection(self):
        """
        Check if the connection to iRacing is active.
        
        Returns:
            bool: True if connected, False otherwise
        """
        if self.state.ir_connected and not (self.ir.is_initialized and self.ir.is_connected):
            self.state.ir_connected = False
            self.state.last_session_info_update = -1
            self.ir.shutdown()
            logger.warning('irsdk desconectado - SDK dejó de responder')
            return False
        elif not self.state.ir_connected and self.ir.startup() and self.ir.is_initialized and self.ir.is_connected:
            self.state.ir_connected = True
            
            # Log additional session information
            try:
                session_info = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]
                #logger.info(f"Conectado a sesión: {session_info['SessionName']} - Tipo: {session_info['SessionType']}")
                logger.info(f"Pista: {self.ir['OnPitRoad']}")
            except Exception as e:
                logger.warning(f"No se pudo obtener información detallada de la sesión: {str(e)}")
                
            return True
        return self.state.ir_connected

    def create_session_data(self):
        """
        Create a JSON object with the current session data.
        
        Returns:
            dict: Session data or None if data is not available
        """
        try:
            # Check if we have session and track data
            if not self.ir['SessionInfo']:
                logger.error("No hay SessionInfo disponible")
                return None
            
            if not self.ir['WeekendInfo']:
                logger.error("No hay WeekendInfo disponible")
                return None
            
            # Check if SessionNum exists and is valid
            if self.ir['SessionNum'] is None:
                logger.error("SessionNum no está disponible")
                return None
                
            # Check if the index is valid
            session_index = self.ir['SessionNum']
            if session_index >= len(self.ir['SessionInfo']['Sessions']):
                logger.error(f"Índice de sesión inválido: {session_index}, máximo: {len(self.ir['SessionInfo']['Sessions'])-1}")
                return None
            
            # -----------------------------------------------------------
            # --- NUEVA LÓGICA: DETECTAR CAMBIO DE SESIÓN Y RESETEAR ---
            # -----------------------------------------------------------
            if self.state.current_session_num != session_index:
                # Not the initial load (default value -1)
                if self.state.current_session_num != -1:
                    logger.info(f"Cambio de sesión detectado: {self.state.current_session_num} -> {session_index}. Reseteando récords.")
                    # Save previous session to history before resetting
                    if not self.state.history_saved:
                        self._try_save_history()
                    self.state.reset_session_data()

                # Update current session number in state
                self.state.current_session_num = session_index
            # -----------------------------------------------------------

            # logger.info(f"Creando session_json. info de la sesión: {self.ir['CameraInfo']}")
            
            # Protect access to fields that might not exist
            session_name = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']].get('SessionName', 'Sesión Desconocida')
            #logger.info(session_name)
            track_name = self.ir['WeekendInfo']['TrackName']
            #logger.info(track_name)
            track_config = self.ir['WeekendInfo'].get('TrackConfigName', '') if 'TrackConfigName' in self.ir['WeekendInfo'] else ""
            #logger.info(track_config)
            session_type = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']].get('SessionType', 'Desconocido')
            #logger.info(session_type)
            session_laps = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']].get('SessionLaps', 0)
            
            # Update the session type in the state object
            self.state.update_session_type(session_type)
            
            # Per-car finish detection for race sessions
            if self.state.current_session_type == State.SESSION_RACE:
                session_state = self.ir['SessionState']

                # Detect checkered flag transition (SessionState 5 = checkered waving)
                if session_state in [5, 6] and not self.state.is_checkered_flag:
                    self.state.is_checkered_flag = True
                    # Snapshot each car's current lap at the moment the checkered drops
                    car_laps = self.ir['CarIdxLap']
                    if car_laps:
                        for idx, lap in enumerate(car_laps):
                            if lap >= 0:  # Car is active on track
                                self.state.checkered_laps[idx] = lap
                    logger.info(f"Checkered flag! Tracking {len(self.state.checkered_laps)} cars for finish detection.")

                # Per-car finish: detect each car crossing the start/finish line after checkered
                if self.state.is_checkered_flag and not self.state.is_race_finished:
                    car_laps = self.ir['CarIdxLap']
                    if car_laps:
                        for idx, current_lap in enumerate(car_laps):
                            if idx in self.state.finished_cars:
                                continue  # Already finished
                            if idx in self.state.checkered_laps:
                                if current_lap > self.state.checkered_laps[idx]:
                                    self.state.finished_cars.add(idx)
                                    logger.info(f"CarIdx {idx} crossed the finish line ({len(self.state.finished_cars)} cars finished)")

                # Final results: SessionState 6 = cooldown (all cars done or timeout)
                if session_state == 6:
                    self.state.is_race_finished = True
                    if not self.state.history_saved:
                        self._try_save_history()
                        self.state.history_saved = True
                elif session_state not in [5, 6]:
                    # Race still going, reset flags
                    self.state.is_race_finished = False
                    self.state.is_checkered_flag = False
                    self.state.finished_cars.clear()
                    self.state.checkered_laps.clear()
            
            # Build session data
            session_data = {
                "timestamp": time.time(),
                "sessionName": session_name,
                "trackName": track_name,
                "trackConfig": track_config,
                "sessionType": session_type,
                "sessionState": self.ir['SessionState'],
                "sessionTime": self.ir['SessionTime'],
                "sessionTimeRemaining": self.ir['SessionTimeRemain'],
                "sessionLapsRemaining": self.ir['SessionLapsRemaining'],
                "sessionLapsTotal": session_laps,
                "sessionFlags": int(self.ir['SessionFlags'] or 0)
            }
            #logger.info(session_data)
            
            # Get driver data with exception handling
            try:
                from iracing.data_processor import get_drivers_data
                drivers = get_drivers_data(self.ir)
                session_data["drivers"] = drivers
                #logger.info(f"Datos de sesión creados. Pilotos: {len(drivers)}")
            except Exception as e:
                logger.error(f"Error al obtener datos de pilotos: {str(e)}", exc_info=True)
                session_data["drivers"] = []  # Empty list in case of error
                
            return session_data
        
        except Exception as e:
            logger.error(f"Error al crear datos de sesión: {str(e)}", exc_info=True)
            return None

    def _try_save_history(self):
        """Write the current session's results to race_history.json."""
        try:
            from iracing.history import save_session_result
            sd = self.state.session_data
            if not sd or not isinstance(sd, dict):
                logger.warning("history: no session_data available to save")
                return
            drivers = sd.get('drivers', [])
            if not drivers:
                logger.warning("history: no drivers in session_data, skipping save")
                return
            save_session_result(
                track=sd.get('trackName', 'unknown'),
                track_config=sd.get('trackConfig', ''),
                session_type=self.state.current_session_type,
                drivers_data=drivers,
            )
            self.state.history_saved = True
        except Exception as e:
            logger.error(f"history: _try_save_history failed: {e}", exc_info=True)

    def update_data(self):
        """
        Update session data by freezing the telemetry buffer and processing the data.
        
        Returns:
            bool: True if data was updated successfully, False otherwise
        """
        try:
            # Freeze the buffer with live telemetry
            self.ir.freeze_var_buffer_latest()
            logger.debug("Buffer de telemetría congelado para procesamiento")
            
            # Update focused driver details in state
            try:
                focused_idx = self.ir['CamCarIdx']
                all_drivers_info = self.ir['DriverInfo']['Drivers']
                
                # Find the driver details using the focused index
                focused_driver = None
                if 0 <= focused_idx < len(all_drivers_info):
                    driver_raw = all_drivers_info[focused_idx]
                    # Extract only necessary details to avoid circular references or large objects
                    focused_driver = {
                        "carIdx": driver_raw.get('CarIdx'),
                        "userName": driver_raw.get('UserName', "Unknown"),
                        "carNumber": driver_raw.get('CarNumber', "N/A"),
                        "teamName": driver_raw.get('TeamName', "")
                    }
                    logger.debug(f"Updated focused_driver_details in state to: {focused_driver}")
                else:
                    logger.warning(f"CamCarIdx {focused_idx} is out of bounds for Drivers list (len={len(all_drivers_info)}).")
                    focused_driver = None # Ensure it's None if index is invalid

                self.state.focused_driver_details = focused_driver

            except KeyError:
                logger.warning("CamCarIdx or DriverInfo not found in iRacing data for focused driver update.")
                self.state.focused_driver_details = None
            except Exception as e:
                logger.error(f"Error updating focused_driver_details in state: {e}", exc_info=True)
                self.state.focused_driver_details = None

            # Create JSON with session data
            session_data = self.create_session_data()
            
            if session_data:
                self.state.session_data = session_data
                self.state.broadcast_data()
                return True
            else:
                logger.warning("No se pudieron crear los datos de la sesión")
                return False
                
        except Exception as e:
            logger.error(f"Error al procesar datos de telemetría: {str(e)}", exc_info=True)
            return False
            
    def update_minisector_crossings(self):
        """
        Fast-tick method (50ms) to record when each car crosses minisector reference points.
        Only reads CarIdxLapDistPct and SessionTime — lightweight by design.
        """
        try:
            if not (self.ir.is_initialized and self.ir.is_connected):
                return

            self.ir.freeze_var_buffer_latest()

            dist_pcts = self.ir['CarIdxLapDistPct']
            session_time = self.ir['SessionTime']

            if not dist_pcts or session_time is None:
                return

            for car_idx, current_pct in enumerate(dist_pcts):
                if current_pct < 0:  # Car not on track
                    continue

                last_pct = self.state.last_car_minisector.get(car_idx, -1.0)

                if car_idx not in self.state.crossing_times:
                    self.state.crossing_times[car_idx] = {}

                for ms_idx, ms_pct in enumerate(self.state.minisector_pcts):
                    # Detect forward crossing of this boundary
                    if last_pct < ms_pct <= current_pct:
                        self.state.crossing_times[car_idx][ms_idx] = session_time
                    # Handle lap wrap-around (crossing start/finish, minisector 0)
                    elif ms_idx == 0 and current_pct < 0.05 and last_pct > 0.95:
                        self.state.crossing_times[car_idx][0] = session_time

                self.state.last_car_minisector[car_idx] = current_pct

        except Exception as e:
            logger.debug(f"Minisector update error: {e}")

    def update_sector_crossings(self):
        """
        Fast-tick method (50ms) to detect sector boundary crossings with high precision.
        Initializes sectors once, then delegates to update_sector_times.
        """
        try:
            if not (self.ir.is_initialized and self.ir.is_connected):
                return

            from iracing.data_processor import init_sectors, update_sector_times
            # One-time initialization of sector boundaries
            if not self.state.track_sectors:
                init_sectors(self.ir, self.state)

            update_sector_times(self.ir, self.state)
        except Exception as e:
            logger.debug(f"Sector crossing update error: {e}")

    # Camera control methods

    def focus_camera_on_position(self, position, camera=0):
        """
        Focus the camera on a car based on its position.
        
        Args:
            position (int): Position of the car in the race
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.camera_focus.focus_on_car_position(position, 0, camera)
        
    def focus_camera_on_car_number(self, car_number, camera=0):
        """
        Focus the camera on a car based on its number.
        
        Args:
            car_number (int): Number of the car to focus on
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.camera_focus.focus_on_car_number(car_number, 0, camera)
        
    def focus_camera_on_driver(self, driver_name, camera=0):
        """
        Focus the camera on a driver by name.
        
        Args:
            driver_name (str): Name of the driver to focus on
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.camera_focus.focus_on_driver_by_name(driver_name, 0, camera)
        
    def focus_camera_on_leader(self, camera=0):
        """
        Focus the camera on the race leader.
        
        Args:
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.camera_focus.focus_on_leader(0, camera)
        
    def focus_camera_on_battles(self, gap_threshold=1.0, camera=0):
        """
        Focus the camera on close battles on track.
        
        Args:
            gap_threshold (float, optional): Maximum gap in seconds to consider a battle. Defaults to 1.0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.camera_focus.focus_on_battles(gap_threshold, 0, camera)
        
    def get_available_cameras(self):
        """
        Get a list of available cameras.
        
        Returns:
            list: List of available camera groups and cameras
        """
        return self.camera_focus.get_available_cameras()
