#!/usr/bin/env python3
"""
Liest alle partial_*.json Dateien (von den Workern erzeugt, hier aus dem
Artifacts-Ordner) ein, summiert Spieler- und Team-Punkte ueber ALLE Turniere
und schreibt die Ergebnisse nach docs/data/, damit GitHub Pages sie direkt
ausliefern kann:
    docs/data/leaderboard_players.json
    docs/data/leaderboard_teams.json
    docs/data/meta.json     - Zeitstempel + Anzahl ausgewerteter Turniere
    errors.json             - Fehler beim Abruf (nicht auf der Webseite)

Umgebungsvariablen:
    PARTIALS_DIR   - Ordner, in dem nach partial_*.json gesucht wird (Default: artifacts)
    OUTPUT_DIR     - Zielordner fuer die JSON-Dateien der Webseite (Default: docs/data)
"""
import glob
import json
import os
from datetime import datetime, timezone

PARTIALS_DIR = os.environ.get("PARTIALS_DIR", "artifacts")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "docs/data")


def main() -> int:
    pattern = os.path.join(PARTIALS_DIR, "**", "partial_*.json")
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        # Fallback: vielleicht liegen sie im aktuellen Verzeichnis
        files = sorted(glob.glob("partial_*.json"))

    print(f"Gefundene Teil-Ergebnisdateien: {len(files)}")

    player_totals: dict = {}
    team_totals: dict = {}
    team_names: dict = {}
    total_processed = 0
    all_errors = []

    for fname in files:
        with open(fname, encoding="utf-8") as f:
            data = json.load(f)

        total_processed += data.get("processed", 0)

        for user, pts in data.get("player_points", {}).items():
            player_totals[user] = player_totals.get(user, 0) + pts

        for team, pts in data.get("team_points", {}).items():
            team_totals[team] = team_totals.get(team, 0) + pts

        for team, name in data.get("team_names", {}).items():
            team_names.setdefault(team, name)

        all_errors.extend(data.get("errors", []))

    player_rank = sorted(player_totals.items(), key=lambda x: (-x[1], x[0].lower()))
    team_rank = sorted(team_totals.items(), key=lambda x: (-x[1], x[0].lower()))

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    players_out = [
        {"rank": i + 1, "username": u, "points": p} for i, (u, p) in enumerate(player_rank)
    ]
    teams_out = [
        {"rank": i + 1, "team_id": t, "team_name": team_names.get(t, t), "points": p}
        for i, (t, p) in enumerate(team_rank)
    ]
    meta_out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tournaments_processed": total_processed,
        "teams_count": len(team_rank),
        "players_count": len(player_rank),
        "errors_count": len(all_errors),
    }

    with open(os.path.join(OUTPUT_DIR, "leaderboard_players.json"), "w", encoding="utf-8") as f:
        json.dump(players_out, f, indent=2, ensure_ascii=False)

    with open(os.path.join(OUTPUT_DIR, "leaderboard_teams.json"), "w", encoding="utf-8") as f:
        json.dump(teams_out, f, indent=2, ensure_ascii=False)

    with open(os.path.join(OUTPUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta_out, f, indent=2, ensure_ascii=False)

    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(all_errors, f, indent=2, ensure_ascii=False)

    print(f"Fertig: {total_processed} Turniere ausgewertet, {len(team_rank)} Teams, {len(player_rank)} Spieler.")
    print(f"Fehler: {len(all_errors)}")
    print(f"Geschrieben nach: {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    exit(main())
