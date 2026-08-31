# Data processor for iRacing driver data

import logging
import sys
import os
import json
import logging
import os
import sys

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web')) # For config_manager
from web.config import ConfigManager # Import ConfigManager

from utils.formatting import format_lap_time, format_time_difference, format_driver_name

# Initialize logger
logger = logging.getLogger("iracing-timing")

# General compound map: 0 for Dry, 1 for Wet
COMPOUND_MAP = {0: 'Dry', 1: 'Wet'}

# Define path for car brands config and teams config
CAR_BRANDS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'web', 'config', 'carBrands.json')
TEAMS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'web', 'config', 'teams.json')

def load_car_brands():
    """Loads car brand data from the JSON file."""
    try:
        if os.path.exists(CAR_BRANDS_FILE_PATH):
            with open(CAR_BRANDS_FILE_PATH, 'r') as f:
                content = f.read().strip()
                if not content:
                    logger.warning(f"Car brands file is empty: {CAR_BRANDS_FILE_PATH}. Creating default.")
                    default_data = {}
                    save_car_brands(default_data)
                    return default_data
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in {CAR_BRANDS_FILE_PATH}. Creating fresh file.")
                    default_data = {}
                    save_car_brands(default_data)
                    return default_data
        else:
            logger.warning(f"Car brands file not found: {CAR_BRANDS_FILE_PATH}. Creating default.")
            default_data = {}
            save_car_brands(default_data)
            return default_data
    except Exception as e:
        logger.error(f"Error loading car brands file: {e}", exc_info=True)
        return {}

def save_car_brands(data):
    """Saves car brand data to the JSON file."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(CAR_BRANDS_FILE_PATH), exist_ok=True)
        with open(CAR_BRANDS_FILE_PATH, 'w') as f:
            json.dump(data, f, indent=4)  # Use indent for readability
        logger.info(f"Car brands data saved to {CAR_BRANDS_FILE_PATH}")
    except Exception as e:
        logger.error(f"Error saving car brands file: {e}", exc_info=True)
        return {}

def load_teams_config(state):
    """Loads team configuration from the JSON file."""
    try:
        # Initialize ConfigManager here, passing the state object
        teams_config_manager = ConfigManager(TEAMS_FILE_PATH, state)
        return teams_config_manager.load_config()
    except Exception as e:
        logger.error(f"Error loading teams configuration: {e}", exc_info=True)
        return {}

def save_car_brands(data):
    """Saves car brand data to the JSON file."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(CAR_BRANDS_FILE_PATH), exist_ok=True)
        with open(CAR_BRANDS_FILE_PATH, 'w') as f:
            json.dump(data, f, indent=4)  # Use indent for readability
        logger.info(f"Car brands data saved to {CAR_BRANDS_FILE_PATH}")
    except Exception as e:
        logger.error(f"Error saving car brands file: {e}", exc_info=True)
        return {}
    
def init_sectors(ir, state):
    if state.track_sectors:
        return

    split_info = ir['SessionInfo'].get('SplitTimeInfo')
    use_virtual = True

    # Intentar cargar sectores oficiales
    if split_info and 'Sectors' in split_info:
        sectors = split_info.get('Sectors', [])
        if sectors:
            use_virtual = False
            ordered = sorted(sectors, key=lambda s: s['SectorStartPct'])
            state.track_sectors = [
                {
                    "index": s['SectorNum'],
                    "start": s['SectorStartPct'],
                    "name": s.get('SectorName', f"S{s['SectorNum']}")
                }
                for s in ordered
            ]
            logger.info(f"init_sectors: Inicializados {len(state.track_sectors)} sectores oficiales.")

    # Fallback: Generar PUNTOS DE CONTROL virtuales
    if use_virtual:
        logger.warning("init_sectors: Generando puntos de control virtuales para parciales.")
        # Definimos DÓNDE TERMINA cada sector para capturar el tiempo
        state.track_sectors = [
            {
                # Este punto marca el FINAL del Sector 1 y el INICIO del Sector 2
                "index": 1,
                "start": 0.3333, 
                "name": "Split 1 (33%)"
            },
            {
                # Este punto marca el FINAL del Sector 2 y el INICIO del Sector 3
                "index": 2,
                "start": 0.6666,
                "name": "Split 2 (66%)"
            }
            # El Sector 3 termina cuando la vuelta cambia (en el 0.0/1.0),
            # eso lo maneja la lógica de cambio de vuelta automáticamente.
        ]

def init_car_sector_state(state, carIdx):
    if carIdx not in state.sector_data:
        state.sector_data[carIdx] = {
            "lastLap": -1,
            "lastPct": 0.0,
            "lapStartTime": None,  # session time when current lap started (S/F crossing)
            "last_boundary_time": None,
            "last_valid_sector_cache": None,
            "current_lap_sector_status": [0, 0, 0], # [S1, S2, S3] (0=None, 1=Gray, 2=Green, 3=Purple)
            "sector_deltas": [None, None, None],     # delta vs session best at time of crossing (before best update)
            "incomplete_lap": True, # First lap observed is incomplete (joined mid-lap)
            "laps": {}
        }
        
    # Inicializar registro de récords personales si no existe
    if carIdx not in state.driver_best_sectors:
        state.driver_best_sectors[carIdx] = {}

