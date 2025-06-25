#!/bin/bash
#
# Ensures a venve exists for the test runner and is cleanly created.

venv="test_cogs"
venv_dir="$HOME/.venvs/$venv/"
dev_dir="$HOME/workspace/CoGs/Source/develop"

rm -rf "$venv_dir"
python -m pip cache purge
python -m venv "$venv_dir"
source "$venv_dir/bin/activate"
pip --verbose install --upgrade pip
pip --verbose install wheel

cd "$dev_dir"
pip --verbose install -r requirements.txt
