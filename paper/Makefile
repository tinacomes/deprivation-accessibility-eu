.PHONY: all includes clean distclean

all:
	latexmk -pdf -interaction=nonstopmode main.tex

includes:
	python3 make_includes.py

clean:
	latexmk -c
	rm -f main.bbl

distclean:
	latexmk -C
