.PHONY: build clean clean-gke fixes gke help pip-compile pip-install-local stop test up


help:
	@echo "Welcome to the Telemetry Airflow\n"
	@echo "The list of commands for local development:\n"
	@echo "  build              Builds the docker images for the docker-compose setup"
	@echo "  clean              Stops and removes all docker containers"
	@echo "  fixes              Applies Black and Ruff fixes to Python files"
	@echo "  pip-compile        Compile dependencies from 'requirements.in' into 'requirements.txt'"
	@echo "  pip-install-local  Install pip project requirements to your local environment"
	@echo "  test               Runs pytest"
	@echo "  up                 Runs the whole stack, served under http://localhost:8080/"
	@echo "  gke                Create a sandbox gke cluster for testing"
	@echo "  clean-gke          Delete the sandbox gke cluster"
	@echo "  stop               Stops the docker containers"

build:
	docker-compose build

pip-compile:
	pip-compile --strip-extras --no-annotate requirements.in
	pip-compile --strip-extras --no-annotate requirements-dev.in

fixes:
	ruff check . --fix
	ruff format .

clean: stop
	docker-compose down --volumes
	docker-compose rm -f
	rm -rf logs/*
	if [ -f airflow-worker.pid ]; then rm airflow-worker.pid; fi

pip-install-local:
	pip install -r requirements.txt -r requirements-dev.txt
	pip install -r requirements-override.txt --upgrade

stop:
	docker-compose down
	docker-compose stop

up:
	grep -qF 'AIRFLOW_UID=' .env || echo "AIRFLOW_UID=$$(id -u)" >> .env
	grep -qF 'FERNET_KEY=' .env || echo "FERNET_KEY=$$(python3 -c "from cryptography.fernet import Fernet; fernet_key = Fernet.generate_key(); print(fernet_key.decode())")" >> .env
	mkdir -p logs
	docker-compose up --wait
	docker-compose exec airflow-webserver airflow variables import dev_variables.json
	docker-compose exec airflow-webserver airflow connections import dev_connections.json

gke:
	bin/start_gke

clean-gke:
	bin/stop_gke

test:
	python -m pytest tests/
