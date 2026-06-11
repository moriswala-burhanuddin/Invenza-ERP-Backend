import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()

from erp_core.models import ERPUser
from django.contrib.auth.models import User as DjangoUser
from django.db import transaction

def fix_missing_shadow_accounts():
    print("--- 🚀 Starting ERP User Shadow Account Fix-up (V2.1) ---")
    erp_users = ERPUser.objects.all()
    print(f"Checking {erp_users.count()} users for cloud login compatibility.")

    with transaction.atomic():
        for erp_user in erp_users:
            # 1. Check if an auth.User with this email already exists
            auth_user = DjangoUser.objects.filter(email__iexact=erp_user.email).first()
            
            if not auth_user:
                print(f"Creating new Shadow Account for: {erp_user.name} ({erp_user.email})")
                auth_user = DjangoUser(
                    username=erp_user.username or erp_user.email,
                    email=erp_user.email,
                )
                # Set a dummy password; the serializer will use the ERPUser's raw hash
                auth_user.set_password("Shadow-Auth-Only-Use-ERP-Hash")
                auth_user.save()
            else:
                print(f"Found existing auth record for: {erp_user.email}. Ensuring it's a Shadow Account.")
                # We do NOT copy the hash here to avoid double-hashing
                # The auth system will now use erp_user.password via bcrypt fallback
                if not auth_user.password or len(auth_user.password) < 10:
                     auth_user.set_password("Shadow-Auth-Only-Use-ERP-Hash")
                     auth_user.save()

            # 2. Link them
            erp_user.django_user = auth_user
            erp_user.save()
            print(f"SUCCESS: Link established for {erp_user.email}")

    print("--- ✅ Fix-up Complete! ---")

if __name__ == "__main__":
    fix_missing_shadow_accounts()
