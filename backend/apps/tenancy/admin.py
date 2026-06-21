from django.contrib import admin

from apps.tenancy.models import Domain, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "schema_name", "status", "created_on")
    search_fields = ("name", "schema_name")
    list_filter = ("status",)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    search_fields = ("domain",)
