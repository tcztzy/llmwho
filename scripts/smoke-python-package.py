import sys

import llmwho


expected_tag = sys.argv[1]
assert expected_tag == f"v{llmwho.__version__}"
assert hasattr(llmwho, "JSONLStore")
assert not hasattr(llmwho, "ND" + "JSONStore")
assert [plugin["id"] for plugin in llmwho.science.plugins()] == ["output_affinity"]
