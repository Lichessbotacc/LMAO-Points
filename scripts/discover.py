#!/usr/bin/env python3
"""
Findet ALLE vom Ziel-User erstellten Lichess-Arena-Turniere, deren Name
"LMAO Day" oder "LMAO Night" enthaelt (kompletter Scan, kein State),
und schreibt sie nach tournaments.json.

Nutzt den NDJSON-Streaming-Endpoint:
    GET https://lichess.org/api/user/{username}/tournament/created?nb={n}

Umgebungsvariablen:
    LICHESS_USER   - Lichess-Benutzername (Default: DarkOnCrack)
    LICHESS_TOKEN  - optionales Personal Access Token (erhoeht Rate-Limits)
    DISCOVER_NB    - wie viele Turniere maximal vom Server angefragt werden
                     (Default 6000, der User hat aktuell 2629 Turniere total)
    NAME_FILTERS   - kommagetrennte, kleingeschriebene Substrings, die im
                     Turniernamen vorkommen muessen (Default: "lmao day,lmao night")
    ONLY_FINISHED  - "1" (Default) = nur abgeschlossene Turniere (status 30)
                     aufnehmen, weil nur die ein finales Ergebnis haben
"""
import json
import os
import sys

import requests

USER = os.environ.get("LICHESS_USER", "DarkOnCrack")
TOKEN = os.environ.get("LICHESS_TOKEN")
NB = int(os.environ.get("DISCOVER_NB", "6000"))
NAME_FILTERS = [
    s.strip().lower()
    for s in os.environ.get("NAME_FILTERS", "lmao day,lmao night").split(",")
    if s.strip()
]
ONLY_FINISHED = os.environ.get("ONLY_FINISHED", "1") == "1"
STATUS_FINISHED = 30

headers = {"Accept": "application/x-ndjson"}
if TOKEN:
    headers["Authorization"] = f"Bearer {TOKEN}"


def main() -> int:
    url = f"https://lichess.org/api/user/{USER}/tournament/created"
    print(f"Frage Turnierliste ab: {url} (nb={NB})", file=sys.stderr)

    resp = requests.get(url, headers=headers, params={"nb": NB}, stream=True, timeout=120)
    resp.raise_for_status()

    matches = []
    scanned = 0

    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        scanned += 1
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        name = obj.get("fullName") or obj.get("name") or ""
        lname = name.lower()

        if not any(f in lname for f in NAME_FILTERS):
            continue

        if ONLY_FINISHED and obj.get("status") != STATUS_FINISHED:
            continue

        matches.append(
            {
                "id": obj.get("id"),
                "fullName": name,
                "startsAt": obj.get("startsAt"),
                "status": obj.get("status"),
                "nbPlayers": obj.get("nbPlayers"),
            }
        )

    print(f"Gescannt: {scanned} Turniere insgesamt", file=sys.stderr)
    print(f"Gefunden: {len(matches)} LMAO Day/Night Turniere", file=sys.stderr)

    if scanned >= NB:
        print(
            f"WARNUNG: Es wurden genau NB={NB} Turniere zurueckgegeben - "
            "moeglicherweise gibt es aeltere Turniere, die nicht erfasst wurden. "
            "Erhoehe DISCOVER_NB und starte den Workflow erneut.",
            file=sys.stderr,
        )

    if not matches:
        print("WARNUNG: Keine passenden Turniere gefunden!", file=sys.stderr)

    with open("tournaments.json", "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
