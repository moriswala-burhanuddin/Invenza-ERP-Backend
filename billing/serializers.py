from rest_framework import serializers
from .models import Plan, Feature

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ('id', 'name', 'monthly_price', 'description')

class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ('id', 'name', 'price', 'description', 'internal_id')
