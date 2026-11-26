# Integration testing - static verification

Status: `pending`. This is a static review of repository files only; no build, deploy, or test command was executed.

## Sources inspected

- `doc/source/contributor/testing.rst`: defines Unit, Functional, and Tempest suites; `tox` is the preferred runner.
- `tox.ini`: `[testenv:functional]` sets `OS_TEST_PATH=./cinder/tests/functional`.
- `setup.cfg`: registers the in-tree Tempest plugin via `tempest.test_plugins`.
- `cinder/tests/tempest/README.rst`: Tempest plugin command and a sample devstack `local.conf`.
- `tools/test-setup.sh`: local MySQL/PostgreSQL database setup used by CI.

## Real entrypoints (not executed)

- Functional suite from the repository root: `tox -e functional`. It runs with a database present, may start Cinder services, and should not need other non-Cinder OpenStack services.
- Tempest plugin integration suite: from a Tempest checkout with this project installed, `tox -e all-plugin -- volume` (the README example uses `cd /opt/stack/tempest && tox -e all-plugin -- volume`). It requires a running devstack with Nova/Glance/Keystone and discovery of the Cinder plugin.
- Functional tests that use a local database follow `tools/test-setup.sh`.

## Success criteria (not defined in the repository)

A concrete gate must be supplied by the task or environment owner. The repository defines test runners only: no IT case list, assertion set, pass thresholds, cleanup, or evidence location is configured. A generic tox exit status is not a documented acceptance gate.

## Gaps (readiness: pending)

1. No integration-test target environment is configured in this workspace; the Tempest suite needs an external Tempest checkout and a running devstack, neither present here.
2. No `tempest.conf` or credential acquisition path is provided; `cinder/tests/tempest/README.rst` only contains a sample devstack `local.conf` with placeholder passwords.
3. The functional suite requires a prepared database (`tools/test-setup.sh`) and may start Cinder services; no such prepared environment is available.
4. No explicit IT success criteria, thresholds, cleanup, or evidence location is defined; empty or all-skipped runs must not be treated as a pass.
