# Test environment deployment (static verification only — not executed)

## Verified sources

- `contrib/block-box/README.md` — build/run/access, noauth mode.
- `contrib/block-box/Makefile` — `all: base lvm devbox`; `make base`, `make lvm`, `make devbox`; PLATFORM/CINDER_BRANCH/TAG variables.
- `contrib/block-box/docker-compose.yml` — services rabbitmq, mariadb, cinder-api, cinder-scheduler, cinder-volume; network 172.49.49.0/24; API port 8776.
- `contrib/block-box/docker-compose-add-vol-service.yml` — optional extra backend.
- `contrib/block-box/init-scripts/cinder-api.sh` — `cinder-manage db sync` then `cinder-api -d`.
- `contrib/block-box/cinder.rc` — noauth credentials; `contrib/block-box/etc-cinder/cinder.conf` — service config.

## Target environment

Standalone containerized Cinder via Docker Compose, working directory `contrib/block-box`. noauth mode (no Keystone), API `http://127.0.0.1:8776/v3`. Images built from OpenStack LOCI (`debian`/`ubuntu`/`centos` via Makefile `PLATFORM`).

## Build, synchronize, deploy (real commands; NOT executed)

```
cd contrib/block-box
make                       # all: base lvm devbox; external storage only needs `make base`
docker-compose up -d
```

Optional extra backend: `docker-compose -f ./docker-compose-add-vol-service.yml up -d`.
Modify `etc-cinder/cinder.conf` for the target driver before starting; LVM image requires the configured volume group to pre-exist on the host.

## Credentials

`contrib/block-box/cinder.rc`: `OS_AUTH_SYSTEM=noauth`, `CINDER_ENDPOINT=http://127.0.0.1:8776/v3`, `OS_PROJECT_ID`, `OS_USERNAME`, `OS_VOLUME_API_VERSION=3.27`. DB root password is set inline in `docker-compose.yml`. No secrets are read from a vault/managed source.

## Verify (real example, not a pass criterion)

`docker run -it -e OS_AUTH_TYPE=noauth -e CINDERCLIENT_BYPASS_URL=http://cinder-api:8776/v3 -e OS_PROJECT_ID=foo -e OS_VOLUME_API_VERSION=3.27 --network blockbox_default cinderclient list` (`README.md:157-161`). The repo defines no health/readiness endpoint, effective-version check, or expected-result pass criterion.

## Failure and rollback — GAP

No rollback entry exists in the repository: README, Makefile, compose files and init-scripts contain no `docker-compose down`, image/version revert, or data cleanup command. Must be supplied by the environment owner before Deploy is ready.

## Gaps (readiness: pending)

1. No real rollback command (see above).
2. No deployment acceptance criteria (health/readiness, effective-version verification, expected results).
3. No test-environment identifier/owner, authorization boundary, or retention/release agreement.

This is static verification only; no build, deploy, or test command was executed.
