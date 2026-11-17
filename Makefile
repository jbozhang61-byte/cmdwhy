.PHONY: test demo check clean

test:
	python3 -m unittest discover -s tests -v

demo:
	python3 -m cmdwhy demo

check:
	python3 -m compileall -q cmdwhy tests
	python3 -m unittest discover -s tests

clean:
	rm -rf __pycache__ cmdwhy/__pycache__ tests/__pycache__ build dist *.egg-info
