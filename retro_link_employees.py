from erp_core.models import Employee, ERPUser

count = 0
for e in Employee.objects.filter(erp_user__isnull=True):
    u = None
    if e.user_id:
        u = ERPUser.objects.filter(id=e.user_id).first()
    if not u and e.email:
         u = ERPUser.objects.filter(email=e.email).first()
    if u:
        e.erp_user = u
        e.save()
        count += 1
print(f"{count} Employees successfully auto-linked!")
