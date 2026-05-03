from pathlib import Path
from genomeai.cli import main

def test_validate_examples_ok():
    repo = Path(__file__).resolve().parents[1]
    rc = main(["validate", "--input", str(repo/"data/examples"), "--contracts", str(repo/"configs/contracts")])
    assert rc == 0
