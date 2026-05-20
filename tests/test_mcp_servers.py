import os
import tempfile
import shutil
from pathlib import Path
import pytest

from mcp_servers.filesystem_server import (
    list_study_files,
    read_study_file,
    search_notes,
    get_notes_index,
    mcp as fs_mcp
)
from mcp_servers.memory_server import (
    memory_set,
    memory_get,
    memory_list_keys,
    memory_delete,
    get_session_summary,
    _store
)


@pytest.fixture
def temp_notes_dir():
    """Create a temporary directory with mock B2B materials for testing."""
    temp_dir = tempfile.mkdtemp()
    
    # Create mock markdown files
    (Path(temp_dir) / "value_prop.md").write_text("# Value Proposition\nLead Accelerator B2B automation.", encoding="utf-8")
    (Path(temp_dir) / "case_study.md").write_text("# Case Study\nAcme increased conversion by 400%.", encoding="utf-8")
    (Path(temp_dir) / "notes.txt").write_text("Should not be listed.", encoding="utf-8")
    
    # Nested folder
    nested = Path(temp_dir) / "nested"
    nested.mkdir()
    (nested / "deep_prop.md").write_text("# Deep Prop\nSome deeper value hook details here.", encoding="utf-8")

    # Patch NOTES_BASE in filesystem_server module
    import mcp_servers.filesystem_server
    original_base = mcp_servers.filesystem_server.NOTES_BASE
    mcp_servers.filesystem_server.NOTES_BASE = Path(temp_dir)

    yield Path(temp_dir)

    # Restore and cleanup
    mcp_servers.filesystem_server.NOTES_BASE = original_base
    shutil.rmtree(temp_dir)


def test_list_study_files(temp_notes_dir):
    """Test listing markdown materials recursively."""
    files = list_study_files()
    assert len(files) == 3
    assert "value_prop.md" in files
    assert "case_study.md" in files
    assert str(Path("nested/deep_prop.md")) in files
    assert "notes.txt" not in files


def test_read_study_file(temp_notes_dir):
    """Test reading a markdown material file."""
    # Successful read
    content = read_study_file("value_prop.md")
    assert "Value Proposition" in content
    assert "B2B automation" in content

    # Nested read
    nested_content = read_study_file(str(Path("nested/deep_prop.md")))
    assert "deeper value hook" in nested_content

    # File not found
    error_content = read_study_file("missing.md")
    assert "Error" in error_content
    assert "missing.md" in error_content

    # Block non-markdown files
    block_txt = read_study_file("notes.txt")
    assert "Error" in block_txt
    assert "only .md files" in block_txt

    # Security traversal block
    security_error = read_study_file("../some_key.env")
    assert "traversal attempt blocked" in security_error


def test_search_notes(temp_notes_dir):
    """Test case-insensitive substring searching across files."""
    # Match in multiple files
    results = search_notes("prop")
    assert len(results) >= 2
    files_matched = [r["file"] for r in results]
    assert "value_prop.md" in files_matched
    assert str(Path("nested/deep_prop.md")) in files_matched

    # Specific match
    results_specific = search_notes("conversion")
    assert len(results_specific) == 1
    assert results_specific[0]["file"] == "case_study.md"
    assert results_specific[0]["line_number"] == 2
    assert "Acme increased conversion" in results_specific[0]["line"]

    # No match
    results_none = search_notes("missing_query")
    assert len(results_none) == 0


def test_get_notes_index(temp_notes_dir):
    """Test rendering the B2B materials index resource."""
    index = get_notes_index()
    assert "# B2B Materials Index" in index
    assert "value_prop.md" in index
    assert "case_study.md" in index
    assert "Total: 3 file(s)" in index


def test_memory_crud():
    """Test full CRM session memory CRUD tools."""
    session_id = "test_sess_123"
    
    # Reset store
    _store.clear()

    # Get empty memory key (should return string "null")
    val_empty = memory_get(session_id, "nonexistent")
    assert val_empty == "null"

    # Set value
    set_msg = memory_set(session_id, "explained", "Acme Case Study")
    assert "Stored" in set_msg
    assert session_id in set_msg

    # Get value
    val = memory_get(session_id, "explained")
    assert val == "Acme Case Study"

    # List keys
    keys = memory_list_keys(session_id)
    assert keys == ["explained"]

    # Delete key
    del_msg = memory_delete(session_id, "explained")
    assert "Deleted" in del_msg

    # Verify deleted
    val_deleted = memory_get(session_id, "explained")
    assert val_deleted == "null"

    # Delete missing key
    del_missing = memory_delete(session_id, "explained")
    assert "not found" in del_missing


def test_get_session_summary():
    """Test generating a session summary resource."""
    session_id = "test_sess_456"
    _store.clear()

    # Empty summary
    empty_sum = get_session_summary(session_id)
    assert "No data stored yet" in empty_sum

    # Populated summary
    memory_set(session_id, "score", "0.85")
    memory_set(session_id, "lead_name", "Sarah Connor")
    
    summary = get_session_summary(session_id)
    assert f"# Session Memory: {session_id}" in summary
    assert "## score" in summary
    assert "Value: 0.85" in summary
    assert "## lead_name" in summary
    assert "Value: Sarah Connor" in summary
