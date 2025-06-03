#!/usr/bin/env python3

import argparse
import requests
import time
import json
import base64

# -- Constants --
REQUEST_DELAY_SECONDS = (
    2  # Time to wait between requests to be polite to the server (in seconds)
)

# --- FFLogs API V2 Credentials (Replace with your actual Client ID and Secret) ---
# IMPORTANT: DO NOT SHARE YOUR CLIENT SECRET!
FFLOGS_CLIENT_ID = "9f09fad4-d982-4ca4-906d-dae828e8860c"
FFLOGS_CLIENT_SECRET = "RzaEKwdwvE06LDD3ChLElR9tG8P3chIm39M52nxa"
# ----------------------------------------------------------------------------------

FFLOGS_OAUTH_TOKEN_URL = "https://www.fflogs.com/oauth/token"
FFLOGS_GRAPHQL_API_URL = "https://www.fflogs.com/api/v2/client"

# --- Boss/Encounter to Creature GameID Mapping ---
# This map is needed because fight.encounterID is not the same as enemyNPC.gameID.
# The `encounterID` is the general encounter (e.g., P12S), while `gameID` is the specific creature.
# We map the encounterID to the `gameID` of the primary boss creature for that encounter.
# You will need to extend this map for other encounters you wish to track.
ENCOUNTER_BOSS_CREATURE_MAP = {
    97: 18361,  # EncounterID 97 (P12S) maps to Creature GameID 18361 (Pandaemonium)
    98: 18340,
}

# --- Debuffs to Track ---
# These are the 'abilityGameID's for debuffs that signify "Damage Down" applied by bosses.
# You can find these by inspecting events in an FFLogs report (e.g., using a working GraphQL query).
DEBUFF_ABILITY_IDS_TO_TRACK = [
    1002911,  # Example: This ID is known to be for the "Damage Down" debuff in some FFLogs contexts.
    # Add other specific debuff abilityGameIDs that reduce player OUTGOING damage.
]


# --- Helper Functions for FFLogs V2 API ---


def get_fflogs_access_token(client_id, client_secret):
    """
    Obtains an access token for the FFLogs V2 API using the client_credentials grant.
    This token is required for all subsequent GraphQL API calls.
    """
    credentials = f"{client_id}:{client_secret}".encode("ascii")
    base64_credentials = base64.b64encode(credentials).decode("ascii")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {base64_credentials}",
    }
    data = {"grant_type": "client_credentials"}

    print("Attempting to obtain FFLogs API access token...")
    try:
        response = requests.post(
            FFLOGS_OAUTH_TOKEN_URL, headers=headers, data=data, timeout=10
        )
        response.raise_for_status()
        token_data = response.json()

        if "access_token" in token_data:
            print("Successfully obtained access token!")
            return token_data["access_token"], token_data.get("expires_in")
        else:
            print(
                f"Error obtaining token: {token_data.get('error_description', token_data)}"
            )
            return None, None
    except requests.exceptions.RequestException as e:
        print(f"Request error during token retrieval: {e}")
        return None, None
    except json.JSONDecodeError:
        print(
            f"Error decoding JSON response for token. Raw response: {response.text if 'response' in locals() else 'N/A'}"
        )
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred during token retrieval: {e}")
        return None, None


