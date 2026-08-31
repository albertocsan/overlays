import json
import time
import os
import logging
import threading

logger = logging.getLogger("iracing-timing")

class DataRecorder:
    """
    Records iRacing session data to a file.
    """
    def __init__(self, output_dir="recordings"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.is_recording = False
        self.record_file = None
        self.start_time = None

    def start_recording(self, session_name="session"):
        """
        Starts recording data to a new file.
        """
        if self.is_recording:
            logger.warning("Already recording. Stop current recording before starting a new one.")
            return False

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"{session_name}_{timestamp}.jsonl"
        self.record_file_path = os.path.join(self.output_dir, filename)

        try:
            self.record_file = open(self.record_file_path, 'w')
            self.is_recording = True
            self.start_time = time.time()
            logger.info(f"Recording started to {self.record_file_path}")
            return True
        except IOError as e:
            logger.error(f"Failed to open recording file {self.record_file_path}: {e}")
            return False

    def record_frame(self, session_data):
        """
        Records a single frame of session data.
        """
        if not self.is_recording or not self.record_file:
            return

        try:
            # Add a relative timestamp to each frame
            frame_data = {
                "timestamp_relative": time.time() - self.start_time,
                "data": session_data
            }
            self.record_file.write(json.dumps(frame_data) + '\n')
        except Exception as e:
            logger.error(f"Error writing frame to recording file: {e}")

    def stop_recording(self):
        """
        Stops the current recording and closes the file.
        """
        if self.is_recording and self.record_file:
            self.record_file.close()
            self.record_file = None
            self.is_recording = False
            logger.info(f"Recording stopped. File saved to {self.record_file_path}")
            return True
        return False

class DataPlayback:
    """
    Plays back recorded iRacing session data from a file.
    """
    def __init__(self, state):
        self.state = state
        self.is_playing = False
        self.playback_thread = None
        self.stop_event = threading.Event()
        self.playback_speed = 1.0 # 1.0 for real-time, 2.0 for 2x speed, etc.

    def start_playback(self, file_path, playback_speed=1.0):
        """
        Starts playing back data from the specified file.
        """
        if self.is_playing:
            logger.warning("Already playing back. Stop current playback before starting a new one.")
            return False

        if not os.path.exists(file_path):
            logger.error(f"Playback file not found: {file_path}")
            return False

        self.file_path = file_path
        self.playback_speed = playback_speed
        self.is_playing = True
        self.stop_event.clear()
        self.playback_thread = threading.Thread(target=self._playback_loop)
        self.playback_thread.start()
        logger.info(f"Playback started from {file_path} at {playback_speed}x speed.")
        return True

    def _playback_loop(self):
        """
        Internal loop for playing back data frames.
        """
        try:
            with open(self.file_path, 'r') as f:
                frames = [json.loads(line) for line in f]

            if not frames:
                logger.warning("No frames found in playback file.")
                self.is_playing = False
                return

            # Get the initial timestamp for relative timing
            first_timestamp_relative = frames[0]["timestamp_relative"]
            
            for i, frame_data in enumerate(frames):
                if self.stop_event.is_set():
                    break

                current_timestamp_relative = frame_data["timestamp_relative"]
                session_data = frame_data["data"]

                # Calculate delay for real-time playback
                if i > 0:
                    prev_timestamp_relative = frames[i-1]["timestamp_relative"]
                    time_diff = (current_timestamp_relative - prev_timestamp_relative) / self.playback_speed
                    if time_diff > 0:
                        time.sleep(time_diff)

                # Update state and broadcast
                # The session_data from the recording contains the 'drivers' list
                # and other session info that was part of the 'data_to_send' in broadcast_data
                # We need to extract these and update the state object accordingly.
                
                # Assuming 'session_data' in the recorded frame is the 'data_to_send' dictionary
                # from State.broadcast_data()
                self.state.session_data = session_data.get("drivers")
                self.state.focused_driver_details = session_data.get("focusedDriver")
                self.state.current_session_type = session_data.get("sessionType", self.state.SESSION_UNKNOWN)
                # Update other state attributes if they were recorded
                self.state.sessionName = session_data.get("sessionName", 'Unknown Session')
                self.state.sessionTimeRemaining = session_data.get("sessionTimeRemaining", 0)
                self.state.sessionLapsTotal = session_data.get("sessionLapsTotal", 0)
                self.state.sessionLapsRemaining = session_data.get("sessionLapsRemaining", 0)
                self.state.trackName = session_data.get("trackName", 'Unknown Track')
                self.state.trackConfig = session_data.get("trackConfig", '')
                self.state.last_session_info_update = session_data.get("timestamp", time.time()) # Use recorded timestamp

                self.state.broadcast_data()

            logger.info("Playback finished.")

        except FileNotFoundError:
            logger.error(f"Playback file not found: {self.file_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from playback file {self.file_path}: {e}")
        except Exception as e:
            logger.error(f"Error during playback: {e}", exc_info=True)
        finally:
            self.is_playing = False

    def stop_playback(self):
        """
        Stops the current playback.
        """
        if self.is_playing:
            self.stop_event.set()
            if self.playback_thread:
                self.playback_thread.join(timeout=5) # Wait for thread to finish
                if self.playback_thread.is_alive():
                    logger.warning("Playback thread did not terminate gracefully.")
            self.is_playing = False
            logger.info("Playback stopped.")
            return True
        return False
