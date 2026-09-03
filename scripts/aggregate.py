#!/usr/bin/env python3
"""
Liest alle partial_*.json Dateien (von den Workern erzeugt, hier aus dem
Artifacts-Ordner) ein, summiert Spieler- und Team-Punkte ueber ALLE Turniere
und schreibt:
    LEADERBOARD.md          - lesbare Markdown-Rangliste (Teams + Spieler)
    leaderboard_players.json
    leaderboard_teams.json
    errors.json             - alle waehrend des Abrufs aufgetretenen Fehler

Umgebungsvariablen:
    PARTIALS_DIR   - Ordner, in dem nach partial_*.json gesucht wird (Default: artifacts)
    TOP_N_MD       - wie viele Zeilen je Tabelle ins Markdown geschrieben werden (Default: 0 = alle)
"""
import glob
import json
import os

PARTIALS_DIR = os.environ.get("PARTIALS_DIR", "artifacts")
TOP_N_MD = int(os.environ.get("TOP_N_MD", "0"))


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

    with open("leaderboard_players.json", "w", encoding="utf-8") as f:
        json.dump(
            [{"rank": i + 1, "username": u, "points": p} for i, (u, p) in enumerate(player_rank)],
            f,
            indent=2,
            ensure_ascii=False,
        )

    with open("leaderboard_teams.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {"rank": i + 1, "team_id": t, "team_name": team_names.get(t, t), "points": p}
                for i, (t, p) in enumerate(team_rank)
            ],
            f,
            indent=2,
            ensure_ascii=False,
        )

    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(all_errors, f, indent=2, ensure_ascii=False)

    team_lines = team_rank if TOP_N_MD <= 0 else team_rank[:TOP_N_MD]
    player_lines = player_rank if TOP_N_MD <= 0 else player_rank[:TOP_N_MD]

    with open("LEADERBOARD.md", "w", encoding="utf-8") as f:
        f.write("# LMAO Day / LMAO Night - Gesamtrangliste\n\n")
        f.write(f"Ausgewertete Turniere: **{total_processed}**  \n")
        f.write(f"Teams: **{len(team_rank)}**, Spieler: **{len(player_rank)}**\n\n")

        f.write("## Team-Rangliste\n\n")
        f.write("| Platz | Team | Punkte |\n|---:|---|---:|\n")
        for i, (team_id, pts) in enumerate(team_lines, 1):
            f.write(f"| {i} | {team_names.get(team_id, team_id)} | {pts} |\n")

        f.write("\n## Einzelspieler-Rangliste\n\n")
        f.write("| Platz | Spieler | Punkte |\n|---:|---|---:|\n")
        for i, (user, pts) in enumerate(player_lines, 1):
            f.write(f"| {i} | {user} | {pts} |\n")

        if all_errors:
            f.write(f"\n\n> {len(all_errors)} Fehler beim Abruf einzelner Turniere - Details in `errors.json`.\n")

    print(f"Fertig: {total_processed} Turniere ausgewertet, {len(team_rank)} Teams, {len(player_rank)} Spieler.")
    print(f"Fehler: {len(all_errors)}")
    return 0


if __name__ == "__main__":
    exit(main())
