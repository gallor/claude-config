# Zensical Reference

Zensical is a documentation framework that succeeds Material for MkDocs. It is configured via **TOML** (not YAML). Claude's training data likely does not cover Zensical — use this reference for all Zensical work.

## Key Differences from MkDocs Material

| MkDocs Material | Zensical |
|-----------------|----------|
| `mkdocs.yml` (YAML) | `zensical.toml` (TOML) |
| `mkdocs serve` / `mkdocs build` | `zensical serve` / `zensical build` |
| Icon prefix: `material/` | Icon prefix: `lucide/` (Lucide icons) |
| `theme:` top-level | `[project.theme]` section |
| `plugins:` list | `[project.plugins.NAME]` tables |

## Configuration Structure (`zensical.toml`)

```toml
[project]
site_name = "Project Documentation"
site_description = "One-line description"
site_author = "Team Name"
copyright = "Copyright &copy; 2025 Team Name"
repo_url = "https://github.com/org/repo"
repo_name = "org/repo"
# edit_uri = "edit/main/docs/"  # GitHub auto-derives this; override if needed

# Navigation: implicit (directory structure) or explicit
# nav = [
#   { "Get started" = "index.md" },
#   { "API Reference" = "api.md" },
# ]

[project.theme]
language = "en"
# variant = "classic"  # use traditional Material look
# custom_dir = "overrides"
features = [
    "content.code.annotate",
    "content.code.copy",
    "content.code.select",
    "content.tabs.link",
    "navigation.footer",
    "navigation.indexes",
    "navigation.instant",
    "navigation.instant.prefetch",
    "navigation.sections",
    "navigation.top",
    "navigation.tracking",
    "search.highlight",
    # "content.action.edit",   # adds edit button linking to repo
    # "content.action.view",   # adds view-source button linking to repo
]

# Color scheme with dark mode toggle
[[project.theme.palette]]
media = "(prefers-color-scheme)"
toggle.icon = "lucide/sun-moon"
toggle.name = "Switch to light mode"

[[project.theme.palette]]
media = "(prefers-color-scheme: light)"
scheme = "default"
toggle.icon = "lucide/sun"
toggle.name = "Switch to dark mode"

[[project.theme.palette]]
media = "(prefers-color-scheme: dark)"
scheme = "slate"
toggle.icon = "lucide/moon"
toggle.name = "Switch to system preference"

[project.theme.icon]
logo = "lucide/smile"
repo = "fontawesome/brands/github"  # or gitlab, bitbucket, etc.
# edit = "lucide/pencil"
# view = "lucide/eye"

# mkdocstrings for API docs
[project.plugins.mkdocstrings.handlers.python]
inventories = ["https://docs.python.org/3/objects.inv"]
paths = ["src"]

[project.plugins.mkdocstrings.handlers.python.options]
docstring_style = "google"
inherited_members = true
show_source = false
```

## Repository Link

Add a repository link (displayed as an icon in the header) with these `[project]` keys:

```toml
[project]
repo_url = "https://github.com/org/repo"   # required
repo_name = "org/repo"                      # optional; displayed as tooltip
edit_uri = "edit/main/docs/"                # optional; GitHub auto-derives this
```

To add edit/view-source buttons on each page, enable the corresponding theme features:

```toml
[project.theme]
features = [
    "content.action.edit",
    "content.action.view",
]
```

Set the repo icon (defaults to the detected provider's icon):

```toml
[project.theme.icon]
repo = "fontawesome/brands/github"   # or gitlab, bitbucket
edit = "lucide/pencil"
view = "lucide/eye"
```

For GitHub-hosted repos, `edit_uri` and the edit/view URLs are derived automatically from `repo_url`.

## Page Frontmatter

Pages use Lucide icon names in frontmatter:

```markdown
---
icon: lucide/home
---

# Page Title
```

Common icons: `lucide/home`, `lucide/database`, `lucide/settings`, `lucide/book-open`, `lucide/code`, `lucide/server`, `lucide/shield`.

## API Documentation (mkdocstrings)

Use `:::` directive syntax to auto-generate API docs from docstrings:

```markdown
# API Reference

::: my_package
```

Or for specific modules/classes:

```markdown
::: my_package.module_name

::: my_package.MyClass
    options:
      show_source: true
      members_order: source
```

## Limitations

- Projects using `mkdocs-macros-plugin` cannot be fully converted to Zensical
- Always read the existing `zensical.toml` before making changes to understand project-specific conventions
