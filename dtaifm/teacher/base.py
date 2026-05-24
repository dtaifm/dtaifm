from abc import ABC, abstractmethod

from dtaifm.teacher.contract import TeacherRequest, TeacherResponse
from dtaifm.teacher.prompt import render_teacher_prompt


class Teacher(ABC):
    """The cognitive layer. Proposes candidate rules — never executes them.

    Subclasses implement `propose`. The default `render_prompt` uses the shared
    template; adapters may override it for provider-specific formats.
    """

    def render_prompt(self, request: TeacherRequest) -> str:
        return render_teacher_prompt(request)

    @abstractmethod
    def propose(self, request: TeacherRequest) -> TeacherResponse:
        """
        Given a TeacherRequest, return a TeacherResponse carrying a portable RuleSet.
        Adapters MUST return artifacts only — never validate or execute.
        """
        ...
