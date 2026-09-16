import re

file_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace any number of leading spaces followed by ar = payload_data with exactly 4 spaces
content = re.sub(r'\n\s+([a-zA-Z0-9_]+) = payload_data\n', r'\n    \1 = payload_data\n', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Indentation fixed")
