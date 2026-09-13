PYTHON ?= .venv/bin/python

.PHONY: test run

test:
	$(PYTHON) -m py_compile bot.py config.py services/*.py tests/*.py scripts/*.py
	$(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) bot.py
