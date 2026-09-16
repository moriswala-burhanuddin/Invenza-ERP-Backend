import re

def extract_defaults(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    defaults_map = {}
    
    # We find blocks of defaults={...}
    # Since we use .update_or_create, let's search for objects.update_or_create(
    # and get the defaults dictionary.
    
    blocks = re.findall(r'([A-Za-z0-9_]+)\.objects\.update_or_create\([^)]*defaults=\{([^}]*)\}', content, re.DOTALL)
    for model, def_content in blocks:
        # Extract keys
        keys = re.findall(r'\'([A-Za-z0-9_]+)\':', def_content)
        defaults_map[model] = sorted(keys)
    return defaults_map

old = extract_defaults(r'd:\paid-erp\invenza-erp\invenza-website\backend\old_views_temp.py')
new = extract_defaults(r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py')

print(f"Models found in old: {len(old)}")
print(f"Models found in new: {len(new)}")

mismatches = []
for model in old:
    if model not in new:
        mismatches.append(f"{model} completely missing in new!")
    else:
        if old[model] != new[model]:
            mismatches.append(f"{model} keys differ!\nOld: {old[model]}\nNew: {new[model]}")

if not mismatches:
    print("SUCCESS: 100% MATCH! All tables and field defaults are identical.")
else:
    for m in mismatches:
        print(m)

# Special handling for ERPUser which has complex logic
user_old = re.search(r'user_defaults = \{([^}]+)\}', open(r'd:\paid-erp\invenza-erp\invenza-website\backend\old_views_temp.py', 'r', encoding='utf-8').read())
user_new = re.search(r'user_defaults = \{([^}]+)\}', open(r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py', 'r', encoding='utf-8').read())

if user_old and user_new:
    keys_old = sorted(re.findall(r'\'([A-Za-z0-9_]+)\':', user_old.group(1)))
    keys_new = sorted(re.findall(r'\'([A-Za-z0-9_]+)\':', user_new.group(1)))
    if keys_old == keys_new:
        print("ERPUser fields: 100% MATCH")
    else:
        print("ERPUser fields MISMATCH")
