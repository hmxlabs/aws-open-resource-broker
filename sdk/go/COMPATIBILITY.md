# Compatibility Matrix

| orb-go | orb-py | Notes |
|--------|--------|-------|
| v1.5.2 | v1.5.2 | Current release |
| v1.2.2 | v1.2.2 | Initial release |

## Release Automation

When orb-py ships a new release, it should trigger orb-go's sync workflow via repository dispatch:

```bash
# From orb-py CI (add to orb-py's release workflow):
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/awslabs/orb-go/dispatches \
  -d '{"event_type":"orb-py-release","client_payload":{"version":"1.2.3"}}'
```

The orb-go sync workflow will:
1. Export the new OpenAPI spec from the new orb-py version
2. Update `MinCompatibleVersion` in `orb/version.go`
3. Open a PR for human review
4. After merge → automatically create git tag and GitHub Release