def update_sector_times(ir, state):
    if not state.track_sectors: return
    dist_pcts = ir['CarIdxLapDistPct']
    car_laps = ir['CarIdxLap']
    if not dist_pcts or not car_laps: return
    session_time = ir['SessionTime']

    for car_idx, lap_progress in enumerate(dist_pcts):
        if car_idx >= len(car_laps): continue
        current_lap = car_laps[car_idx]

        init_car_sector_state(state, car_idx)
        car_sector_state = state.sector_data[car_idx]

        # --- 1. CAMBIO DE VUELTA ---
        if car_sector_state["lastLap"] != current_lap:
            # Procesar el ÚLTIMO sector (Meta) de la vuelta anterior
            last_bound = car_sector_state["last_boundary_time"]
            if last_bound is not None and car_sector_state["lastLap"] != -1:
                final_split_time = session_time - last_bound
                if final_split_time > 0.5:
                    # El índice del último sector es siempre el último de la lista
                    last_idx = len(state.track_sectors) 
                    # NOTA: Si tus sectores son [S1, S2], el S3 es implícito. 
                    # Asumiremos que index 0=S1, 1=S2, 2=S3 (Meta)
                    
                    process_sector_color(state, car_idx, last_idx, final_split_time)

            is_initial = car_sector_state["lastLap"] == -1

            # RESET para nueva vuelta
            car_sector_state["lastLap"] = current_lap
            car_sector_state["lastPct"] = 0.0

            if is_initial:
                # First time seeing this car — don't set a fake boundary time
                # Mark sectors already passed as crossed so they won't produce bogus times
                car_sector_state["last_boundary_time"] = None
                car_sector_state["laps"][current_lap] = []
                for s in state.track_sectors:
                    already_passed = lap_progress >= s["start"]
                    car_sector_state["laps"][current_lap].append({
                        "name": s["name"], "time": None,
                        "crossed": already_passed, "valid": False
                    })
            else:
                car_sector_state["last_boundary_time"] = session_time
                car_sector_state["lapStartTime"] = session_time  # record when this lap began
                car_sector_state["sector_deltas"] = [None, None, None]  # reset per-lap deltas
                car_sector_state["laps"][current_lap] = [
                    {"name": s["name"], "time": None, "crossed": False, "valid": False}
                    for s in state.track_sectors
                ]

                # Clear out lap flag: car crossed start/finish
                if state.on_out_lap.get(car_idx, False):
                    state.on_out_lap[car_idx] = False

        # Protección integridad estructura
        current_lap_sectors = car_sector_state["laps"].get(current_lap, [])
        if len(current_lap_sectors) != len(state.track_sectors):
             car_sector_state["laps"][current_lap] = [
                {"name": s["name"], "time": None, "crossed": False, "valid": False}
                for s in state.track_sectors
            ]
             current_lap_sectors = car_sector_state["laps"][current_lap]

        # --- 2. SECTORES INTERMEDIOS ---
        for idx, sector in enumerate(state.track_sectors):
            sector_record = current_lap_sectors[idx]
            if sector_record["crossed"]: continue

            if lap_progress >= sector["start"]:
                last_bound = car_sector_state["last_boundary_time"]
                
                if last_bound is not None:
                    split_time = session_time - last_bound
                    if split_time > 0.1:
                        sector_record["time"] = split_time
                        sector_record["valid"] = True
                        
                        # Cache para columna Last Sector (skip during out laps)
                        if not state.on_out_lap.get(car_idx, False):
                            # Compute delta BEFORE process_sector_color updates the best
                            current_best = state.session_best_sectors.get(idx)
                            delta = (split_time - current_best) if current_best is not None else None
                            car_sector_state["last_valid_sector_cache"] = {
                                "name": f"S{idx + 1}",
                                "time": split_time,
                                "delta": delta
                            }
                            # Store per-sector delta for focused driver card
                            deltas = car_sector_state.setdefault("sector_deltas", [None, None, None])
                            if idx < len(deltas):
                                deltas[idx] = delta
                        
                        # --- PROCESAR COLOR DEL SECTOR ---
                        process_sector_color(state, car_idx, idx, split_time)
                        # ---------------------------------
                    else:
                        sector_record["valid"] = False
                else:
                    sector_record["valid"] = False

                car_sector_state["last_boundary_time"] = session_time
                sector_record["crossed"] = True
        
        car_sector_state["lastPct"] = lap_progress

def process_sector_color(state, car_idx, sector_index, time_value):
    """
    Determina el color del sector y gestiona la exclusividad del 'Morado'.
    Si se bate un récord absoluto, busca al anterior poseedor en la vuelta actual y lo pasa a Verde.
    """
    # Out lap: don't count as PB or session best, mark as gray
    if state.on_out_lap.get(car_idx, False):
        status_list = state.sector_data[car_idx]["current_lap_sector_status"]
        while len(status_list) <= sector_index:
            status_list.append(0)
        if sector_index == 0:
            for i in range(1, len(status_list)):
                status_list[i] = 0
        status_list[sector_index] = 1  # Gray - out lap / incomplete sector
        return

    status_code = 1 # Por defecto Gris

    # 1. Comprobar PERSONAL BEST
    pbs = state.driver_best_sectors[car_idx]
    current_pb = pbs.get(sector_index)

    is_pb = False
    if current_pb is None or time_value <= current_pb:
        pbs[sector_index] = time_value
        is_pb = True
        status_code = 2 # Verde

    # 2. Comprobar OVERALL BEST (Récord Absoluto)
    overall_best = state.session_best_sectors.get(sector_index)

    # Solo robamos el morado si el tiempo es ESTRICTAMENTE MENOR (<)
    # (Si es empate, se lo queda el que lo hizo primero, así que no entramos aquí)
    if overall_best is None or time_value < overall_best:
        # ¡Nuevo récord absoluto!
        state.session_best_sectors[sector_index] = time_value
        status_code = 3 # Morado
        
        # --- LIMPIEZA: Quitar morados antiguos ---
        # Recorremos todos los coches activos para ver si alguien tenía el morado en este sector
        # y se lo bajamos a Verde (ya que por definición era su Personal Best)
        for other_idx, data in state.sector_data.items():
            if other_idx == car_idx: 
                continue # No nos tocamos a nosotros mismos todavía
            
            # Acceder a la lista de estados visuales del otro piloto
            status_list = data.get("current_lap_sector_status", [])
            
            # Verificar si tiene un estado guardado para este sector
            if len(status_list) > sector_index:
                if status_list[sector_index] == 3: # Si tenía Morado
                    status_list[sector_index] = 2  # Se lo bajamos a Verde
                    # logger.info(f"Récord batido por Car {car_idx}. Car {other_idx} pasa de Morado a Verde en S{sector_index+1}")
        # -----------------------------------------

    # Guardar estado en la lista del piloto actual
    status_list = state.sector_data[car_idx]["current_lap_sector_status"]
    while len(status_list) <= sector_index:
        status_list.append(0)
        
    if sector_index == 0:
        for i in range(1, len(status_list)):
            status_list[i] = 0
    status_list[sector_index] = status_code

def get_lap_data(ir, car_idx):
    """
    Get lap data for a specific car.

    Args:
        ir (irsdk.IRSDK): iRacing SDK instance
        car_idx (int): Car index

    Returns:
        dict: Lap data for the specified car
    """
    lap_data = {}

    # Check if we have data for the current session
    if ir['SessionInfo'] and 'Sessions' in ir['SessionInfo']:
        current_session = ir['SessionInfo']['Sessions'][ir['SessionNum']]

        # Check if results are available
        if 'ResultsPositions' in current_session and current_session['ResultsPositions'] is not None:
            for result in current_session['ResultsPositions']:
                if int(result['CarIdx']) == car_idx:
                    # Add times if available
                    if 'LastTime' in result:
                        raw = result['LastTime']
                        lap_data['lastLapTimeRaw'] = raw if raw > 0 else None
                        lap_data['lastLapTime'] = format_lap_time(raw)
                    if 'FastestTime' in result:
                        lap_data['bestLapTime'] = format_lap_time(result['FastestTime'])
                    if 'LapsComplete' in result:
                        lap_data['lapsComplete'] = result['LapsComplete']
                    if 'Position' in result:
                        lap_data['position'] = result['Position']
                        #logger.debug(f"get_lap_data: CarIdx {car_idx} - Official Position from ResultsPositions: {result['Position']}")
                    if 'Time' in result: # Assuming 'Time' holds the total race time for finished drivers
                        lap_data['raceTime'] = result['Time']
                        #logger.debug(f"get_lap_data: CarIdx {car_idx} - Race Time from ResultsPositions: {result['Time']}")
    # Try to get more real-time driver data
    if car_idx < len(ir['CarIdxLap']):
        lap_data['currentLap'] = ir['CarIdxLap'][car_idx]

    if car_idx < len(ir['CarIdxLapDistPct']):
        lap_data['lapProgress'] = ir['CarIdxLapDistPct'][car_idx]

    return lap_data

