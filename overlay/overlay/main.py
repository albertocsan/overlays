#!/usr/bin/env python3
# Main entry point for the iRacing Timing Overlay application

import time
import logging
import os
import sys
import argparse
import subprocess
from threading import Thread

from models.state import State
from iracing.client import IRacingClient
from iracing.recorder import DataRecorder, DataPlayback # Import new classes
from web.server import WebServer
from license_info import LICENSE_TEXT, BUILD_ID


class OverlayWindowManager:
    """Starts/stops the PyQt5 transparent overlay window as a subprocess."""

    def __init__(self, script_path):
        self.script_path = script_path
        self.process = None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.is_running():
            return
        if getattr(sys, 'frozen', False):
            # Compiled build: each component lives in its own sibling folder next
            # to this one, e.g. overlay_server/overlay_server.exe + ../overlay_window/overlay_window.exe
            suite_root = os.path.dirname(os.path.dirname(sys.executable))
            exe_path = os.path.join(suite_root, 'overlay_window', 'overlay_window.exe')
            cmd = [exe_path]
        else:
            cmd = [sys.executable, self.script_path]
        self.process = subprocess.Popen(cmd)

    def stop(self):
        if self.is_running():
            self.process.terminate()
        self.process = None

def setup_logging():
    """
    Set up logging configuration.
    
    Returns:
        logging.Logger: Configured logger
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("logs/iracing_timing_debug.log"), 
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("iracing-timing")

def iracing_loop(client, state, logger, recorder=None): # Add recorder as an optional argument
    """
    Main loop for fetching data from iRacing.
    
    Args:
        client (IRacingClient): iRacing client
        state (State): Application state
        logger (logging.Logger): Logger
        recorder (DataRecorder, optional): Data recorder instance. Defaults to None.
    """
    logger.info("Iniciando hilo de monitoreo de iRacing")
    loop_count = 0
    
    while True:
        try:
            # Check if we're connected to iRacing
            connection_status = client.check_connection()
            if connection_status:
                logger.debug(f"Estado de la conexión: {'conectado' if state.ir_connected else 'desconectado'}")
            
            # If we're connected, process the data
            if state.ir_connected:
                try:
                    # Update the data
                    update_success = client.update_data()
                    
                    if update_success:
                        # Log complete info every 60 iterations (approx. every minute)
                        if loop_count % 60 == 0:
                            session_data = state.session_data
                            logger.info(f"Datos actualizados - Sesión: {session_data['sessionName']} en {session_data['trackName']} - Pilotos: {len(session_data['drivers'])}")
                        else:
                            logger.debug(f"Datos actualizados - {len(state.session_data['drivers'])} pilotos")
                        
                        # Record data if recorder is active
                        if recorder and recorder.is_recording:
                            # Get the data that was just broadcasted
                            # Note: state.broadcast_data() now returns the data_to_send dict
                            data_to_record = state.broadcast_data() 
                            recorder.record_frame(data_to_record)
                    else:
                        logger.warning("No se pudieron crear los datos de la sesión")
                        
                except Exception as e:
                    logger.error(f"Error al procesar datos de telemetría: {str(e)}", exc_info=True)
            else:
                logger.debug("No conectado a iRacing, esperando conexión...")
                
            loop_count += 1
            if loop_count > 10000:  # Prevent the counter from growing indefinitely
                loop_count = 0
                
        except Exception as e:
            logger.error(f"Error en el bucle principal de iRacing: {str(e)}", exc_info=True)
        
        # Wait before the next update
        time.sleep(1)

def minisector_loop(client, state, logger):
    """
    Fast loop (50ms) for recording minisector crossing times and sector boundary crossings.
    Only updates crossing timestamps — no heavy data processing.
    """
    logger.info("Starting minisector timing thread (50ms)")
    while True:
        try:
            if state.ir_connected:
                client.update_minisector_crossings()
                client.update_sector_crossings()
        except Exception as e:
            logger.debug(f"Minisector loop error: {e}")
        time.sleep(0.05)  # 50ms

def main():
    """Main entry point for the application."""
    # Set up logging
    logger = setup_logging()
    logger.info("=== Iniciando aplicación iRacing Timing Tower ===")
    logger.info(f"{LICENSE_TEXT} [{BUILD_ID}]")
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="iRacing Timing Overlay application.")
    parser.add_argument('--record', action='store_true', help='Record live iRacing data.')
    parser.add_argument('--playback', type=str, help='Playback data from a specified file.')
    parser.add_argument('--playback-speed', type=float, default=1.0, help='Playback speed (e.g., 0.5 for half, 2.0 for double).')
    args = parser.parse_args()

    render_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'renderoverlay.py')
    overlay_window_manager = OverlayWindowManager(render_path)

    try:
        # Initialize state
        state = State()

        # Web server uses this to start/stop the overlay window from /config

        # Initialize web server
        web_server = WebServer(state, overlay_window_manager)

        # Start web server in a separate thread
        logger.info("Iniciando servidor web en http://0.0.0.0:5000")
        web_server_thread = Thread(target=web_server.run, args=('0.0.0.0', 5000, False), daemon=True)
        web_server_thread.start()
        logger.info("Servidor web iniciado correctamente")

        # Launch the overlay window if enabled (config is loaded into state by WebServer/ConfigManager above)
        if state.overlay_window_enabled:
            overlay_window_manager.start()
            logger.info("Ventana de overlay (PyQt5) iniciada")

        if args.playback:
            # Playback mode
            logger.info(f"Modo de reproducción activado. Reproduciendo desde: {args.playback}")
            data_playback = DataPlayback(state)
            data_playback.start_playback(args.playback, args.playback_speed)
            
            # Keep the main thread alive while playback is active
            while data_playback.is_playing:
                time.sleep(1)
            logger.info("Reproducción finalizada.")

        else:
            # Live mode or Recording mode
            iracing_client = IRacingClient(state)
            recorder = None
            if args.record:
                logger.info("Modo de grabación activado.")
                recorder = DataRecorder()
                recorder.start_recording()

            # Start iRacing thread (1000ms - full data processing)
            logger.info("Iniciando hilo de iRacing...")
            iracing_thread = Thread(target=iracing_loop, args=(iracing_client, state, logger, recorder), daemon=True)
            iracing_thread.start()
            logger.info("Hilo de iRacing iniciado correctamente")

            # Start fast minisector thread (50ms - crossing times only)
            minisector_thread = Thread(target=minisector_loop, args=(iracing_client, state, logger), daemon=True)
            minisector_thread.start()
            logger.info("Minisector timing thread started (50ms)")
            
            # Keep the main thread alive
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Interrupción por teclado detectada.")
            finally:
                if recorder and recorder.is_recording:
                    recorder.stop_recording()
                logger.info("Cerrando hilos de iRacing y servidor web.")

    except Exception as e:
        logger.critical(f"Error fatal en la aplicación: {str(e)}", exc_info=True)
    finally:
        overlay_window_manager.stop()
        logger.info("=== Finalizando aplicación iRacing Timing Tower ===")

if __name__ == '__main__':
    main()
