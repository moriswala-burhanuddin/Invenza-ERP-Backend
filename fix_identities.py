import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()

from erp_core.models import ERPUser
from django.contrib.auth.models import User
from django.db.models import Count

def fix_identities():
    print("--- Multi-Tenant Identity Audit ---")
    
    # Check for DjangoUsers linked to multiple ERPUsers
    # (Shouldn't happen with OneToOne, but let's be safe if sync logic was manual)
    collided_links = ERPUser.objects.values('django_user').annotate(cnt=Count('id')).filter(cnt__gt=1, django_user__isnull=False)
    
    if collided_links.exists():
        print(f"Found {collided_links.count()} collided DjangoUser links!")
        for entry in collided_links:
            du_id = entry['django_user']
            du = User.objects.get(id=du_id)
            profiles = ERPUser.objects.filter(django_user=du)
            print(f"User {du.email} is shared by companies: {[p.company.name for p in profiles]}")
            
            # Keep the first one, nullify others to trigger fresh isolated creation on next sync
            first = True
            for p in profiles:
                if first:
                    first = False
                    continue
                print(f"  -> Resetting shadow link for {p.company.name}")
                p.django_user = None
                p.save()
    else:
        print("No collided DjangoUser links found.")

    # Check for ERPUsers in different companies sharing the same email
    # but potentially missing their own isolated DjangoUser because they share one globally.
    # This is handled by the new sync logic, but we can proactively trigger isolation here.
    
    all_users = ERPUser.objects.all()
    for u in all_users:
        if u.django_user:
            # Check if this DjangoUser is being "owned" by another company's email/logic
            # (e.g. if the email belongs to a company owner but this is a staff user)
            pass

    print("Audit Complete.")

if __name__ == "__main__":
    fix_identities()
