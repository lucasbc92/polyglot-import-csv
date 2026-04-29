#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Installing..."
    brew install python3
fi

echo "Building macOS app..."
python3 setup.py py2app

echo "Running the macOS app..."
./dist/polyglotimportcsv.app/Contents/MacOS/polyglotimportcsv \
    ./data/data.csv \
    --dbconfig=./data/db.json \
    --database=redis \
    --entity="[col1,col2]=e1" \
    --entity="[col3,col4]=e2" \
    --database=postgres \
    --entity="[col5=key,col6=key,col7]=e3" \
    --entity="[col8,col9,col10,col11]=e4" \
    --rel="[e3,e4,col9,col10,col22]=r1" \
    --database=mongodb \
    --entity="[col12,--entity=[col13,col14]=ne1,--array=[col15,col16,col17]=arr1,col18]=e5" \
    --entity="[col19,col20,col21]=e6" \
    --database=cassandra \
    --entity="[col23,col24,--entity=[col25,col26]=ne2]=e7" \
    --database=neo4j \
    --entity="[col27,col28,col29]=e8" \
    --entity="[col30,col31]=e9" \
    --rel="[e8,e9,col32,col33]=r2" \
    --rel="[e8,e8,col34]=r3"

echo "Done."
