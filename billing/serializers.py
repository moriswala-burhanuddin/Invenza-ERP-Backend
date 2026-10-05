import re

from rest_framework import serializers
from .models import Plan, Subscription
from .countries import COUNTRY_CODES


class BillingDetailsSerializer(serializers.Serializer):
    """Phone number + country collected at checkout (sent to Stripe and stored on Company)."""
    phone = serializers.CharField(max_length=32)
    country = serializers.CharField(max_length=2)

    def validate_phone(self, value):
        # Strip common formatting characters, keep leading '+' and digits only.
        cleaned = re.sub(r'[\s\-().]', '', value.strip())
        if not re.fullmatch(r'\+?\d{7,15}', cleaned):
            raise serializers.ValidationError(
                'Enter a valid phone number including country code (e.g. +44 7700 900123).'
            )
        return cleaned

    def validate_country(self, value):
        code = value.strip().upper()
        if code not in COUNTRY_CODES:
            raise serializers.ValidationError('Select a valid country.')
        return code


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
