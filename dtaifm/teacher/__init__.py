from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import PromptContext, TeacherRequest, TeacherResponse
from dtaifm.teacher.diagnostics import describe_all, describe_teacher, format_teachers_text
from dtaifm.teacher.feedback import (
    RejectedRuleRecord,
    RuleViolation,
    TeacherFeedback,
    build_feedback,
)
from dtaifm.teacher.mock_teacher import MockTeacher
from dtaifm.teacher.parser import (
    KNOWN_CONDITION_TYPES,
    ProviderResponseError,
    parse_provider_payload,
    parse_provider_text,
)
from dtaifm.teacher.prompt import render_teacher_prompt
from dtaifm.teacher.registry import (
    UnknownTeacherError,
    available_teachers,
    get_teacher,
    register_teacher,
    teacher_is_registered,
)

__all__ = [
    "Teacher",
    "MockTeacher",
    "PromptContext",
    "TeacherRequest",
    "TeacherResponse",
    "TeacherFeedback",
    "RejectedRuleRecord",
    "RuleViolation",
    "build_feedback",
    "ProviderResponseError",
    "KNOWN_CONDITION_TYPES",
    "parse_provider_payload",
    "parse_provider_text",
    "render_teacher_prompt",
    "UnknownTeacherError",
    "available_teachers",
    "get_teacher",
    "register_teacher",
    "teacher_is_registered",
    "describe_all",
    "describe_teacher",
    "format_teachers_text",
]
