output "kms_key_arns" {
  description = "Customer managed KMS key ARN per data domain."
  value       = { for dom, k in aws_kms_key.domain : dom => k.arn }
}

output "buckets" {
  description = "Per dataset: bucket name, protection profile, and the key used (null means SSE-S3)."
  value = {
    for name, d in local.datasets : name => {
      bucket             = aws_s3_bucket.dataset[name].bucket
      protection_profile = d.protection_profile
      kms_key_arn        = d.protection_profile == "pp1" ? null : aws_kms_key.domain[d.data_domain].arn
      tags               = local.dataset_tags[name]
    }
  }
}
