# Integration testing (static verification only — not executed)

## Verified sources

- `doc/source/contributor/testing.rst` — test suites (Unit / Functional / Tempest) and run commands; Tempest tests are the public-API integration tests (`testing.rst:34-40`).
- `tox.ini` — `[testenv:functional]` with `OS_TEST_PATH = ./cinder/tests/functional`; `commands = ostestr {posargs}`.
- `cinder/tests/tempest/README.rst` — `tox -e all-plugin -- volume` plus example devstack `local.conf`.
- `cinder/tests/tempest/plugin.py` — `CinderTempestPlugin`; `setup.cfg` — `tempest.test_plugins = cinder_tests = cinder.tests.tempest.plugin:CinderTempestPlugin`.
- `test-requirements.txt` — `tempest>=16.1.0`; `tools/test-setup.sh` — local DB setup; `tools/hooks/run_multi_backend_matrix.sh` — Tempest multi-backend CI script.

## Real entry points (NOT executed)

- Functional: `tox -e functional` (OS_TEST_PATH=./cinder/tests/functional, ostestr).
- Tempest integration: `cd /opt/stack/tempest && tox -e all-plugin -- volume` (`cinder/tests/tempest/README.rst:13`); also `tox -e all-plugin` (`testing.rst:80-81`).
- DB preparation: `tools/test-setup.sh` (creates local MySQL/PostgreSQL `openstack_citest` with in-script credentials).

## Environment and credentials

Functional tests need a local DB prepared by `tools/test-setup.sh`. Tempest plugin tests require a full devstack deployment (`/opt/stack/tempest`, `etc/tempest.conf`); the repo ships only an example `local.conf`, not a reproducible environment or a credential retrieval method.

## Success criteria — GAP

The repo defines no acceptance criteria: no all-cases-pass rule, no empty/all-skipped exclusion, no aggregate gate or coverage thresholds, and no case-to-assertion mapping. `testing.rst` documents how to run suites but not what constitutes a pass.

## Gaps (readiness: pending)

1. No `success_criteria` / pass-fail gate defined.
2. Tempest integration target environment and credentials live outside the repo (devstack `/opt/stack/tempest`, `etc/tempest.conf`); no reproducible in-tree setup or credential source.
3. No IT case list / case-to-assertion mapping and no data cleanup or rollback guidance.

This is static verification only; no build, deploy, or test command was executed.
