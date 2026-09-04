#!/usr/bin/env python3
"""
Ein einzelner Worker. Bekommt per CHUNK_INDEX/NUM_WORKERS einen Ausschnitt
der Turnierliste zugewiesen (round-robin verteilt, damit lange und kurze
Turniere sich ueber die Worker hinweg ausgleichen), ruft fuer jedes Turnier

  - GET /api/tournament/{id}/results       (individuelle Spielerpunkte + rank)
  - GET /api/tournament/{id}/teams         (Team-Punkte + rank, nur bei Team-Battles)

ab und schreibt die aufsummierten Zwischenergebnisse UND die Einzelergebnisse
pro Turnier nach partial_{CHUNK_INDEX}.json (letzteres wird fuer erweiterte
Stats wie Best Tournament, Best Finish, Streaks etc. gebraucht).

Umgebungsvariablen:
    LICHESS_TOKEN    - optionales Personal Access Token
    CHUNK_INDEX       - 0-basierter Index dieses Workers (Pflicht)
    NUM_WORKERS       - Gesamtzahl paralleler Worker (Pflicht)
    REQUEST_DELAY     - Sekunden Pause zwischen einzelnen API-Calls (Default 1.0)
    TOURNAMENTS_FILE  - Pfad zur tournaments.json (Default: tournaments.json)
"""
import json
import os
import sys
import time

import requests

TOKEN = os.environ.get("LICHESS_TOKEN")
CHUNK_INDEX = int(os.environ["CHUNK_INDEX"])
NUM_WORKERS = int(os.environ["NUM_WORKERS"])
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "1.0"))
TOURNAMENTS_FILE = os.environ.get("TOURNAMENTS_FILE", "tournaments.json")

MAX_RETRIES = 8
INITIAL_BACKOFF = 5.0
MAX_BACKOFF = 90.0

session = requests.Session()
session.headers.update({"Accept": "application/x-ndjson"})
if TOKEN:
    session.headers["Authorization"] = f"Bearer {TOKEN}"


def get_with_retry(url, **kwargs):
    """GET mit exponentiellem Backoff bei 429 (Rate-Limit) / 5xx."""
    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=30, **kwargs)
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            print(f"  Netzwerkfehler ({e}), retry in {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue

        if r.status_code == 429:
            print(f"  429 Rate-Limit auf {url}, warte {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue

        if r.status_code >= 500 and attempt < MAX_RETRIES:
            print(f"  {r.status_code} Serverfehler, retry in {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue

        return r

    raise RuntimeError(f"Aufgegeben nach {MAX_RETRIES} Versuchen: {url}")


def fetch_results(t: dict, player_points: dict, player_records: dict) -> None:
    tid = t["id"]
    url = f"https://lichess.org/api/tournament/{tid}/results"
    r = get_with_retry(url, params={"sheet": "false"}, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"results status={r.status_code}")

    nb_players = t.get("nbPlayers")

    for raw_line in r.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        row = json.loads(raw_line)
        uname = row.get("username") or row.get("name")
        score = row.get("score", 0)
        rank = row.get("rank")
        if not uname:
            continue

        player_points[uname] = player_points.get(uname, 0) + score

        player_records.setdefault(uname, []).append(
            {
                "id": tid,
                "name": t.get("fullName"),
                "startsAt": t.get("startsAt"),
                "score": score,
                "rank": rank,
                "nbPlayers": nb_players,
            }
        )


def fetch_teams(t: dict, team_points: dict, team_names: dict, team_records: dict) -> None:
    tid = t["id"]
    url = f"https://lichess.org/api/tournament/{tid}/teams"
    r = get_with_retry(url)
    if r.status_code == 404:
        return  # kein Team-Battle
    if r.status_code != 200:
        raise RuntimeError(f"teams status={r.status_code}")

    data = r.json()
    teams = data.get("teams", [])
    # Lichess liefert die Teams eines Team-Battles bereits nach Score
    # sortiert zurueck -> Position in der Liste = Rang im Turnier.
    for idx, team in enumerate(teams):
        team_id = team.get("id")
        score = team.get("score", 0)
        if not team_id:
            continue
        team_points[team_id] = team_points.get(team_id, 0) + score
        team_names.setdefault(team_id, team.get("name", team_id))

        team_records.setdefault(team_id, []).append(
            {
                "id": tid,
                "name": t.get("fullName"),
                "startsAt": t.get("startsAt"),
                "score": score,
                "rank": idx + 1,
                "nbTeams": len(teams),
            }
        )


def main() -> int:
    with open(TOURNAMENTS_FILE, encoding="utf-8") as f:
        all_tournaments = json.load(f)

    my_tournaments = all_tournaments[CHUNK_INDEX::NUM_WORKERS]
    print(
        f"[Worker {CHUNK_INDEX}/{NUM_WORKERS}] {len(my_tournaments)} von "
        f"{len(all_tournaments)} Turnieren zugewiesen",
        file=sys.stderr,
    )

    player_points: dict = {}
    player_records: dict = {}
    team_points: dict = {}
    team_names: dict = {}
    team_records: dict = {}
    errors = []
    processed = 0

    for t in my_tournaments:
        tid = t["id"]
        try:
            fetch_results(t, player_points, player_records)
        except Exception as e:
            errors.append({"id": tid, "name": t.get("fullName"), "stage": "results", "error": str(e)})
        time.sleep(REQUEST_DELAY)

        try:
            fetch_teams(t, team_points, team_names, team_records)
        except Exception as e:
            errors.append({"id": tid, "name": t.get("fullName"), "stage": "teams", "error": str(e)})
        time.sleep(REQUEST_DELAY)

        processed += 1
        if processed % 10 == 0 or processed == len(my_tournaments):
            print(f"[Worker {CHUNK_INDEX}] {processed}/{len(my_tournaments)} verarbeitet", file=sys.stderr)

    out = {
        "worker": CHUNK_INDEX,
        "processed": processed,
        "player_points": player_points,
        "player_records": player_records,
        "team_points": team_points,
        "team_names": team_names,
        "team_records": team_records,
        "errors": errors,
    }

    out_path = f"partial_{CHUNK_INDEX}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(
        f"[Worker {CHUNK_INDEX}] fertig: {processed} Turniere, "
        f"{len(player_points)} Spieler, {len(team_points)} Teams, {len(errors)} Fehler -> {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
