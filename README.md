# Look Again 🔎 / 再看一眼

Face-first guessing game built on the public [FBI Wanted API](https://api.fbi.gov/wanted/v1/list).
See the photo from a real FBI wanted poster, guess what the person is wanted for (one tap, optional clue peek), then get the real charge, the FBI page and a link to [tips.fbi.gov](https://tips.fbi.gov/). The end screen shows your gut vs reality.

- Only wanted fugitives/suspects with a clear photo are guessed (`fq` flag from `tools/faces.py`: FBI-seal placeholders and silhouettes are detected automatically, weak portraits are listed in `tools/face_skip.txt`). Missing persons, kidnapping victims and seeking-information posters are never scored; a few missing people appear in a separate, unscored "Help find them" strip.

- Players never contact FBI servers: a GitHub Action (`.github/workflows/refresh.yml`) runs `tools/build_cases.py` once a day, paginates the API slowly (1.2 s between pages, capped at 60 API requests), downloads and shrinks portraits only for new cases (capped at 400 image requests, 1 s apart), prunes removed or captured cases and their images, and commits only when something changed.
- Excluded: child-exploitation, unidentified remains, homicide/sexual-assault ViCAP files, deceased-victim cases, anything graphic. No race, ethnicity or appearance details are shown.
- Charges are allegations. Everyone is presumed innocent until proven guilty.
