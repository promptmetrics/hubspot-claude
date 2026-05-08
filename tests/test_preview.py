from hubspot_agent.preview import format_preview, render_field_diff, render_pattern_summary


def test_render_field_diff():
    old = [{"id": "1", "email": "old@example.com", "region": "West"}]
    new = [{"id": "1", "email": "new@example.com", "region": "East"}]
    result = render_field_diff(old, new, max_records=10)
    assert "Record 1" in result
    assert "`email`: `old@example.com` -> `new@example.com`" in result
    assert "`region`: `West` -> `East`" in result


def test_render_field_diff_empty():
    assert render_field_diff([], [], max_records=10) == ""


def test_render_field_diff_max_records():
    old = [{"id": str(i), "field": "old"} for i in range(15)]
    new = [{"id": str(i), "field": "new"} for i in range(15)]
    result = render_field_diff(old, new, max_records=10)
    assert result.count("Record ") == 10


def test_render_field_diff_no_changes():
    old = [{"id": "1", "field": "same"}]
    new = [{"id": "1", "field": "same"}]
    result = render_field_diff(old, new, max_records=10)
    assert "(no changes)" in result


def test_render_pattern_summary_consistent():
    old = [{"id": str(i), "region": "West"} for i in range(15)]
    new = [{"id": str(i), "region": "East"} for i in range(15)]
    result = render_pattern_summary(old, new, start_index=10)
    assert "Remaining 5 records" in result
    assert "`region`: `West` -> `East`" in result


def test_render_pattern_summary_inconsistent():
    old = [{"id": str(i), "region": "West" if i % 2 == 0 else "North"} for i in range(15)]
    new = [{"id": str(i), "region": "East" if i % 2 == 0 else "South"} for i in range(15)]
    result = render_pattern_summary(old, new, start_index=10)
    assert "same change pattern" in result


def test_render_pattern_summary_no_remaining():
    old = [{"id": "1", "field": "old"}]
    new = [{"id": "1", "field": "new"}]
    assert render_pattern_summary(old, new, start_index=10) == ""


def test_format_preview_diff_mode():
    old = [{"id": "1", "email": "old@example.com"}]
    new = [{"id": "1", "email": "new@example.com"}]
    result = format_preview(old, new, impact_count=1, mode="diff")
    assert "**Impact:** 1 records" in result
    assert "Record 1" in result
    assert "`email`: `old@example.com` -> `new@example.com`" in result


def test_format_preview_summary_mode():
    result = format_preview([], [], impact_count=42, mode="summary")
    assert result == "**Impact:** 42 records"
