PYTHON ?= python3.12
VENV   ?= .venv
UV     ?= $(HOME)/.local/bin/uv

.PHONY: help venv install install-dev install-cpu smoke bootstrap update serve mcp         snapshot-criar snapshot-restaurar eval test lint clean

help:
	@echo "Alvos disponíveis:"
	@echo "  venv         cria .venv com Python 3.12"
	@echo "  install      instala dependências de produção"
	@echo "  install-dev  instala dependências de produção + dev"
	@echo "  install-cpu  idem, com torch CPU (máquina sem GPU NVIDIA)"
	@echo "  smoke        roda smoke test (3 artigos da CF, busca híbrida)"
	@echo "  bootstrap    indexa o corpus do zero (761 documentos; horas sem GPU — prefira o snapshot)"
	@echo "  update       roda update incremental (delta semanal)"
	@echo "  serve        sobe o daemon de inferência (foreground)"
	@echo "  mcp          inicia o MCP server (stdio) — exige o daemon no ar"
	@echo "  snapshot-criar               empacota data/ em dist/lex-rag-snapshot.zip"
	@echo "  snapshot-restaurar ORIGEM=…  restaura um zip local ou URL em data/ (FORCAR=1 substitui)"
	@echo "  eval         roda dataset de avaliação anti-alucinação"
	@echo "  test         roda pytest (exclui marker 'network')"
	@echo "  lint         ruff check"
	@echo "  clean        remove caches e artefatos"

venv:
	$(UV) venv --python $(PYTHON) $(VENV)

install: venv
	$(UV) pip install --python $(VENV)/bin/python -e .

install-dev: venv
	$(UV) pip install --python $(VENV)/bin/python -e ".[dev,eval]"

# Sem o --index-url o pip traz o wheel CUDA (~2 GB de bibliotecas NVIDIA) mesmo sem GPU.
install-cpu: venv
	$(UV) pip install --python $(VENV)/bin/python torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
	$(UV) pip install --python $(VENV)/bin/python -e ".[dev]"

smoke:
	$(VENV)/bin/python scripts/smoke_test.py

bootstrap:
	$(VENV)/bin/python scripts/bootstrap_full_index.py

update:
	$(VENV)/bin/python -m lex_rag.update.cli --mode delta

serve:
	$(VENV)/bin/python -m lex_rag.service

mcp:
	$(VENV)/bin/python -m lex_rag.mcp_server.server

snapshot-criar:
	$(VENV)/bin/python scripts/snapshot.py criar

snapshot-restaurar:
	$(VENV)/bin/python scripts/snapshot.py restaurar "$(ORIGEM)" $(if $(FORCAR),--forcar,)

eval:
	$(VENV)/bin/python eval/run_ragas.py

test:
	$(VENV)/bin/pytest -m "not network" -q

lint:
	$(VENV)/bin/ruff check src tests scripts

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
