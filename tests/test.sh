#!/bin/bash
# A simple test runner that ensures we run Django tests in a test venv.
venv="test_cogs"
venv_dir="$HOME/.venvs/$venv"
dev_dir="$HOME/workspace/CoGs/Source/develop"

source $venv_dir/bin/activate
python "$dev_dir/manage.py" test "$@" 