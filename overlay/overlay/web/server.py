# Flask web server setup

from flask import Flask
import sys
import os
from flask_sock import Sock

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.state import State
import logging
from .config import ConfigManager
from .routes import register_routes
from .template_utils import ensure_template_directory, create_html_template

# Initialize logger
logger = logging.getLogger("iracing-timing")

class WebServer:
    """
    Web server for the iRacing timing overlay.
    """
    def __init__(self, state, overlay_window_manager=None):
        """
        Initialize the web server.

        Args:
            state (State): Application state object
            overlay_window_manager (OverlayWindowManager, optional): Controls the PyQt5 overlay window process.
        """
        self.app = Flask(__name__, template_folder='templates')
        self.app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB, mainly for dorsal uploads
        self.sock = Sock(self.app)
        self.state = state
        self.config_manager = ConfigManager(os.path.join(os.path.dirname(__file__), 'config', 'columns.json'), self.state)

        # Register routes
        register_routes(self.app, self.state, self.config_manager, overlay_window_manager)
        
        # WebSocket endpoint
        @self.sock.route('/ws/timing-data')
        def ws_timing_data(ws):
            self.state.add_websocket(ws)
            try:
                while True:
                    # Keep the connection open, waiting for data to be sent
                    # The actual data sending will happen in data_processor.py
                    ws.receive()  # Wait for incoming messages (or connection close)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self.state.remove_websocket(ws)

        # Start config monitor
        self.config_manager.start_config_monitor()

        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        ensure_template_directory(template_dir)
        create_html_template(os.path.join(template_dir, 'index.html'))

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """
        Run the web server.

        Args:
            host (str): Host to bind to
            port (int): Port to bind to
            debug (bool): Whether to run in debug mode
        """
        logger.info(f"Starting web server on http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)
