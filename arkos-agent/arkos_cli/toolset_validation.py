"""Validation of legacy per-platform toolset selections for embedding hosts."""


def validate_platform_toolsets(selections, validate_toolset, toolset_allowed_for_platform):
    """Return actionable diagnostics without mutating the caller's configuration."""
    if selections is None:
        return []
    if not isinstance(selections, dict):
        return ["platform_toolsets must be a mapping of platform names to toolset lists."]
    warnings = []
    for platform, toolsets in selections.items():
        if not isinstance(platform, str) or not isinstance(toolsets, list):
            warnings.append(f"Invalid platform_toolsets entry for {platform!r}: expected a list.")
            continue
        for toolset in toolsets:
            if not isinstance(toolset, str) or not validate_toolset(toolset):
                warnings.append(f"Unknown toolset {toolset!r} for platform {platform!r}.")
            elif not toolset_allowed_for_platform(toolset, platform):
                warnings.append(f"Toolset {toolset!r} is unavailable on platform {platform!r}.")
    return warnings
