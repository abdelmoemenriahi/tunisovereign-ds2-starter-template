from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AgentLoopExecution, AnalysisMetric, AuditFinding, Cohort,
    ProjectSubmission, StakeholderUser, VerifiableCredentialReceipt,
)


@admin.register(StakeholderUser)
class StakeholderUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Track 6 profile", {"fields": ("role", "institution", "governorate", "wallet_address", "preferred_dialect")}),
    )
    list_display = ("username", "email", "role", "institution", "is_staff")


admin.site.register([Cohort, ProjectSubmission, AnalysisMetric, AuditFinding,
                     AgentLoopExecution, VerifiableCredentialReceipt])