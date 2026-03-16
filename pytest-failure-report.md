# Pytest Failure Report

Run on March 13, 2026 with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q --tb=short
```

Result:

- `459 failed`
- `147 errors`
- `1435 passed`
- `129 skipped`

This report groups the failures by likely root cause rather than listing all 600+ individually.

## 1. Domain Model / Test Contract Drift

This is the largest "expected behavior changed" bucket. The tests are still constructing aggregates and exceptions using older signatures and looser models.

Representative failures:

- [tests/unit/domain/test_machine_aggregate.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_machine_aggregate.py)
- [tests/unit/domain/test_request_aggregate.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_request_aggregate.py)
- [tests/unit/domain/test_template_aggregate.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_template_aggregate.py)
- [tests/unit/domain/test_business_rules.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_business_rules.py)

Examples:

- `Machine(...)` tests pass raw strings or omit now-required fields like `provider_type` and `image_id`.
- `Request.create_new_request(...)` tests still pass `requester_id`, but the current factory expects `request_id` and provider-selection-driven fields instead.
- `Request.create_return_request(...)` tests still pass `machine_ids=...` as a keyword the factory no longer accepts.
- Template tests still expect validation on fields like `max_number` and older exception constructors.

Assessment:

- Mostly stale tests, not evidence of a new regression.
- The repo’s domain objects have clearly moved toward stricter Pydantic/value-object validation and different factory signatures.

High-volume files:

- `31` failures in [tests/unit/domain/test_business_rules.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_business_rules.py)
- `30` failures in [tests/unit/domain/test_request_aggregate.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_request_aggregate.py)
- `25` failures in [tests/unit/domain/test_machine_aggregate.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_machine_aggregate.py)
- `11` failures in [tests/unit/domain/test_template_aggregate.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/domain/test_template_aggregate.py)

## 2. Provider Strategy / Context Contract Drift

A large cluster of tests is written against older provider-strategy abstractions.

Representative failures:

- [tests/providers/base/strategy/test_provider_context.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/base/strategy/test_provider_context.py)
- [tests/providers/base/strategy/test_provider_context_edge_cases.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/base/strategy/test_provider_context_edge_cases.py)
- [tests/providers/base/strategy/test_provider_context_integration.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/base/strategy/test_provider_context_integration.py)
- [tests/test_provider_strategy_examples.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/test_provider_strategy_examples.py)

Examples:

- Mock strategies fail to instantiate because the abstract base now requires `generate_provider_name`, `get_provider_name_pattern`, and `parse_provider_name`.
- Some tests call async strategy/context methods as if they were synchronous and then try to read `.success` from a coroutine.
- One test expects a `provider_context` fixture that no longer exists.

Assessment:

- Mostly stale tests caused by provider-strategy interface evolution.
- The failures are broad and consistent enough that this looks like test maintenance, not one isolated implementation bug.

High-volume files:

- `21` failures/errors in [tests/providers/base/strategy/test_provider_context.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/base/strategy/test_provider_context.py)
- `11` failures in [tests/providers/base/strategy/test_provider_context_edge_cases.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/base/strategy/test_provider_context_edge_cases.py)
- `21` failures/errors in [tests/test_provider_strategy_examples.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/test_provider_strategy_examples.py)

## 3. DI / Registry / Storage Registration Problems

This bucket looks like a mix of real wiring issues and tests written against old constructor contracts.

Representative failures:

- [tests/unit/infrastructure/di/test_dependency_resolver.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/infrastructure/di/test_dependency_resolver.py)
- [tests/unit/infrastructure/test_storage_registration.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/infrastructure/test_storage_registration.py)
- [tests/unit/infrastructure/test_configuration_manager.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/infrastructure/test_configuration_manager.py)
- [tests/integration/test_bootstrap_integration.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/integration/test_bootstrap_integration.py)

Examples:

- `DependencyResolver.__init__()` now requires `container`, but tests still construct it with the old argument list.
- SQL storage is being re-registered repeatedly: `Type 'sql' is already registered`.
- Later tests then fail because JSON storage is not registered: `Type 'json' is not registered`.
- Bootstrap tests pass mocked path/config objects that now flow into `os.path.join(...)`, which fails on `Mock`.

Assessment:

- Mixed bucket.
- The constructor-signature failures are test drift.
- The repeated storage-registration/global-state failures look like a real test-isolation problem, and possibly a real registration lifecycle issue.

High-volume files:

- `33` failures in [tests/unit/infrastructure/test_configuration_manager.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/infrastructure/test_configuration_manager.py)
- `27` errors in [tests/unit/infrastructure/di/test_dependency_resolver.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/infrastructure/di/test_dependency_resolver.py)
- `17` failures in [tests/unit/infrastructure/test_storage_registration.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/infrastructure/test_storage_registration.py)

## 4. API/Auth Failure Cascade

This looks like a real bug.

Representative failures:

- [tests/integration/api/test_api_endpoints.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/integration/api/test_api_endpoints.py)
- [tests/integration/api/test_authentication_flows.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/integration/api/test_authentication_flows.py)
- [tests/security/test_auth_security.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/security/test_auth_security.py)

Observed pattern:

- Auth middleware logs the expected `401`-class problem.
- Then exception handling fails with `Object of type datetime is not JSON serializable`.
- The test ends up seeing `500: Authentication service error` instead of the intended auth failure response.

Assessment:

- Real implementation problem, not just stale tests.
- The auth path itself may be fine, but the exception/response serialization path is broken and masks the expected behavior.

High-volume files:

- `8` failures in [tests/security/test_auth_security.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/security/test_auth_security.py)
- `3` failures across the API auth integration files listed above

## 5. Live / OnAWS Environment Assumptions

These are environment/setup failures, not local logic regressions.

Representative failures:

- [tests/onaws/test_onaws.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/onaws/test_onaws.py)
- [tests/onaws/test_rest_api_onaws.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/onaws/test_rest_api_onaws.py)

Observed pattern:

- `FileNotFoundError: AWS provider templates not found: config/awsprov_templates.json`

Assessment:

- Expected environment failure.
- These tests assume checked-in AWS HostFactory template material or a live AWS-oriented setup that is not present in this workspace.

Volume:

- `52` errors in [tests/onaws/test_onaws.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/onaws/test_onaws.py)
- `5` errors in [tests/onaws/test_rest_api_onaws.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/onaws/test_rest_api_onaws.py)

## 6. AWS Test Contract Drift

A separate chunk of AWS tests is failing because AWS domain/config objects have become stricter.

Representative failures:

- [tests/unit/providers/aws/test_launch_template_manager.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/providers/aws/test_launch_template_manager.py)
- [tests/providers/aws/test_aws_validation_adapter.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/aws/test_aws_validation_adapter.py)

Examples:

- `AWSTemplate(...)` setup in launch-template-manager tests omits `provider_api`, which is now required.
- AWS validation-adapter fallback tests appear to assume older config-manager fallback behavior.

Assessment:

- Mostly stale tests / constructor drift.
- Not obviously caused by your Azure work.

Volume:

- `18` errors in [tests/unit/providers/aws/test_launch_template_manager.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/unit/providers/aws/test_launch_template_manager.py)

## 7. AWS Moto / Feature-Gap Failures

This looks like a real test-environment or mock-support limitation.

Representative failures:

- [tests/providers/aws/test_botocore_metrics.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/aws/test_botocore_metrics.py)

Observed pattern:

- `The modify_fleet action has not been implemented`

Assessment:

- Likely a Moto support gap rather than a regression in ORB itself.
- Could also indicate the tests now exercise an API path that the mock layer does not support.

Volume:

- `16` failures in [tests/providers/aws/test_botocore_metrics.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/aws/test_botocore_metrics.py)

## 8. Native Spec / Template Context Drift

These failures look like expectation drift around how templates/defaults/context variables are rendered.

Representative failures:

- [tests/config/test_template_defaults.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/config/test_template_defaults.py)
- [tests/integration/test_native_spec_all_providers.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/integration/test_native_spec_all_providers.py)

Examples:

- Test still expects `max_number`; code now normalizes to `max_instances`.
- A native-spec test still sees literal `{{ request_id }}` instead of a rendered request ID.

Assessment:

- Mixed bucket.
- `max_number` is clearly test drift.
- Unrendered context variables may be a real implementation regression.

## 9. Missing Fixtures / Test Harness Drift

Some tests fail before reaching product code because their shared fixtures are gone or renamed.

Representative failures:

- [tests/test_logging_integration.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/test_logging_integration.py)
- [tests/providers/base/strategy/test_provider_context.py](/Users/ikemilian-lewis/Software/open-resource-broker/tests/providers/base/strategy/test_provider_context.py)

Examples:

- `fixture 'complete_test_environment' not found`
- `fixture 'provider_context' not found`

Assessment:

- Test harness drift, not product-code behavior.

## Prioritization

If the goal is to reduce the failure count quickly and meaningfully, I would tackle them in this order:

1. API/auth exception serialization bug
2. DI/storage registration and bootstrap state leakage
3. Provider strategy / context contract updates in tests
4. Domain aggregate test drift
5. AWS launch template test drift
6. OnAWS environment-dependent tests

## Likely Impact of Recent Azure Work

Very little of this failure set looks Azure-specific.

The Azure-focused tests are now passing separately. Most of the remaining red tests are in:

- old domain aggregate tests
- provider context / strategy examples
- bootstrap/DI/storage registration
- API auth/security
- AWS/onaws-specific suites

