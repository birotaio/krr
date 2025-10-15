# Common KRR parameters
KRR_HPA = pipenv run krr hpa -r Deployment --low-usage-percentile 40 --cpu_limit_percent 200 --memory_limit_percent 300 --max_replicas 6 --cpu-min 10 --mem-min 100 --formatter ready-to-deploy
KRR_SIMPLE = pipenv run krr basic --cpu-min 10 --mem-min 100 --formatter ready-to-deploy

SELECTOR = zoov.io/team=backend

HPA_DEPLOYMENTS = alert area auth bike entity gateway-maas gateway-partner gateway-product gateway-sabiweb gateway-wirma healthcheck integration migrations notifier payment raw-data rental station ticket user
SIMPLE_DEPLOYMENTS = event-data-transformer gateway-omni gbfs history mds webhook

# Production configuration
PROD_CLUSTER = prod
PROD_DEPLOYMENT_PATH = zoov-prod

# Staging configuration
STAGING_CLUSTER = staging
STAGING_DEPLOYMENT_PATH = zoov-staging

# Partners configuration
PARTNERS_CLUSTER = partners
PARTNERS_DEPLOYMENT_PATH = zoov-partners-prod


# Generic update method
define update-environment
	$(KRR_HPA) -c $(CLUSTER) -s $(SELECTOR) --fileoutput generated/hpa_$(CLUSTER).yaml
	python3 script/update_deployment.py ../generated/hpa_$(CLUSTER).yaml $(DEPLOYMENT_PATH) --include $(subst $(space),$(comma),$(HPA_DEPLOYMENTS))

	$(KRR_SIMPLE) -c $(CLUSTER) -s $(SELECTOR) --fileoutput generated/simple_$(CLUSTER).yaml
	python3 script/update_deployment.py ../generated/simple_$(CLUSTER).yaml $(DEPLOYMENT_PATH) --include $(subst $(space),$(comma),$(SIMPLE_DEPLOYMENTS))
endef

# Helper variables for list conversion
comma := ,
space := $(empty) $(empty)

update-prod:
	$(MAKE) run-update CLUSTER=$(PROD_CLUSTER) DEPLOYMENT_PATH=$(PROD_DEPLOYMENT_PATH)

update-staging:
	$(MAKE) run-update CLUSTER=$(STAGING_CLUSTER) DEPLOYMENT_PATH=$(STAGING_DEPLOYMENT_PATH)

update-partners:
	$(MAKE) run-update CLUSTER=$(PARTNERS_CLUSTER) DEPLOYMENT_PATH=$(PARTNERS_DEPLOYMENT_PATH)

run-update:
	$(update-environment)

update-all: update-prod update-staging update-partners
