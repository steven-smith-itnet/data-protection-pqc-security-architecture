# Label-driven encryption for Amazon S3.
#
# Flow: dataset tags -> protection profile -> key and bucket settings.
#   pp1  SSE-S3 (AWS owned key), versioning, public access blocked, TLS only.
#   pp2  SSE-KMS with the data domain's customer managed KMS key, S3 Bucket
#        Keys, bucket policy denying uploads that name any other key.
#   pp3  pp2 plus: the key lives in a custom key store (CloudHSM or XKS) when
#        custom_key_store_id is set, and uploads must use SSE-KMS explicitly.
#
# One KMS key per data domain keeps blast radius and access reviews aligned
# with data ownership. Key admins and key users are separate statements.

locals {
  # Domains whose keys must go to the custom key store (any pp3 dataset).
  pp3_domains = toset([for d in local.datasets : d.data_domain if d.protection_profile == "pp3"])

  domain_tags = {
    for dom in local.cmk_domains : dom => {
      "data-classification" = local.domain_classification[dom]
      "data-domain"         = dom
      "protection-profile"  = contains(local.pp3_domains, dom) ? "pp3" : "pp2"
      "environment"         = var.environment
    }
  }
}

data "aws_iam_policy_document" "key" {
  for_each = local.cmk_domains

  statement {
    sid       = "KeyAdministration"
    effect    = "Allow"
    actions   = ["kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*", "kms:Put*", "kms:Update*", "kms:Revoke*", "kms:Disable*", "kms:Get*", "kms:TagResource", "kms:UntagResource", "kms:RotateKeyOnDemand", "kms:CancelKeyDeletion"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = var.key_admin_arns
    }
  }

  # Admins cannot use the key for data. Deletion is not granted to admins:
  # kms:ScheduleKeyDeletion is granted only to the break-glass role here, and
  # the organization SCP in code/policy/aws-scp/ denies it to everyone else.
  statement {
    sid       = "BreakGlassKeyDeletion"
    effect    = "Allow"
    actions   = ["kms:ScheduleKeyDeletion", "kms:CancelKeyDeletion", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = [var.break_glass_role_arn]
    }
  }

  dynamic "statement" {
    for_each = length(lookup(var.key_user_arns, each.key, [])) > 0 ? [1] : []
    content {
      sid       = "KeyUseThroughS3Only"
      effect    = "Allow"
      actions   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
      resources = ["*"]
      principals {
        type        = "AWS"
        identifiers = var.key_user_arns[each.key]
      }
      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["s3.${var.region}.amazonaws.com"]
      }
      condition {
        test     = "StringEquals"
        variable = "kms:CallerAccount"
        values   = [var.account_id]
      }
    }
  }
}

resource "aws_kms_key" "domain" {
  for_each = local.cmk_domains

  description             = "${var.name_prefix} ${var.environment} ${each.key} data key"
  key_usage               = "ENCRYPT_DECRYPT"
  enable_key_rotation     = true
  rotation_period_in_days = var.rotation_period_in_days
  deletion_window_in_days = var.deletion_window_in_days
  custom_key_store_id     = contains(local.pp3_domains, each.key) ? var.custom_key_store_id : null
  policy                  = data.aws_iam_policy_document.key[each.key].json
  tags                    = local.domain_tags[each.key]
}

resource "aws_kms_alias" "domain" {
  for_each = local.cmk_domains

  name          = "alias/${var.name_prefix}-${var.environment}-${each.key}"
  target_key_id = aws_kms_key.domain[each.key].key_id
}

resource "aws_s3_bucket" "dataset" {
  for_each = local.datasets

  bucket = "${var.name_prefix}-${var.environment}-${each.key}"
  tags   = local.dataset_tags[each.key]
}

resource "aws_s3_bucket_public_access_block" "dataset" {
  for_each = local.datasets

  bucket                  = aws_s3_bucket.dataset[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "dataset" {
  for_each = local.datasets

  bucket = aws_s3_bucket.dataset[each.key].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "dataset" {
  for_each = local.datasets

  bucket = aws_s3_bucket.dataset[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dataset" {
  for_each = local.datasets

  bucket = aws_s3_bucket.dataset[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = each.value.protection_profile == "pp1" ? "AES256" : "aws:kms"
      kms_master_key_id = each.value.protection_profile == "pp1" ? null : aws_kms_key.domain[each.value.data_domain].arn
    }
    bucket_key_enabled = each.value.protection_profile != "pp1"
  }
}

data "aws_iam_policy_document" "bucket" {
  for_each = local.datasets

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.dataset[each.key].arn, "${aws_s3_bucket.dataset[each.key].arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid       = "DenyTlsBelow12"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.dataset[each.key].arn, "${aws_s3_bucket.dataset[each.key].arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "NumericLessThan"
      variable = "s3:TlsVersion"
      values   = ["1.2"]
    }
  }

  dynamic "statement" {
    for_each = each.value.protection_profile == "pp1" ? [] : [1]
    content {
      sid       = "DenyOtherKmsKeys"
      effect    = "Deny"
      actions   = ["s3:PutObject"]
      resources = ["${aws_s3_bucket.dataset[each.key].arn}/*"]
      principals {
        type        = "*"
        identifiers = ["*"]
      }
      condition {
        test     = "StringNotEqualsIfExists"
        variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
        values   = [aws_kms_key.domain[each.value.data_domain].arn]
      }
    }
  }

  dynamic "statement" {
    for_each = each.value.protection_profile == "pp3" ? [1] : []
    content {
      sid       = "RequireSseKmsHeader"
      effect    = "Deny"
      actions   = ["s3:PutObject"]
      resources = ["${aws_s3_bucket.dataset[each.key].arn}/*"]
      principals {
        type        = "*"
        identifiers = ["*"]
      }
      condition {
        test     = "StringNotEquals"
        variable = "s3:x-amz-server-side-encryption"
        values   = ["aws:kms"]
      }
    }
  }
}

resource "aws_s3_bucket_policy" "dataset" {
  for_each = local.datasets

  bucket = aws_s3_bucket.dataset[each.key].id
  policy = data.aws_iam_policy_document.bucket[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.dataset]
}
