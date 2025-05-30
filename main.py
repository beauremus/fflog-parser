#!/usr/bin/env python3

import argparse
import requests
import time
import json


# -- Constants --
# Time to wait between requests to be polite to the server (in seconds)
REQUEST_DELAY_SECONDS = 2
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",  # From captured request
    "X-Requested-With": "XMLHttpRequest",  # FFLogs graph endpoint seems to expect this
    "Sec-Fetch-Dest": "empty",  # From captured request
    "Sec-Fetch-Mode": "cors",  # From captured request
    "Sec-Fetch-Site": "same-origin",  # From captured request
}


def get_dynamic_headers(report_code, encounter_id=97, difficulty_id=101):
    """
    Constructs dynamic headers for FFLogs API requests, including a Referer.
    This mimics a browser request originating from a specific report page.
    The encounter_id and difficulty_id here are primarily for the Referer header,
    making the request appear to come from a relevant FFLogs report page.

    Args:
        report_code (str): The FFLogs report code.
        encounter_id (int): The ID of the specific encounter/boss (e.g., 97 for M5).
                            This is part of the URL when viewing a specific boss's page on FFLogs.
        difficulty_id (int): The ID of the difficulty setting (e.g., 101 for Savage, 100 for Normal).
                             This is part of the URL when viewing a specific difficulty's page on FFLogs.

    Returns:
        dict: A dictionary of HTTP headers.
    """
    referer_url = (
        f"https://www.fflogs.com/reports/{report_code}"
        f"?boss={encounter_id}&difficulty={difficulty_id}&wipes=1&hostility=1&type=resources"
    )
    headers = BASE_HEADERS.copy()
    headers["Referer"] = referer_url
    return headers


def get_fight_details(report_code, headers):
    """
    Fetches details for all fights within a given FFLogs report.
    This endpoint provides start and end times for each individual fight,
    along with boss and difficulty IDs.

    Args:
        report_code (str): The FFLogs report code.
        headers (dict): HTTP headers for the request.

    Returns:
        list: A list of dictionaries, where each dictionary contains details for a fight
              (e.g., 'id', 'startTime', 'endTime', 'boss', 'name', 'difficulty').
              Returns None if an error occurs or no fights are found.
    """
    url = f"https://www.fflogs.com/reports/fights-and-participants/{report_code}/0"
    print(f"Fetching fight count from log.")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raises an exception for bad status codes
        fight_data = response.json()

        if "fights" in fight_data:
            print(f"Found {len(fight_data['fights'])} fights in log.")
            return fight_data["fights"]
        else:
            print(f"Warning: No fights found in log: {report_code}.")
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred getting fight details: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred getting fight details: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout occurred getting fight details: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred during request getting fight details: {req_err}")
    except json.JSONDecodeError:
        print("Error decoding JSON response getting fight details.")
    except Exception as e:
        print(f"An unexpected error occurred getting fight details: {e}")

    return None


