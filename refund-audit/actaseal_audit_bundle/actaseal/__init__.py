"""ActaSeal runtime contracts."""


def __getattr__(name: str):
    # `actaseal.autopatch(...)` without importing the SDK (and its dependencies)
    # for everything that merely imports `actaseal`.
    if name == "autopatch":
        from actaseal.sdk.autopatch import autopatch

        return autopatch
    raise AttributeError(f"module 'actaseal' has no attribute {name!r}")
