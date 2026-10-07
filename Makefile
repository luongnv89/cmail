.PHONY: test lint

test:
	@bash scripts/test.sh

lint:
	@shellcheck -x cmail lib/*.sh install.sh scripts/*.sh completions/cmail.bash
