from __future__ import annotations

from typing import Any

def render_field_diff(
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    max_records: int = 10,
) -> str:
    """Render a markdown table of per-field diffs for the first N records."""
    lines: list[str] = []
    count = min(len(old_records), len(new_records), max_records)
    if count == 0:
        return ""

    for i in range(count):
        old = old_records[i]
        new = new_records[i]
        record_id = old.get("id", new.get("id", f"record_{i}"))
        lines.append(f"**Record {record_id}**")
        diff_lines: list[str] = []
        for key in sorted(set(old.keys()) | set(new.keys())):
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                diff_lines.append(f"- `{key}`: `{old_val}` -> `{new_val}`")
        if diff_lines:
            lines.extend(diff_lines)
        else:
            lines.append("- (no changes)")
        lines.append("")

    return "\n".join(lines)


def render_pattern_summary(
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    start_index: int = 10,
) -> str:
    """Summarize remaining records by identical change pattern."""
    remaining = min(len(old_records), len(new_records)) - start_index
    if remaining <= 0:
        return ""

    # Identify fields that change in every remaining record with the same old->new mapping
    if start_index >= len(old_records) or start_index >= len(new_records):
        return f"*Remaining {remaining} records: same change pattern.*"

    first_old = old_records[start_index]
    first_new = new_records[start_index]
    changed_fields: dict[str, tuple[Any, Any]] = {}

    for key in sorted(set(first_old.keys()) | set(first_new.keys())):
        old_val = first_old.get(key)
        new_val = first_new.get(key)
        if old_val != new_val:
            changed_fields[key] = (old_val, new_val)

    # Verify pattern holds across all remaining records
    consistent = True
    for i in range(start_index + 1, min(len(old_records), len(new_records))):
        old = old_records[i]
        new = new_records[i]
        for key, (expected_old, expected_new) in changed_fields.items():
            if old.get(key) != expected_old or new.get(key) != expected_new:
                consistent = False
                break
        if not consistent:
            break

    if consistent and changed_fields:
        parts = [f"`{k}`: `{v[0]}` -> `{v[1]}`" for k, v in sorted(changed_fields.items())]
        return f"*Remaining {remaining} records: all have {'; '.join(parts)}.*"

    return f"*Remaining {remaining} records: same change pattern.*"


def format_preview(
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    impact_count: int,
    mode: str = "diff",
) -> str:
    """Format a preview with inline diffs or a summary."""
    if mode != "diff":
        return f"**Impact:** {impact_count} records"

    diff = render_field_diff(old_records, new_records, max_records=10)
    summary = render_pattern_summary(old_records, new_records, start_index=10)
    lines = [f"**Impact:** {impact_count} records", ""]
    if diff:
        lines.append(diff)
    if summary:
        lines.append(summary)
    return "\n".join(lines)


