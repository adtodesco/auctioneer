import json as json_module
import logging
import time
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

FANTRAX_BASE_URL = "https://www.fantrax.com"


def fantrax_scorer_id(player):
    """Strip '*' characters from player.fantrax_id for use with the Fantrax API."""
    return player.fantrax_id.replace("*", "")


def contract_to_csid(contract_year):
    """Map a contract end year to Fantrax's csId value.

    2026 -> "2", 2027 -> "3", ..., 2033 -> "9", 2034 -> "A", 2035 -> "B"
    """
    offset = contract_year - 2024
    if offset <= 9:
        return str(offset)
    # 10 -> A, 11 -> B, etc.
    return chr(ord("A") + offset - 10)


def parse_cookies(cookies_str):
    """Parse a cookie header string into a dict."""
    cookies = {}
    for pair in cookies_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, value = pair.split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies


def _fxpa_request(session, league_id, method, data):
    """Make a request to the /fxpa/req RPC endpoint."""
    url = f"{FANTRAX_BASE_URL}/fxpa/req"
    if league_id:
        url += f"?leagueId={league_id}"

    payload = {
        "msgs": [{"method": method, "data": data}],
        "uiv": 3,
        "refUrl": f"{FANTRAX_BASE_URL}/fantasy/league/{league_id}/team/roster;adminMode=true",
        "dt": 0,
        "at": 0,
        "av": "0.0",
        "tz": "America/New_York",
        "v": "179.0.1",
    }

    resp = session.post(
        url,
        data=json_module.dumps(payload),
        headers={"Content-Type": "text/plain"},
    )
    resp.raise_for_status()
    result = resp.json()

    logger.info(f"fxpa {method} response: {json_module.dumps(result)[:1000]}")

    responses = result.get("responses", [])
    if not responses:
        raise RuntimeError(f"No responses from Fantrax for method {method}: {result}")

    resp_data = responses[0]
    if resp_data.get("error"):
        raise RuntimeError(f"Fantrax error for {method}: {resp_data['error']}")

    return resp_data.get("data", {})


def claim_player(session, league_id, player, team):
    """Add a free agent to a team on Fantrax.

    Step 1: Get claim confirmation info (validates claim, gets best position).
    Step 2: Execute the claim with salary set.
    """
    scorer_id = fantrax_scorer_id(player)
    team_id = team.fantrax_team_id

    # Step 1: Get claim confirmation info
    confirm_url = f"{FANTRAX_BASE_URL}/fxa/getClaimDropConfirmInfo?leagueId={league_id}"
    confirm_payload = {
        "claimScorerId": scorer_id,
        "dropScorerId": None,
        "adminMode": True,
        "rosterLimitPeriod": "1",
        "fantasyTeamId": team_id,
    }

    resp = session.post(confirm_url, json=confirm_payload)
    resp.raise_for_status()
    confirm_data = resp.json()

    best_pos_id = confirm_data.get("bestPosId", "017")
    best_status_id = confirm_data.get("bestStatusId", "2")

    # Step 2: Execute the claim
    claim_url = f"{FANTRAX_BASE_URL}/fxa/createClaimDrop?leagueId={league_id}"
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    claim_payload = {
        "rosterLimitPeriod": "1",
        "claimScorerId": scorer_id,
        "dropScorerId": None,
        "claimRosterActionId": None,
        "fantasyTeamId": team_id,
        "txDateTime": now_str,
        "freeAgentBidAmount": player.salary,
        "claimPosId": best_pos_id,
        "claimStatusId": best_status_id,
        "future": True,
        "override": False,
        "adminModeProcessClaimNow": True,
        "adminModeDropToStatusId": "4",
        "doConfirm": False,
        "faClaimSystem": "BIDDING",
    }

    resp = session.post(claim_url, json=claim_payload)
    resp.raise_for_status()
    claim_data = resp.json()

    if claim_data.get("code") != "EXECUTED":
        raise RuntimeError(
            f"Claim failed for {player.name}: {claim_data.get('genericMessage', claim_data)}"
        )

    logger.info(f"Claimed {player.name} to {team.short_team_name} on Fantrax")
    return claim_data


def get_team_roster(session, league_id, team):
    """Fetch the full roster fieldMap for a team in admin mode."""
    data = _fxpa_request(session, league_id, "getTeamRosterInfo", {
        "fantasyTeamId": team.fantrax_team_id,
        "rosterLimitPeriod": 1,
        "adminMode": True,
    })

    field_map = data.get("fieldMap", {})
    if not field_map:
        raise RuntimeError(f"Empty fieldMap returned for team {team.short_team_name}")

    return field_map


def set_contract(session, league_id, player, team, roster_field_map):
    """Update a player's contract year in the roster fieldMap and save.

    Two-phase: confirm (dry run), then execute.
    """
    scorer_id = fantrax_scorer_id(player)
    cs_id = contract_to_csid(player.contract)

    if scorer_id not in roster_field_map:
        raise RuntimeError(
            f"Player {player.name} ({scorer_id}) not found in roster fieldMap"
        )

    # Update the contract year for this player
    roster_field_map[scorer_id]["csId"] = cs_id

    base_data = {
        "rosterLimitPeriod": 1,
        "fantasyTeamId": team.fantrax_team_id,
        "daily": False,
        "adminMode": True,
        "applyToFuturePeriods": True,
        "fieldMap": roster_field_map,
    }

    # Phase 1: Confirm (dry run)
    confirm_data = dict(base_data)
    confirm_data["confirm"] = True
    _fxpa_request(session, league_id, "confirmOrExecuteTeamRosterChanges", confirm_data)

    # Phase 2: Execute
    _fxpa_request(session, league_id, "confirmOrExecuteTeamRosterChanges", base_data)

    logger.info(
        f"Set contract for {player.name} to {player.contract} (csId={cs_id}) on Fantrax"
    )


def lock_player(cookies_str, league_id, player, team):
    """High-level orchestrator: claim a player, set their contract on Fantrax.

    Returns (success: bool, message: str).
    """
    session = requests.Session()
    cookies = parse_cookies(cookies_str)
    for name, value in cookies.items():
        session.cookies.set(name, value)

    session.headers.update({
        "Origin": FANTRAX_BASE_URL,
        "Referer": f"{FANTRAX_BASE_URL}/newui/fantasy/claimDrop.go?leagueId={league_id}&appType=0&appVersion=undefined",
    })

    try:
        # Step 1: Claim the player (add to team with salary)
        try:
            claim_player(session, league_id, player, team)
        except RuntimeError as e:
            # If claim fails, player may already be on the team from a previous attempt
            logger.warning(f"Claim step failed for {player.name}, continuing to set contract: {e}")

        # Wait for Fantrax to process the claim before fetching roster
        time.sleep(3)

        # Step 2: Get the full roster fieldMap
        roster_field_map = get_team_roster(session, league_id, team)

        # Step 3: Set the contract year
        set_contract(session, league_id, player, team, roster_field_map)

        return True, f"Locked {player.name} to {team.short_team_name}"

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            msg = "Fantrax session has expired. Please contact the league manager to refresh credentials."
        else:
            msg = f"HTTP error locking {player.name}: {e}"
        logger.error(msg)
        return False, msg
    except RuntimeError as e:
        msg = str(e)
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"Unexpected error locking {player.name}: {e}"
        logger.error(msg)
        return False, msg
