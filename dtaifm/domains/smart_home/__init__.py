"""Smart home domain pack — residential automation (lights, HVAC, locks)."""

from dtaifm.domains.base import Domain
from dtaifm.domains.registry import register_domain


SMART_HOME = Domain(
    id="smart_home",
    version="0.1",
    description="Residential home automation: lights, HVAC, locks, sensors.",
    trigger_events=frozenset({
        "motion_detected",
        "motion_cleared",
        "user_arrived",
        "user_departed",
        "door_opened",
        "door_closed",
        "temperature_below_threshold",
        "temperature_above_threshold",
    }),
    condition_types=frozenset({
        "time_range",
        "mode_not",
        "mode_is",
        "device_state",
    }),
    action_kinds=frozenset({
        "turn_on",
        "turn_off",
        "lock",
        "unlock",
        "set_temperature",
        "set_brightness",
    }),
)


register_domain(SMART_HOME)
