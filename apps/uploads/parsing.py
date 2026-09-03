"""Column standardization + row parsing for uploaded Census workplan files.

Design: never silently guess past a confidence threshold. Exact alias
matches are applied first; anything left over gets one fuzzy-matching pass
(rapidfuzz) and is still reported back to the uploader as "detected" so it
can be corrected on the preview screen rather than trusted blindly.
"""

import io
import re
from datetime import date, datetime

import pandas as pd
from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 80

# Internal field name -> human label, in the order they should be previewed.
FIELDS = {
    "name": "Milestone / Activity",
    "start_date": "Start Date",
    "end_date": "End Date",
    "duration_days": "Duration / Days",
    "workstream": "Workstream",
    "dependency": "Dependency / Input",
    "deliverable": "Deliverable / Expected Output",
    "responsible": "Responsible Person / Team Contact",
    "status": "Status / Remark",
    "phase": "Phase",
}

REQUIRED_FIELDS = ["name"]

COLUMN_ALIASES = {
    "name": [
        "milestone", "activity", "milestone activity", "activity milestone",
        "task", "task name", "workplan item", "milestone/activity", "description",
    ],
    "start_date": ["start date", "start", "planned start", "start_date", "begin date"],
    "end_date": [
        "end date", "end", "finish date", "planned end", "deadline", "target date",
        "due date", "completion date",
    ],
    "duration_days": [
        "duration", "days", "duration days", "no of days", "number of days", "duration (days)",
    ],
    "workstream": ["workstream", "work stream", "component", "theme", "unit", "team"],
    "dependency": ["dependency", "input", "dependency input", "prerequisite", "prerequisites", "dependencies"],
    "deliverable": [
        "deliverable", "expected output", "output", "deliverable expected output",
        "outputs", "expected deliverable",
    ],
    "responsible": [
        "responsible person", "responsible", "team contact", "owner", "responsible officer",
        "focal point", "responsible person team contact", "assigned to", "contact person",
    ],
    "status": [
        "status", "remark", "remarks", "status remark", "comments", "progress status", "comment",
    ],
    "phase": ["phase", "stage", "census phase"],
}

STATUS_KEYWORDS = [
    # "done" is deliberately excluded: phrases like "65% done" describe
    # progress, not completion, and would otherwise false-positive here.
    ("COMPLETED", ["completed", "complete", "finished", "closed"]),
    ("DELAYED", ["delayed", "behind schedule", "late", "slipped"]),
    ("AT_RISK", ["at risk", "at-risk", "risk", "critical"]),
    ("ONGOING", ["ongoing", "in progress", "in-progress", "on track", "on-track", "started"]),
    ("NOT_STARTED", ["not started", "not yet started", "pending", "yet to start", "planned", "scheduled"]),
]

_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")


def normalize_header(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"[\\/_\-]+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def match_columns(headers):
    """Returns (mapping, unmatched) where mapping is {field: original_header}
    for every field that could be matched (exactly or fuzzily), and
    unmatched is the list of original headers that matched nothing."""
    normalized = {h: normalize_header(h) for h in headers}
    alias_lookup = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            alias_lookup[alias] = field

    mapping = {}
    remaining = dict(normalized)

    # Exact match pass.
    for original, norm in list(remaining.items()):
        if norm in alias_lookup and alias_lookup[norm] not in mapping:
            mapping[alias_lookup[norm]] = original
            del remaining[original]

    # Fuzzy pass for whatever's left.
    all_aliases = list(alias_lookup.keys())
    for original, norm in list(remaining.items()):
        if not all_aliases:
            break
        best = process.extractOne(norm, all_aliases, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= FUZZY_THRESHOLD:
            field = alias_lookup[best[0]]
            if field not in mapping:
                mapping[field] = original
                del remaining[original]

    unmatched = list(remaining.keys())
    return mapping, unmatched


HEADER_SCAN_ROWS = 10
MIN_HEADER_MATCHES = 2


def _promote_header_row(df):
    """Real-world workbooks sometimes carry a title row (and a blank row)
    above the real header -- e.g. "STATISTICS SIERRA LEONE, 2026 PHC
    WORKPLAN..." merged across columns A:H, with the actual "Milestone /
    Activity", "Start Date", ... header one or two rows down. Detects that
    by scanning the first few rows for the one that matches the most known
    field aliases, and promotes it to the header if it looks better than
    row 0. Sheets whose header is already row 0 (the common case) are
    returned unchanged."""
    if df.empty:
        return df

    scan_limit = min(HEADER_SCAN_ROWS, len(df))
    best_row, best_score = 0, -1
    for i in range(scan_limit):
        candidate = [str(v) for v in df.iloc[i].tolist()]
        mapping, _ = match_columns(candidate)
        score = len(mapping)
        if score > best_score:
            best_row, best_score = i, score

    # Row 0 is used as a fallback header whenever nothing scored well
    # enough to be confident -- this preserves the previous default
    # behaviour (first row is the header) for sheets with no recognizable
    # standard columns at all.
    header_row = best_row if best_score >= MIN_HEADER_MATCHES else 0

    new_header = [str(v).strip() for v in df.iloc[header_row].tolist()]
    data = df.iloc[header_row + 1 :].reset_index(drop=True)
    data.columns = new_header
    return data


def read_uploaded_file(file_obj, filename):
    """Returns {sheet_name: DataFrame}. A CSV becomes a single "pseudo
    sheet" named after the file (minus extension)."""
    raw = file_obj.read()
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, header=None)
        stem = re.sub(r"\.csv$", "", filename, flags=re.IGNORECASE)
        return {stem: _promote_header_row(df)}
    raw_sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, dtype=str, keep_default_na=False, header=None)
    return {name: _promote_header_row(df) for name, df in raw_sheets.items()}


