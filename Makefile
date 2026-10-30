.PHONY: bench test

bench:
	python3 -m synbios.sym3.reproduce

test:
	python3 -m unittest discover -s tests -v
