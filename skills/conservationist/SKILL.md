---
name: conservationist
description: Expert usage of conservationist-client CLI for managing conda environment definitions
---

# conservationist-client CLI

Tool for building and managing conda-based application environment definitions. Creates fully pinned, reproducible conda environments.

## Key Concepts

| Term | Definition |
|------|------------|
| **Ecology** | Collection of package match specifications + metadata for building environment definitions |
| **Environment Definition (envdef)** | Fully pinned list of packages that creates identical conda environments |
| **Package Match Specification** | String conda understands to identify candidate packages (e.g., `python>=3.9`) |
| **Variant** | Named set of additional package specs applied at envdef creation time |
| **Tag** | Named reference to a specific envdef identifier within an ecology |

## Setup

### Environment

Run all commands via micromamba:

```sh
micromamba run -n cp314 conservationist-client --help
```

For brevity, examples below omit the prefix. Always prepend:
```sh
micromamba run -n cp314 <command>
```

### API Configuration

Configure the API URL (production instance):

```sh
export CONSERVATIONIST_API=https://conservationist.chip.gts.drw/
```

Or pass `--api <URL>` to each command.

## Common Commands

### Ecology Operations

```sh
# List all ecologies
conservationist-client ecology list

# Create ecology with package specs
conservationist-client ecology create <name> <pkg1> <pkg2> ...

# Read ecology details (shows tags, variants, envdefs)
conservationist-client ecology read <name>

# Update ecology (add tags, variants, etc.)
conservationist-client ecology update <name> '<json_patch>'

# Diff the last two envdefs from an ecology
conservationist-client ecology diff-latest <name>
```

### Environment Definition Operations

```sh
# List all envdefs
conservationist-client envdef list

# Create envdef from ecology
conservationist-client envdef create <ecology_name>

# Create with tags
conservationist-client envdef create <ecology_name> -t v1.0 -t stable

# Create with variant
conservationist-client envdef create <ecology_name> -v <variant_name>

# Read envdef (JSON output)
conservationist-client envdef read <envdef_id>

# Read in conda-compatible format
conservationist-client envdef read <envdef_id> --condafy

# Diff two envdefs
conservationist-client envdef diff <envdef_id_1> <envdef_id_2>

# Yank/unyank an envdef (mark as unsuitable for use)
conservationist-client envdef yank <envdef_id>
conservationist-client envdef unyank <envdef_id>
```

### Conda Environment Operations

```sh
# Create a conda env directly from an envdef
conservationist-client conda-env create -n <env_name> -e <envdef_id>

# Use micromamba instead of conda
conservationist-client conda-env create -n <env_name> -e <envdef_id> --conda-exe micromamba

# Allow yanked envdefs (not recommended)
conservationist-client conda-env create -n <env_name> -e <envdef_id> --allow-yanked
```

### Validation

```sh
# Check envdef against version specifiers
conservationist-client envdef checkspec <envdef_id> -s <pkg> <specifier>

# Check against rules file
conservationist-client envdef check <envdef_id> <rules.json>
```

### String Templates

```sh
# Generate formatted output using jinja2 templates
conservationist-client envdef stringify "<template>" <envdef_id>

# Example: show Python version
conservationist-client envdef stringify "{{ envdef|version_of('python') }}" <envdef_id>
```

## Common Workflows

### Create and Deploy an Environment

```sh
# 1. Create ecology (one-time)
conservationist-client ecology create my-app my-package gunicorn "python>=3.9"

# 2. Create envdef
conservationist-client envdef create my-app -t v1.0

# 3. Create conda env directly from envdef
conservationist-client conda-env create -n my-app-env -e <envdef_id>

# Or with a specific conda executable (default: conda)
conservationist-client conda-env create -n my-app-env -e <envdef_id> --conda-exe micromamba
```

### Create Environment from a Solve Version

```sh
# One-shot: resolve solve tag → envdef ID → create conda env
ENVDEF=$(conservationist-client ecology read <ecology_name> | jq -r '.tags."<solve_version>"') && \
  conservationist-client conda-env create -n <env_name> -e "$ENVDEF" --conda-exe micromamba
```

### Add Tags to Existing Envdef

```sh
conservationist-client ecology update <ecology_name> '{"tags": {"production": "<envdef_id>"}}'
```

### Define Variants

```sh
# Add Python version variants
conservationist-client ecology update <ecology_name> '{"variants": {"py311": ["python=3.11"], "py312": ["python=3.12"]}}'

# Use variant when creating envdef
conservationist-client envdef create <ecology_name> -v py312
```

### Get Envdef ID from Solve Version

Solve versions (e.g., `2026.2.1solve0`) are stored as **tags** on ecologies. The ecology name is typically the conda package name (from `meta.yaml`).

```sh
# Fast: read the ecology and extract the tag
conservationist-client ecology read <ecology_name> | jq -r '.tags."<solve_version>"'

# Example: get envdef ID for queso solve 2026.2.1solve0
conservationist-client ecology read queso | jq -r '.tags."2026.2.1solve0"'
```

### Get Envdef ID from Tag (General)

```sh
conservationist-client ecology read <name> | jq -r '.tags."<tag_name>"'
```

### Diff Local Environment vs Envdef

```sh
diff -y <(conservationist-client envdef read <envdef_id> --condafy) \
        <(micromamba env export --explicit --md5) | less
```

### Chain Commands with jq

```sh
# Read envdef for a specific tag
conservationist-client envdef read $(conservationist-client ecology read <name> | jq -r '.tags."v1.0"')

# Get specific package version from envdef (use --condafy, not jq — .data is a string, not an array)
conservationist-client envdef read <envdef_id> --condafy | rg <package_name>

# One-shot: look up package version(s) for a solve tag without storing the envdef ID
ENVDEF=$(conservationist-client ecology read <ecology_name> | jq -r '.tags."<solve_version>"') && \
  conservationist-client envdef read "$ENVDEF" --condafy | rg '<package_name>'
```

## Rules File Format (for `envdef check`)

```json
{
  "package_name": {
    "required": true,
    "specifier": ">=1.0,<2.0",
    "version_regex": "^1\\.",
    "platforms": ["linux-64"],
    "build_id_regex": "py3.*"
  }
}
```

## Search

```sh
# Find envdefs containing specific conda packages
conservationist-client search conda-pkg <package_name>
```

## CHIP Utilities

CHIP-specific workflows for managing envdefs with standardized tagging:

```sh
# Create envdef with CHIP-style tagging
conservationist-client chiputils create-envdef <ecology_name>

# Get human-readable envdef name formats
conservationist-client chiputils envdef-name <envdef_id>

# Get latest tag for a version
conservationist-client chiputils latest-tag <ecology_name> <version>

# Get next tag for an envdef
conservationist-client chiputils next-tag <ecology_name>

# Re-solve an environment using CHIP tagging conventions
conservationist-client chiputils re-solve <ecology_name>

# Confirm all packages in a file are available
conservationist-client chiputils confirm-pkgs <file>
```

## Tips

- Use `jq` for JSON processing and extracting specific fields
- Use subshells `$(...)` to compose commands
- Use process substitution `<(...)` for diffing outputs
- Tags are mutable pointers; envdef IDs are immutable
- Variants help manage multi-python or optional-dependency builds
- The `--condafy` flag outputs conda-compatible lockfile format
