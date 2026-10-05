# Installation Guide

## Quick Install

Add the marketplace from GitHub, then install the plugin:

```bash
/plugin marketplace add https://github.com/sganot-r7/ti-claude-plugin.git
/plugin install ti-plugin@ti-plugin-marketplace
/reload-plugins
```

## Verify Installation

Check that the skills are loaded:

```bash
/skills
```

You should see:
- `ti-plugin:setup-service-tests`
- `ti-plugin:add-service-test`
- `ti-plugin:searching-es-logs` (read-only prod ES logs; needs VPN/WARP + Kibana cookie, see README)
- `ti-plugin:searching-firestore` (read-only Firestore; needs `gcloud auth login`, defaults to prod `intsights`)

## Usage

### Generate Service Test Infrastructure

```bash
/ti-plugin:setup-service-tests ~/code/ti-my-service
```

This will:
1. Analyze your service repository
2. Generate complete test infrastructure
3. Create Kubernetes manifests
4. Set up MockServer configurations
5. Generate test code (Python or TypeScript)
6. Create docker-compose.yaml and Tiltfile

### Add New Test Cases

After initial setup, add more tests:

```bash
# Add test for specific flow
/ti-plugin:add-service-test "create alert via pubsub"

# Get suggestions for untested flows
/ti-plugin:add-service-test
```

## Updating the Plugin

To get the latest version:

```bash
/plugin marketplace update ti-plugin-marketplace
/plugin update ti-plugin@ti-plugin-marketplace
/reload-plugins
```

## Local Development

To test plugin changes locally:

```bash
claude --plugin-dir ~/code/ti-claude-plugin
```

## Uninstall

To remove the plugin:

```bash
/plugin uninstall ti-plugin
```

## Troubleshooting

### Plugin not found
- Verify the GitHub repository is accessible
- Check your network connection
- Try reinstalling: `/plugin uninstall ti-plugin` then `/plugin install ti-plugin@ti-plugin-marketplace`

### Skills not appearing
- Run `/reload-plugins` after installation
- Restart Claude Code CLI
- Check plugin is listed in `/plugin list`

### Skills not executing correctly
- Ensure the [ti-service-test](https://github.com/Intsights/ti-service-test) repository is cloned locally (e.g. `~/code/ti-service-test`)
- Verify Python/Poetry is installed
- Check Docker is running (for generated tests)

## Support

- GitHub Issues: https://github.com/sganot-r7/ti-claude-plugin/issues
- Repository: https://github.com/sganot-r7/ti-claude-plugin