def _parse_date(value):
    if value is None:
        return None, None
    if isinstance(value, (datetime, date)):
        return (value.date() if isinstance(value, datetime) else value), None
    text = str(value).strip()
    if not text:
        return None, None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, errors="raise")
        return parsed.date(), None
    except Exception:
        return None, f"Could not parse date '{text}'"


def _parse_int(value):
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def normalize_status_text(raw_text):
    """Best-effort mapping of free-form status/remark text to our Status
    enum plus a progress percentage guess. Falls back to ONGOING when text
    is present but unrecognized (better default than NOT_STARTED for an
    activity someone bothered to write a remark about), and NOT_STARTED
    when the cell is empty."""
    text = (raw_text or "").strip().lower()
    if not text:
        return "NOT_STARTED", 0

    percent_match = _PERCENT_RE.search(text)
    progress = int(percent_match.group(1)) if percent_match else None

    for status, keywords in STATUS_KEYWORDS:
        if any(kw in text for kw in keywords):
            if progress is None:
                progress = {"COMPLETED": 100, "NOT_STARTED": 0}.get(status, 50)
            return status, min(progress, 100)

    return "ONGOING", progress if progress is not None else 50


class ParsedRow:
    def __init__(self, row_number, data, errors):
        self.row_number = row_number
        self.data = data
        self.errors = errors

    @property
    def is_valid(self):
        return not self.errors


def parse_sheet(df, mapping, default_workstream_name=None):
    """Turns a raw DataFrame + column mapping into a list of ParsedRow."""
    rows = []
    for idx, raw_row in df.iterrows():
        row_number = idx + 2  # header is row 1
        errors = []

        def get(field):
            col = mapping.get(field)
            if col is None:
                return ""
            return str(raw_row.get(col, "")).strip()

        name = get("name")
        if not name:
            # Entirely blank rows are silently skipped, not reported as errors.
            if not any(get(f) for f in FIELDS if f != "name"):
                continue
            errors.append("Missing Milestone / Activity name")

        start_date, start_err = _parse_date(get("start_date")) if mapping.get("start_date") else (None, None)
        end_date, end_err = _parse_date(get("end_date")) if mapping.get("end_date") else (None, None)
        if start_err:
            errors.append(f"Start date: {start_err}")
        if end_err:
            errors.append(f"End date: {end_err}")
        if start_date and end_date and end_date < start_date:
            errors.append("End date is before start date")

        duration = _parse_int(get("duration_days")) if mapping.get("duration_days") else None

        workstream_name = get("workstream") if mapping.get("workstream") else ""
        workstream_name = workstream_name or default_workstream_name or "General"

        status_value, progress = normalize_status_text(get("status"))

        data = {
            "name": name,
            "start_date": start_date,
            "end_date": end_date,
            "duration_days": duration,
            "workstream_name": workstream_name,
            "dependency": get("dependency"),
            "deliverable": get("deliverable"),
            "responsible_text": get("responsible"),
            "status": status_value,
            "progress_percent": progress,
            "phase": get("phase"),
            "remarks": get("status"),
        }
        rows.append(ParsedRow(row_number, data, errors))
    return rows
