file_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\utils.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('"\""', '"""')
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed utils.py')
