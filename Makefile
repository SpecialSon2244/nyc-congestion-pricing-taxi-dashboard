VENV=.venv
PY=$(VENV)/bin/python
.PHONY: all setup data analyze app clean
all: setup data analyze
setup:
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -r requirements.txt
data:
	$(PY) src/download.py && $(PY) src/prepare.py && $(PY) src/geo.py
analyze:
	$(PY) src/analyze.py
app:
	$(VENV)/bin/streamlit run app.py
clean:
	rm -rf data/raw data/processed images/*.png findings.json
