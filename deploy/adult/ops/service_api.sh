#!/bin/sh
set -eu
export GENOMEAI_WEB_DISABLE_WORKER=1
exec uvicorn web_cabinet.app:app --host 0.0.0.0 --port 8000 --workers ${GENOMEAI_API_WORKERS:-2}
