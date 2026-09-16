from rest_framework import serializers
from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    annual_price_calculated = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'monthly_price', 'annual_price', 'annual_price_calculated',
            'billing_interval', 'description', 'is_active', 'trial_period_days',
            'stripe_price_id',
        ]


class SubscriptionStatusSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    monthly_price = serializers.DecimalField(
        source='plan.monthly_price', max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = Subscription
        fields = [
            'status', 'plan_name', 'monthly_price', 'billing_interval',
            'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'auto_renew', 'is_active',
        ]
