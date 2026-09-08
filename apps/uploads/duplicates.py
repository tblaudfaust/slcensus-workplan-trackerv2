"""Duplicate detection for the upload preview step.

Nothing here blocks a commit -- these are advisory flags shown on the
preview screen so a human decides what to do, the same way invalid rows
are reported but not silently dropped without being shown. Two kinds of
duplicate are detected:

1. Within-file duplicates: two rows in *this* upload resolve to the same
   (workstream, name) -- a repeated row in the source spreadsheet, or the
   same milestone listed twice across different sheets under the same
   workstream. The second occurrence would silently overwrite the first
   on commit (matched by the same dedup key used for re-uploads), so it's
   flagged rather than left to happen quietly.
2. Cross-project near-duplicates: a row's name is a close fuzzy match to
   an activity that already exists in the project, in *any* workstream --
   this is the case that motivated building this: a master/roadmap sheet
   (e.g. "GENERAL") describing the same milestone a team's detailed sheet
   already covers, worded slightly differently and/or filed under a
   different workstream, which the exact-match dedup key can't catch.
"""

from rapidfuzz import fuzz

from .parsing import normalize_header

# token_sort_ratio, not token_set_ratio: the latter scores a shorter name
# as a 100% match whenever its words are a subset of a longer one's (e.g.
# "Training of Trainers" vs "Training of Master Trainers" -- two genuinely
# different activities), which would flood the preview with false
# positives. token_sort_ratio is more conservative and will occasionally
# miss a real duplicate that adds/drops a word, but a human reviewing the
# preview screen can still catch those; it won't cry wolf on distinct
# activities that happen to share phrasing.
SIMILARITY_THRESHOLD = 87


def load_existing_activities(project):
    """One query, reused across every sheet in the upload, rather than
    re-querying per row."""
    from apps.activities.models import Activity

    return [
        {
            "name": name,
            "name_norm": normalize_header(name),
            "workstream_name": workstream_name,
            "workstream_norm": normalize_header(workstream_name),
        }
        for name, workstream_name in Activity.objects.filter(project=project).values_list(
            "name", "workstream__name"
        )
    ]


def check_duplicates(rows, seen_within_upload, existing_activities):
    """Mutates each ParsedRow in `rows` (already filtered to valid ones),
    setting `.duplicate_info` to None or a short human-readable reason.
    `seen_within_upload` is a {(workstream_norm, name_norm): row_number}
    dict shared across every sheet in the same upload -- pass the same
    dict into each call so duplicates spanning sheets are caught too."""
    for row in rows:
        name_norm = normalize_header(row.data["name"])
        workstream_norm = normalize_header(row.data["workstream_name"])
        key = (workstream_norm, name_norm)

        if key in seen_within_upload:
            row.duplicate_info = f"Same as row {seen_within_upload[key]} in this upload"
            continue
        seen_within_upload[key] = row.row_number

        best_score, best_match = 0, None
        for candidate in existing_activities:
            if candidate["workstream_norm"] == workstream_norm and candidate["name_norm"] == name_norm:
                # Exact match in the same workstream is an update on
                # commit, not a duplicate concern.
                continue
            score = fuzz.token_sort_ratio(name_norm, candidate["name_norm"])
            if score >= SIMILARITY_THRESHOLD and score > best_score:
                best_score, best_match = score, candidate

        row.duplicate_info = (
            f'{round(best_score)}% similar to "{best_match["name"]}" already in {best_match["workstream_name"]}'
            if best_match
            else None
        )