def _get_pit_lane_markers(ir, state):
    """
    Gets the pit entry percentage from iRacing session info and stores it in state.
    """
    if state.pit_entry_pct == -1.0: # Only try to get it once
        try:
            split_time_info = ir['SessionInfo'].get('SplitTimeInfo', {})
            sectors = split_time_info.get('Sectors', [])
            for sector in sectors:
                if sector['SectorName'] == 'Pit Entry':
                    state.pit_entry_pct = sector['SectorStartPct']
                    logger.info(f"Marcador de entrada a pits encontrado en {state.pit_entry_pct:.4f} (% de la vuelta).")
                    return
        except Exception as e:
            logger.error(f"Error al procesar los marcadores de la pista: {e}")

def get_drivers_data(ir):
    """
    Get data for all drivers in the session.

    Args:
        ir (irsdk.IRSDK): iRacing SDK instance

    Returns:
        list: List of driver data dictionaries
    """
    from models.state import State

    # Get the state object from the client
    state = None
    try:
        from iracing.client import IRacingClient
        for client in IRacingClient.__instances__:
            if client.ir == ir:
                state = client.state
                break
    except:
        # If we can't get the state, create a temporary one
        state = State()
    drivers_data = []
    logger.info("Processing driver data")

    # Load car brands and teams config
    car_brands = load_car_brands()
    teams_config = load_teams_config(state) # Pass the state object
    new_cars_found = False  # Flag to track if we need to update the file

    # Get pit entry percentage if not already set
    if state:
        _get_pit_lane_markers(ir, state)
        # Sector init and update_sector_times are now handled by the 50ms thread

    try:
        drivers_list = ir['DriverInfo']['Drivers']
        logger.debug(f"Procesando datos de {len(drivers_list)} pilotos")

        # Get current lap distance percentages for pit detection
        current_lap_dist_pcts = ir['CarIdxLapDistPct']

        for driver in drivers_list:
            try:
                if not driver or not isinstance(driver, dict):
                    logger.warning("Piloto inválido encontrado, ignorando.")
                    continue

                # Get carIdx
                car_idx = driver.get('CarIdx')
                currentLap = ir['CarIdxLap'][car_idx]
                currentPct = ir['CarIdxLapDistPct'][car_idx]
                sessionTime = ir['SessionTime']
                if car_idx is None:
                    logger.warning(f"Piloto sin carIdx: {driver}")
                    continue

                # Only include real drivers (not AI or ghosts)
                if driver.get('UserID', 0) > 0:
                    # Get the original full name
                    full_name = driver.get('UserName', "Desconocido")

                    # Get the name format from state if available, default to "full"
                    name_format = "full"
                    if state and hasattr(state, 'driver_name_format'):
                        name_format = state.driver_name_format

                    # Format the driver name according to the selected format
                    formatted_name = format_driver_name(full_name, name_format)

                    driver_info = {
                        "carIdx": car_idx,
                        "userName": formatted_name,
                        "fullName": full_name,  # Keep the original name for reference
                        "carNumber": driver.get('CarNumber', "N/A"),
                        "carName": driver.get('CarScreenName', "N/A"),
                        "iRating": driver.get('IRating', 0),
                        "UserID": driver.get('UserID', 0),
                        "teamName": driver.get('TeamName', ""), # Default from iRacing
                        "teamLogoUrl": "", # Default empty
                        "pitstops": state.pit_stop_counts.get(car_idx, 0) if state else 0, # Include pitstops
                        "finished": (car_idx in state.finished_cars) if state else False,
                        "startPosition": driver.get('GridStartingPosition', 0) # Add starting position
                    }

                    # Add tire compound information
                    tire_compound_int = ir['CarIdxTireCompound'][car_idx]
                    current_tire_compound = COMPOUND_MAP.get(tire_compound_int)

                    if current_tire_compound:
                        # If we have a valid compound, use it and update the cache
                        driver_info['tireCompound'] = current_tire_compound
                        if state:
                            state.last_known_tire_compounds[car_idx] = current_tire_compound
                    else:
                        # If current compound is unknown, try to get from cache
                        if state and car_idx in state.last_known_tire_compounds:
                            driver_info['tireCompound'] = state.last_known_tire_compounds[car_idx]
                        else:
                            driver_info['tireCompound'] = "Unknown"

                    # Override teamName and add teamLogoUrl from teams.json if configured
                    for team_name, team_data in teams_config.items():
                        if not isinstance(team_data, dict):
                            continue
                        # Ensure team_data has 'drivers' and 'logo' properties
                        team_drivers = team_data.get('drivers', [])
                        team_logo = team_data.get('logo', '')

                        # Check if the current driver (by UserID or carNumber) is in this team
                        if any(d.get('id') == driver_info['UserID'] for d in team_drivers):
                            driver_info['teamName'] = team_name
                            if team_logo:
                                driver_info['teamLogoUrl'] = f"/static/team_logos/{team_logo}"
                            else:
                                driver_info['teamLogoUrl'] = "" # No logo assigned
                            break # Driver found in a team, no need to check other teams

                    # Car Brand Logic
                    car_name = driver.get('CarScreenName', "N/A")
                    if car_name not in car_brands:
                        # Only add new car if it doesn't exist, preserving any existing URLs
                        car_brands[car_name] = car_brands.get(car_name, "")  # Preserve existing or set empty
                        new_cars_found = True
                    driver_info['brandImageUrl'] = car_brands[car_name]  # Always use current value

                    # Look for lap time data in the current session
                    lap_data = get_lap_data(ir, car_idx)
                    if driver.get('UserID') != 559690 and driver.get('UserID') != 820378:
                        if lap_data:
                            driver_info.update(lap_data)
                            # Track lap completions for consistency scoring
                            if state and car_idx is not None:
                                current_laps = driver_info.get('lapsComplete') or 0
                                last_laps = state.driver_laps_complete.get(car_idx, -1)
                                if last_laps >= 0 and current_laps > last_laps:
                                    raw_t = driver_info.get('lastLapTimeRaw')
                                    if raw_t and raw_t > 0:
                                        state.driver_lap_times.setdefault(car_idx, []).append(raw_t)
                                state.driver_laps_complete[car_idx] = current_laps
                            # Ensure officialPosition is always set from the initial 'position' if available
                            if 'position' in driver_info:
                                driver_info['officialPosition'] = driver_info['position']
                            
                            # Calculate positions gained/lost
                            # Prefer qualifying grid order from SessionInfo, fall back to GridStartingPosition
                            start_pos = driver_info['startPosition']
                            if (not start_pos or start_pos <= 0) and state and car_idx in state.qualify_grid_order:
                                start_pos = state.qualify_grid_order[car_idx]
                                driver_info['startPosition'] = start_pos
                            current_pos = driver_info.get('position', 0)
                            if start_pos > 0 and current_pos > 0:
                                driver_info['positionsGained'] = start_pos - current_pos
                            else:
                                driver_info['positionsGained'] = 0
                        last_sector_str = "-"
                        driver_info['lastSectorRawTime'] = None
                        driver_info['lastSectorIndex'] = None
                        driver_info['lastSectorDelta'] = None
                        if state and car_idx in state.sector_data:
                            # Accedemos a la caché que creamos en el paso 2
                            cache = state.sector_data[car_idx].get("last_valid_sector_cache")
                            if cache:
                                # Formato: "S1 30.52" (Nombre + Tiempo con 2 decimales)
                                last_sector_str = f"{cache['name']} {cache['time']:.2f}"
                                driver_info['lastSectorRawTime'] = cache['time']
                                driver_info['lastSectorDelta'] = cache.get('delta')
                                # Extract sector index from name "S1" -> 0, "S2" -> 1, "S3" -> 2
                                driver_info['lastSectorIndex'] = int(cache['name'][1]) - 1

                        driver_info['lastSector'] = last_sector_str
                        if state and car_idx in state.sector_data:
                            status_list = state.sector_data[car_idx]["current_lap_sector_status"]
                            # Nos aseguramos de enviar solo los 3 primeros (o los que quepan en la visualización)
                            # Normalmente S1, S2, S3
                            driver_info['sectors'] = status_list[:3] 
                        else:
                            driver_info['sectors'] = [0, 0, 0]
                        drivers_data.append(driver_info)
                    else:
                        logger.debug("removed charly from the list of drivers_data")

                    # Enhanced pit status detection - check multiple conditions
                    if state:
                        # Check if car is on pit road
                        current_on_pit_road = False
                        if car_idx < len(ir['CarIdxOnPitRoad']):
                            current_on_pit_road = ir['CarIdxOnPitRoad'][car_idx]

                        # Check if car is abandoned/retired (NotInWorld or UndefinedMaterial)
                        car_abandoned = False
                        if car_idx < len(ir['CarIdxTrackSurface']):
                            track_surface = ir['CarIdxTrackSurface'][car_idx]
                            # -1 = NotInWorld, 0 = UndefinedMaterial (both indicate abandoned/retired)
                            car_abandoned = track_surface in [-1, 0]

                        # Determine final pit status
                        driver_info['onPitRoad'] = current_on_pit_road or car_abandoned

                        # Track pit state changes and count pit stops
                        last_pit_state = state.last_pit_state.get(car_idx, False)
                        current_session_time = ir['SessionTime']

                        if current_on_pit_road != last_pit_state:
                            if current_on_pit_road:
                                # Car entered pits - record entry time, lap number, and increment counter
                                state.pit_entry_times[car_idx] = current_session_time
                                current_lap = ir['CarIdxLap'][car_idx] if car_idx < len(ir['CarIdxLap']) else 0
                                state.last_pit_lap[car_idx] = current_lap
                                if state.current_session_type == State.SESSION_RACE:
                                    state.pit_stop_counts[car_idx] = state.pit_stop_counts.get(car_idx, 0) + 1
                                    logger.info(f"Pit stop detected for CarIdx {car_idx} on lap {current_lap}. Total pit stops: {state.pit_stop_counts[car_idx]}")
                                else:
                                    logger.info(f"CarIdx {car_idx} entered pits on lap {current_lap} (not counted - not a race)")
                            else:
                                # Car exited pits - calculate pit stop duration
                                if car_idx in state.pit_entry_times:
                                    pit_duration = current_session_time - state.pit_entry_times[car_idx]
                                    state.last_pit_duration[car_idx] = pit_duration
                                    logger.info(f"CarIdx {car_idx} exited pits. Duration: {pit_duration:.2f}s")
                                else:
                                    logger.info(f"CarIdx {car_idx} exited pits (no entry time recorded)")
                                # Mark car as on out lap (practice/qualifying)
                                if state.current_session_type in (State.SESSION_PRACTICE, State.SESSION_QUALIFY):
                                    state.on_out_lap[car_idx] = True
                            state.last_pit_state[car_idx] = current_on_pit_road

                        # --- Pit box tracking (CarIdxTrackSurface == 1 = InPitStall) ---
                        if car_idx < len(ir['CarIdxTrackSurface']):
                            last_surface = state.last_surface_state.get(car_idx, -1)
                            in_pit_stall = (track_surface == 1)
                            was_in_pit_stall = (last_surface == 1)
                            if in_pit_stall and not was_in_pit_stall:
                                state.pit_box_entry_times[car_idx] = current_session_time
                            elif not in_pit_stall and was_in_pit_stall:
                                if car_idx in state.pit_box_entry_times:
                                    box_duration = current_session_time - state.pit_box_entry_times[car_idx]
                                    state.last_pit_box_duration[car_idx] = box_duration
                                    logger.info(f"CarIdx {car_idx} left pit box. Box duration: {box_duration:.2f}s")
                            state.last_surface_state[car_idx] = track_surface

                        # Also handle abandoned cars separately
                        if car_abandoned and not current_on_pit_road:
                            logger.info(f"CarIdx {car_idx} abandoned/retired (track surface: {track_surface})")
                            # Update display status to show abandoned
                            driver_info['onPitRoad'] = True

                        # Add pit timing data to driver info
                        driver_info['lastPitTime'] = state.last_pit_duration.get(car_idx, None)
                        driver_info['lastPitBoxTime'] = state.last_pit_box_duration.get(car_idx, None)
                        driver_info['lastPitLap'] = state.last_pit_lap.get(car_idx, None)
                        driver_info['onOutLap'] = state.on_out_lap.get(car_idx, False)
                    
            except Exception as e:
                logger.error(f"Error al procesar datos del piloto con carIdx={car_idx}: {str(e)}", exc_info=True)
        
        # Update last_lap_dist_pct for the next iteration (only if state exists)
        if state:
            state.last_lap_dist_pct = {idx: dist for idx, dist in enumerate(current_lap_dist_pcts)}

        # Calculate real track position based on lap and progress
        try:
            # First, make sure all drivers have necessary data
            for driver in drivers_data:
                if 'currentLap' not in driver:
                    driver['currentLap'] = 0
                if 'lapProgress' not in driver:
                    driver['lapProgress'] = 0
                if 'bestLapTime' not in driver or driver['bestLapTime'] == "N/A":
                    driver['bestLapTime'] = "N/A"  # Default high value for sorting

            # Process drivers based on session type
            if state and state.is_time_based_session():
                # Practice or Qualifying: Sort by best lap time
                logger.info(f"Processing {state.current_session_type} session data")
                drivers_data = process_time_based_session(drivers_data)
            elif state and state.current_session_type == State.SESSION_RACE and state.is_race_finished:
                # Race is finished, show results
                logger.info("Race is finished, showing results")
                drivers_data = process_race_results(drivers_data)
            else:
                session_state = ir['SessionState']

                # Create a position key that combines lap and progress
                for driver in drivers_data:
                    driver['trackPosition'] = (driver['currentLap'] * 100) + driver['lapProgress']

                # --- Build qualifying grid order from SessionInfo if not cached ---
                if state and not state.qualify_grid_order:
                    try:
                        sessions = ir['SessionInfo']['Sessions']
                        for s in reversed(sessions):
                            s_type = (s.get('SessionType') or '').upper()
                            if 'QUALIFY' in s_type:
                                rp_list = s.get('ResultsPositions') or []
                                for rp in rp_list:
                                    ci = rp.get('CarIdx')
                                    pos = rp.get('Position', 999)
                                    if ci is not None and pos > 0:
                                        state.qualify_grid_order[ci] = pos
                                if state.qualify_grid_order:
                                    logger.info(f"Built qualifying grid order for {len(state.qualify_grid_order)} drivers from SessionInfo")
                                break
                    except Exception as e:
                        logger.warning(f"Could not build qualifying grid order: {e}")

                # --- Track green flag transition for 2-second delay ---
                if state and session_state is not None:
                    if session_state >= 4 and state.green_flag_time is None:
                        state.green_flag_time = ir['SessionTime']
                        logger.info(f"Green flag detected at session time {state.green_flag_time}")

                # Determine if we should use grid order (before green + 2s after)
                use_grid_order = False
                if state and session_state is not None:
                    if session_state < 4:
                        use_grid_order = True
                    elif state.green_flag_time is not None:
                        elapsed = ir['SessionTime'] - state.green_flag_time
                        if elapsed < 2.0:
                            use_grid_order = True

                # --- GRIDDING: Before green flag (+ 2s), use qualifying grid order ---
                if use_grid_order:
                    logger.info("Gridding: using qualifying order")
                    def grid_sort_key(x):
                        ci = x.get('carIdx')
                        # Prefer qualifying ResultsPositions, fall back to GridStartingPosition
                        if state and ci in state.qualify_grid_order:
                            return state.qualify_grid_order[ci]
                        sp = x.get('startPosition', 0)
                        return sp if sp > 0 else 999
                    drivers_data = sorted(drivers_data, key=grid_sort_key)
                    for index, driver in enumerate(drivers_data):
                        driver['virtualPosition'] = index + 1
                        driver['interval'] = "-"
                        driver['gap'] = "-"

                # --- CHECKERED: Freeze finished cars, track-sort unfinished ---
                elif state and state.is_checkered_flag:
                    logger.info("Checkered flag: freezing finished car positions")
                    finished = [d for d in drivers_data if d.get('finished', False)]
                    unfinished = [d for d in drivers_data if not d.get('finished', False)]

                    # Freeze position for newly finished cars using officialPosition
                    for d in finished:
                        car_idx = d.get('carIdx')
                        if car_idx not in state.frozen_positions:
                            state.frozen_positions[car_idx] = d.get('officialPosition', d.get('position', 999))

                    finished.sort(key=lambda x: state.frozen_positions.get(x.get('carIdx'), 999))
                    unfinished.sort(key=lambda x: x.get('trackPosition', 0), reverse=True)

                    drivers_data = finished + unfinished
                    for index, driver in enumerate(drivers_data):
                        driver['virtualPosition'] = index + 1

                    drivers_data = calculate_intervals_with_virtual_positions(drivers_data, state)

                # --- NORMAL RACE: Virtual positions by track position ---
                else:
                    logger.info("Using virtual positions based on track position")
                    drivers_data = sorted(drivers_data, key=lambda x: x.get('trackPosition', 0), reverse=True)
                    for index, driver in enumerate(drivers_data):
                        driver['virtualPosition'] = index + 1

                    drivers_data = calculate_intervals_with_virtual_positions(drivers_data, state)

                # For ongoing race, 'position' should reflect the virtual position
                for driver in drivers_data:
                    driver['position'] = driver['virtualPosition']
                    # Recalculate positionsGained using displayed position vs qualifying grid
                    car_idx = driver.get('carIdx')
                    start_pos = driver.get('startPosition', 0)
                    if (not start_pos or start_pos <= 0) and state and car_idx in state.qualify_grid_order:
                        start_pos = state.qualify_grid_order[car_idx]
                        driver['startPosition'] = start_pos
                    if start_pos > 0 and driver['position'] > 0:
                        driver['positionsGained'] = start_pos - driver['position']
                    else:
                        driver['positionsGained'] = 0
                    logger.debug(f"get_drivers_data: CarIdx {car_idx} - Position: {driver.get('position')} - StartPos: {start_pos} - Gained: {driver.get('positionsGained')}")
        except Exception as e:
            logger.error(f"Error en cálculo de posiciones virtuales: {str(e)}", exc_info=True)
            # Fallback to original method if the new one fails
            drivers_data = calculate_intervals(drivers_data)
            drivers_data = sorted(drivers_data, key=lambda x: x.get('position', 999))

        logger.debug(f"Obtenidos datos de {len(drivers_data)} pilotos")
    except Exception as e:
        logger.error(f"Error general en get_drivers_data: {str(e)}", exc_info=True)

    if state:
        state.session_data = drivers_data
        state.session_time = ir['SessionTime']
        # Update focused driver details in state
        try:
            focused_idx = ir['CamCarIdx']
            all_drivers = ir['DriverInfo']['Drivers']

            # Find the driver details using the focused index
            focused_driver = None
            if 0 <= focused_idx < len(all_drivers):
                driver_raw = all_drivers[focused_idx]
                car_idx = driver_raw.get('CarIdx')
                focused_driver = {
                    "carIdx": car_idx,
                    "userName": driver_raw.get('UserName', "Unknown"),
                    "carNumber": driver_raw.get('CarNumber', "N/A"),
                    "teamName": driver_raw.get('TeamName', ""),
                    # Qualifying sector data
                    "lapStartTime": None,
                    "sectorStatus": [0, 0, 0],
                    "sectorTimes": [],
                }
                if car_idx is not None and car_idx in state.sector_data:
                    sd = state.sector_data[car_idx]
                    focused_driver["lapStartTime"] = sd.get("lapStartTime")
                    focused_driver["sectorStatus"] = sd.get("current_lap_sector_status", [0, 0, 0])
                    focused_driver["sectorDeltas"] = sd.get("sector_deltas", [None, None, None])
                    current_lap = sd.get("lastLap", -1)
                    lap_sectors = sd.get("laps", {}).get(current_lap, [])
                    focused_driver["sectorTimes"] = [
                        s["time"] for s in lap_sectors if s.get("crossed") and s.get("valid") and s.get("time") is not None
                    ]
                logger.debug(f"Updated focused_driver_details to: {focused_driver}")
            else:
                 logger.warning(f"CamCarIdx {focused_idx} is out of bounds for Drivers list (len={len(all_drivers)}).")
                 focused_driver = None # Ensure it's None if index is invalid

            state.focused_driver_details = focused_driver

        except KeyError:
            logger.warning("CamCarIdx or DriverInfo not found in iRacing data.")
            state.focused_driver_details = None
        except Exception as e:
            logger.error(f"Error updating focused_driver_details: {e}", exc_info=True)
            state.focused_driver_details = None
            
        # state.broadcast_data() # Consider if broadcasting focused driver is needed

    # Calculate performance scores using the full, position-enriched driver list
    try:
        from iracing.performance_score import calculate_performance_score
        for driver in drivers_data:
            driver['performanceScore'] = calculate_performance_score(driver, drivers_data, state)
    except Exception as e:
        logger.error(f"Error calculating performance scores: {e}", exc_info=True)

    # Save car brands if needed
    if new_cars_found:
        save_car_brands(car_brands)
    # --- DEBUG: imprimir sectores por coche ---
    # logger.info(state.sector_data.items())
    # for car_idx, car_data in state.sector_data.items():
    #     if car_data["laps"]:  # Solo coches con al menos una vuelta
    #         logger.info(f"\nCarIdx {car_idx} tiene {len(car_data['laps'])} vueltas registradas:")
    #         for lap_num, sectors in car_data["laps"].items():
    #             logger.info(f"  Vuelta {lap_num}:")
    #             for sector in sectors:
    #                 name = sector.get("name", f"S{sector.get('index', '?')}")
    #                 time = sector.get("time", "N/A")
    #                 crossed = sector.get("crossed", False)
    #                 logger.info(f"    Sector {name}: {time}s - {'Pasado' if crossed else 'Pendiente'}")
    # --- FIN DEBUG ---
    return drivers_data

