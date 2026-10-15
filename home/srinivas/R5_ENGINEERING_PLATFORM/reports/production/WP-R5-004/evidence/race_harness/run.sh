#!/bin/bash
# $1 = package dir containing engineering_dispatcher
PY=/home/srinivas/.venvs/zerodha-phase1-r5/bin/python
rm -rf /home/srinivas/.r5_race_test/plat; mkdir -p /home/srinivas/.r5_race_test/plat
python3 - <<P
import json
json.dump({"platform_root":"/home/srinivas/.r5_race_test/plat","workers":{"claude":{"command":["/home/srinivas/.r5_race_test/bin/slow"]},"auditor":{"command":["true"],"enabled":False}},"auditor":{"enabled":False}},open("/home/srinivas/.r5_race_test/d.json","w"))
json.dump({"id":"RACE-1","type":"GENERAL","objective":"o","prompt":"p"},open("/home/srinivas/.r5_race_test/pkg.json","w"))
P
cd $1
$PY -m engineering_dispatcher.dispatcher --config /home/srinivas/.r5_race_test/d.json --submit /home/srinivas/.r5_race_test/pkg.json >/dev/null
$PY -m engineering_dispatcher.dispatcher --config /home/srinivas/.r5_race_test/d.json --once > /home/srinivas/.r5_race_test/A.out 2>&1 &
sleep 2
$PY -m engineering_dispatcher.dispatcher --config /home/srinivas/.r5_race_test/d.json --once > /home/srinivas/.r5_race_test/B.out 2>&1
wait
grep -c '"event": "START"' /home/srinivas/.r5_race_test/plat/logs/dispatcher.log | sed 's/^/START events: /'
grep -h '"event": "RECOVERED"\|UNEXPECTED_EXIT' /home/srinivas/.r5_race_test/plat/logs/dispatcher.log | cut -c1-140
cat /home/srinivas/.r5_race_test/A.out /home/srinivas/.r5_race_test/B.out | tr '\n' ' '; echo
