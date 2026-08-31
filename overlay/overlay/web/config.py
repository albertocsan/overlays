import json
import logging
import os
import threading
import time

logger = logging.getLogger("iracing-timing")

class ConfigManager:
    """Manages loading, saving, and monitoring the configuration file."""

    def __init__(self, config_file, state):
        """
        Initialize the config manager.

        Args:
            config_file (str): Path to the configuration file.
            state (State): Application state object.
        """
        self.config_file = config_file
        self.state = state
        self.config_last_modified = 0
        self.ensure_config_directory()
        if os.path.exists(self.config_file):
            self.load_config()  # Initial load
        elif self.config_file.endswith('columns.json'):
            self.save_config()  # Initial save with the columns/app-settings defaults
        else:
            # Any other config file (e.g. teams.json) starts empty - it must not
            # be seeded with the columns-shaped defaults from save_config().
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)
            self.config_last_modified = os.path.getmtime(self.config_file)

    def ensure_config_directory(self):
        """Ensure the config directory exists."""
        config_dir = os.path.dirname(self.config_file)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
            logger.info(f"Created config directory: {config_dir}")

    def save_config(self, config_data=None):
        """Save the configuration to file."""
        try:
            if config_data is None:
                config_data = {
                    "activeColumns": self.state.active_columns,
                    "driverNameFormat": self.state.driver_name_format,
                    "focusedDriverEnabled": self.state.focused_driver_enabled,
                    "showFocusedDriverTeamLogo": self.state.show_focused_driver_team_logo, # New config
                    "overlayWindowEnabled": self.state.overlay_window_enabled,
                    "focusedDriverBattleMode": self.state.focused_driver_battle_mode_enabled,
                    "timestamp": time.time()
                }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)

            self.config_last_modified = os.path.getmtime(self.config_file)
            logger.info(f"Saved configuration to {self.config_file}")
            # Broadcast the updated configuration via WebSocket
            self.state.broadcast_data()
        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")
            
    def load_config(self):
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                current_mtime = os.path.getmtime(self.config_file)

                # Only load if file has been modified
                if current_mtime > self.config_last_modified:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)

                    # Only set values if they exist in config and this is the columns config file
                    if self.config_file.endswith('columns.json'):
                        if config_data.get('activeColumns') is not None:
                            # CHANGE: Always update active_columns from the config file, even if it's an empty list
                            self.state.active_columns = config_data['activeColumns']
                            logger.debug(f"Active columns updated from config file: {self.config_file} -> {self.state.active_columns}")
                        else:
                            # If activeColumns is not in config_data, apply session defaults
                            if self.state.current_session_type == self.state.SESSION_PRACTICE:
                                self.state.active_columns = self.state.practice_columns
                            elif self.state.current_session_type == self.state.SESSION_QUALIFY:
                                self.state.active_columns = self.state.qualifying_columns
                            elif self.state.current_session_type in [self.state.SESSION_RACE, self.state.SESSION_GRIDDING]:
                                self.state.active_columns = self.state.race_columns
                            else:
                                # Fallback to a default if session type is unknown or not yet set
                                self.state.active_columns = ["position", "carNumber", "userName", "interval", "gap", "bestLapTime"]
                            logger.info(f"Applied default active columns for session type (not in {self.config_file}): {self.state.current_session_type}")
                    # END of columns.json specific logic

                    # Load driver name format if available
                    if 'driverNameFormat' in config_data:
                        if self.state.driver_name_format is None:  # Only set if not already set
                            self.state.driver_name_format = config_data['driverNameFormat']
                        else:
                            logger.debug("Driver name format already set, preserving existing value")
                    
                    if 'focusedDriverEnabled' in config_data:
                        self.state.focused_driver_enabled = config_data['focusedDriverEnabled']  # Always update this
                    
                    if 'showFocusedDriverTeamLogo' in config_data: # Load new config
                        self.state.show_focused_driver_team_logo = config_data['showFocusedDriverTeamLogo']

                    if 'overlayWindowEnabled' in config_data:
                        self.state.overlay_window_enabled = config_data['overlayWindowEnabled']

                    if 'focusedDriverBattleMode' in config_data:
                        self.state.focused_driver_battle_mode_enabled = config_data['focusedDriverBattleMode']

                    self.config_last_modified = current_mtime
                    logger.info(f"Loaded configuration from {self.config_file}")
                    return config_data
                else:
                    # If the file hasn't been modified, re-read and update state to ensure consistency
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    
                    # Ensure state is updated even if mtime hasn't changed (e.g., initial load or monitor re-read)
                    # Ensure state is updated even if mtime hasn't changed (e.g., initial load or monitor re-read)
                    if self.config_file.endswith('columns.json'):
                        if config_data.get('activeColumns') is not None:
                            self.state.active_columns = config_data['activeColumns']
                        else:
                            if self.state.current_session_type == self.state.SESSION_PRACTICE:
                                self.state.active_columns = self.state.practice_columns
                            elif self.state.current_session_type == self.state.SESSION_QUALIFY:
                                self.state.active_columns = self.state.qualifying_columns
                            elif self.state.current_session_type in [self.state.SESSION_RACE, self.state.SESSION_GRIDDING]:
                                self.state.active_columns = self.state.race_columns
                            else:
                                self.state.active_columns = ["position", "carNumber", "userName", "interval", "gap", "bestLapTime"]
                            logger.debug(f"Applied default active columns for session type (not in {self.config_file}, mtime not changed): {self.state.current_session_type}")
                    # END of columns.json specific logic

                    if 'driverNameFormat' in config_data:
                        self.state.driver_name_format = config_data['driverNameFormat']
                    
                    if 'focusedDriverEnabled' in config_data:
                        self.state.focused_driver_enabled = config_data['focusedDriverEnabled']
                    
                    if 'showFocusedDriverTeamLogo' in config_data:
                        self.state.show_focused_driver_team_logo = config_data['showFocusedDriverTeamLogo']

                    if 'overlayWindowEnabled' in config_data:
                        self.state.overlay_window_enabled = config_data['overlayWindowEnabled']

                    if 'focusedDriverBattleMode' in config_data:
                        self.state.focused_driver_battle_mode_enabled = config_data['focusedDriverBattleMode']

                    logger.debug(f"Re-read configuration (mtime not changed) from {self.config_file}")
                    return config_data
            
            # Return default values if file doesn't exist
            return {
                "activeColumns": self.state.active_columns,
                "driverNameFormat": self.state.driver_name_format,
                "focusedDriverEnabled": self.state.focused_driver_enabled,
                "showFocusedDriverTeamLogo": self.state.show_focused_driver_team_logo, # Default value
                "overlayWindowEnabled": self.state.overlay_window_enabled,
                "focusedDriverBattleMode": self.state.focused_driver_battle_mode_enabled,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            # Return default values in case of error
            return {
                "activeColumns": self.state.active_columns,
                "driverNameFormat": self.state.driver_name_format,
                "focusedDriverEnabled": self.state.focused_driver_enabled,
                "showFocusedDriverTeamLogo": self.state.show_focused_driver_team_logo, # Default value
                "overlayWindowEnabled": self.state.overlay_window_enabled,
                "focusedDriverBattleMode": self.state.focused_driver_battle_mode_enabled,
                "timestamp": time.time()
            }

    def monitor_config_file(self):
        """Monitor the config file for changes in a background thread."""
        while True:
            try:
                # Check if config file has changed
                if self.load_config():
                    logger.info("Config file changed, updated active columns")

                # Sleep for a short time before checking again
                time.sleep(4)
            except Exception as e:
                logger.error(f"Error in config monitor thread: {str(e)}")
                time.sleep(5)  # Wait longer if there was an error

    def start_config_monitor(self):
        """Start the background thread to monitor config changes."""
        monitor_thread = threading.Thread(target=self.monitor_config_file, daemon=True)
        monitor_thread.start()
        logger.info("Started config file monitor thread")
