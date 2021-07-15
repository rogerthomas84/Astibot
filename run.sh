#!/usr/bin/env bash

DIRECTORY=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
cd "${DIRECTORY}" || exit

py3_check=$(which python3)
if [ "${py3_check}" != "" ]; then
  python3 src/Astibot.py
else
  python src/Astibot.py
fi