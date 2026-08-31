#!/usr/bin/env python3
"""
Simple run script for the iRacing Timing Overlay.
This script is a convenience wrapper to run the whole application:
overlay web server + Director (camera control desktop app).

The overlay window (PyQt5) is launched by main.py itself and can be
toggled on/off from http://localhost:5000/config.
"""

import os
import sys
import subprocess
import signal
import time

FROZEN = getattr(sys, 'frozen', False)
BASE_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))

if FROZEN:
    # Compiled build: each component lives in its own sibling folder next to
    # this one, e.g. EMS_Overlay/EMS_Overlay.exe + ../overlay_server/overlay_server.exe
    SUITE_ROOT = os.path.dirname(BASE_DIR)
    main_command_base = [os.path.join(SUITE_ROOT, 'overlay_server', 'overlay_server.exe')]
    control_command = [os.path.join(SUITE_ROOT, 'director', 'director.exe')]
else:
    # Dev mode: run the .py scripts with the current interpreter.
    main_path = os.path.join(BASE_DIR, 'overlay', 'main.py')
    control_camaras_path = os.path.join(BASE_DIR, 'controlcamaras.py')
    main_command_base = [sys.executable, main_path]
    control_command = [sys.executable, control_camaras_path]

if __name__ == '__main__':
    processes = []
    try:
        # Collect arguments to pass to the web server (e.g. --record, --playback)
        # sys.argv[0] is this script/exe, so we slice from index 1
        main_args = sys.argv[1:]

        main_command = main_command_base + main_args
        main_process = subprocess.Popen(main_command)
        processes.append(main_process)

        # Launch the Director app (camera control)
        control_process = subprocess.Popen(control_command)
        processes.append(control_process)

        # Wait for the processes to complete
        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Terminating subprocesses.")
        for p in processes:
            p.terminate() # or p.kill() for a more forceful termination
    finally:
        # Ensure all processes are terminated on exit
        for p in processes:
            if p.poll() is None:
                p.terminate()
        print("All subprocesses terminated.")
