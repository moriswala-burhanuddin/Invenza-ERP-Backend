import os
import re

file_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\backend_core\settings.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Make sure logs directory exists
logs_dir = r'd:\paid-erp\invenza-erp\invenza-website\backend\logs'
os.makedirs(logs_dir, exist_ok=True)

# Add logging config if not already there
if 'LOGGING = {' not in content:
    logging_config = '''

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'sync_file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'sync.log'),
            'formatter': 'verbose',
        },
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'erp_core.sync': {
            'handlers': ['sync_file', 'console'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
'''
    content += logging_config
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Logging config added to settings.py')
else:
    print('LOGGING already exists in settings.py')
