import os
import tempfile

# Isolated data dir for every test run (must be set before app modules are imported).
os.environ.setdefault("TELEPATH_DATA_DIR", tempfile.mkdtemp(prefix="telepath-test-"))
# The real HoVer-Net cell counter is slow; tests that need it patch in a fake.
os.environ.setdefault("TELEPATH_CELLS", "0")
# Tests start from an empty queue.
os.environ.setdefault("TELEPATH_DEMO_CASES", "0")
