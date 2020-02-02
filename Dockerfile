FROM returntocorp/sgrep:develop

ADD entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]