file_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\views.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace SyncPushEndpoint with the simplified dispatcher version
new_class = '''from .sync.dispatcher import SyncDispatcher
from .sync.utils import get_company_for_user

class SyncPushEndpoint(APIView):
    """
    Electron calls this to push locally-made changes up to the cloud.
    Delegates all processing to SyncDispatcher.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        company = get_company_for_user(request.user)
        if not company:
            return Response(
                {"error": "No company found for this user."},
                status=status.HTTP_403_FORBIDDEN
            )

        if company.subscription_status == 'expired':
            return Response(
                {"error": "SUBSCRIPTION_EXPIRED", "detail": "Your subscription has expired. Please renew to continue syncing data."},
                status=status.HTTP_403_FORBIDDEN
            )

        payload = request.data.get('payload', {})
        print(f"[SYNC] PUSH received from {request.user.email} (Company: {company.name})")
        print(f"[SYNC] Payload tables: {list(payload.keys())}")
        
        result = SyncDispatcher.dispatch_push(payload, company)
        return Response(result, status=status.HTTP_200_OK)
'''

import re
# We need to replace everything from class SyncPushEndpoint(APIView): to the end of the file.
# Wait, are there other classes after SyncPushEndpoint in views.py?
# Let's check!
import sys
if re.search(r'\nclass [A-Za-z0-9_]+\(', content[content.find('class SyncPushEndpoint'):+30]):
    print("Warning: there are other classes after SyncPushEndpoint. Use careful regex.")
else:
    content = re.sub(r'class SyncPushEndpoint\(APIView\):.*', new_class, content, flags=re.DOTALL)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced SyncPushEndpoint successfully")
