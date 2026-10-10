.PHONY: up down logs ps test smoke deploy

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

test:
	docker compose run --rm api python -m pytest -q

smoke:
	bash scripts/smoke.sh

deploy:
	bash scripts/deploy.sh
