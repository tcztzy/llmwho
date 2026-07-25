import sys
from tempfile import TemporaryDirectory
from pathlib import Path

import llmwho


expected_tag = sys.argv[1]
assert expected_tag == f"v{llmwho.__version__}"
assert hasattr(llmwho, "JSONLStore")
assert hasattr(llmwho, "SQLiteStore")
assert hasattr(llmwho, "RemoteStore")
assert not hasattr(llmwho, "ND" + "JSONStore")
assert [plugin["id"] for plugin in llmwho.science.plugins()] == ["output_affinity"]
with TemporaryDirectory() as directory:
    with llmwho.SQLiteStore(Path(directory) / "collector.sqlite3") as store:
        assert store.table_names() == llmwho.SQLiteStore.TABLES
