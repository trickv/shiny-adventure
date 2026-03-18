syntax:
	python3 -m py_compile obd-logger
	python3 -m py_compile battery.py
	python3 -m py_compile charging_status.py
	python3 -m py_compile battery-check
	python3 -m py_compile pisugar-poweroff
	python3 -m py_compile coolant-display
	python3 -m py_compile server/import-to-sqlite
	bash -n onboot
	bash -n update
	bash -n post-to-hass
	bash -n sync-data
	bash -n install
