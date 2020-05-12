release:
	@echo "Releasing semgrep-action"
	git tag --force v1
	git push --tags --force
