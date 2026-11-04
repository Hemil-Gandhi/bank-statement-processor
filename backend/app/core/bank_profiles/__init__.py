"""Bank profile registry."""
from __future__ import annotations

from app.core.bank_profiles import axis, bob, generic, hdfc, icici, kotak, pnb, sbi
from app.core.bank_profiles.base import BankProfile

PROFILES: dict[str, BankProfile] = {
    profile.PROFILE.id: profile.PROFILE
    for profile in (sbi, hdfc, icici, axis, kotak, pnb, bob)
}
GENERIC_PROFILE = generic.PROFILE
PROFILES[GENERIC_PROFILE.id] = GENERIC_PROFILE

IFSC_TO_PROFILE: dict[str, str] = {}
for _profile in PROFILES.values():
    for _prefix in _profile.ifsc_prefixes:
        IFSC_TO_PROFILE[_prefix.upper()] = _profile.id


def get_profile(profile_id: str | None) -> BankProfile:
    if profile_id and profile_id in PROFILES:
        return PROFILES[profile_id]
    return GENERIC_PROFILE


def all_profiles() -> list[BankProfile]:
    return list(PROFILES.values())
