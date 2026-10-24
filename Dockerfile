FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY ui/requirements.txt /app/ui/requirements.txt
RUN pip install --no-cache-dir -r /app/ui/requirements.txt
COPY bss_core.py business_rules.py business_rules.json catalogue_assistant.py catalogue_core.py catalogue.json contract_core.py cpq_core.py cpq_policy.json customer_core.py customers.json email_core.py order_core.py product_constraints.py rule_assistant.py state_store.py /app/
COPY ui /app/ui
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "120", "ui.app:app"]
