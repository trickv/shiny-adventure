syntax:
	python3 -m py_compile quick.py
	bash -n onboot
	bash -n ci
	bash -n post-to-hass
	bash -n sync-data
