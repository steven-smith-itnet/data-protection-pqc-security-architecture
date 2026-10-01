# DELIBERATELY NON-COMPLIANT configuration. It exists only to produce a real
# Terraform plan JSON that the OPA policies in code/policy/opa/ must reject.
# Never apply it. Same offline provider settings as ../offline-plan.

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

# Violation: KMS key without rotation and without the data-classification tag.
resource "aws_kms_key" "unrotated" {
  description         = "key without rotation"
  enable_key_rotation = false
}

# Violation: restricted payment data on pp2, encrypted only with SSE-S3.
resource "aws_s3_bucket" "cards" {
  bucket = "hosp-dp-dev-card-exports"
  tags = {
    "data-classification" = "restricted"
    "protection-profile"  = "pp2"
    "data-domain"         = "payment"
    "regulatory-scope"    = "pci"
    "data-owner"          = "payments-team"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cards" {
  bucket = aws_s3_bucket.cards.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Violation: public access block switched off.
resource "aws_s3_bucket_public_access_block" "cards" {
  bucket                  = aws_s3_bucket.cards.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# Violation: bucket with no classification tag, a public-read ACL, and no
# public access block at all.
resource "aws_s3_bucket" "untagged" {
  bucket = "hosp-dp-dev-scratch"
}

resource "aws_s3_bucket_acl" "untagged" {
  bucket = aws_s3_bucket.untagged.id
  acl    = "public-read"
}
