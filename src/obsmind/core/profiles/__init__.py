from .base import Profile
from .dev import DevProfile

PROFILES: dict[str, type["Profile"]] = {
    "dev": DevProfile,
}


def get_profile(name: str) -> "Profile":
    cls = PROFILES.get(name)
    if cls is None:
        raise ValueError(
            f"Profile '{name}' not found. "
            f"Available: {', '.join(PROFILES)}. "
            "See profiles/README.md to add a new one."
        )
    return cls()