def process_time_based_session(drivers_data):
    """
    Process driver data for time-based sessions (Practice, Qualifying).
    Sort drivers by best lap time and calculate time differences.

    Args:
        drivers_data (list): List of driver data dictionaries

    Returns:
        list: Processed driver data
    """
    # Convert best lap times to seconds for sorting
    for driver in drivers_data:
                if driver['bestLapTime'] != "N/A" and driver['bestLapTime'] != "999:59.999" and driver['bestLapTime'] != "-":
                    try:
                        minutes, seconds = map(float, driver['bestLapTime'].split(':'))
                        driver['bestLapTimeSeconds'] = minutes * 60 + seconds
                    except:
                        driver['bestLapTimeSeconds'] = 999999  # Default high value
                        driver['bestLapTime'] = "-"  # Show as "-" in the UI
                else:
                    driver['bestLapTimeSeconds'] = 999999  # Default high value
                    driver['bestLapTime'] = "-"  # Show as "-" in the UI

    # Sort by best lap time (ascending)
    drivers_data = sorted(drivers_data, key=lambda x: x.get('bestLapTimeSeconds', 999999))

    # Assign positions based on best lap time
    for index, driver in enumerate(drivers_data):
        driver['position'] = index + 1

    # Calculate time differences (gap and interval)
    leader_best_time = None
    prev_best_time = None

    for driver in drivers_data:
        if driver['position'] == 1:
            # Leader
            leader_best_time = driver.get('bestLapTimeSeconds', 0)
            prev_best_time = leader_best_time
            driver['interval'] = "Leader"
            driver['gap'] = "Leader"
        else:
            # Calculate interval (difference to previous driver)
            if prev_best_time and driver.get('bestLapTimeSeconds', 0) < 999999:
                interval_seconds = driver['bestLapTimeSeconds'] - prev_best_time
                driver['interval'] = format_time_difference(interval_seconds)
            else:
                driver['interval'] = "N/A"

            # Calculate gap (difference to leader)
            if leader_best_time and driver.get('bestLapTimeSeconds', 0) < 999999:
                gap_seconds = driver['bestLapTimeSeconds'] - leader_best_time
                driver['gap'] = format_time_difference(gap_seconds)
            else:
                driver['gap'] = "N/A"

            prev_best_time = driver.get('bestLapTimeSeconds', 0)

    return drivers_data

