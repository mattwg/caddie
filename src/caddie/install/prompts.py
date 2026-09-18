"""Interactive accept-or-override prompts used by `caddie install`.

Each field is pre-filled with a default when one is known (from
caddie.default.yaml) and requires typing when it isn't. Pressing enter
on a pre-filled prompt accepts the default with no typing required.
"""


def prompt_value(label: str, default: str | None = None) -> str:
    if default is not None:
        raw = input(f"{label} [{default}]: ").strip()
        return raw or default
    while True:
        raw = input(f"{label}: ").strip()
        if raw:
            return raw
        print("This field is required.")


def prompt_list(label: str, default: list[str] | None = None) -> list[str]:
    default_str = ", ".join(default) if default else None
    raw = prompt_value(label, default_str)
    return [item.strip() for item in raw.split(",") if item.strip()]
