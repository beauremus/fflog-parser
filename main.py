import requests
import time
import json


# -- Constants --
# Unique ID for your log upload
REPORT_CODE = "KjfFrNzXphm13VYb"
# This is the end of fight 15
REPORT_END_TIME = 7533202
# Dunno, gotta have it
ENCOUNTER_FILTER = "97.1.101.-1"
BOSS_ACTOR_ID = 20  # Dancing Green, Boss
EXPECTED_BOSS_NAME = "Dancing Green"
# Number of fights, 15 is what I found
FIGHT_IDS = range(1, 16)
REFERER_URL = f"https://www.fflogs.com/reports/{REPORT_CODE}?boss=97&difficulty=101&wipes=1&hostility=1&type=resources"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",  # From captured request
    "X-Requested-With": "XMLHttpRequest",  # FFLogs graph endpoint seems to expect this
    "Sec-Fetch-Dest": "empty",  # From captured request
    "Sec-Fetch-Mode": "cors",  # From captured request
    "Sec-Fetch-Site": "same-origin",  # From captured request
    "Referer": REFERER_URL,  # Added Referer
}
# Time to wait between requests to be polite to the server (in seconds)
REQUEST_DELAY = 2

all_boss_health_data = {}


def fetch_fight_health_data(fight_id):
    url = f"https://www.fflogs.com/reports/resources-graph/{REPORT_CODE}/0/0/{REPORT_END_TIME}/1000/{fight_id}/0/0/{ENCOUNTER_FILTER}/0/Any"
    print(f"Fetching data for fight ID: {fight_id} from {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()  # Raises an exception for bad status codes

        try:
            report_graph_data = response.json()
        except json.JSONDecodeError as json_err:
            print(json_err)
            return None

        boss_health_series = None
        if "series" in report_graph_data:
            for series_item in report_graph_data["series"]:
                if (
                    series_item.get("id") == BOSS_ACTOR_ID
                    and series_item.get("name") == EXPECTED_BOSS_NAME
                    and series_item.get("type") == "Boss"
                ):
                    boss_health_series = series_item
                    break

        if boss_health_series:
            # The 'data' field contains [timestamp, healthPercentage]
            health_percentage_series = boss_health_series.get("data", [])

            print(
                f"Successfully extracted data for boss (ID: {BOSS_ACTOR_ID}) in fight {fight_id}."
            )
            return {
                "fight_id": fight_id,
                "health_percentage_series": health_percentage_series,  # [timestamp, health_percent]
            }
        else:
            print(
                f"Warning: Boss series (ID: {BOSS_ACTOR_ID}, Name: '{EXPECTED_BOSS_NAME}') not found for fight {fight_id}."
            )
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred for fight {fight_id}: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred for fight {fight_id}: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout occurred for fight {fight_id}: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred during request for fight {fight_id}: {req_err}")
    except json.JSONDecodeError:
        print(f"Error decoding JSON response for fight {fight_id}.")
    except Exception as e:
        print(f"An unexpected error occurred for fight {fight_id}: {e}")

    return None


def main():
    pass
    print(f"Starting data extraction for report: {REPORT_CODE}")
    print(f"Targeting boss: '{EXPECTED_BOSS_NAME}' (Actor ID: {BOSS_ACTOR_ID})")

    all_fights_boss_data = {}

    for fight_id in FIGHT_IDS:
        fight_data = fetch_fight_health_data(fight_id)

        if fight_data:
            all_fights_boss_data[fight_id] = fight_data

        print(f"Waiting for {REQUEST_DELAY} seconds before next request...")
        time.sleep(REQUEST_DELAY)

    print("\n--- Data Download Complete ---")

    if all_fights_boss_data:
        print(f"Successfully fetched data for {len(all_fights_boss_data)} fights.")

        output_filename = f"{REPORT_CODE}_boss_health_all_fights.json"
        try:
            with open(output_filename, "w") as f:
                json.dump(all_fights_boss_data, f, indent=4)
            print(f"All collected boss health data saved to: {output_filename}")
        except IOError as e:
            print(f"Error saving data to file: {e}")
            print("Printing data to console instead:")
            print(json.dumps(all_fights_boss_data, indent=4))

        if 1 in all_fights_boss_data:
            print("\nHealth Percentages for Fight 1:")
            for timestamp, hp_percent in all_fights_boss_data[1][
                "health_percentage_series"
            ]:
                print(f"  Time: {timestamp}, HP: {hp_percent}%")
    else:
        print("No data was successfully fetched for any fight.")


if __name__ == "__main__":
    main()