def process_race_session(drivers_data):
    """
    Process driver data for race sessions.
    Sort drivers by track position and calculate intervals based on track position.

    Args:
        drivers_data (list): List of driver data dictionaries

    Returns:
        list: Processed driver data
    """
    try:
        # Create a position key that combines lap and progress
        for driver in drivers_data:
            # Higher lap means better position, higher progress within same lap means better position
            driver['trackPosition'] = (driver['currentLap'] * 100) + driver['lapProgress']

        # Sort by this combined value (descending order - higher is better)
        drivers_data = sorted(drivers_data, key=lambda x: x.get('trackPosition', 0), reverse=True)

        # Assign virtual positions based on this sorting
        for index, driver in enumerate(drivers_data):
            driver['virtualPosition'] = index + 1

        # Use these virtual positions for interval calculations
        drivers_data = calculate_intervals_with_virtual_positions(drivers_data)

        # Keep both positions, but use virtual for display
        for driver in drivers_data:
            if 'position' in driver:
                driver['officialPosition'] = driver['position']
            driver['position'] = driver['virtualPosition']

    except Exception as e:
        logger.error(f"Error en cálculo de posiciones virtuales: {str(e)}", exc_info=True)
        # Fallback to original method if the new one fails
        drivers_data = calculate_intervals(drivers_data)
        drivers_data = sorted(drivers_data, key=lambda x: x.get('position', 999))

    return drivers_data

