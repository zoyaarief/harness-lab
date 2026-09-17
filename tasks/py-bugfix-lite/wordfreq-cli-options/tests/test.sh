#!/bin/bash
# Hidden tests run from /app so relative data paths resolve.
mkdir -p /logs/verifier
cd /app
PYTHONPATH=/app python -m pytest -q -p no:cacheprovider /tests/test_hidden.py
if [ $? -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
