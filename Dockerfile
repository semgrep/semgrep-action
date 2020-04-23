FROM returntocorp/semgrep:develop

ADD entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]