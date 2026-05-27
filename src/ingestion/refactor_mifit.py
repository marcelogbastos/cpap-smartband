import re

with open('d:/1 Organizados/Projetos/CPAP-ResMed/src/ingestion/mifitness_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add logging
content = content.replace('import argparse', 'import argparse\nimport logging\n\nlogging.basicConfig(level=logging.INFO, format=\'%(asctime)s - %(levelname)s - %(message)s\')\nlogger = logging.getLogger(__name__)')

# Replace print with logger.info/warning/error
content = content.replace('print("  \\u26a0\\ufe0f', 'logger.warning("')
content = content.replace('print("\\u274c', 'logger.error("')
content = content.replace('print(', 'logger.info(')

# Replace hardcoded Marcelo
content = content.replace("'patient': 'Marcelo'", "'patient': self.patient_slug.title()")
content = content.replace("df['patient'] = 'Marcelo'", "df['patient'] = self.patient_slug.title()")

with open('d:/1 Organizados/Projetos/CPAP-ResMed/src/ingestion/mifitness_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
