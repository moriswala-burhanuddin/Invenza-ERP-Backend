from django.contrib import admin
from .models import Company

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'subscription_status', 'is_ai_enabled', 'created_at')
    list_filter = ('subscription_status', 'is_ai_enabled')
    search_fields = ('name', 'owner__username')
    prepopulated_fields = {'slug': ('name',)}
