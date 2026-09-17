#!/bin/bash
# Reference solution: copy the fixed files over the project.
set -e
cp -r "$(dirname "$0")/fixed/." /app/
