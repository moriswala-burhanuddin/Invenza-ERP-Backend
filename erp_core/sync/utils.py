from decimal import Decimal, InvalidOperation
from erp_core.models import ERPUser
from companies.models import Company

def to_decimal(value, default="0"):
    """Safely convert any input to a Decimal, handling formatting like commas."""
    if value is None or str(value).strip() == "":
        return Decimal(str(default))
    try:
        # First try direct conversion
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        # Fallback: remove common formatting characters
        try:
            clean = str(value).replace(',', '').strip()
            return Decimal(clean)
        except:
            return Decimal(str(default))

def to_time(val):
    """Extracts HH:MM:SS from ISO strings or returns raw time strings."""
    if not val: return None
    val = str(val).strip().strip('"').strip("'")
    if 'T' in val:
        time_part = val.split('T')[1]
        return time_part.split('.')[0].replace('Z', '')
    if ' ' in val: # Handle "2024-04-08 16:16:58"
        parts = val.split(' ')
        if len(parts) > 1:
            return parts[1].split('.')[0]
    return val

def to_date(val):
    """Extracts YYYY-MM-DD from ISO strings or returns raw date strings."""
    if not val: return None
    val = str(val).strip().strip('"').strip("'")
    if 'T' in val:
        return val.split('T')[0]
    if ' ' in val:
        return val.split(' ')[0]
    return val

def parse_payroll_month_year(row):
    """
    Intelligently extracts numeric month and year from a payload row.
    Handles 'month': 4, 'year': 2026 OR 'month': 'April 2026'.
    """
    month_raw = str(row.get('month', '')).strip()
    year_raw = str(row.get('year', '')).strip()
    
    # Fallbacks
    m, y = 1, 2024
    
    # 1. Try direct numeric conversion
    try:
        return int(month_raw), int(year_raw)
    except (ValueError, TypeError):
        pass
        
    # 2. Handle combined strings like "April 2026" or "JUNE 2026"
    combined = month_raw if ' ' in month_raw else f"{month_raw} {year_raw}"
    parts = combined.split()
    
    if len(parts) >= 1:
        name_part = parts[0].lower()
        months_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        for k, v in months_map.items():
            if name_part.startswith(k):
                m = v
                break
                
    if len(parts) >= 2:
        try:
            y = int(parts[-1])
        except:
            pass
            
    return m, y

def get_company_for_user(django_user):
    """
    Safely retrieve the Company associated with the logged-in Django user.
    Handles both Company Owners and Staff Members (Employees).
    """
    # 1. Primary Owner lookup
    owner_company = Company.objects.filter(owner=django_user).first()
    if owner_company:
        return owner_company
    
    # 2. Staff/Employee lookup (via ERPUser profile)
    erp_profile = ERPUser.objects.filter(django_user=django_user).first()
    if erp_profile:
        return erp_profile.company
        
    return None
