"""
Tests for the load_rdf() and load_rdf_file() functions in ontology_qa.py
"""
import os
from pathlib import Path
import rdflib
from scripts.ontology_qa import load_rdf, load_rdf_file

TESTS_DIR = os.path.join(os.path.dirname(__file__))


# Tests for direct loading single RDF files

def test_direct_load_single_turtle_file(tmp_path):
    """Test loading a single Turtle file directly"""
    file = tmp_path / "test.ttl"
    file.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    success, file_graph, log_msg = load_rdf_file(str(file))
    assert success
    assert len(file_graph) > 0
    assert "Loading data from:" in log_msg
    assert str(file) in log_msg

def test_direct_load_single_rdfxml_file(tmp_path):
    """Test loading a single RDF/XML file directly"""
    file = tmp_path / "test.rdf"
    file.write_text("""<?xml version="1.0"?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:owl="http://www.w3.org/2002/07/owl#">
        <rdf:Description rdf:about="http://example.org#Cat">
            <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Class"/>
        </rdf:Description>
    </rdf:RDF>
    """)
    success, file_graph, log_msg = load_rdf_file(str(file))
    assert success
    assert len(file_graph) > 0
    assert "Loading data from:" in log_msg
    assert str(file) in log_msg

def test_direct_load_nonexistent_file(tmp_path):
    """Test loading a file file directly"""
    file = tmp_path / "nonexistent.ttl"
    success, file_graph, log_msg = load_rdf_file(str(file))
    assert not success
    assert len(file_graph) == 0
    assert "Loading data from:" in log_msg
    assert str(file) in log_msg
    assert "Failed to parse" in log_msg

def test_direct_load_file_with_syntax_error(tmp_path):
    """Test loading a file with invalid RDF syntax directly"""
    file = tmp_path / "bad.ttl"
    file.write_text("this is not valid turtle syntax @@@ !!!")
    success, file_graph, log_msg = load_rdf_file(str(file))
    assert not success
    assert len(file_graph) == 0
    assert "Loading data from:" in log_msg
    assert str(file) in log_msg
    assert "Failed to parse" in log_msg
    assert "Bad syntax" in log_msg


# Tests for loading single RDF files

def test_load_single_turtle_file(tmp_path):
    """Test loading a single Turtle file"""
    file = tmp_path / "test.ttl"
    file.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file_counter, files_processed, graph, log_results = load_rdf([str(file)])
    assert file_counter == 1
    assert len(files_processed) == 1
    assert str(file) in files_processed[0]
    assert len(graph) > 0
    assert "Loading data from:" in log_results
    assert str(file) in log_results

def test_load_single_rdfxml_file(tmp_path):
    """Test loading a single RDF/XML file"""
    file = tmp_path / "test.rdf"
    file.write_text("""<?xml version="1.0"?>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:owl="http://www.w3.org/2002/07/owl#">
        <rdf:Description rdf:about="http://example.org#Cat">
            <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Class"/>
        </rdf:Description>
    </rdf:RDF>
    """)
    file_counter, files_processed, graph, log_results = load_rdf([str(file)])
    assert file_counter == 1
    assert len(files_processed) == 1
    assert len(graph) > 0
    assert "Loading data from:" in log_results
    assert str(file) in log_results

def test_load_nonexistent_file(tmp_path):
    """Test loading a file file"""
    file = tmp_path / "nonexistent.ttl"
    file_counter, files_processed, graph, log_results = load_rdf([str(file)])
    assert file_counter == 0
    assert len(files_processed) == 0
    assert len(graph) == 0
    assert "Loading data from:" not in log_results
    assert str(file) not in log_results

def test_load_file_with_syntax_error(tmp_path):
    """Test loading a file with invalid RDF syntax"""
    file = tmp_path / "bad.ttl"
    file.write_text("this is not valid turtle syntax @@@ !!!")
    file_counter, files_processed, graph, log_results = load_rdf([str(file)])
    assert file_counter == 0
    assert len(files_processed) == 0
    assert len(graph) == 0
    assert "Loading data from:" not in log_results
    assert str(file) not in log_results

def test_empty_input_returns_empty_graph():
    """Test that empty input returns an empty graph"""
    file_counter, files_processed, graph, _ = load_rdf([])
    assert file_counter == 0
    assert len(files_processed) == 0
    assert len(graph) == 0

# Tests for loading multiple RDF files

