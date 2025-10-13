# Common KRR parameters
KRR_BASE_CMD = pipenv run krr hpa -r Deployment --low-usage-percentile 40 --cpu_limit_percent 200 --memory_limit_percent 300 --max_replicas 6 --cpu-min 10 --mem-min 100 --formatter ready-to-deploy

# Production configuration
PROD_CLUSTER = prod
PROD_SELECTOR = zoov.io/team=backend
PROD_OUTPUT = generated/prod.yaml
PROD_DEPLOYMENT_PATH = zoov-prod

# Staging configuration
STAGING_CLUSTER = staging
STAGING_SELECTOR = zoov.io/team=backend
STAGING_OUTPUT = generated/staging.yaml
STAGING_DEPLOYMENT_PATH = zoov-staging

# Partners configuration
PARTNERS_CLUSTER = partners
PARTNERS_SELECTOR = zoov.io/team=backend
PARTNERS_OUTPUT = generated/partners.yaml
PARTNERS_DEPLOYMENT_PATH = zoov-partners-prod


update-prod:
	$(KRR_BASE_CMD) -c $(PROD_CLUSTER) -s $(PROD_SELECTOR) --fileoutput $(PROD_OUTPUT)
	python3 script/update_deployment.py ../$(PROD_OUTPUT) $(PROD_DEPLOYMENT_PATH)

update-staging:
	$(KRR_BASE_CMD) -c $(STAGING_CLUSTER) -s $(STAGING_SELECTOR) --fileoutput $(STAGING_OUTPUT)
	python3 script/update_deployment.py ../$(STAGING_OUTPUT) $(STAGING_DEPLOYMENT_PATH)

update-partners:
	$(KRR_BASE_CMD) -c $(PARTNERS_CLUSTER) -s $(PARTNERS_SELECTOR) --fileoutput $(PARTNERS_OUTPUT)
	python3 script/update_deployment.py ../$(PARTNERS_OUTPUT) $(PARTNERS_DEPLOYMENT_PATH)

update-all: update-prod update-staging update-partners
