#!/usr/bin/env bash
# Kill any Flask/Python processes on ports 5000 and 5001.
# Usage: ./scripts/kill_flask.sh

PORTS=(5000 5001)

killed=0
for port in "${PORTS[@]}"; do
    while read -r pid; do
        comm=$(ps -p "$pid" -o comm= 2>/dev/null || true)
        if [[ "$comm" == *Python* || "$comm" == *python* || "$comm" == *flask* ]]; then
            kill "$pid" 2>/dev/null && echo "Killed PID $pid ($comm) on :$port" && ((killed++))
        fi
    done < <(lsof -ti :"$port" 2>/dev/null)
done

if [ "$killed" -eq 0 ]; then
    echo "No Flask server running on :${PORTS[*]}"
fi
