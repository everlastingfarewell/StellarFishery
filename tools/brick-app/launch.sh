#!/bin/sh
set -eu
cd /opt/stellar
export PYTHONPATH=/opt/stellar:/opt/stellar/vendor
export OPENBLAS_NUM_THREADS=1
exec ./python/bin/python3 -m stellar.handheld "$@"