def test_load_multiple_files(tmp_path):
    """Test loading multiple files at once"""
    file1 = tmp_path / "test1.ttl"
    file1.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file2 = tmp_path / "test2.ttl"
    file2.write_text("""
    @prefix : <http://example.org#> .
    :Dog a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file_counter, files_processed, graph, _ = load_rdf([str(file1), str(file2)])
    assert file_counter == 2
    assert len(files_processed) == 2
    assert len(graph) >= 2

def test_load_mixed_valid_and_invalid_files(tmp_path):
    """Test loading a mix of valid and invalid files"""
    valid_file = tmp_path / "valid.ttl"
    valid_file.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    invalid_file = tmp_path / "invalid.ttl"
    invalid_file.write_text("not valid turtle @@@ !!!")
    
    file_counter, files_processed, graph, log_results = load_rdf([str(valid_file), str(invalid_file)])
    assert file_counter == 1
    assert len(files_processed) == 1
    assert str(valid_file) in files_processed[0]
    assert len(graph) > 0
    # Test that non-verbose mode only includes logs for successful files
    assert str(valid_file) in log_results
    assert str(invalid_file) not in log_results

def test_load_multiple_files_graph_merges(tmp_path):
    """Test that classes from multiple files are present in the merged graph"""
    file1 = tmp_path / "test1.ttl"
    file1.write_text("""
    @prefix : <http://example.org#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    :Cat a owl:Class .
    """)
    file2 = tmp_path / "test2.ttl"
    file2.write_text("""
    @prefix : <http://example.org#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    :Dog a owl:Class .
    """)
    _, _, graph, _ = load_rdf([str(file1), str(file2)])
    namespace = rdflib.Namespace("http://example.org#")
    assert (namespace.Cat, rdflib.RDF.type, rdflib.OWL.Class) in graph
    assert (namespace.Dog, rdflib.RDF.type, rdflib.OWL.Class) in graph


# Tests for loading RDF files from directories and subdirectories

def test_load_from_directory(tmp_path):
    """Test loading all RDF files from a directory"""
    file1 = tmp_path / "test1.ttl"
    file1.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file2 = tmp_path / "test2.ttl"
    file2.write_text("""
    @prefix : <http://example.org#> .
    :Dog a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file_counter, files_processed, graph, _ = load_rdf([str(tmp_path)])
    assert file_counter == 2
    assert len(files_processed) == 2
    assert len(graph) >= 2

def test_load_from_nested_directory(tmp_path):
    """Test loading RDF files from nested directories"""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    file1 = tmp_path / "test1.ttl"
    file1.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file2 = subdir / "test2.ttl"
    file2.write_text("""
    @prefix : <http://example.org#> .
    :Dog a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file_counter, files_processed, graph, _ = load_rdf([str(tmp_path)])
    assert file_counter == 2
    assert len(files_processed) == 2
    assert len(graph) >= 2

def test_load_empty_directory(tmp_path):
    """Test loading from an empty directory"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    file_counter, files_processed, graph, _ = load_rdf([str(empty_dir)])
    assert file_counter == 0
    assert len(files_processed) == 0
    assert len(graph) == 0

def test_load_directory_ignores_non_files(tmp_path):
    """Test that non-RDF files are attempted to load but fail gracefully"""
    file = tmp_path / "test.ttl"
    file.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("This is not an RDF file")
    file_counter, files_processed, graph, _ = load_rdf([str(tmp_path)])
    # Only the TTL file should load successfully
    assert file_counter == 1
    assert len(files_processed) == 1

def test_load_mixed_files_and_directories(tmp_path):
    """Test loading a mix of file and directory paths"""
    # Create a directory with a file
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    dir_file = subdir / "dir_file.ttl"
    dir_file.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    # Create a file outside the directory
    outer_file = tmp_path / "outer_file.ttl"
    outer_file.write_text("""
    @prefix : <http://example.org#> .
    :Dog a <http://www.w3.org/2002/07/owl#Class> .
    """)
    file_counter, files_processed, graph, _ = load_rdf([str(outer_file), str(subdir)])
    assert file_counter == 2
    assert len(files_processed) == 2
    assert len(graph) >= 2
    # Repeat, but navigating the directory.
    file_counter, files_processed, graph, _ = load_rdf([str(tmp_path)])
    assert file_counter == 2
    assert len(files_processed) == 2
    assert len(graph) >= 2


# Tests for verbose output

def test_verbose_mode_nonexistent_file(tmp_path):
    """Test loading a file file"""
    file = tmp_path / "nonexistent.ttl"
    _, _, _, log_results = load_rdf([str(file)], verbose=True)
    assert "Loading data from:" in log_results
    assert str(file) in log_results
    assert "Failed to parse" in log_results

def test_verbose_mode_file_with_syntax_error(tmp_path):
    """Test loading a file with invalid RDF syntax"""
    file = tmp_path / "bad.ttl"
    file.write_text("this is not valid turtle syntax @@@ !!!")
    _, _, _, log_results = load_rdf([str(file)], verbose=True)
    assert "Loading data from:" in log_results
    assert str(file) in log_results
    assert "Failed to parse" in log_results
    assert "Bad syntax" in log_results

def test_verbose_mode_includes_all_logs(tmp_path):
    """Test that verbose mode includes logs for both successful and failed files"""
    valid_file = tmp_path / "valid.ttl"
    valid_file.write_text("""
    @prefix : <http://example.org#> .
    :Cat a <http://www.w3.org/2002/07/owl#Class> .
    """)
    invalid_file = tmp_path / "invalid.ttl"
    invalid_file.write_text("not valid turtle @@@ !!!")
    _, _, _, log_results = load_rdf([str(valid_file), str(invalid_file)], verbose=True)
    assert str(valid_file) in log_results
    assert str(invalid_file) in log_results
    assert "Bad syntax" in log_results


# Tests for namespace binding

def test_namespace_binding_preserved(tmp_path):
    """Test that namespaces from source files are bound to the target graph"""
    file1 = tmp_path / "test1.ttl"
    file1.write_text("""
    @prefix ex: <http://example.org#> .
    @prefix custom: <http://custom.org#> .
    ex:Cat a ex:Class .
    """)
    _, _, graph, _ = load_rdf([str(file1)])
    # Check that namespaces are bound
    namespaces = dict(graph.namespace_manager.namespaces())
    assert any("example.org" in str(ns) for ns in namespaces.values())
    assert any("custom.org" in str(ns) for ns in namespaces.values())

