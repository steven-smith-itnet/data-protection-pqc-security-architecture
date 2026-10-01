# Offline plan harness: produces a real Terraform plan JSON for the OPA tests
# in code/policy/opa/ without any AWS account. The provider is configured with
# placeholder credentials and every call that would reach AWS is skipped, so
# `terraform plan` works but `terraform apply` must never be run from here.
#
#   terraform init -backend=false
#   terraform plan -refresh=false -out=tfplan
#   terraform show -json tfplan > ../../../../policy/opa/fixtures/aws_plan_compliant.json

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }
}

provider "aws" {
  region                      = "eu-west-1"
  access_key                  = "placeholder-not-a-key"
  secret_key                  = "placeholder-not-a-key"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}

module "data_protection" {
  source = "../.."

  name_prefix          = "hosp-dp"
  environment          = "dev"
  account_id           = "111122223333"
  region               = "eu-west-1"
  key_admin_arns       = ["arn:aws:iam::111122223333:role/key-admin"]
  break_glass_role_arn = "arn:aws:iam::111122223333:role/break-glass"
  key_user_arns = {
    payment = ["arn:aws:iam::111122223333:role/payment-settlement"]
    guest   = ["arn:aws:iam::111122223333:role/guest-platform"]
  }

  datasets = {
    "card-vault-backup" = {
      data_domain         = "payment"
      data_classification = "restricted"
      regulatory_scope    = "pci_gdpr"
      data_owner          = "payments-team"
      data_residency      = "eu"
      retention_class     = "r1y"
    }
    "guest-profiles" = {
      data_domain         = "guest"
      data_classification = "confidential"
      regulatory_scope    = "gdpr"
      data_owner          = "guest-platform"
      data_residency      = "eu"
      retention_class     = "r3y"
    }
    "property-brochures" = {
      data_domain         = "operations"
      data_classification = "public"
      regulatory_scope    = "none"
      data_owner          = "marketing-ops"
      data_residency      = "global"
      retention_class     = "r1y"
    }
  }
}

output "buckets" {
  value = module.data_protection.buckets
}
