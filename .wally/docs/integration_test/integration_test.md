# Integration testing

## Sources and scope

Static verification only: no test command was executed. Sources: `README.rst`, `tox.ini`, `.testr.conf`, `setup.cfg`, `test-requirements.txt`, `bindep.txt`, `doc/source/contributor/testing.rst`, `doc/source/contributor/jenkins.rst`, `cinder/tests/README.rst`, `cinder/tests/tempest/README.rst`, `tools/test-setup.sh`.

## Runner and entrypoint

`tox.ini` defines the real runners: `tox` (unit tests via `ostestr`), `tox -e functional` (functional tests with `OS_TEST_PATH=./cinder/tests/functional`), and `tox -e all-plugin -- volume` for the in-tree Tempest plugin (`tempest.test_plugins = cinder_tests` in `setup.cfg`). The IT command recorded in `.wally/config.json` is the Tempest volume plugin command, run from a Tempest checkout with the plugin installed. Functional tests are a related but separate suite and are not a substitute for end-to-end IT. `tools/test-setup.sh` prepares MySQL/PostgreSQL test databases used by unit/functional tests and uses hard-coded `openstack_citest` credentials.

## Environment, configuration, and data

Tempest requires an external checkout (documented example `/opt/stack/tempest`) against a devstack deployment with Cinder enabled; `cinder/tests/tempest/README.rst` provides a sample `local.conf` (noauth is not used there). Some unit/functional tests need a local database set up by `tools/test-setup.sh`. No secure credential acquisition method, pinned Cinder/Tempest/devstack versions, configured service endpoints, or target environment are defined in this repository. Do not invent commands, access, or successful results.

## Assertions, results, and cleanup

For six-step tasks design cases in Plan, execute after deployment, and record individual results plus aggregate gates in the task's IT artifact. Assertions must exercise real integration boundaries through public APIs. Distinguish assertion failures, environment errors, and execution errors; empty or all-skipped runs are not passes. Record command, code version, test/request identifiers, output, and conclusion; clean up created volumes and restore test data. For defect/performance A/B retain comparable before/after evidence and limits. Keep all six phases.

## Gaps

Pending in `.wally/config.json`: no configured Tempest/devstack target environment or endpoint; no secure credential source (only a hard-coded `local.conf` sample); no pinned versions or repository-defined aggregate IT gate thresholds beyond a successful run. Marked BLOCKED, not automatically skipped; a guide path alone does not activate the phase.
