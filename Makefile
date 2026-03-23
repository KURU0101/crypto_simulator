.PHONY: setup run run-real-data test

setup:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r requirements-dev.txt

run:
	python3 scripts/run_simulation.py --config config/simulation.example.json

run-real-data:
	python3 scripts/run_real_data_comparisons.py --config config/real_data_comparison.example.json

test:
	python3 -m pytest