def fetch_fight_health_data(report_code, fight_details, headers):
    """
    Fetches boss health data for a specific fight within an FFLogs report.
    The URL is constructed to precisely specify the start and end times of the fight
    and the correct boss/difficulty parameters to ensure only data relevant to
    that single fight is retrieved.

    Args:
        report_code (str): The FFLogs report code.
        fight_details (dict): A dictionary containing details for the specific fight,
                              including 'id', 'startTime', 'endTime', 'boss', and 'difficulty'.
        headers (dict): HTTP headers for the request.

    Returns:
        dict: A dictionary containing 'fight_id' and 'health_percentage_series' ([timestamp, healthPercentage] tuples),
              or None if data cannot be retrieved or parsed.
    """
    fight_id = fight_details["id"]
    # start_time and end_time are relative to the start of the entire report in milliseconds
    start_time_ms = fight_details["start_time"]
    end_time_ms = fight_details["end_time"]
    encounter_id = fight_details.get("boss")
    boss_name = fight_details.get("name")
    difficulty_id = fight_details.get("difficulty")

    # This limit controls the maximum number of data points returned for the graph.
    # 1000 is a common default that provides a good balance of detail and response size.
    graph_data_point_limit = 1_000

    # The 'view_string' parameter in the URL (e.g., '97.101.0.0' or '97.1.101.-1') specifies
    # the encounter, difficulty, and sometimes a metric or phase.
    # Format: {encounter_id}.{rank/phase_id}.{difficulty_id}.{metric_id}
    # - {encounter_id}: The ID of the boss/encounter for this specific fight.
    # - {rank/phase_id}: Often '0' or '1' for general boss health graphs. '1' is common.
    # - {difficulty_id}: The difficulty of the fight.
    # - {metric_id}: '-1' usually means a general or default metric (like total health).
    #                Other values could indicate specific metrics like total damage or healing.
    # We will use '1' for rank/phase_id and '-1' for metric_id as they are common defaults for boss health graphs.
    if encounter_id is None or difficulty_id is None:
        print(
            f"Skipping fight {fight_id}: Missing boss or difficulty ID in fight details."
        )
        return None

    # I dunno what 1 and -1 are, but they work
    view_string = f"{encounter_id}.1.{difficulty_id}.-1"

    # The URL for resources-graph generally follows this structure:
    # /reports/resources-graph/{report_code}/
    # {fixed_0}/   ???
    # {fight_start_time_ms}/
    # {fight_end_time_ms}/
    # {max_data_points_limit}/
    # {specific_fight_id}/
    # {source_actor_id}/
    # {target_actor_id}/
    # {view_string}/
    # {ability_id}/
    # {resource_type}
    url = (
        f"https://www.fflogs.com/reports/resources-graph/"
        f"{report_code}/0/{start_time_ms}/{end_time_ms}/{graph_data_point_limit}/"
        f"{fight_id}/0/0/{view_string}/0/Any"
    )
    print(
        f"Fetching data for fight ID: {fight_id} <{boss_name}> (Times: {start_time_ms}-{end_time_ms}, View: {view_string})"
    )

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raises an exception for bad status codes
        report_graph_data = response.json()

        boss_health_series = None

        if "series" in report_graph_data:
            for series_item in report_graph_data["series"]:
                if series_item.get("type") == "Boss":
                    boss_health_series = series_item
                    break

        if boss_health_series:
            # The 'data' field contains [timestamp, healthPercentage]
            health_percentage_series = boss_health_series.get("data", [])

            print(
                f"Successfully extracted boss health data for fight {fight_id} "
                f"({len(health_percentage_series)} data points)."
            )
            return {
                "fight_id": fight_id,
                "boss": boss_name,
                "health_percentage_series": health_percentage_series,  # [timestamp, health_percent]
            }
        else:
            print(f"Warning: No boss series found in graph data for fight {fight_id}.")
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
    parser = argparse.ArgumentParser(
        description="Fetch boss health data from an FF Logs report for a specific encounter."
    )
    parser.add_argument(
        "report_code", help="The FF Logs report code (e.g., KjfFrNzXphm13VYb)."
    )

    args = parser.parse_args()
    report_code = args.report_code

    print(f"Starting data extraction for report: {report_code}")
    # Default encounter_id and difficulty_id for the Referer header (can be general)
    headers = get_dynamic_headers(report_code, encounter_id=97, difficulty_id=101)

    all_fights_boss_data = {}

    # Fetch detailed information for all fights in the report, including start, end, boss, and difficulty.
    fight_details_list = get_fight_details(report_code, headers)

    if not fight_details_list:
        print("Could not retrieve fight details. Exiting.")
        return

    print(f"Proceeding to fetch data for {len(fight_details_list)} fights.")

    for fight_details in fight_details_list:
        fight_id_in_report = fight_details["id"]

        # Skip fights that are not recognized as boss encounters (e.g., trash pulls, interludes)
        # The 'boss' field being 0 or missing often indicates a non-boss segment,
        # or a non-standard fight type that doesn't have a direct 'boss' health bar.
        if "boss" not in fight_details or fight_details["boss"] == 0:
            print(
                f"Skipping fight ID {fight_id_in_report} (not a recognized boss encounter or no boss ID)."
            )
            continue

        fight_data = fetch_fight_health_data(report_code, fight_details, headers)

        if fight_data:
            all_fights_boss_data[fight_id_in_report] = fight_data

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