def process_race_results(drivers_data):
    """
    Process driver data for race results.
    Sort drivers by official position and show time differences.

    Args:
        drivers_data (list): List of driver data dictionaries

    Returns:
        list: Processed driver data
    """
    # Sort by official position, falling back to virtual position or a high default
    drivers_data = sorted(drivers_data, key=lambda x: x.get('officialPosition', x.get('virtualPosition', 999)))

    # After sorting, ensure 'position' reflects the official position for display
    for driver in drivers_data:
        if 'officialPosition' in driver:
            driver['position'] = driver['officialPosition']
        elif 'virtualPosition' in driver:
            driver['position'] = driver['virtualPosition']
        else:
            driver['position'] = 999 # Fallback if no position is found

        logger.debug(f"process_race_results (after sorting): CarIdx {driver.get('carIdx')} - Final Position: {driver.get('position')} - OfficialPosition: {driver.get('officialPosition')} - VirtualPosition: {driver.get('virtualPosition')}")
    # Calculate time differences for finished drivers using total race time and laps complete
    leader_race_time = None
    leader_laps_complete = 0
    prev_race_time = None
    prev_laps_complete = 0

    # Find the leader (first driver in the sorted list)
    if drivers_data:
        leader = drivers_data[0]
        leader['position'] = 1

        # Set finished to True for the leader in race results
        leader['finished'] = True

        # Get leader's race time and laps if available
        if 'raceTime' in leader and leader['raceTime'] is not None:
            try:
                leader_race_time = float(leader['raceTime'])
                prev_race_time = leader_race_time
            except ValueError:
                logger.warning(f"Could not convert leader's raceTime '{leader['raceTime']}' to float.")
                leader_race_time = None

        if 'lapsComplete' in leader and leader['lapsComplete'] is not None:
            leader_laps_complete = int(leader['lapsComplete'])
            prev_laps_complete = leader_laps_complete

        leader['interval'] = "Leader"
        leader['gap'] = "Leader"

        # Process the rest of the drivers
        for i in range(1, len(drivers_data)):
            driver = drivers_data[i]

            # Set finished to True for all drivers in race results
            driver['finished'] = True

            current_laps_complete = int(driver.get('lapsComplete', 0))
            current_race_time = None
            if 'raceTime' in driver and driver['raceTime'] is not None:
                try:
                    current_race_time = float(driver['raceTime'])
                except ValueError:
                    logger.warning(f"Could not convert driver's raceTime '{driver['raceTime']}' to float for CarIdx {driver.get('carIdx')}.")

            # Handle lapped drivers first
            if current_laps_complete < leader_laps_complete:
                lap_diff = leader_laps_complete - current_laps_complete
                driver['gap'] = f"+{lap_diff} Lap{'s' if lap_diff > 1 else ''}"

                # For interval, compare to previous driver's laps
                if current_laps_complete < prev_laps_complete:
                    interval_lap_diff = prev_laps_complete - current_laps_complete
                    driver['interval'] = f"+{interval_lap_diff} Lap{'s' if interval_lap_diff > 1 else ''}"
                elif current_laps_complete == prev_laps_complete and current_race_time is not None and prev_race_time is not None:
                    # Same lap as previous driver, calculate time interval
                    interval_seconds = current_race_time - prev_race_time
                    driver['interval'] = format_time_difference(interval_seconds)
                else:
                    driver['interval'] = "N/A" # Should not happen if sorted correctly
            elif current_laps_complete == leader_laps_complete and current_race_time is not None and leader_race_time is not None:
                # Same lap as leader, calculate time differences
                # Interval to previous driver
                if prev_race_time is not None:
                    interval_seconds = current_race_time - prev_race_time
                    driver['interval'] = format_time_difference(interval_seconds)
                else:
                    driver['interval'] = "N/A"

                # Gap to leader
                gap_seconds = current_race_time - leader_race_time
                driver['gap'] = format_time_difference(gap_seconds)
            else:
                # Driver did not finish or has no valid race time/laps
                driver['interval'] = "N/A"
                driver['gap'] = "N/A"

            prev_race_time = current_race_time if current_race_time is not None else prev_race_time # Update prev_race_time only if valid
            prev_laps_complete = current_laps_complete

    return drivers_data

