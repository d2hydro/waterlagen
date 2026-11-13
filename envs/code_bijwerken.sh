#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec pixi exec --spec 'python=3.13' -- python "$project_dir/code_bijwerken.py" "$@"
