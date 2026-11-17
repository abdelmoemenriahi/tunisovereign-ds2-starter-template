from tunisovereign_core.models import Cohort, ProjectSubmission, StakeholderUser

Role = StakeholderUser.Role
PASSWORD = "Str0ng-Pass-2026"


def make_user(username, role=Role.STUDENT, **extra):
    return StakeholderUser.objects.create_user(username=username, password=PASSWORD, role=role, **extra)


def make_cohort(name="Cohort A", **extra):
    return Cohort.objects.create(name=name, institution="ISG Tunis", governorate="Tunis", **extra)


def make_submission(cohort, student, code, **extra):
    return ProjectSubmission.objects.create(
        cohort=cohort,
        student=student,
        project_code=code,
        title=f"Project {code}",
        repo_url=f"https://github.com/{student.username}/{code.lower()}",
        **extra,
    )
