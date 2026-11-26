# Test environment deployment

## Sources and scope

Static verification only: no build, deployment, or test command was executed. Sources: `README.rst`, `HACKING.rst`, `tox.ini`, `setup.cfg`, `.testr.conf`, `bindep.txt`, `doc/source/contributor/testing.rst`, `contrib/block-box/README.md`, `contrib/block-box/Makefile`, `contrib/block-box/docker-compose.yml`, `contrib/block-box/cinder.rc`, `contrib/block-box/init-scripts/cinder-api.sh`, `contrib/block-box/docker-entrypoint-initdb.d/script.sql`.

## Prerequisites and authorization

Working directory: `contrib/block-box`. Requires Docker and Docker Compose, network access to build the loci-based base image, and a Linux host with LVM/iSCSI available for `cinder-lvm` (pre-existing volume group required per `README.md`). No target test environment, owner, or authorization boundary is defined in the repository; `contrib/block-box` is a containerized development example. Credentials are hard-coded sample values (`MYSQL_ROOT_PASSWORD=password`, cinder/password in `script.sql`, noauth values in `cinder.rc`) and are not a secure source.

## Build, synchronize, and deploy

Documented sequence: `cd contrib/block-box && make base && make lvm && docker-compose up -d`.

- `make base` builds `cinder:latest` from `https://git.openstack.org/openstack/loci-cinder.git#:debian` with `CINDER_BRANCH` (default `master`); `PLATFORM` and `TAG` are Makefile variables.
- `make lvm` builds `cinder-lvm` from `docker_files/Dockerfile.cinder-lvm` (lvm2, tgt, udev/LVM settings).
- `docker-compose up -d` starts mariadb, rabbitmq, cinder-api (runs `cinder-manage db sync` via `INIT_DB=true`), cinder-scheduler and cinder-volume; services use `network_mode: host` and static IPs.
- Optional extra backend: `docker-compose -f ./docker-compose-add-vol-service.yml up -d`. `make devbox` builds a development image and is not part of service deployment.

## Verification

`docker-compose ps` should show all services running; a volume list against the noauth endpoint `http://127.0.0.1:8776/v3` should succeed with `OS_AUTH_TYPE=noauth`, `CINDER_ENDPOINT`, `OS_PROJECT_ID` and `OS_USERNAME`. Note `cinder.rc` uses the older `OS_AUTH_SYSTEM` name instead of `OS_AUTH_TYPE`; confirm against the installed python-cinderclient. No effective-version check is defined. This is not evidence of execution.

## Failure and rollback

No rollback or version-restore procedure/command is documented in the repository. Stack teardown, image-tag restoration, and data cleanup must be defined by the environment owner; do not guess commands. Record environment retention/release ownership and actual results at execution time.

## Gaps

Pending in `.wally/config.json`: no dedicated test-environment target/owner/authorization; no secure credential source; no rollback/version-restore or effective-version check; loci base-image source may be unavailable; no deployment acceptance criteria. Marked BLOCKED, not automatically skipped; a guide path alone does not activate the phase.
