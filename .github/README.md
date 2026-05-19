# GitHub Actions

Jobs in `.github/workflows/` must set:

```yaml
runs-on: blacksmith-2vcpu-ubuntu-2404
```

Do not use GitHub-hosted Ubuntu runners (`ubuntu-latest`, `ubuntu-24.04`, …) or larger Blacksmith SKUs (`blacksmith-4vcpu-*`, …) unless you change the allowed label in `scripts/check_workflow_runners.py` and update this section.

Composite actions under `.github/actions/` do not use `runs-on`.
