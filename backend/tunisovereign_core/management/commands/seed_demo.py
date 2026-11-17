"""python manage.py seed_demo  -> creates demo users, a cohort and 6 submissions (idempotent).

DEV ONLY: demo accounts share a well-known password.
"""
from django.core.management.base import BaseCommand

from tunisovereign_core.models import Cohort, ProjectSubmission, StakeholderUser

DEMO_PASSWORD = "Demo-Pass-2026!"
Role = StakeholderUser.Role

USERS = [
    ("student1", Role.STUDENT), ("student2", Role.STUDENT), ("student3", Role.STUDENT),
    ("student4", Role.STUDENT), ("mentor1", Role.MENTOR_AUDITOR),
    ("admin1", Role.NATIONAL_ADMIN), ("agent1", Role.AGENT_SERVICE),
]
PROJECTS = [
    ("TSK-2026-001", "student1", "Smart irrigation dashboard"),
    ("TSK-2026-002", "student2", "Pharmacy stock tracker"),
    ("TSK-2026-003", "student3", "Municipal budget portal"),
    ("TSK-2026-004", "student4", "Olive oil traceability API"),
    ("TSK-2026-005", "student1", "Solar micro-grid monitor"),
    ("TSK-2026-006", "student2", "Remittance fee comparator"),
]


class Command(BaseCommand):
    help = "Create demo users, one cohort and six project submissions (safe to re-run)."

    def handle(self, *args, **options):
        users = {}
        for username, role in USERS:
            user, created = StakeholderUser.objects.get_or_create(
                username=username,
                defaults={"role": role, "email": f"{username}@demo.tn", "governorate": "Tunis"},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            users[username] = user

        cohort, _ = Cohort.objects.get_or_create(
            name="3-BIS Cohort 2026", institution="ISG Tunis", defaults={"governorate": "Tunis"}
        )
        for code, owner, title in PROJECTS:
            ProjectSubmission.objects.get_or_create(
                project_code=code,
                defaults={
                    "cohort": cohort,
                    "student": users[owner],
                    "title": title,
                    "repo_url": f"https://github.com/{owner}/{code.lower()}",
                },
            )
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(USERS)} users, 1 cohort, {len(PROJECTS)} submissions. "
            f"Password for all demo users: {DEMO_PASSWORD}"
        ))
