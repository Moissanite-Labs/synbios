.PHONY: bench test site-build

bench:
	python3 -m synbios.sym3.reproduce

test:
	python3 -m unittest discover -s tests -v

site-build:
	python3 site/inject_version.py
