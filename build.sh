#!/bin/sh
set -eu
python -m pip install -r requirements.txt
python -m pip install --no-deps ./vendor/eduvize-admin
python -m pip install --no-deps ./vendor/eduvize-fotogalerie
