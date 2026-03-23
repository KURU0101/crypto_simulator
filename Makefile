.PHONY: setup run run-real-data run-pseudo-realtime test

setup:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r requirements-dev.txt

run:
	python3 scripts/run_simulation.py --config config/simulation.example.json

run-real-data:
	python3 scripts/run_real_data_comparisons.py --config config/real_data_comparison.example.json

run-pseudo-realtime:
	python3 scripts/run_pseudo_realtime_replay.py --config config/pseudo_realtime_replay.example.json

test:
	python3 -m pytest
