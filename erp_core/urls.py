from django.urls import path
from .views import SyncPullEndpoint, SyncPushEndpoint, DashboardStatsView, SendSupplierEmailView, IssueReportView

urlpatterns = [
    path('sync/pull/', SyncPullEndpoint.as_view(), name='sync_pull'),
    path('sync/push/', SyncPushEndpoint.as_view(), name='sync_push'),
    path('online-reports/stats/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('online-reports/send-supplier-email/', SendSupplierEmailView.as_view(), name='send_supplier_email'),
    path('issue-report/', IssueReportView.as_view(), name='issue_report'),
]
