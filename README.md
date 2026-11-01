# Look Again 🔎 / 再看一眼

A respectful guessing game built on the public [FBI Wanted API](https://api.fbi.gov/wanted/v1/list).
Read the facts from a real FBI poster (no names, no photos), pick which FBI list it is on, then see the face and the full poster with a link to [tips.fbi.gov](https://tips.fbi.gov/).

- Players never contact FBI servers: a GitHub Action (`.github/workflows/refresh.yml`) runs `tools/build_cases.py` once a day, paginates the API slowly (1.2 s between pages, capped at 60 API requests), downloads and shrinks portraits only for new cases (capped at 400 image requests, 1 s apart), prunes removed or captured cases and their images, and commits only when something changed.
- Excluded: child-exploitation, unidentified remains, homicide/sexual-assault ViCAP files, deceased-victim cases, anything graphic. No race, ethnicity or appearance details are shown.
- Charges are allegations. Everyone is presumed innocent until proven guilty.
