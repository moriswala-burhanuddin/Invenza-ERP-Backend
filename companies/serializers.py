import random
import string
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from .models import Company
from billing.models import Subscription, Plan
from billing.services import send_welcome_email


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = (
            'id', 'name', 'slug', 'subscription_status', 'expiry_date',
            'legal_name', 'tax_id', 'address', 'city', 'state', 'pincode',
            'phone', 'logo', 'website', 'is_ai_enabled', 'trial_days_left'
        )
        read_only_fields = ('slug', 'subscription_status', 'is_ai_enabled', 'trial_days_left')


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    company_name = serializers.CharField()

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_company_name(self, value):
        if Company.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A company with this name already exists.")
        return value

    def create(self, validated_data):
        from erp_core.models import Store, ERPUser

        # 1. Create Django Website User
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )

        # 2. Generate a secure temporary password for the Electron ERP
        temp_erp_pass = "Invenza" + "".join(random.choices(string.digits, k=4)) + "!"

        # 3. Create the Company (Tenant)
        company = Company.objects.create(
            name=validated_data['company_name'],
            slug=validated_data['company_name'].lower().replace(' ', '-'),
            owner=user,
            erp_password=temp_erp_pass,
            subscription_status='trial'
        )

        # 4. Create a default Store (required for Electron ERP to boot)
        default_store = Store.objects.create(
            company=company,
            name=validated_data['company_name'],
            branch='Main Branch',
        )

        # 5. Create the Admin ERPUser (the owner's desktop ERP login)
        name_parts = validated_data['username'].split(' ', 1)
        erp_admin = ERPUser.objects.create(
            company=company,
            django_user=user,
            name=validated_data['username'],
            email=validated_data['email'],
            username=validated_data['username'],
            password=make_password(temp_erp_pass),  # Hashed — used in Electron local login
            role='super_admin', # Primary user is always super_admin
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else '',
            is_active=True,
            is_staff=True,
        )
        erp_admin.stores.set([default_store])

        # 6. Initialize a trial subscription
        try:
            trial_plan = Plan.objects.get(name__icontains='Trial')
            Subscription.objects.create(company=company, plan=trial_plan, is_active=True)
        except Plan.DoesNotExist:
            Subscription.objects.create(company=company, is_active=True)

        # 7. Send welcome email with ERP credentials
        try:
            send_welcome_email(user, company, temp_erp_pass)
        except Exception as e:
            print(f"[EMAIL] Failed to send welcome email: {e}")

        return user, company


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM TOKEN SERIALIZER  —  Allows login via EMAIL for the desktop app
# ─────────────────────────────────────────────────────────────────────────────
class EmailTokenObtainPairSerializer(serializers.Serializer):
    # Accept either "email" or "username" as the key from different clients
    email = serializers.CharField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)
    company_id = serializers.CharField(required=False)

    def validate(self, attrs):
        from django.contrib.auth import authenticate
        from rest_framework_simplejwt.tokens import RefreshToken
        from django.db.models import Q
        from erp_core.models import ERPUser
        from .models import Company

        # Get identifier from either 'email' or 'username' key
        identifier = attrs.get('email') or attrs.get('username')
        password = attrs.get('password')
        requested_company_id = attrs.get('company_id')
        
        if not identifier:
            raise serializers.ValidationError({"detail": "Username or Email is required."})

        print(f"[AUTH_DEBUG] Attempting login for identifier: {identifier} (Company Filter: {requested_company_id or 'None'})")

        # ── SMART DISCOVERY ──
        # Find all Django Users who either:
        # a) Have this email/username globally (primary accounts)
        # b) Are linked to an ERPUser who has this email/username in ANY company (secondary/legacy IDs)
        erp_django_uids = ERPUser.objects.filter(
            Q(email__iexact=identifier) | Q(username__iexact=identifier),
            is_deleted=False
        ).values_list('django_user_id', flat=True)
        
        potential_users = User.objects.filter(
            Q(email__iexact=identifier) | Q(username__iexact=identifier) | Q(id__in=erp_django_uids)
        ).distinct()
        
        if not potential_users.exists():
            print(f"[AUTH_DEBUG] No potential users found for identifier: {identifier}")
            raise serializers.ValidationError({"detail": "No user found with this email or username."})
        
        authenticated_user = None
        
        # If company_id is provided, we can strictly filter candidates
        if requested_company_id:
            # Robust extraction: handles slugs and float-formatted strings like '3.0'
            raw_id_str = str(requested_company_id).strip()
            cleaned_numeric_id = raw_id_str.split('.')[0]
            
            company_query = Q(slug__iexact=raw_id_str)
            if cleaned_numeric_id.isdigit():
                company_query |= Q(id=int(cleaned_numeric_id))
            
            target_companies = Company.objects.filter(company_query)
            
            if not target_companies.exists():
                print(f"[AUTH_DEBUG] Company Not Found: {requested_company_id}")
                raise serializers.ValidationError({"detail": "The requested company does not exist."})

            # Filter users who are either owners of these companies OR staff in these companies
            company_uids = target_companies.values_list('owner_id', flat=True)
            erp_uids = ERPUser.objects.filter(company__in=target_companies).values_list('django_user_id', flat=True)
            valid_ids = list(set(list(company_uids) + list(erp_uids)))
            potential_users = potential_users.filter(id__in=valid_ids)
            
            if not potential_users.exists():
                print(f"[AUTH_DEBUG] Identity Mismatch: {identifier} is not associated with company {requested_company_id}")
                raise serializers.ValidationError({"detail": "This account is not associated with the requested company."})

        # Because multiple companies can share an email (isolated by company), 
        # we must check the password against all candidates to find the correct local identity.
        for user in potential_users:
            print(f"[AUTH_DEBUG] Testing candidate: {user.username} ({user.email})")
            
            # 1. Attempt standard Django authentication
            from django.contrib.auth import authenticate
            auth_test = authenticate(username=user.username, password=password)
            if auth_test:
                authenticated_user = auth_test
                print(f"[AUTH_DEBUG] SUCCESS: Standard Login for {user.username}")
                break
                
            # 2. Attempt Portal-specific ERP Password fallback (Owners)
            company_owned = Company.objects.filter(owner=user).first()
            if company_owned and password == company_owned.erp_password:
                authenticated_user = user
                print(f"[AUTH_DEBUG] SUCCESS: Portal Fallback Login for {user.username}")
                break
                
            # 3. Attempt ERP-BCrypt fallback (Desktop-synced Staff)
            from erp_core.models import ERPUser
            import bcrypt
            
            erp_profile = ERPUser.objects.filter(django_user=user, is_deleted=False).first()
            if erp_profile and erp_profile.password:
                try:
                    if bcrypt.checkpw(password.encode('utf-8'), erp_profile.password.encode('utf-8')):
                        authenticated_user = user
                        print(f"[AUTH_DEBUG] SUCCESS: BCrypt Fallback Login for {user.username}")
                        break
                except ValueError:
                    # Fallback for plain text passwords (e.g. users created directly in Django admin)
                    if password == erp_profile.password:
                        authenticated_user = user
                        print(f"[AUTH_DEBUG] SUCCESS: Plain text Fallback Login for {user.username}")
                        break
                except Exception as e:
                    print(f"[AUTH_DEBUG] BCrypt error for {user.username}: {e}")

        if not authenticated_user:
            print(f"[AUTH_DEBUG] Auth FAILED: No candidates matched password for {identifier}")
            raise serializers.ValidationError({"detail": "Invalid password or credentials."})
        
        if not authenticated_user.is_active:
            raise serializers.ValidationError({"detail": "User account is disabled."})

        # 4. Determine Company & Tenant Context
        company = None
        
        # If we had a requested_company_id, use that directly
        if requested_company_id:
            from .models import Company
            raw_id_str = str(requested_company_id).strip()
            cleaned_numeric_id = raw_id_str.split('.')[0]
            
            company_query = Q(slug__iexact=raw_id_str)
            if cleaned_numeric_id.isdigit():
                company_query |= Q(id=int(cleaned_numeric_id))
            
            company = Company.objects.filter(company_query).first()
        
        # Fallback to derivation if not found or not provided
        if not company:
            # Scenario A: User is the Primary Owner of a Company
            company = Company.objects.filter(owner=authenticated_user).first()
            
            # Scenario B: User is a Staff/Employee (linked via ERPUser)
            if not company:
                from erp_core.models import ERPUser
                erp_profile = ERPUser.objects.filter(django_user=authenticated_user, is_deleted=False).first()
                if erp_profile:
                    company = erp_profile.company
                    print(f"[AUTH_DEBUG] Staff Account identified for {identifier}. Company: {company.name}")

        if not company:
            print(f"[AUTH_DEBUG] NO COMPANY FOUND for user {authenticated_user.email}")
            raise serializers.ValidationError({"detail": "No company associated with this account."})

        # 5. Generate SimpleJWT tokens manually
        refresh = RefreshToken.for_user(authenticated_user)

        # 6. Inject custom claims into the JWT token
        refresh['company_id'] = company.id
        refresh['company_name'] = company.name
        
        # Store primary store choice if possible (employee's primary store)
        store_id = None
        employee_id = None
        
        # 1. First check if company owner
        if Company.objects.filter(owner=authenticated_user).exists():
           from erp_core.models import Store
           store_id = Store.objects.filter(company=company).first().id if Store.objects.filter(company=company).exists() else 'store-1'
        else:
           # 2. Check ERP profile for assigned stores
           from erp_core.models import ERPUser, Employee, Store
           u = ERPUser.objects.filter(django_user=authenticated_user).first()
           if u:
               if u.stores.exists():
                   store_id = u.stores.first().id
               
               # 3. Resolve the actual employee model ID for HR functions
               emp = Employee.objects.filter(erp_user=u).first()
               if emp:
                   employee_id = emp.id
                   if not store_id: # Fallback to employee's own store_id field
                       store_id = emp.store_id
        
        # 4. Final safety fallback
        if not store_id:
             store_id = Store.objects.filter(company=company).first().id if Store.objects.filter(company=company).exists() else 'store-1'

        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'company_id': company.id,
            'company_name': company.name,
            'user': {
                'id': authenticated_user.id,
                'name': authenticated_user.username,
                'email': authenticated_user.email,
                'role': 'super_admin' if Company.objects.filter(owner=authenticated_user).exists() else (
                    ERPUser.objects.filter(django_user=authenticated_user).first().role if ERPUser.objects.filter(django_user=authenticated_user).exists() else 'staff'
                ),
                'store_id': store_id,
                'employee_id': employee_id
            }
        }
