all:
	latexmk -pdf -interaction=nonstopmode main.tex
	latexmk -pdf -interaction=nonstopmode si.tex
figures:
	python3 make_figs_print.py
clean:
	latexmk -c; rm -f main.bbl si.bbl
