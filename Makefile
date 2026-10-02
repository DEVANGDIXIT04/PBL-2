.PHONY: run test lint seed train evaluate migrate

run test lint seed train evaluate migrate:
	$(MAKE) -C pfm $@
