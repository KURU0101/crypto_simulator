.PHONY: setup run test

setup:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r requirements-dev.txt

run:
	python3 scripts/run_simulation.py --config config/simulation.example.json

test:
	python3 -m pytest
