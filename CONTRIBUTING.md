<!-- Copyright 2026 Loreum Digital Inc. SPDX-License-Identifier: Apache-2.0 -->

# Contributing

Thanks for helping improve the RetiQo examples.

## Before you open a pull request

- Run `pipenv run test` (or `pytest` inside `pipenv shell`). Every example must pass offline.
- If you change the memory model in `examples/common/ledger.py`, run `pipenv run sync-schemas` and commit the updated `schema.scd` files.
- If you add a dependency, use `pipenv install <package>` and commit both `Pipfile` and `Pipfile.lock`.
- Start every new file with the copyright header used in the existing files:
  ```
  # Copyright 2026 Loreum Digital Inc
  # SPDX-License-Identifier: Apache-2.0
  ```
- Keep examples fictional. Never commit real company data, credentials, application or agent IDs, account numbers, `.env`, or anything in `.retiqo/`.

## Adding an example

1. Create `examples/<name>/` with `main.py`, `schema.scd` and `README.md`.
2. Put the domain classes in `schema.scd`, then run `pipenv run sync-schemas` to add the memory classes.
3. In `main.py`, describe the scenario as data with `Scenario` and `Rule` from `examples/common/loop.py`: the cases, the reviewers, and for each rule how a violation is detected, what is learned, when a lesson applies and how the plan is fixed. Keep it runnable with `--offline`.
4. Add the example to `tests/test_examples_offline.py` and to the tables in the top-level README.

By contributing, you agree that your contributions are licensed under the Apache License 2.0.
