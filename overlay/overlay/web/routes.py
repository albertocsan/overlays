from flask import jsonify, request, render_template
from models.state import State
import json
import logging
import os
import re

logger = logging.getLogger("iracing-timing")

DORSAL_NUMBER_PATTERN = re.compile(r'^[A-Za-z0-9]{1,10}$')
ALLOWED_DORSAL_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}

# Get the first available iRacing client instance
def get_iracing_client():
    from iracing.client import IRacingClient
    if IRacingClient.__instances__:
        return IRacingClient.__instances__[0]
    return None

def register_routes(app, state, config_manager, overlay_window_manager=None):
    """Register all web routes."""

    @app.route('/')
    def index():
        # Redirect to the timing page
        return render_template('timing.html')

    @app.route('/config')
    def config():
        return render_template('config.html')

    @app.route('/team_assignment')
    def team_assignment():
        return render_template('team_assignment.html')
    @app.route('/raceinfo')
    def raceinfo():
        return render_template('race_info_card.html')
    @app.route('/raceresults')
    def raceresults():
        return render_template('race_results_card.html')

    @app.route('/grid')
    def starting_grid():
        return render_template('starting_grid.html')

    @app.route('/results')
    def race_results():
        return render_template('race_results.html')

    @app.route('/config/teams.json')
    def get_teams_config():
        teams_config_path = os.path.join(app.root_path, 'config', 'teams.json') # Corrected path
        if os.path.exists(teams_config_path):
            with open(teams_config_path, 'r') as f:
                return jsonify(json.load(f))
        return jsonify({})

    @app.route('/save_teams', methods=['POST'])
    def save_teams_config():
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "No data provided"}), 400

        teams_config_path = os.path.join(app.root_path, 'config', 'teams.json') # Corrected path
        try:
            with open(teams_config_path, 'w') as f:
                json.dump(data, f, indent=4)
            return jsonify({"success": True, "message": "Teams configuration saved."})
        except Exception as e:
            logger.error(f"Error saving teams configuration: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/controls')
    def controls():
        # Render the controls page
        return render_template('controls.html')
        
    @app.route('/camera')
    def camera_controls():
        """Render camera controls page with camera groups data."""
        client = get_iracing_client()
        if not client:
            return render_template('camera_controls.html', camera_groups={})
            
        try:
            cameras = client.get_available_cameras()
            # Group cameras by group
            camera_groups = {}
            for cam in cameras:
                group_idx = cam['group_idx']
                if group_idx not in camera_groups:
                    camera_groups[group_idx] = {
                        'name': cam['group_name'],
                        'cameras': []
                    }
                camera_groups[group_idx]['cameras'].append({
                    'idx': cam['camera_idx'],
                    'name': cam['camera_name']
                })
            return render_template('camera_controls.html', camera_groups=camera_groups)
        except Exception as e:
            logger.error(f"Error getting cameras: {str(e)}", exc_info=True)
            return render_template('camera_controls.html', camera_groups={})

    @app.route('/api/timing-data')
    def timing_data():
        if state.session_data:
            return jsonify(state.session_data)
        return jsonify({"error": "No hay datos disponibles"})

    @app.route('/api/available_drivers')
    def available_drivers():
        if state.session_data and 'drivers' in state.session_data:
            drivers_for_assignment = []
            for driver in state.session_data['drivers']:
                drivers_for_assignment.append({
                    "id": driver.get('UserID'),
                    "name": driver.get('userName')
                })
        return jsonify({"success": True, "drivers": drivers_for_assignment})
        return jsonify({"success": False, "error": "No hay datos de pilotos disponibles"})

    @app.route('/api/team_logos')
    def team_logos():
        logos_dir = os.path.join(app.root_path, 'static', 'team_logos')
        if os.path.exists(logos_dir):
            logo_files = [f for f in os.listdir(logos_dir) if os.path.isfile(os.path.join(logos_dir, f))]
            return jsonify({"success": True, "logos": logo_files})
        return jsonify({"success": False, "error": "Team logos directory not found."})

    @app.route('/api/dorsales')
    def list_dorsales():
        dorsales_dir = os.path.join(app.root_path, 'static', 'dorsales')
        os.makedirs(dorsales_dir, exist_ok=True)
        files = sorted(f for f in os.listdir(dorsales_dir) if os.path.isfile(os.path.join(dorsales_dir, f)))
        return jsonify({"success": True, "dorsales": files})

    @app.route('/api/upload-dorsal', methods=['POST'])
    def upload_dorsal():
        car_number = (request.form.get('carNumber') or '').strip()
        if not DORSAL_NUMBER_PATTERN.match(car_number):
            return jsonify({"success": False, "error": "Número de coche inválido."}), 400

        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({"success": False, "error": "No se ha enviado ningún archivo."}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_DORSAL_EXTENSIONS or not (file.mimetype or '').startswith('image/'):
            return jsonify({"success": False, "error": "El archivo debe ser una imagen (png, jpg, webp)."}), 400

        dorsales_dir = os.path.join(app.root_path, 'static', 'dorsales')
        os.makedirs(dorsales_dir, exist_ok=True)
        # Always store as {carNumber}.png - the frontend hardcodes this extension
        file.save(os.path.join(dorsales_dir, f"{car_number}.png"))

        return jsonify({"success": True, "carNumber": car_number, "file": f"{car_number}.png"})

    @app.route('/api/delete-dorsal', methods=['POST'])
    def delete_dorsal():
        data = request.get_json() or {}
        car_number = (data.get('carNumber') or '').strip()
        if not DORSAL_NUMBER_PATTERN.match(car_number):
            return jsonify({"success": False, "error": "Número de coche inválido."}), 400

        dorsales_dir = os.path.join(app.root_path, 'static', 'dorsales')
        dest_path = os.path.join(dorsales_dir, f"{car_number}.png")
        if os.path.exists(dest_path):
            os.remove(dest_path)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "No existe ese dorsal."}), 404

    @app.route('/api/active-columns')
    def active_columns():
        # Return the currently active columns (resolved value, not the raw file
        # content - config_manager.load_config() may return a stale/null value
        # from disk while state.active_columns already holds the resolved one)
        config_manager.load_config()
        return jsonify({
            "success": True,
            "activeColumns": state.active_columns
        })

    @app.route('/api/columns')
    def columns():
        # Return all available columns and active columns, and focused driver settings
        config_manager.load_config()
        return jsonify({
            "success": True,
            "availableColumns": state.timing_columns,
            "activeColumns": state.active_columns,
            "focusedDriverEnabled": state.focused_driver_enabled, # Include focused driver enabled state
            "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo, # Include new config
            "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
        })

    @app.route('/api/update-columns', methods=['POST'])
    def update_columns():
        data = request.get_json()
        if 'columns' in data:
            state.active_columns = data['columns']
            logger.debug(f"Updating active columns to: {state.active_columns}") # Add log here

            # Guardar la configuración en el archivo
            config_manager.save_config({
                "activeColumns": state.active_columns,
                "driverNameFormat": state.driver_name_format,
                "focusedDriverEnabled": state.focused_driver_enabled, # Ensure all configs are saved
                "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo, # Ensure all configs are saved
                "overlayWindowEnabled": state.overlay_window_enabled,
                "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
            })

            return jsonify({"success": True, "activeColumns": state.active_columns})
        return jsonify({"success": False, "error": "No columns provided"})

    @app.route('/api/driver-name-format', methods=['GET'])
    def get_driver_name_format():
        """Endpoint para obtener el formato actual de nombres de pilotos."""
        return jsonify({
            "success": True,
            "format": state.driver_name_format
        })

    @app.route('/api/update-driver-name-format', methods=['POST'])
    def update_driver_name_format():
        """Endpoint para actualizar el formato de nombres de pilotos."""
        data = request.get_json()
        if 'format' in data:
            format_type = data['format']
            # Validar que el formato sea válido
            if format_type in ["full", "initial_last", "three_letters"]:
                state.driver_name_format = format_type

                # Actualizar la configuración
                config_manager.save_config({
                    "activeColumns": state.active_columns,
                    "driverNameFormat": state.driver_name_format,
                    "focusedDriverEnabled": state.focused_driver_enabled, # Ensure all configs are saved
                    "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo, # Ensure all configs are saved
                    "overlayWindowEnabled": state.overlay_window_enabled,
                    "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
                })

                return jsonify({
                    "success": True,
                    "format": state.driver_name_format
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Formato inválido. Debe ser 'full', 'initial_last' o 'three_letters'"
                })
        return jsonify({"success": False, "error": "No format provided"})

    @app.route('/api/config-file')
    def config_file():
        """Endpoint para obtener la ruta del archivo de configuración."""
        config_data = config_manager.load_config()
        return jsonify({
            "success": True,
            "configFile": config_manager.config_file,
            "lastModified": config_data['timestamp']
        })
        
    # Camera control API endpoints
    
    @app.route('/api/cameras')
    def get_cameras():
        """Get available cameras."""
        client = get_iracing_client()
        if not client:
            return jsonify({"success": False, "error": "iRacing client not available"})
            
        try:
            cameras_data = client.get_available_cameras()
            # Extract only the camera names
            camera_names = [cam['camera_name'] for cam in cameras_data]
            return jsonify({"success": True, "cameras": camera_names})
        except Exception as e:
            logger.error(f"Error getting cameras: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})
    
    @app.route('/api/camera/focus-leader', methods=['POST'])
    def focus_camera_on_leader():
        """Focus camera on race leader."""
        client = get_iracing_client()
        if not client:
            return jsonify({"success": False, "error": "iRacing client not available"})
            
        try:
            data = request.get_json() or {}
            camera = data.get('camera', 0)
            
            result = client.focus_camera_on_leader(camera)
            if result:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Failed to focus camera on leader"})
        except Exception as e:
            logger.error(f"Error focusing camera on leader: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})
    
    @app.route('/api/camera/focus-position', methods=['POST'])
    def focus_camera_on_position():
        """Focus camera on car in specific position."""
        client = get_iracing_client()
        if not client:
            return jsonify({"success": False, "error": "iRacing client not available"})
            
        try:
            data = request.get_json() or {}
            position = data.get('position')
            camera = data.get('camera', 0)
            
            if position is None:
                return jsonify({"success": False, "error": "Position is required"})
                
            result = client.focus_camera_on_position(position, camera)
            if result:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": f"Failed to focus camera on position {position}"})
        except Exception as e:
            logger.error(f"Error focusing camera on position: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})
    
    @app.route('/api/camera/focus-car-number', methods=['POST'])
    def focus_camera_on_car_number():
        """Focus camera on car with specific number."""
        client = get_iracing_client()
        if not client:
            return jsonify({"success": False, "error": "iRacing client not available"})
            
        try:
            data = request.get_json() or {}
            car_number = data.get('car_number')
            camera = data.get('camera', 0)
            
            if car_number is None:
                return jsonify({"success": False, "error": "Car number is required"})
                
            result = client.focus_camera_on_car_number(car_number, camera)
            if result:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": f"Failed to focus camera on car number {car_number}"})
        except Exception as e:
            logger.error(f"Error focusing camera on car number: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})
    
    @app.route('/api/camera/focus-driver', methods=['POST'])
    def focus_camera_on_driver():
        """Focus camera on specific driver by name."""
        client = get_iracing_client()
        if not client:
            return jsonify({"success": False, "error": "iRacing client not available"})
            
        try:
            data = request.get_json() or {}
            driver_name = data.get('driver_name')
            camera = data.get('camera', 0)
            
            if not driver_name:
                return jsonify({"success": False, "error": "Driver name is required"})
                
            result = client.focus_camera_on_driver(driver_name, camera)
            if result:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": f"Failed to focus camera on driver {driver_name}"})
        except Exception as e:
            logger.error(f"Error focusing camera on driver: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})
    
    @app.route('/api/camera/focus-battles', methods=['POST'])
    def focus_camera_on_battles():
        """Focus camera on close battles on track."""
        client = get_iracing_client()
        if not client:
            return jsonify({"success": False, "error": "iRacing client not available"})
            
        try:
            data = request.get_json() or {}
            gap_threshold = data.get('gap_threshold', 1.0)
            camera = data.get('camera', 0)
            
            result = client.focus_camera_on_battles(gap_threshold, camera)
            if result:
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Failed to focus camera on battles"})
        except Exception as e:
            logger.error(f"Error focusing camera on battles: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})

    @app.route('/api/focused_driver')
    def get_focused_driver():
        """Endpoint to get the details of the driver currently focused by the camera."""
        if not state.focused_driver_enabled:
            return jsonify({
                "success": True,
                "focusedDriver": None,
                "message": "Focused driver functionality is disabled"
            })
            
        if state.focused_driver_details:
            # Return the stored details directly
            return jsonify({
                "success": True,
                "focusedDriver": state.focused_driver_details 
            })
        else:
            # If no driver details are stored (e.g., not connected, error during processing)
            return jsonify({"error": "Focused driver details not available."}), 404
            
    @app.route('/api/toggle-focused-driver', methods=['POST'])
    def toggle_focused_driver():
        """Endpoint to enable/disable focused driver functionality."""
        data = request.get_json() or {}
        if 'enabled' in data:
            state.focused_driver_enabled = bool(data['enabled'])
            logger.debug(f"Toggling focused driver to: {state.focused_driver_enabled}. Current active columns: {state.active_columns}") # Add log here
            # Save the configuration
            config_manager.save_config({
                "activeColumns": state.active_columns,
                "driverNameFormat": state.driver_name_format,
                "focusedDriverEnabled": state.focused_driver_enabled,
                "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo, # Ensure all configs are saved
                "overlayWindowEnabled": state.overlay_window_enabled,
                "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
            })
            return jsonify({
                "success": True,
                "enabled": state.focused_driver_enabled
            })
        return jsonify({
            "success": False,
            "error": "Missing 'enabled' parameter"
        })

    @app.route('/api/toggle-focused-driver-team-logo', methods=['POST'])
    def toggle_focused_driver_team_logo():
        """Endpoint to enable/disable showing the focused driver's team logo."""
        data = request.get_json() or {}
        if 'enabled' in data:
            state.show_focused_driver_team_logo = bool(data['enabled'])
            # Save the configuration
            config_manager.save_config({
                "activeColumns": state.active_columns,
                "driverNameFormat": state.driver_name_format,
                "focusedDriverEnabled": state.focused_driver_enabled,
                "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo,
                "overlayWindowEnabled": state.overlay_window_enabled,
                "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
            })
            return jsonify({
                "success": True,
                "enabled": state.show_focused_driver_team_logo
            })
        return jsonify({
            "success": False,
            "error": "Missing 'enabled' parameter"
        })

    @app.route('/api/toggle-focused-driver-battle-mode', methods=['POST'])
    def toggle_focused_driver_battle_mode():
        """Endpoint to enable/disable the P1/P2 duel/train card for the focused driver."""
        data = request.get_json() or {}
        if 'enabled' in data:
            state.focused_driver_battle_mode_enabled = bool(data['enabled'])
            config_manager.save_config({
                "activeColumns": state.active_columns,
                "driverNameFormat": state.driver_name_format,
                "focusedDriverEnabled": state.focused_driver_enabled,
                "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo,
                "overlayWindowEnabled": state.overlay_window_enabled,
                "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
            })
            return jsonify({
                "success": True,
                "enabled": state.focused_driver_battle_mode_enabled
            })
        return jsonify({
            "success": False,
            "error": "Missing 'enabled' parameter"
        })

    @app.route('/api/overlay-window-status')
    def overlay_window_status():
        """Return whether the PyQt5 overlay window is enabled/running."""
        return jsonify({
            "success": True,
            "enabled": state.overlay_window_enabled,
            "running": overlay_window_manager.is_running() if overlay_window_manager else False
        })

    @app.route('/api/toggle-overlay-window', methods=['POST'])
    def toggle_overlay_window():
        """Endpoint to start/stop the PyQt5 overlay window."""
        data = request.get_json() or {}
        if 'enabled' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'enabled' parameter"
            })

        enabled = bool(data['enabled'])
        state.overlay_window_enabled = enabled

        if overlay_window_manager:
            if enabled:
                overlay_window_manager.start()
            else:
                overlay_window_manager.stop()

        config_manager.save_config({
            "activeColumns": state.active_columns,
            "driverNameFormat": state.driver_name_format,
            "focusedDriverEnabled": state.focused_driver_enabled,
            "showFocusedDriverTeamLogo": state.show_focused_driver_team_logo,
            "overlayWindowEnabled": state.overlay_window_enabled,
            "focusedDriverBattleMode": state.focused_driver_battle_mode_enabled
        })

        return jsonify({
            "success": True,
            "enabled": state.overlay_window_enabled,
            "running": overlay_window_manager.is_running() if overlay_window_manager else False
        })

    @app.route('/api/session-results')
    def session_results():
        """Return ResultsPositions from SessionInfo, enriched with driver names/numbers.
        Query params:
          - session: 'race', 'qualify', 'practice', or a session number. Defaults to current.
          - for_grid: if 'true', returns qualifying results sorted by position (for starting grid).
        """
        client = get_iracing_client()
        if not client or not client.ir:
            return jsonify({"error": "iRacing not connected"}), 503

        try:
            session_info = client.ir['SessionInfo']
            driver_info = client.ir['DriverInfo']
            weekend_info = client.ir['WeekendInfo']

            if not session_info or not driver_info:
                return jsonify({"error": "No session data available"}), 503

            sessions = session_info.get('Sessions', [])
            drivers_list = driver_info.get('Drivers', [])

            # Build CarIdx -> driver lookup
            driver_lookup = {}
            for d in drivers_list:
                if d.get('UserID', 0) > 0:
                    car_idx = d.get('CarIdx')
                    if car_idx is not None:
                        full_name = d.get('UserName', 'Unknown')
                        name_format = state.driver_name_format or 'full'
                        from iracing.data_processor import format_driver_name
                        driver_lookup[car_idx] = {
                            'carNumber': d.get('CarNumber', 'N/A'),
                            'userName': format_driver_name(full_name, name_format),
                            'fullName': full_name,
                            'carIdx': car_idx,
                            'startPosition': d.get('GridStartingPosition', 0),
                        }

            # Determine which session to read
            for_grid = request.args.get('for_grid', 'false').lower() == 'true'
            session_param = request.args.get('session', None)
            target_session = None

            if session_param is not None:
                if session_param.isdigit():
                    idx = int(session_param)
                    if 0 <= idx < len(sessions):
                        target_session = sessions[idx]
                else:
                    # Find by type name
                    keyword = session_param.upper()
                    for s in reversed(sessions):
                        s_type = (s.get('SessionType') or '').upper()
                        s_name = (s.get('SessionName') or '').upper()
                        if keyword in s_type or keyword in s_name:
                            target_session = s
                            break

            # Default: for grid use qualifying, for results use current session
            if target_session is None:
                if for_grid:
                    # Look for qualifying session
                    for s in reversed(sessions):
                        s_type = (s.get('SessionType') or '').upper()
                        if 'QUALIFY' in s_type:
                            target_session = s
                            break
                if target_session is None:
                    # Fall back to current session
                    current_num = client.ir['SessionNum']
                    if current_num is not None and 0 <= current_num < len(sessions):
                        target_session = sessions[current_num]

            if not target_session:
                return jsonify({"error": "No matching session found"}), 404

            results_positions = target_session.get('ResultsPositions') or []
            fastest_lap_info = target_session.get('ResultsFastestLap') or []
            fastest_car_idx = None
            if fastest_lap_info:
                fl = fastest_lap_info[0]
                if fl.get('FastestTime', -1) > 0:
                    fastest_car_idx = fl.get('CarIdx')

            # Build enriched results
            enriched = []
            p1_time = None
            for rp in results_positions:
                car_idx = rp.get('CarIdx')
                drv = driver_lookup.get(car_idx)
                if not drv:
                    continue

                pos = rp.get('Position', 999)
                gap_seconds = rp.get('Time', -1)
                fastest_time = rp.get('FastestTime', -1)
                laps_complete = rp.get('LapsComplete', 0)
                reason_out = rp.get('ReasonOutStr', 'Running')
                laps_led = rp.get('LapsLed', 0)

                # Format fastest time
                best_lap_str = ''
                if fastest_time > 0:
                    mins = int(fastest_time // 60)
                    secs = fastest_time % 60
                    best_lap_str = f"{mins}:{secs:06.3f}" if mins > 0 else f"{secs:.3f}"

                # Format gap
                if pos == 1:
                    p1_time = gap_seconds
                    gap_str = 'WINNER' if reason_out == 'Running' else reason_out
                elif reason_out not in ('Running', ''):
                    gap_str = reason_out
                elif gap_seconds > 0:
                    gap_str = f"+{gap_seconds:.3f}"
                else:
                    gap_str = '-'

                entry = {
                    'position': pos,
                    'carNumber': drv['carNumber'],
                    'userName': drv['userName'],
                    'fullName': drv['fullName'],
                    'carIdx': car_idx,
                    'startPosition': drv['startPosition'],
                    'gap': gap_str,
                    'gapSeconds': gap_seconds,
                    'bestLapTime': best_lap_str,
                    'fastestTimeRaw': fastest_time,
                    'lapsComplete': laps_complete,
                    'lapsLed': laps_led,
                    'reasonOut': reason_out,
                    'isFastestLap': car_idx == fastest_car_idx,
                }

                # Positions gained
                if drv['startPosition'] > 0 and pos > 0:
                    entry['positionsGained'] = drv['startPosition'] - pos
                else:
                    entry['positionsGained'] = 0

                enriched.append(entry)

            # Sort by position
            enriched.sort(key=lambda x: x['position'])

            return jsonify({
                'trackName': weekend_info.get('TrackName', 'Unknown'),
                'trackConfig': weekend_info.get('TrackConfigName', ''),
                'sessionName': target_session.get('SessionName', ''),
                'sessionType': target_session.get('SessionType', ''),
                'resultsLapsComplete': target_session.get('ResultsLapsComplete', -1),
                'drivers': enriched,
            })

        except Exception as e:
            logger.error(f"Error building session results: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route('/api/weekend_info')
    def weekend_info():
        client = get_iracing_client()
        if client and client.ir:
            return jsonify(client.ir['WeekendInfo'])
        return jsonify({"error": "No data available"})

    @app.route('/api/import-history', methods=['POST'])
    def import_history():
        """Import iRacing event result JSONs from overlay/old_iracing_races/ into race_history.json."""
        try:
            from iracing.history import import_iracing_files
            result = import_iracing_files()
            return jsonify({"success": True, **result})
        except Exception as e:
            logger.error(f"import_history route error: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/history-stats')
    def history_stats():
        """Return a summary of what is in race_history.json."""
        try:
            from iracing.history import _get_history
            history = _get_history()
            sessions = history.get('sessions', [])
            summary = []
            for s in sessions:
                summary.append({
                    "session_id":   s.get('session_id'),
                    "track":        s.get('track'),
                    "date":         s.get('date'),
                    "session_type": s.get('session_type'),
                    "drivers":      len(s.get('results', [])),
                })
            return jsonify({"success": True, "total_sessions": len(sessions), "sessions": summary})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
