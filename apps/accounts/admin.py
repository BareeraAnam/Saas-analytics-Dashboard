from django.contrib import admin

from .models import APIKey, Membership

# The signing secret and the key hash are server-side only.
class APIKeyAdmin(admin.ModelAdmin):
    exclude = ("signing_secret", "key_hash")
    readonly_fields = ("key_id", "prefix", "created_at", "last_used_at")


admin.site.register(APIKey, APIKeyAdmin)
admin.site.register(Membership)
