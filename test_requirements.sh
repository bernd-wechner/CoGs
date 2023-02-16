rm -rf ~/.virtualenvs/test_cogs/
python -m pip cache purge
python -m venv ~/.virtualenvs/test_cogs
source ~/.virtualenvs/test_cogs/bin/activate
pip --verbose install --upgrade pip
pip --verbose install wheel
cd ~/workspace/CoGs/
pip --verbose install -r requirements.txt
