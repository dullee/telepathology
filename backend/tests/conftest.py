import os
import tempfile

# Isolated data dir for every test run (must be set before app modules are imported).
os.environ.setdefault("TELEPATH_DATA_DIR", tempfile.mkdtemp(prefix="telepath-test-"))
