"""Target names as the webapp shows them ("iPhone 17 · iOS 27", "Chrome 157 · Desktop")."""

from minitest_cli.models.batch import BatchTargetView

OS_NAMES = {"ios": "iOS", "android": "Android"}
BROWSER_NAMES = {"chrome": "Chrome", "firefox": "Firefox", "edge": "Edge", "safari": "Safari"}
CLOUD_DEVICES = {
    ("ios", "phone"): "iPhone",
    ("ios", "tablet"): "iPad",
    ("android", "phone"): "Android phone",
    ("android", "tablet"): "Android tablet",
}


def _device_name(model: str | None) -> str | None:
    """A model with no space and an underscore is an emulator image id, not a name."""
    name = (model or "").strip()
    if not name or (" " not in name and "_" in name):
        return None
    return name


def _os_label(platform: str, version: str | None) -> str | None:
    name = OS_NAMES.get(platform)
    return f"{name} {version.strip()}" if name and version and version.strip() else None


def _requested_device(target: BatchTargetView) -> str | None:
    if target.backend == "physical":
        models = target.device_models or []
        return models[0] if len(models) == 1 else None
    if target.backend not in (None, "cloud"):
        return None
    return CLOUD_DEVICES.get((target.platform, target.device_type or "phone"))


def _web_label(target: BatchTargetView) -> str:
    name = BROWSER_NAMES.get(target.browser or "")
    ran = (target.browser_version or "").strip().split(".")[0]
    major = ran or (target.browser_version_requested or "").strip()
    if not name or not major or not target.label.startswith(name):
        return target.label
    return f"{name} {major}{target.label[len(name) :]}"


def target_display_label(target: BatchTargetView) -> str:
    if target.browser or target.platform not in OS_NAMES:
        return _web_label(target)
    if target.device_type == "tv":
        return "Android TV"
    model = _device_name(target.ran_device_model)
    ran_os = _os_label(target.platform, target.ran_os_version)
    if model:
        return f"{model} · {ran_os}" if ran_os else model
    requested = _requested_device(target)
    os = ran_os or (_os_label(target.platform, target.os_version) if requested else None)
    base = requested or target.label
    if not os:
        return base
    return os if base == OS_NAMES[target.platform] else f"{base} · {os}"
