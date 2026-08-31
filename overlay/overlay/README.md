# iRacing Timing Overlay

A web-based timing overlay for iRacing that displays real-time race information.

## Project Structure

The project is organized into the following modules:

```
overlay/
├── __init__.py
├── main.py                # Entry point
├── iracing/
│   ├── __init__.py
│   ├── client.py          # iRacing connection and data fetching
│   └── data_processor.py  # Process and format iRacing data
├── web/
│   ├── __init__.py
│   ├── server.py          # Flask server setup
│   └── templates/
│       └── index.html     # HTML template
├── models/
│   ├── __init__.py
│   └── state.py           # State class and data models
└── utils/
    ├── __init__.py
    └── formatting.py      # Utility functions for formatting data
```

## Features

- Real-time timing tower with customizable columns
- Session information display (track, session type, time remaining)
- Connection status indicator
- Configurable column display
- Debug information panel

## Requirements

- Python 3.6+
- iRacing SDK (irsdk)
- Flask

## Installation

1. Clone the repository
2. Install the required dependencies:
   ```
   pip install irsdk flask
   ```

## Usage

1. Start iRacing or connect to an existing session
2. Run the overlay:
   ```
   python run.py
   ```
3. Open a web browser and navigate to `http://localhost:5000`

## Customization

You can customize which columns are displayed in the timing tower by using the column selector in the web interface. Available columns include:

- Position
- Car Number
- Driver Name
- Team Name
- Car Name
- Best Lap Time
- Last Lap Time
- Laps Completed
- Interval
- Gap
- Pit Stops
- iRating

## Development

The application is structured to be modular and maintainable:

- `main.py`: Entry point that initializes all components and starts the application
- `iracing/client.py`: Handles connection to iRacing and fetching data
- `iracing/data_processor.py`: Processes driver data and calculates intervals and gaps
- `web/server.py`: Sets up the Flask web server and routes
- `models/state.py`: Defines the application state
- `utils/formatting.py`: Utility functions for formatting time data

## License

This project is open source and available under the MIT License.
