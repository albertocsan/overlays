# Camera control functionality for iRacing using pyirsdk

import irsdk
import logging
import ctypes
from enum import Enum

# Initialize logger
logger = logging.getLogger("iracing-timing")

class CameraState(Enum):
    """Enum for camera states"""
    IS_CAMERA_TOOL_ACTIVE = 0
    IS_UI_HIDDEN = 1
    IS_USING_CUSTOM_CAMERA_CONTROLS = 2
    IS_MOUSE_POS_LOCKED = 3
    IS_MOUSE_WHEEL_LOCKED = 4
    IS_KEYBOARD_LOCKED = 5

class CameraFocusSystem:
    """
    Class to handle camera focus functionality in iRacing.
    """
    def __init__(self, ir_sdk=None):
        """
        Initialize the camera focus system.
        
        Args:
            ir_sdk (irsdk.IRSDK, optional): iRacing SDK instance. If None, a new instance will be created.
        """
        self.ir = ir_sdk if ir_sdk else irsdk.IRSDK()
        logger.info("Camera focus system initialized")

        
    def focus_on_car_position(self, car_position, camera_group=0, camera=0):
        """
        Focus the camera on a car based on its position in the race.
        
        Args:
            car_position (int): Position of the car in the race (1-based)
            camera_group (int, optional): Camera group to use. Defaults to 0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        try:
            # Based on user example, the correct parameter order is:
            # car_position, camera (not camera_group, camera)
            # The camera_group parameter seems to be used differently
            logger.debug(f"Focusing camera on position {car_position} with camera {camera}")
            result = self.ir.cam_switch_pos(car_position, camera)
            
            if result:
                logger.info(f"Camera focused on car in position {car_position} (camera: {camera})")
            else:
                logger.warning(f"Failed to focus camera on car in position {car_position}")
                
            return result
        except Exception as e:
            logger.error(f"Error focusing camera on car position: {str(e)}", exc_info=True)
            return False
            
    def focus_on_car_number(self, car_number, camera_group=0, camera=0):
        """
        Focus the camera on a car based on its number.
        
        Args:
            car_number (int): Number of the car to focus on
            camera_group (int, optional): Camera group to use. Defaults to 0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        try:
            # Based on user example, the correct parameter order is:
            # car_number, camera (not camera_group, camera)
            logger.debug(f"Focusing camera on car number {car_number} with camera {camera}")
            result = self.ir.cam_switch_num(car_number, camera)
            
            if result:
                logger.info(f"Camera focused on car number {car_number} (camera: {camera})")
            else:
                logger.warning(f"Failed to focus camera on car number {car_number}")
                
            return result
        except Exception as e:
            logger.error(f"Error focusing camera on car number: {str(e)}", exc_info=True)
            return False
            
    def set_camera_state(self, camera_state, value):
        """
        Set a camera state.
        
        Args:
            camera_state (CameraState): The camera state to set
            value (int): Value to set (0 for off, 1 for on)
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        try:
            # Broadcast message to set camera state
            # Parameters: camera state, unused, unused
            result = self.ir.cam_set_state(camera_state.value, 0, 0)
            
            if result:
                logger.info(f"Camera state {camera_state.name} set to {value}")
            else:
                logger.warning(f"Failed to set camera state {camera_state.name}")
                
            return result
        except Exception as e:
            logger.error(f"Error setting camera state: {str(e)}", exc_info=True)
            return False
            
    def focus_on_driver_by_name(self, driver_name, camera_group=0, camera=0):
        """
        Focus the camera on a driver by their name.
        
        Args:
            driver_name (str): Name of the driver to focus on
            camera_group (int, optional): Camera group to use. Defaults to 0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        try:
            # Get the list of drivers
            drivers = self.ir['DriverInfo']['Drivers']
            
            # Debug logging with more detailed information
            logger.info(f"Attempting to focus on driver: '{driver_name}'")
            logger.info(f"Number of drivers in session: {len(drivers)}")
            
            # Find the driver by name with more flexible matching
            found = False
            for driver in drivers:
                user_name = driver.get('UserName', '').strip()
                logger.info(f"Comparing: '{user_name}' vs '{driver_name}'")
                
                # More flexible name matching strategies
                name_match_conditions = [
                    user_name.lower() == driver_name.lower(),  # Exact match
                    driver_name.lower() in user_name.lower(),  # Partial match
                    user_name.lower() in driver_name.lower(),  # Reverse partial match
                    # Handle abbreviated first names
                    any(
                        driver_name.lower() == f"{first_initial}.{last_name}".lower() 
                        for first_initial, last_name in [
                            (user_name.split()[0][0], user_name.split()[-1])
                        ]
                    ),
                    # Handle full name variations
                    any(
                        driver_name.lower() == f"{first_name} {last_name}".lower() 
                        for first_name, last_name in [
                            (user_name.split()[0], user_name.split()[-1]),
                            (user_name.split()[-1], user_name.split()[0])
                        ]
                    )
                ]
                
                if any(name_match_conditions):
                    found = True
                    # Get the car number
                    car_number = driver.get('CarNumber', -1)
                    user_id = driver.get('UserID', None)
                    logger.info(f"Found driver match: {user_name} with car number {car_number}")
                    
                    try:
                        car_number = int(car_number)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid car number format: {car_number}")
                        continue
                    
                    if car_number >= 0:
                        # Focus on the car
                        logger.info(f"Attempting to focus on car number {car_number}")
                        result = self.focus_on_car_number(car_number, camera_group, camera)
                        logger.info(f"Camera focus result: {result}")
                        
                        # If first attempt fails, try alternative methods
                        if not result:
                            # Try with padded car number
                            padded_car_number = f"{car_number:03d}"
                            logger.info(f"Trying padded car number: {padded_car_number}")
                            result = self.focus_on_car_number(padded_car_number, camera_group, camera)
                            logger.info(f"Padded car number focus result: {result}")
                        
                        return result
                    else:
                        logger.warning(f"Driver {user_name} found but car number is invalid")
            
            if not found:
                logger.warning(f"Driver '{driver_name}' not found in the list of {len(drivers)} drivers")
                # Log all driver names for comprehensive debugging
                for i, driver in enumerate(drivers):
                    logger.info(f"Available driver {i+1}: '{driver.get('UserName', 'Unknown')}'")
            
            return False
        except Exception as e:
            logger.error(f"Error focusing camera on driver by name: {str(e)}", exc_info=True)
            return False
            
    def focus_on_driver_by_id(self, driver_id, camera_group=0, camera=0):
        """
        Focus the camera on a driver by their iRacing ID.
        
        Args:
            driver_id (int): iRacing ID of the driver to focus on
            camera_group (int, optional): Camera group to use. Defaults to 0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        try:
            # Get the list of drivers
            drivers = self.ir['DriverInfo']['Drivers']
            
            # Find the driver by ID
            for driver in drivers:
                if driver.get('UserID', 0) == driver_id:
                    # Get the car number
                    car_number = int(driver.get('CarNumber', -1))
                    
                    if car_number >= 0:
                        # Focus on the car
                        return self.focus_on_car_number(car_number, camera_group, camera)
                    else:
                        logger.warning(f"Driver with ID {driver_id} found but car number is invalid")
                        return False
            
            logger.warning(f"Driver with ID {driver_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error focusing camera on driver by ID: {str(e)}", exc_info=True)
            return False
            
    def focus_on_leader(self, camera_group=0, camera=0):
        """
        Focus the camera on the race leader.
        
        Args:
            camera_group (int, optional): Camera group to use. Defaults to 0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        # Focus on position 1 (the leader)
        return self.focus_on_car_position(1, camera_group, camera)
        
    def focus_on_battles(self, gap_threshold=1.0, camera_group=0, camera=0):
        """
        Focus the camera on close battles on track.
        
        Args:
            gap_threshold (float, optional): Maximum gap in seconds to consider a battle. Defaults to 1.0.
            camera_group (int, optional): Camera group to use. Defaults to 0.
            camera (int, optional): Camera to use. Defaults to 0.
            
        Returns:
            bool: True if a battle was found and camera focused, False otherwise
        """
        try:
            # Get session data
            if not self.ir['SessionInfo'] or not self.ir['SessionInfo']['Sessions']:
                logger.warning("No session data available")
                return False
                
            current_session = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]
            
            # Check if results are available
            if 'ResultsPositions' not in current_session or not current_session['ResultsPositions']:
                logger.warning("No results data available")
                return False
                
            # Find close battles
            results = current_session['ResultsPositions']
            
            # Sort by position
            sorted_results = sorted(results, key=lambda x: x.get('Position', 999))
            
            # Find the closest battle
            closest_battle_gap = float('inf')
            closest_battle_pos = None
            
            for i in range(len(sorted_results) - 1):
                car1 = sorted_results[i]
                car2 = sorted_results[i + 1]
                
                # Calculate gap between cars
                if 'Time' in car1 and 'Time' in car2:
                    gap = abs(car2['Time'] - car1['Time'])
                    
                    # Check if this is a close battle
                    if gap < gap_threshold and gap < closest_battle_gap:
                        closest_battle_gap = gap
                        closest_battle_pos = car1['Position']
            
            # Focus on the closest battle if found
            if closest_battle_pos is not None:
                logger.info(f"Found close battle at position {closest_battle_pos} with gap {closest_battle_gap:.3f}s")
                return self.focus_on_car_position(closest_battle_pos, camera_group, camera)
            else:
                logger.info(f"No close battles found with gap < {gap_threshold}s")
                return False
                
        except Exception as e:
            logger.error(f"Error focusing on battles: {str(e)}", exc_info=True)
            return False
            
    def get_available_cameras(self):
        """
        Get a list of available cameras.
        
        Returns:
            list: List of available camera groups and cameras
        """
        try:
            cameras = []
            
            # Get camera info
            if 'CameraInfo' in self.ir:
                camera_info = self.ir['CameraInfo']
                
                # Get groups
                if 'Groups' in camera_info:
                    for group_idx, group in enumerate(camera_info['Groups']):
                        group_name = group.get('GroupName', f"Group {group_idx}")
                        
                        # Get cameras in this group
                        if 'Cameras' in group:
                            for cam_idx, camera in enumerate(group['Cameras']):
                                camera_name = camera.get('CameraName', f"Camera {cam_idx}")
                                cameras.append({
                                    'group_idx': group_idx,
                                    'group_name': group_name,
                                    'camera_idx': cam_idx,
                                    'camera_name': camera_name
                                })
            
            return cameras
        except Exception as e:
            logger.error(f"Error getting available cameras: {str(e)}", exc_info=True)
            return []
