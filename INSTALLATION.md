# Installation Guide

## Quick Install

Install the ti-plugin directly from GitHub:

```bash
/plugin install https://github.com/sganot-r7/ti-claude-plugin
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

## Usage

### Generate Service Test Infrastructure

```bash
/ti-plugin:setup-service-tests /Users/sganot/code/ti-my-service
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
/plugin update ti-plugin
/reload-plugins
```

## Local Development

To test plugin changes locally:

```bash
claude --plugin-dir /Users/sganot/code/ti-plugin
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
- Try reinstalling: `/plugin uninstall ti-plugin` then `/plugin install ...`

### Skills not appearing
- Run `/reload-plugins` after installation
- Restart Claude Code CLI
- Check plugin is listed in `/plugin list`

### Skills not executing correctly
- Ensure ti-service-test repository is at `/Users/sganot/code/ti-service-test`
- Verify Python/Poetry is installed
- Check Docker is running (for generated tests)

## Support

- GitHub Issues: https://github.com/sganot-r7/ti-claude-plugin/issues
- Repository: https://github.com/sganot-r7/ti-claude-plugin
