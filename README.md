# FF Logs "Dancing Green" Health Scraper

A Python script specifically configured to fetch and extract boss health time-series data for all wipes of the "Dancing Green" encounter (Encounter ID 97, Actor ID 20) from an FF Logs report.

## Prerequisites

- Python 3.7+
- `requests` library (for making HTTP requests)

## Setup

1.  Python: Ensure you have Python 3.7 or newer installed on your system.
2.  Install `requests` library:
    ```bash
    pip install requests
    ```

## Script Overview

This script is pre-configured to target:

- Report Code: `KjfFrNzXphm13VYb`
- Boss: "Dancing Green" (Encounter ID 97, specifically targeting Actor ID 20 within the report data)
- Fights: It iterates through a predefined range of fight IDs (typically all 15 wipes for this encounter in the specified report).

It constructs URLs to a specific FF Logs endpoint (`/reports/resources-graph/...`) for each fight to retrieve graph data, then parses the JSON response to extract health percentages for the boss.

## Usage

To run the script, simply execute it using Python:

```bash
python main.py
```

## Output

The script will:

1. Print progress messages to the console as it fetches data for each fight.
2. Generate a JSON file named `KjfFrNzXphm13VYb_boss_health_all_fights.json` in the same directory where the script is run.

The output file contains a dictionary where:

- Keys are the `fight_id` (e.g., "1", "2", ...)
- Values are:
  - `fight_id`: The fight ID as a number.
  - `health_percentage_series`: A list of `[timestamp, healthPercentage]` pairs.

## TODOs

- Refactor to take the key (need to determine) parameters for another boss.
- Generalize with CLI arguments.
- Is it possible to take the URL where the graph is visible and generate this data? That's the ideal generalization.
  - This may require a series of calls to determine key parameters like number of fights.
