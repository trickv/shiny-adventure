syntax:
	python3 -m py_compile quick.py
	python3 -m py_compile battery.py
	python3 -m py_compile charging_status.py
	python3 -m py_compile server/import-to-sqlite
	bash -n onboot
	bash -n ci
	bash -n post-to-hass
	bash -n sync-data