def calculate_intervals(drivers_data):
    """
    Calculate intervals and gaps between drivers.

    Args:
        drivers_data (list): List of driver data dictionaries

    Returns:
        list: Updated list of driver data with intervals and gaps
    """
    sorted_drivers = sorted(drivers_data, key=lambda x: x.get('position', 999))

    leader_lap_progress = None
    leader_lap = None
    leader_best_time = None
    leader_last_lap_time = None

    # Find the leader
    for driver in sorted_drivers:
        if driver.get('position') == 1:
            leader_lap_progress = driver.get('lapProgress', 0)
            leader_lap = driver.get('currentLap', 0)

            # Try to get the best lap time
            if 'bestLapTime' in driver and driver['bestLapTime'] != "N/A":
                try:
                    minutes, seconds = map(float, driver['bestLapTime'].split(':'))
                    leader_best_time = minutes * 60 + seconds
                except:
                    leader_best_time = None

            # Try to get the last recorded lap time
            if 'lastLapTime' in driver and driver['lastLapTime'] != "N/A":
                try:
                    minutes, seconds = map(float, driver['lastLapTime'].split(':'))
                    leader_last_lap_time = minutes * 60 + seconds
                except:
                    leader_last_lap_time = None

            break  # We found the leader, exit the loop

    # Estimate the leader's lap time if we don't have their best time
    if leader_best_time is None:
        if leader_last_lap_time:
            leader_best_time = leader_last_lap_time  # Use the last lap time if available
        else:
            leader_best_time = 90.0  # As a fallback, assume 90 seconds

    prev_driver_progress = None
    prev_driver_lap = None

    for driver in sorted_drivers:
        current_progress = driver.get('lapProgress', 0)
        current_lap = driver.get('currentLap', 0)

        if driver.get('finished', False):
            continue

        # Interval with the previous driver
        if prev_driver_progress is not None and prev_driver_lap is not None:
            lap_diff = prev_driver_lap - current_lap
            progress_diff = prev_driver_progress - current_progress

            if lap_diff == 0:
                # Same lap, convert progress to time
                if progress_diff < 0:
                    progress_diff += 1  # Adjust if the previous driver is on the next lap

                interval_seconds = progress_diff * leader_best_time
                interval = format_time_difference(interval_seconds)
            else:
                interval = f"+{lap_diff} Lap{'s' if lap_diff > 1 else ''}"

            driver['interval'] = interval
        else:
            driver['interval'] = "Leader"

        # Gap to the leader
        if leader_lap_progress is not None and leader_lap is not None and driver.get('position') != 1:
            lap_diff = leader_lap - current_lap
            progress_diff = leader_lap_progress - current_progress

            if lap_diff == 0:
                # Same lap, convert progress to time
                if progress_diff < 0:
                    progress_diff += 1

                gap_seconds = progress_diff * leader_best_time
                gap = format_time_difference(gap_seconds)
            else:
                gap = f"+{lap_diff} Lap{'s' if lap_diff > 1 else ''}"

            driver['gap'] = gap
        else:
            driver['gap'] = "Leader"

        # Update reference for the next driver
        prev_driver_progress = current_progress
        prev_driver_lap = current_lap

    return sorted_drivers