def fetch_fflogs_graphql_data(access_token, query, variables=None):
    """
    Makes a GraphQL query to the FFLogs V2 API.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    payload = {"query": query, "variables": variables if variables else {}}

    try:
        response = requests.post(
            FFLOGS_GRAPHQL_API_URL, headers=headers, json=payload, timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(
            f"GraphQL HTTP error: {http_err}. Status: {http_err.response.status_code}. Response: {http_err.response.text if http_err.response else 'N/A'}"
        )
        return None
    except requests.exceptions.ConnectionError as conn_err:
        print(f"GraphQL connection error: {conn_err}")
        return None
    except requests.exceptions.Timeout as timeout_err:
        print(f"GraphQL timeout error: {timeout_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred during GraphQL request: {req_err}")
        return None
    except json.JSONDecodeError:
        print(
            f"Error decoding JSON response from GraphQL API. Raw response: {response.text}"
        )
        return None
    except Exception as e:
        print(f"An unexpected error occurred during GraphQL query: {e}")
        return None


# --- Core Logic Functions Using FFLogs V2 API ---


def get_report_metadata_graphql(report_code, access_token):
    """
    Fetches all fights and master data about enemy and player actors from a given FFLogs report using GraphQL.
    Uses aliases for actors query to avoid field collision.
    Note: masterData.actors(type: "Enemy") might not contain maxHealth for all reports.
    """
    query = """
    query GetReportMetadata($code: String!) {
      reportData {
        report(code: $code) {
          fights {
            id
            startTime
            endTime
            name
            encounterID # The generic encounter ID for the fight (e.g., 97 for P12S)
            difficulty
            enemyNPCs { # List of enemy NPC instances in THIS specific fight
              id          # This is the ACTOR INSTANCE ID for THIS fight (e.g., 20) -- what we'll use for targetID
              gameID      # This is the generic CREATURE ID (e.g., 1000016 for Pandaemonium)
              # name        # Name of the specific NPC instance
            }
          }
          masterData {
            enemies: actors(type: "Enemy") { # Use alias 'enemies'
              id          # Master data actor ID (not necessarily instance ID)
              gameID      # This is the CREATURE ID (e.g., 1000016) -- matches enemyNPCs.gameID
              name
              # maxHealth   # This field *should* be here, but might be null or empty for some reports
            }
            players: actors(type: "Player") { # Use alias 'players'
              id
              gameID # This is the player's job ID or character ID, useful for character identification
              name
            }
          }
        }
      }
    }
    """
    variables = {"code": report_code}
    print(
        f"Fetching report metadata (fights, enemies, players) from log via GraphQL: {report_code}"
    )
    data = fetch_fflogs_graphql_data(access_token, query, variables)

    if (
        data
        and "data" in data
        and data["data"]
        and "reportData" in data["data"]
        and data["data"]["reportData"]
    ):
        report_data = data["data"]["reportData"]["report"]
        fights = report_data.get("fights", [])
        master_enemies = report_data.get("masterData", {}).get(
            "enemies", []
        )  # Access via alias
        master_players = report_data.get("masterData", {}).get(
            "players", []
        )  # Access via alias

        print(
            f"Found {len(fights)} fights, {len(master_enemies)} master enemies, {len(master_players)} master players via GraphQL."
        )
        return fights, master_enemies, master_players
    elif data and "errors" in data:
        print(f"GraphQL errors in get_report_metadata_graphql: {data['errors']}")
    else:
        print(
            "No report data found or unexpected data structure from GraphQL API for metadata."
        )
    return None, None, None


def fetch_boss_graph_data_graphql(
    report_code, fight_details, master_enemies, access_token, data_type="Resources"
):
    """
    Fetches boss graph data (e.g., Resources/HP or DamageDone) for a specific fight.
    Attempts to convert raw HP to percentage if maxHealth is available.
    """
    fight_id = fight_details["id"]
    start_time_ms = float(fight_details["startTime"])
    end_time_ms = float(fight_details["endTime"])
    encounter_id = fight_details.get("encounterID")

    if encounter_id == 0 or not fight_details.get("enemyNPCs"):
        print(
            f"Skipping graph data for fight {fight_id}: Not a recognized boss encounter (encounterID is 0) or no enemy NPCs to track."
        )
        return None

    # --- Step 1: Find the specific boss actor instance ID and its generic creature ID ---
    boss_actor_instance_id = None  # This is the 'id' from enemyNPCs for THIS fight instance (used for targetID)
    boss_creature_game_id = None  # This is the 'gameID' from enemyNPCs (used to lookup maxHealth in masterData)
    boss_name = fight_details.get("name", "Unknown Boss")  # Default to fight name

    # Use the mapping to identify the primary boss's gameID from the encounterID
    target_creature_game_id = ENCOUNTER_BOSS_CREATURE_MAP.get(encounter_id)

    if target_creature_game_id is None:
        print(
            f"Warning: No known primary boss creature ID for encounterID {encounter_id} in ENCOUNTER_BOSS_CREATURE_MAP. "
            f"Attempting to infer boss from enemyNPCs. If this is a main boss, please add to map."
        )

        # Fallback heuristic: Try to find the NPC with the highest gameID or lowest ID
        # or just pick the first one if it seems like a boss fight.
        # This is less reliable than a direct map for specific main bosses.
        if fight_details.get("enemyNPCs"):
            # Simple fallback: Take the first NPC instance.
            # This might need refinement for multi-boss fights or fights with many adds.
            first_npc = fight_details["enemyNPCs"][0]
            boss_actor_instance_id = first_npc.get("id")
            boss_creature_game_id = first_npc.get("gameID")
            boss_name = first_npc.get("name", boss_name)
            print(
                f"Defaulting to first enemy NPC in fight {fight_id}: {boss_name} (Actor Instance ID: {boss_actor_instance_id})."
            )
    else:
        # Found a specific mapping, now find the NPC instance that matches this gameID
        for npc_instance in fight_details["enemyNPCs"]:
            if npc_instance.get("gameID") == target_creature_game_id:
                boss_actor_instance_id = npc_instance.get("id")
                boss_creature_game_id = npc_instance.get("gameID")
                boss_name = npc_instance.get("name", boss_name)
                break

        if boss_actor_instance_id is None:
            print(
                f"Warning: Primary boss (Creature ID {target_creature_game_id}) not found in enemyNPCs for fight {fight_id}. "
                f"Perhaps a different NPC is the main boss for this log, or it's a phase change. Skipping graph."
            )
            return None  # Cannot proceed if we can't find the specific boss instance

    if boss_actor_instance_id is None:
        print(
            f"Skipping graph data for fight {fight_id}: Could not determine a target boss actor to query."
        )
        return None

    # --- Step 2: Find maxHealth from master_enemies using the boss's creature ID ---
    boss_max_health = 9_000_000
    for actor in master_enemies:
        if actor.get("gameID") == boss_creature_game_id:
            boss_max_health = actor.get("maxHealth")
            break

    if boss_max_health is None or boss_max_health <= 0:
        print(
            f"Warning: Could not determine max health for {boss_name} (Creature ID: {boss_creature_game_id}). "
            "If 'Resources' is requested, data will be raw HP values, not percentage."
        )

    # --- Step 3: Query the graph for the identified boss actor ---
    query = """
    query GetBossGraphData($code: String!, $fightId: Int!, $start: Float!, $end: Float!, $targetId: Int!, $dataType: GraphDataType!) {
      reportData {
        report(code: $code) {
          graph(
            fightIDs: [$fightId],
            dataType: $dataType,
            targetID: $targetId,
            startTime: $start,
            endTime: $end
          )
        }
      }
    }
    """

    variables = {
        "code": report_code,
        "fightId": fight_id,
        "start": start_time_ms,
        "end": end_time_ms,
        "targetId": boss_actor_instance_id,
        "dataType": data_type,
    }

    print(
        f"Fetching {data_type} graph for {boss_name} (Fight ID: {fight_id}, Target ID: {boss_actor_instance_id}) via GraphQL..."
    )
    data = fetch_fflogs_graphql_data(access_token, query, variables)

    extracted_series = []
    if (
        data
        and "data" in data
        and data["data"]
        and "reportData" in data["data"]
        and data["data"]["reportData"]
    ):
        graph_data_field = data["data"]["reportData"]["report"].get("graph")

        if (
            graph_data_field
            and "data" in graph_data_field
            and graph_data_field["data"] is not None
        ):
            raw_series = graph_data_field["data"]["series"]

            print(
                f"Successfully extracted {len(raw_series)} {data_type} data points for {boss_name} in fight {fight_id}."
            )

            if data_type == "Resources" and boss_max_health and boss_max_health > 0:
                for timestamp, current_value in raw_series:
                    percentage = (current_value / boss_max_health) * 100
                    extracted_series.append([timestamp, percentage])
                print("Converted raw HP to percentage.")
            else:
                extracted_series = raw_series  # Keep as raw (either DamageDone or unconvertible Resources)
                if data_type == "Resources":
                    print(
                        "Health data is raw HP values (max health unknown or invalid or masterData.enemies was empty)."
                    )

            return {
                "fight_id": fight_id,
                "boss_name": boss_name,
                "data_type": data_type,
                "series": extracted_series,
            }
        else:
            print(
                f"Warning: 'graph' or its 'data' field is missing/null for fight {fight_id} ({boss_name}) with dataType: {data_type}."
            )
            print(f"GraphQL response part for 'graph': {graph_data_field}")
    elif data and "errors" in data:
        print(
            f"GraphQL errors in fetch_boss_graph_data_graphql for fight {fight_id}: {data['errors']}"
        )
    else:
        print(
            f"No graph data found or unexpected structure for fight {fight_id} for {boss_name}."
        )
    return None


def fetch_damage_down_debuff_times_graphql(
    report_code, fight_details, boss_actor_instance_id, master_players, access_token
):
    """
    Fetches and processes 'ApplyDebuff' and 'RemoveDebuff' events from the boss to players,
    focusing on specific "Damage Down" debuffs identified by DEBUFF_ABILITY_IDS_TO_TRACK.
    """
    fight_id = fight_details["id"]
    start_time_ms = float(fight_details["startTime"])
    end_time_ms = float(fight_details["endTime"])

    player_actor_ids = {p["id"] for p in master_players}
    player_names_by_id = {p["id"]: p["name"] for p in master_players}

    if not player_actor_ids:
        print(f"No player actors found for report {report_code}. Cannot track debuffs.")
        return []

    # Query all ApplyDebuff and RemoveDebuff events from the boss during this fight
    # Filter by abilityID and dataType
    query = """
    query GetDebuffEvents($code: String!, $fightId: Int!, $start: Float!, $end: Float!, $sourceActorId: Int!, $abilityIDs: [Int!]!) {
      reportData {
        report(code: $code) {
          events(
            fightIDs: [$fightId],
            startTime: $start,
            endTime: $end,
            sourceID: $sourceActorId, # Boss applies the debuff
            abilityID: $abilityIDs,  # Filter by specific debuff ability IDs
            dataType: Debuffs,       # Filter for debuff type events
            # Note: FFLogs events API is paginated. For potentially large number of events,
            # we might need to add a 'limit' and 'nextPageTimestamp' to fetch all pages.
            # For typical debuff tracking, single request is often sufficient.
          ) {
            data {
              timestamp
              type # ApplyDebuff, RemoveDebuff
              sourceID
              targetID
              abilityGameID
              abilityName
            }
          }
        }
      }
    }
    """
    variables = {
        "code": report_code,
        "fightId": fight_id,
        "start": start_time_ms,
        "end": end_time_ms,
        "sourceActorId": boss_actor_instance_id,
        "abilityIDs": DEBUFF_ABILITY_IDS_TO_TRACK,  # Pass the list of IDs
    }

    print(
        f"Fetching debuff events for fight ID: {fight_id} (Source: {boss_actor_instance_id}) via GraphQL..."
    )
    data = fetch_fflogs_graphql_data(access_token, query, variables)

    debuff_periods = []
    if (
        data
        and "data" in data
        and data["data"]
        and "reportData" in data["data"]
        and data["data"]["reportData"]
        and "report" in data["data"]["reportData"]["report"]
        and data["data"]["reportData"]["report"].get("events")
        and data["data"]["reportData"]["report"]["events"].get("data") is not None
    ):
        all_events = data["data"]["reportData"]["report"]["events"]["data"]
        print(
            f"Fetched {len(all_events)} raw debuff events from boss for fight {fight_id}."
        )

        # Track currently active debuffs: {player_name: {debuff_name: start_timestamp}}
        active_debuffs = {}

        for event in all_events:
            event_type = event.get("type")
            target_id = event.get("targetID")
            ability_name = event.get("abilityName")
            timestamp = event.get("timestamp")

            # Ensure event targets a player (source is already filtered by boss_actor_instance_id)
            if target_id in player_actor_ids:
                player_name = player_names_by_id.get(
                    target_id, f"Player ID {target_id}"
                )

                if event_type == "ApplyDebuff":
                    if player_name not in active_debuffs:
                        active_debuffs[player_name] = {}
                    if (
                        ability_name not in active_debuffs[player_name]
                    ):  # Avoid re-applying if already active
                        active_debuffs[player_name][ability_name] = timestamp
                        # print(f"  [{timestamp}] {player_name} applied {ability_name}")

                elif event_type == "RemoveDebuff":
                    if (
                        player_name in active_debuffs
                        and ability_name in active_debuffs[player_name]
                    ):
                        start_time = active_debuffs[player_name].pop(ability_name)
                        debuff_periods.append(
                            {
                                "debuff_name": ability_name,
                                "player_name": player_name,
                                "start_time": start_time,
                                "end_time": timestamp,
                                "duration_ms": timestamp - start_time,
                            }
                        )
                        # print(f"  [{timestamp}] {player_name} removed {ability_name}. Duration: {timestamp - start_time}ms")

        # Handle debuffs still active at the end of the fight
        # Events might not always have a corresponding RemoveDebuff if fight ends mid-debuff
        for player_name, debuffs_on_player in active_debuffs.items():
            for debuff_name, start_time in debuffs_on_player.items():
                debuff_periods.append(
                    {
                        "debuff_name": debuff_name,
                        "player_name": player_name,
                        "start_time": start_time,
                        "end_time": end_time_ms,  # Debuff lasts until fight end
                        "duration_ms": end_time_ms - start_time,
                    }
                )
                # print(f"  [{end_time_ms}] {player_name} had {debuff_name} until fight end. Duration: {end_time_ms - start_time}ms")

        print(
            f"Identified {len(debuff_periods)} damage down debuff periods for fight {fight_id}."
        )
        return debuff_periods

    elif data and "errors" in data:
        print(
            f"GraphQL errors fetching debuff events for fight {fight_id}: {data['errors']}"
        )
    else:
        print(
            f"No debuff events data found or unexpected structure for fight {fight_id}."
        )
    return []


def main():
    parser = argparse.ArgumentParser(
        description="Fetch boss data from an FF Logs report using FFLogs V2 GraphQL API."
    )
    parser.add_argument(
        "report_code", help="The FF Logs report code (e.g., KjfFrNzXphm13VYb)."
    )
    parser.add_argument(
        "--data_type",
        default="Resources",
        choices=["Resources", "DamageDone"],
        help="Type of boss time-series data to fetch: 'Resources' for boss health (raw HP), 'DamageDone' for damage taken.",
    )
    parser.add_argument(
        "--track_debuffs",
        action="store_true",
        help="Enable tracking of specific 'Damage Down' debuffs applied by boss to players.",
    )

    args = parser.parse_args()
    report_code = args.report_code
    data_type_to_fetch = args.data_type
    track_debuffs_enabled = args.track_debuffs

    print(f"Starting data extraction for report: {report_code} using FFLogs V2 API.")

    # --- Step 1: Get Access Token ---
    access_token, _ = get_fflogs_access_token(FFLOGS_CLIENT_ID, FFLOGS_CLIENT_SECRET)
    if not access_token:
        print(
            "Failed to get FFLogs API access token. Please check your Client ID and Secret. Exiting."
        )
        return

    all_fights_processed_data = {}

    # --- Step 2: Fetch all report metadata (fights, master enemies, master players) using GraphQL ---
    fight_details_list, master_enemies, master_players = get_report_metadata_graphql(
        report_code, access_token
    )

    if not fight_details_list:
        print("Could not retrieve fight details. Exiting.")
        return

    print(f"Proceeding to fetch data for {len(fight_details_list)} fights.")

    # --- Step 3: Iterate through fights and fetch requested data ---
    for fight_details in fight_details_list:
        fight_id_in_report = fight_details["id"]
        processed_fight_data = {
            "fight_details": fight_details
        }  # Include basic fight details in output

        # --- Identify Primary Boss Actor for Graph & Debuff Tracking ---
        boss_actor_instance_id = None
        boss_creature_game_id = (
            None  # Needed for maxHealth lookup or specific debuff tracking
        )
        main_boss_name = fight_details.get("name", "Unknown Boss")

        if fight_details.get("encounterID") == 0 or not fight_details.get("enemyNPCs"):
            print(
                f"Skipping fight ID {fight_id_in_report} ('{main_boss_name}'): Not a recognized boss encounter or no enemy NPCs."
            )
            continue  # Skip this fight entirely if it's not a boss or has no enemy NPCs

        # Use the predefined map to find the primary boss's creature ID
        target_creature_game_id = ENCOUNTER_BOSS_CREATURE_MAP.get(
            fight_details["encounterID"]
        )

        if target_creature_game_id:
            # Find the NPC instance in this fight that matches the primary boss creature ID
            for npc_instance in fight_details["enemyNPCs"]:
                if npc_instance.get("gameID") == target_creature_game_id:
                    boss_actor_instance_id = npc_instance.get("id")
                    boss_creature_game_id = npc_instance.get("gameID")
                    main_boss_name = npc_instance.get("name", main_boss_name)
                    break

        if boss_actor_instance_id is None:
            # Fallback if primary boss not found by specific gameID mapping:
            # Try to infer if it's still a boss fight (non-zero encounterID) and pick first NPC.
            # This handles cases where a specific boss might not be in the map or it's a sub-boss.
            if fight_details.get("enemyNPCs"):
                first_npc = fight_details["enemyNPCs"][0]
                boss_actor_instance_id = first_npc.get("id")
                boss_creature_game_id = first_npc.get("gameID")
                main_boss_name = first_npc.get("name", main_boss_name)
                print(
                    f"Warning: Primary boss actor for fight {fight_id_in_report} not found by specific creature ID map. "
                    f"Defaulting to first enemy NPC: {main_boss_name} (Actor ID: {boss_actor_instance_id}, Creature ID: {boss_creature_game_id})."
                )
            else:
                print(
                    f"Skipping fight {fight_id_in_report}: No suitable boss actor found for graph or debuff tracking."
                )
                continue  # Skip if no boss actor instance found at all

        # --- Fetch Boss Graph Data (Health/Damage Taken) ---
        if boss_actor_instance_id:  # Ensure we have an actor to query for graph
            graph_data = fetch_boss_graph_data_graphql(
                report_code,
                fight_details,
                master_enemies,
                access_token,
                data_type=data_type_to_fetch,
            )
            if graph_data:
                processed_fight_data["graph_data"] = graph_data
            else:
                print(
                    f"Failed to fetch {data_type_to_fetch} graph data for fight {fight_id_in_report}."
                )
        else:
            print(
                f"Skipping {data_type_to_fetch} graph data for fight {fight_id_in_report}: No boss actor ID identified."
            )

        # --- Damage Down Debuff Tracking ---
        if track_debuffs_enabled:
            if (
                boss_actor_instance_id
            ):  # Ensure boss actor instance id is identified to be the source
                debuff_data = fetch_damage_down_debuff_times_graphql(
                    report_code,
                    fight_details,
                    boss_actor_instance_id,
                    master_players,
                    access_token,
                )
                processed_fight_data["damage_down_debuffs"] = debuff_data
            else:
                print(
                    f"Skipping damage down debuff tracking for fight {fight_id_in_report}: No boss actor ID identified as source."
                )

        # Store all collected data for this fight
        all_fights_processed_data[fight_id_in_report] = processed_fight_data

        print(f"Waiting for {REQUEST_DELAY_SECONDS} seconds before next request...")
        time.sleep(REQUEST_DELAY_SECONDS)

    print("\n--- Data Download Complete ---")

    if all_fights_processed_data:
        print(f"Successfully fetched data for {len(all_fights_processed_data)} fights.")

        output_filename = f"{report_code}_processed_data_graphql.json"
        try:
            with open(output_filename, "w") as f:
                json.dump(all_fights_processed_data, f, indent=4)
            print(f"All collected data saved to: {output_filename}")
        except IOError as e:
            print(f"Error saving data to file: {e}")
            print("Printing data to console instead:")
            print(json.dumps(all_fights_processed_data, indent=4))
    else:
        print("No data was successfully fetched for any fight.")


if __name__ == "__main__":
    main()
