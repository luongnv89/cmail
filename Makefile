.PHONY: build test lint install

build:
	@cargo build --release --locked

test:
	@bash scripts/test.sh

lint:
	@cargo fmt --check
	@cargo clippy --all-targets --locked -- -D warnings
	@shellcheck -x install.sh scripts/*.sh tests/install_test.sh

install:
	@cargo install --path . --locked
