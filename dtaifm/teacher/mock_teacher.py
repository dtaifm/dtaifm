from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.core.ruleset import RuleSet
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherRequest, TeacherResponse


class MockTeacher(Teacher):
    """
    Deterministic stand-in for an AI teacher. No API keys required.

    Returns a fixed set of rules per domain that deliberately includes one
    unsafe rule so the validator's rejection path is always exercised in demos.

    When a TeacherRequest carries feedback (revision request), the mock drops
    every rule whose id appears in feedback.rejected_rules — giving repropose
    tests a deterministic "the teacher learned from the feedback" outcome that
    works across both shipped domains.

    A real adapter (AnthropicTeacher, OllamaTeacher, LemonadeTeacher) sets
    rationale to the model's actual reasoning so reviewers can audit the proposal.
    """

    def propose(self, request: TeacherRequest) -> TeacherResponse:
        domain_id = request.domain.id if request.domain is not None else "smart_home"
        builder = getattr(self, f"_build_{domain_id}", None)
        if builder is None:
            return TeacherResponse(
                ruleset=RuleSet(source=f"mock_teacher:{domain_id}"),
                raw_provider_output=(
                    f"mock_teacher: no built-in fixture for domain '{domain_id}'"
                ),
            )

        base_ruleset = builder()

        if request.feedback is not None:
            rejected_ids = {rec.rule_id for rec in request.feedback.rejected_rules}
            revised = RuleSet(source=f"mock_teacher:{domain_id}:revised")
            for rule in base_ruleset:
                if rule.id not in rejected_ids:
                    revised.add(rule)
            return TeacherResponse(
                ruleset=revised,
                raw_provider_output=(
                    f"mock_teacher: revised {domain_id} fixture — dropped "
                    f"{len(rejected_ids)} rejected rule(s) per deterministic feedback"
                ),
            )

        return TeacherResponse(
            ruleset=base_ruleset,
            raw_provider_output=f"mock_teacher: built-in {domain_id} fixture",
        )

    # ------------------------------------------------------------------
    # smart_home
    # ------------------------------------------------------------------

    def _build_smart_home(self) -> RuleSet:
        ruleset = RuleSet(source="mock_teacher:smart_home")

        ruleset.add(Rule(
            id="r_motion_night_light",
            name="Motion-Activated Night Light",
            trigger=Trigger(device="motion_sensor", event="motion_detected"),
            conditions=[
                Condition(type="time_range", parameters={"start_hour": 22, "end_hour": 6}),
                Condition(type="mode_not", parameters={"mode": "security"}),
            ],
            actions=[Action(device="hallway_light", action="turn_on", parameters={"duration": 300})],
            satisfies_constraints=["motion_light_hours", "security_override"],
            explanation=(
                "Activates the hallway light on motion only during night hours (22:00-06:00) "
                "and only when the system is not in security mode."
            ),
            rationale=(
                "Comfort lighting from motion should be restricted to user-defined night hours "
                "to avoid unnecessary daytime activation, and disabled in security mode to "
                "preserve the security_override constraint."
            ),
        ))

        ruleset.add(Rule(
            id="r_auto_unlock_door",
            name="Auto-Unlock on Arrival (UNSAFE)",
            trigger=Trigger(device="arrival_sensor", event="user_arrived"),
            conditions=[],
            actions=[Action(device="front_door", action="unlock")],
            satisfies_constraints=[],
            explanation="",
            rationale=(
                "Deliberately unsafe candidate: tests the validator's rejection path against "
                "the no_auto_unlock and rule_must_explain constraints."
            ),
        ))

        ruleset.add(Rule(
            id="r_heating_cold",
            name="Activate Heating When Cold",
            trigger=Trigger(device="thermostat", event="temperature_below_threshold"),
            conditions=[
                Condition(type="device_state", parameters={"device": "ac", "state": "off"}),
                Condition(type="mode_not", parameters={"mode": "security"}),
            ],
            actions=[Action(device="heating", action="turn_on")],
            satisfies_constraints=["no_hvac_conflict", "security_override"],
            explanation=(
                "Activates heating only when AC is confirmed off (prevents HVAC conflict) "
                "and only when the system is not in security mode."
            ),
            rationale=(
                "Heating activation must be gated on AC being off to honor no_hvac_conflict, "
                "and disabled in security mode to honor security_override."
            ),
        ))

        return ruleset

    # ------------------------------------------------------------------
    # network_automation
    # ------------------------------------------------------------------

    def _build_network_automation(self) -> RuleSet:
        ruleset = RuleSet(source="mock_teacher:network_automation")

        ruleset.add(Rule(
            id="r_apply_router_config_safely",
            name="Apply Router Config During Maintenance",
            trigger=Trigger(device="scheduler", event="config_change_requested"),
            conditions=[
                Condition(type="mode_is", parameters={"mode": "maintenance"}),
                Condition(type="mode_not", parameters={"mode": "unapproved"}),
            ],
            actions=[
                Action(device="router1", action="apply_config"),
                Action(device="router1", action="rollback"),
            ],
            satisfies_constraints=[
                "changes_in_maintenance_mode_only",
                "apply_config_requires_rollback",
                "max_apply_config_devices",
                "bgp_reset_requires_approval",
            ],
            explanation=(
                "Applies a router1 config change and registers a rollback action, only during "
                "maintenance mode and when not in unapproved mode."
            ),
            rationale=(
                "All mutability constraints are honored: maintenance-mode gate, rollback "
                "companion action, single-device target within the batch limit, and the "
                "mode_not check satisfies the approval-required mode override."
            ),
        ))

        ruleset.add(Rule(
            id="r_disable_mgmt_unsafe",
            name="Disable Management Interface (UNSAFE)",
            trigger=Trigger(device="monitoring", event="interface_down_alert"),
            conditions=[],
            actions=[Action(device="mgmt0", action="disable")],
            satisfies_constraints=[],
            explanation="",
            rationale=(
                "Deliberately unsafe candidate: tests the validator's rejection path against "
                "the no_disable_mgmt and rule_must_explain constraints."
            ),
        ))

        ruleset.add(Rule(
            id="r_notify_operator_on_flap",
            name="Notify Operator on BGP Flap",
            trigger=Trigger(device="bgp_neighbor_1", event="bgp_session_flap"),
            conditions=[],
            actions=[Action(device="operator_pager", action="notify_operator")],
            satisfies_constraints=["rule_must_explain"],
            explanation="Pages the operator when a BGP session flaps. Pure notification, no config change.",
            rationale=(
                "Notification-only rules don't touch managed devices, so they don't need "
                "maintenance-mode or rollback guards."
            ),
        ))

        return ruleset
