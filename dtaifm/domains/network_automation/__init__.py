"""Network automation domain pack — router/switch config, BGP, maintenance windows."""

from dtaifm.domains.base import Domain
from dtaifm.domains.network_automation.evaluators import (
    action_target_limit,
    companion_action_required,
    mode_required,
)
from dtaifm.domains.registry import register_domain


NETWORK_AUTOMATION = Domain(
    id="network_automation",
    version="0.1",
    description="Network device configuration and lifecycle automation.",
    trigger_events=frozenset({
        "config_change_requested",
        "scheduled_maintenance_start",
        "scheduled_maintenance_end",
        "bgp_session_flap",
        "interface_down_alert",
        "approval_granted",
    }),
    condition_types=frozenset({
        "time_range",
        "mode_not",
        "mode_is",
        "device_state",
    }),
    action_kinds=frozenset({
        "apply_config",
        "rollback",
        "disable",
        "enable",
        "reset_bgp_neighbor",
        "notify_operator",
    }),
    extra_constraint_evaluators={
        "companion_action_required": companion_action_required,
        "action_target_limit": action_target_limit,
        "mode_required": mode_required,
    },
)


register_domain(NETWORK_AUTOMATION)
