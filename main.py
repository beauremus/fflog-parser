#!/usr/bin/env python3

import argparse
import requests
import time
import json


# -- Constants --
# As far as I can tell, this just need to be sufficiently large.
# Beyond the end time of the last fight.
REPORT_END_TIME = 999_999_999
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",  # From captured request
    "X-Requested-With": "XMLHttpRequest",  # FFLogs graph endpoint seems to expect this
    "Sec-Fetch-Dest": "empty",  # From captured request
    "Sec-Fetch-Mode": "cors",  # From captured request
    "Sec-Fetch-Site": "same-origin",  # From captured request
}
# Time to wait between requests to be polite to the server (in seconds)
REQUEST_DELAY_SECONDS = 2

# -- Globals --
all_boss_health_data = {}


def get_dynamic_headers(report_code, encounter_id = 97, difficulty_id = 101):
    referer_url = f"https://www.fflogs.com/reports/{report_code}?boss={encounter_id}&difficulty={difficulty_id}&wipes=1&hostility=1&type=resources"
    headers = BASE_HEADERS.copy()
    headers["Referer"] = referer_url
    return headers


def get_fight_count(report_code, headers):
    url = f"https://www.fflogs.com/reports/fights-and-participants/{report_code}/0"
    print(f"Fetching fight count from log.")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raises an exception for bad status codes
        fight_data = response.json()

        if "fights" in fight_data:
            print(
                f"Found {len(fight_data['fights'])} fights in log."
            )
            return len(fight_data["fights"])
        else:
            print(f"Warning: No fights found in log: {report_code}.")
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred getting fight count: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred getting fight count: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout occurred getting fight count: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred during request getting fight count: {req_err}")
    except json.JSONDecodeError:
        print(f"Error decoding JSON response getting fight count.")
    except Exception as e:
        print(f"An unexpected error occurred getting fight count: {e}")

    return None


def fetch_fight_health_data(report_code, fight_id, headers):
    url = f"https://www.fflogs.com/reports/resources-graph/{report_code}/0/0/{REPORT_END_TIME}/1000/{fight_id}/0/0/97.1.101.-1/0/Any"
    print(f"Fetching data for fight ID: {fight_id}")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raises an exception for bad status codes
        report_graph_data = response.json()

        boss_health_series = None

        if "series" in report_graph_data:
            for series_item in report_graph_data["series"]:
                boss_name = series_item.get("name")

                if series_item.get("type") == "Boss":
                    boss_health_series = series_item
                    break

        if boss_health_series:
            # The 'data' field contains [timestamp, healthPercentage]
            health_percentage_series = boss_health_series.get("data", [])

            print(
                f"Successfully extracted data for the boss in fight {fight_id}."
            )
            return {
                "fight_id": fight_id,
                "health_percentage_series": health_percentage_series,  # [timestamp, health_percent]
            }
        else:
            print(
                f"Warning: Boss series '{boss_name}' not found for fight {fight_id}."
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
    parser = argparse.ArgumentParser(description="Fetch boss health data from an FF Logs report for a specific encounter.")
    parser.add_argument("report_code", help="The FF Logs report code (e.g., KjfFrNzXphm13VYb).")

    args = parser.parse_args()
    report_code = args.report_code

    print(f"Starting data extraction for report: {report_code}")
    headers = get_dynamic_headers(report_code)

    all_fights_boss_data = {}
    fight_ids = range(1, get_fight_count(report_code, headers) + 1)

    for fight_id in fight_ids:
        fight_data = fetch_fight_health_data(report_code, fight_id, headers)

        if fight_data:
            all_fights_boss_data[fight_id] = fight_data

        print(f"Waiting for {REQUEST_DELAY_SECONDS} seconds before next request...")
        time.sleep(REQUEST_DELAY_SECONDS)

    print("\n--- Data Download Complete ---")

    if all_fights_boss_data:
        print(f"Successfully fetched data for {len(all_fights_boss_data)} fights.")

        output_filename = f"{report_code}_boss_health_all_fights.json"
        try:
            with open(output_filename, "w") as f:
                json.dump(all_fights_boss_data, f, indent=4)
            print(f"All collected boss health data saved to: {output_filename}")
        except IOError as e:
            print(f"Error saving data to file: {e}")
            print("Printing data to console instead:")
            print(json.dumps(all_fights_boss_data, indent=4))
    else:
        print("No data was successfully fetched for any fight.")


if __name__ == "__main__":
    main()
