---
name: add-service-test
description: Add a new test case to an existing service test suite. Use when the user wants to add more integration tests to a service that already has test infrastructure set up via /setup-service-tests.
argument-hint: [flow-description]
---

# Add Service Test

Add a new test case to an existing service test suite in `ti-service-test`. This assumes `/setup-service-tests` has already been run and at least one test is passing.

## Input

`$ARGUMENTS` is an optional description of the flow to test (e.g., "create alert via pubsub", "patch endpoint with invalid data", "bulk update"). If not provided, suggest untested flows.

## Phase 1: Understand Existing Infrastructure

Read the current test directory to understand what's available:

1. **Find the test directory**: Look in the `ti-service-test` repo checkout (usually `~/code/ti-service-test/`; if it isn't there, find it or ask the user) for the service (user should be in the service test directory, or specify which service)
2. **Read existing tests**: What flows are already covered?
3. **Read conftest.py / utils/**: What fixtures, factories, clients, and mocks are available?
4. **Read kubernetes/settings.env**: What services are configured?
5. **Read kubernetes/kustomization.yaml**: What mock servers and dependencies are deployed?

## Phase 2: Identify the Flow to Test

If `$ARGUMENTS` is provided, use that as the target flow.

If not provided:
1. Read the source service repository to find endpoints/flows not yet tested
2. Present 3-5 suggestions to the user:
   - Prioritize: error handling paths, edge cases, flows touching multiple dependencies
   - Format: "Which flow should we test next?"
     - `POST /alerts` - create alert with all required fields
     - `PATCH /alerts/{id}` - update alert status (touches external alert service)
     - `PubSub create-alert` - async alert creation flow
     - Error case: invalid payload returns 400

## Phase 3: Generate the Test

Create a new test file following the established patterns.

### For Python:

**tests/test_<flow_name>.py**:
```python
import pytest
# Import existing fixtures from conftest

class TestFlowName:
    def test_happy_path(self, client, database, mock_client):
        # 1. Setup: create test data using factories/fixtures
        # 2. Mock: set up MockServer expectations for external calls this flow makes
        # 3. Execute: trigger the flow (API call, publish message, etc.)
        # 4. Assert: verify response AND side effects (DB state, published messages)
        pass

    def test_error_case(self, client, mock_client):
        # Test error handling (invalid input, dependency failure, etc.)
        pass
```

### For TypeScript:

**tests/<flow-name>.test.ts**:
```typescript
import { client } from "../utils/clients";
import { entityFactory } from "../utils/factories";
import { mockExternalServiceOnce } from "../utils/mocks";

describe("Flow Name", () => {
  // lifecycle hooks...

  it("happy path description", async () => {
    // 1. Setup
    // 2. Mock
    // 3. Execute
    // 4. Assert
  });

  it("error case description", async () => {
    // ...
  });
});
```

### Mock Expectations

If the new flow touches external services:

**Dynamic mocks** (set up in test code for one-time use):
```python
# Python
def setup_mock(mock_client, entity_id, response_data):
    mock_client.put("/expectation", json={
        "httpRequest": {"method": "GET", "path": f"/api/resource/{entity_id}"},
        "httpResponse": {"statusCode": 200, "body": response_data},
        "times": {"remainingTimes": 1, "unlimited": False},
    })
```

```typescript
// TypeScript
export const mockServiceOnce = async (id: string) => {
  await mockClient.put("/expectation", {
    httpRequest: { method: "GET", path: `/api/resource/${id}` },
    httpResponse: { statusCode: 200, body: { id, status: "active" } },
    times: { remainingTimes: 1, unlimited: false },
  });
};
```

**Static mocks** (add to `kubernetes/mock_data/*.json` for always-available responses):
- Use for endpoints that should always return the same thing (e.g., health checks, config endpoints)

## Phase 4: Update Infrastructure (If Needed)

If the new test flow touches a dependency not yet mocked:

1. Create new mock deployment YAML in `kubernetes/`
2. Add mock data JSON file in `kubernetes/mock_data/`
3. Update `kubernetes/kustomization.yaml` to include new resources
4. Add new env vars to `kubernetes/settings.env` (e.g., `NEW_SERVICE_URL=http://new-service-mock:5000`)
5. Update `docker-compose.yaml` with new mock service
6. Add new fixtures/clients in test utils if needed

## Phase 5: Update Existing Utilities

If the test needs new shared code:

- **New factory**: Add to existing `conftest.py` or `utils/factories.ts`
- **New mock helper**: Add to existing mock utilities
- **New client**: Add to existing client configuration
- **New fixture**: Add to `conftest.py`

Prefer extending existing files over creating new utility files.

## Phase 6: Output

After generating the test:
```
## Added Test: <test_name>

### Flow Tested:
<description of what this test validates>

### Files Modified:
- tests/test_<flow>.py (new)
- conftest.py (new fixture added, if any)
- kubernetes/kustomization.yaml (updated, if new dependency)

### Run:
cd <ti-service-test>/<service_slug>
docker compose up -d
poetry run pytest tests/test_<flow>.py -vv

### What This Validates:
1. <specific assertion about behavior>
2. <specific assertion about side effects>
```

## Guidelines

- Each test file should test ONE flow/endpoint
- Include both happy path and at least one error case
- Generate realistic mock data that matches actual API contracts
- Reuse existing fixtures and utilities - don't duplicate
- Test side effects (DB writes, published messages) not just HTTP responses
- Use descriptive test names that explain the scenario
- Keep tests independent - each test should clean up after itself
