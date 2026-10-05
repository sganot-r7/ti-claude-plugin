# TI Service Test Plugin

A Claude Code plugin for generating comprehensive service test infrastructure for microservices. This plugin provides automated test scaffolding with Kubernetes manifests, MockServer configurations, database setups, and emulators.

## Overview

This plugin contains skills for creating and maintaining integration test suites, plus read-only skills for searching prod ES logs and Firestore:

1. **setup-service-tests**: Generates complete test infrastructure from scratch
2. **add-service-test**: Adds new test cases to existing test suites

The generated tests use:
- **Kubernetes/k3d** for test environments
- **MockServer** for HTTP service mocking
- **Emulators** for GCP services (Pub/Sub, GCS, Firestore)
- **MongoDB/PostgreSQL** for database testing
- **Tilt** for local development
- **Docker Compose** for simplified local testing

## Prerequisites

Before using this plugin, ensure you have:

- [ti-service-test](https://github.com/Intsights/ti-service-test) repository cloned locally (e.g. `~/code/ti-service-test`)
- Python 3.9+ with Poetry installed
- Docker and Docker Compose
- k3d (for local Kubernetes testing)
- Tilt (optional, for enhanced local development)

## Installation

### From GitHub

```bash
# Add the marketplace, then install the plugin
/plugin marketplace add https://github.com/sganot-r7/ti-claude-plugin.git
/plugin install ti-plugin@ti-plugin-marketplace

# Reload plugins
/reload-plugins
```

### Local Development

```bash
# Test the plugin locally without installing
claude --plugin-dir ~/code/ti-claude-plugin
```

## Skills

### 1. setup-service-tests

Generates complete service test infrastructure for a microservice.

**Usage:**
```bash
/ti-plugin:setup-service-tests <service-repo-path>
```

**Example:**
```bash
/ti-plugin:setup-service-tests ~/code/ti-my-service
```

**What it does:**
1. Analyzes the target service to identify:
   - Language and framework (Node.js/Python, Express/NestJS/FastAPI/Flask)
   - API endpoints and routes
   - External service dependencies
   - Database requirements (MongoDB, PostgreSQL)
   - Message queues (Pub/Sub)
   - Entity schemas

2. Runs the templater tool to generate base scaffolding:
   ```bash
   python -m templater generate --service-name <service-name> --lang python --provider gcp
   ```

3. Creates additional infrastructure:
   - Kubernetes manifests (deployments, services, ConfigMaps)
   - MockServer configurations for external dependencies
   - Database deployments (MongoDB/PostgreSQL)
   - Emulator setups (Pub/Sub, GCS, Firestore)
   - Environment configuration files
   - Mock data JSON files

4. Generates test code:
   - Python tests with pytest (default for Python services)
   - TypeScript tests with Jest (optional for JS/TS services)
   - Shared fixtures and utilities (conftest.py or utils/)
   - One working test case

5. Creates local development files:
   - `docker-compose.yaml` for Docker-based testing
   - `Tiltfile` for k3d-based testing

**Output structure:**
```
ti-service-test/ti_service_name/
├── Dockerfile
├── Tiltfile
├── Tiltfile-common
├── pyproject.toml
├── docker-compose.yaml
├── kubernetes/
│   ├── kustomization.yaml
│   ├── base/
│   │   ├── <service-name>.yaml
│   │   ├── service-test-pod.yaml
│   │   ├── kustomization.yaml
│   │   └── settings.env
│   ├── mock_data/
│   │   └── *.json
│   ├── *-mock.yaml
│   ├── mongo.yaml
│   └── pubsub-emulator.yaml
└── tests/
    ├── conftest.py
    └── test_*.py
```

### 2. add-service-test

Adds a new test case to an existing service test suite.

**Usage:**
```bash
/ti-plugin:add-service-test [flow-description]
```

**Examples:**
```bash
# Add test for a specific flow
/ti-plugin:add-service-test "create alert via pubsub"

# Get suggestions for untested flows
/ti-plugin:add-service-test
```

**What it does:**
1. Analyzes existing test infrastructure to understand:
   - Available fixtures and factories
   - Configured mock servers
   - Database connections
   - Testing patterns

2. Identifies the flow to test (from user input or suggests untested flows)

3. Generates a new test file with:
   - Happy path test case
   - Error handling test cases
   - Mock expectations for external services
   - Database assertions for side effects

4. Updates infrastructure if needed:
   - Adds new mock deployments for previously unmocked dependencies
   - Creates new mock data JSON files
   - Updates environment variables
   - Extends shared utilities (fixtures, factories, clients)

**Test structure:**
```python
# Python example
class TestFlowName:
    def test_happy_path(self, client, database, mock_client):
        # Setup test data
        # Configure mocks
        # Execute flow
        # Assert response and side effects
        pass

    def test_error_case(self, client):
        # Test error handling
        pass
```

### 3. searching-es-logs

Read-only search of prod logs in the `logs-elasticsearch` cluster (Kibana: logs-kibana.prod.internal.ti.r7ops.com).
Claude uses it automatically when you ask about prod logs, errors, or trace IDs.

**Setup (once, and again whenever the cookie expires):** open Kibana in the browser (VPN/WARP on), copy the
`CF_Authorization`, `CF_AppSession` and `sid` cookies from DevTools → Application → Cookies, then ask Claude to
search ES logs. When the cookie is missing or expired, Claude stops and gives you the exact
`! pbpaste | python3 .../set_cookie.py` command to run.
The cookie is saved to `~/.config/es-logs/cookie` (mode 600).

### 4. searching-firestore

Read-only Firestore lookups (GET, runQuery, aggregation count only) over the REST API.
Claude uses it automatically when you ask about Firestore docs or collections (e.g. `domains_queries_v2`).

**Setup:** `gcloud auth login` with an account that can read the project.

> ⚠️ The default project is **`intsights` (prod)**;
set `FS_PROJECT=intsights-dev-2` (or ask Claude to use dev) to change it.

## Testing Your Plugin Changes

After making modifications to the plugin:

```bash
# Test locally
cd ~/code
claude --plugin-dir ./ti-claude-plugin

# Verify skills are loaded
/skills

# Test setup-service-tests
/ti-plugin:setup-service-tests /path/to/test-service

# Test add-service-test
/ti-plugin:add-service-test "test flow description"
```

## Running Generated Tests

### With Docker Compose (Recommended for quick testing)

```bash
cd ~/code/ti-service-test/<service_slug>

# Start infrastructure
docker compose up -d

# Run tests
poetry run pytest tests/ -vv

# Cleanup
docker compose down
```

### With Tilt (Full Kubernetes environment)

```bash
cd ~/code/ti-service-test/<service_slug>

# Start Tilt
tilt --namespace=<service-name> up

# Tests run automatically in the test pod
# View logs in Tilt UI at http://localhost:10350
```

## CI Integration

Generated tests integrate automatically with CI when:
- The service repository has a workflow that triggers ti-service-test
- The test folder name matches the service repository name (hyphens converted to underscores)

## Development

### Plugin Structure

```
ti-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/
│   ├── setup-service-tests/
│   │   └── SKILL.md
│   └── add-service-test/
│       └── SKILL.md
└── README.md
```

### Modifying Skills

Skills are written in Markdown with YAML frontmatter:

```markdown
---
name: skill-name
description: When Claude should use this skill
argument-hint: [optional-argument]
---

# Skill Instructions

Instructions for Claude to follow...
```

### Publishing Updates

```bash
# Commit changes
git add .
git commit -m "Update skill instructions"

# Push to GitHub
git push origin main

# Users can update with
/plugin marketplace update ti-plugin-marketplace
/plugin update ti-plugin@ti-plugin-marketplace
```

## Support

For issues or questions:
- Check the [ti-service-test documentation](https://github.com/Intsights/ti-service-test)
- Review existing test examples in ti-service-test repository
- File issues on the [plugin repository](https://github.com/sganot-r7/ti-claude-plugin/issues)

## License

MIT