def _get_gap_at_reference_point(state, car_a_idx, car_b_idx):
    """
    Calculate the time gap between two cars at the most recent common
    minisector reference point that car_b has crossed.

    Args:
        state: Application state containing crossing_times
        car_a_idx: CarIdx of the car ahead
        car_b_idx: CarIdx of the car behind

    Returns:
        float or None: Gap in seconds (positive = car_b is behind), or None if no data
    """
    times_a = state.crossing_times.get(car_a_idx)
    times_b = state.crossing_times.get(car_b_idx)

    if not times_a or not times_b:
        return None

    best_gap = None
    best_ms_time_b = -1

    for ms_idx in times_b:
        if ms_idx in times_a:
            time_b = times_b[ms_idx]
            time_a = times_a[ms_idx]
            # Use the most recently crossed sector by car_b
            if time_b > best_ms_time_b:
                best_ms_time_b = time_b
                best_gap = time_b - time_a

    return best_gap


def calculate_intervals_with_virtual_positions(drivers_data, state=None):
    """
    Calculate intervals and gaps between drivers using minisector reference-point timing.
    Falls back to track-position estimation if minisector data is not available.

    Args:
        drivers_data (list): List of driver data dictionaries (sorted by trackPosition)
        state: Application state containing minisector crossing_times

    Returns:
        list: Updated list of driver data with intervals and gaps
    """
    # Drivers should already be sorted by trackPosition (lap + progress)

    leader = None
    leader_best_time = None

    # Find leader and get their best lap time (used as fallback)
    for driver in drivers_data:
        if driver['virtualPosition'] == 1:
            leader = driver

            if 'bestLapTime' in driver and driver['bestLapTime'] != "N/A" and driver['bestLapTime'] != "999:59.999":
                try:
                    minutes, seconds = map(float, driver['bestLapTime'].split(':'))
                    leader_best_time = minutes * 60 + seconds
                except:
                    leader_best_time = None

            if not leader_best_time and 'lastLapTime' in driver and driver['lastLapTime'] != "N/A":
                try:
                    minutes, seconds = map(float, driver['lastLapTime'].split(':'))
                    leader_best_time = minutes * 60 + seconds
                except:
                    leader_best_time = None

            if not leader_best_time:
                leader_best_time = 90.0

            driver['interval'] = "Leader"
            driver['gap'] = "Leader"
            break

    # Check if minisector data is available
    has_minisector_data = state and state.crossing_times and leader

    # Process all drivers
    prev_driver = None
    for driver in drivers_data:
        current_position = driver.get('virtualPosition', 999)
        car_idx = driver.get('carIdx')

        if current_position == 1:
            # Save leader's values before they finish
            if state:
                state.frozen_gaps[car_idx] = "Leader"
                state.frozen_intervals[car_idx] = "Leader"
            prev_driver = driver
            continue

        # Finished driver: freeze gap/interval at the last known value
        if driver.get('finished', False):
            if state:
                driver['gap'] = state.frozen_gaps.get(car_idx, "N/A")
                driver['interval'] = state.frozen_intervals.get(car_idx, "N/A")
            prev_driver = driver
            continue

        current_lap = driver.get('currentLap', 0)
        current_progress = driver.get('lapProgress', 0)

        # --- GAP TO LEADER ---
        if leader:
            lap_diff = leader['currentLap'] - current_lap

            if lap_diff >= 2:
                driver['gap'] = f"+{lap_diff} Lap{'s' if lap_diff > 1 else ''}"
            elif has_minisector_data:
                # Use reference-point timing
                gap = _get_gap_at_reference_point(state, leader['carIdx'], car_idx)
                if gap is not None and gap > 0:
                    driver['gap'] = format_time_difference(gap)
                else:
                    # Fallback: estimate from track position
                    progress_diff = (leader['currentLap'] + leader['lapProgress']) - (current_lap + current_progress)
                    if progress_diff < 0:
                        progress_diff += 1
                    driver['gap'] = format_time_difference(progress_diff * leader_best_time)
            else:
                # No minisector data, use estimation
                progress_diff = (leader['currentLap'] + leader['lapProgress']) - (current_lap + current_progress)
                if progress_diff < 0:
                    progress_diff += 1
                driver['gap'] = format_time_difference(progress_diff * leader_best_time)
        else:
            driver['gap'] = "Unknown"

        # --- INTERVAL TO CAR AHEAD ---
        if prev_driver:
            prev_lap = prev_driver.get('currentLap', 0)
            lap_diff_prev = prev_lap - current_lap

            if lap_diff_prev >= 2:
                driver['interval'] = f"+{lap_diff_prev} Lap{'s' if lap_diff_prev > 1 else ''}"
            elif has_minisector_data:
                interval = _get_gap_at_reference_point(state, prev_driver['carIdx'], car_idx)
                if interval is not None and interval > 0:
                    driver['interval'] = format_time_difference(interval)
                else:
                    # Fallback
                    track_diff = (prev_driver.get('currentLap', 0) + prev_driver.get('lapProgress', 0)) - (current_lap + current_progress)
                    if track_diff < 0:
                        track_diff = 0
                    driver['interval'] = format_time_difference(track_diff * leader_best_time)
            else:
                track_diff = (prev_driver.get('currentLap', 0) + prev_driver.get('lapProgress', 0)) - (current_lap + current_progress)
                if track_diff < 0:
                    track_diff = 0
                driver['interval'] = format_time_difference(track_diff * leader_best_time)
        else:
            driver['interval'] = driver.get('gap', 'Unknown')

        # Save latest values so they can be frozen when this driver finishes
        if state:
            state.frozen_gaps[car_idx] = driver['gap']
            state.frozen_intervals[car_idx] = driver['interval']

        prev_driver = driver

    return drivers_data
