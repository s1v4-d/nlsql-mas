# S3 Data Lake Module Outputs
# ----------------------------
# Exported values for consumption by other modules

# Data Lake Bucket
output "data_lake_bucket_id" {
  description = "ID of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.id
}

output "data_lake_bucket_arn" {
  description = "ARN of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.arn
}

output "data_lake_bucket_name" {
  description = "Name of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.bucket
}

output "data_lake_bucket_domain_name" {
  description = "Domain name of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.bucket_domain_name
}

output "data_lake_bucket_regional_domain_name" {
  description = "Regional domain name of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.bucket_regional_domain_name
}

# Access Logs Bucket
output "logs_bucket_id" {
  description = "ID of the access logs S3 bucket"
  value       = var.enable_access_logging ? aws_s3_bucket.logs[0].id : null
}

output "logs_bucket_arn" {
  description = "ARN of the access logs S3 bucket"
  value       = var.enable_access_logging ? aws_s3_bucket.logs[0].arn : null
}

# KMS Key
output "kms_key_id" {
  description = "ID of the KMS key for S3 encryption"
  value       = var.use_customer_managed_key ? aws_kms_key.s3[0].id : null
}

output "kms_key_arn" {
  description = "ARN of the KMS key for S3 encryption"
  value       = var.use_customer_managed_key ? aws_kms_key.s3[0].arn : null
}

output "kms_key_alias" {
  description = "Alias of the KMS key for S3 encryption"
  value       = var.use_customer_managed_key ? aws_kms_alias.s3[0].name : null
}

# IAM Policy
output "read_policy_arn" {
  description = "ARN of the IAM policy for read access to data lake"
  value       = aws_iam_policy.s3_read.arn
}

output "write_policy_arn" {
  description = "ARN of the IAM policy for write access to exports"
  value       = aws_iam_policy.s3_write.arn
}

# S3 Prefixes
output "data_prefix" {
  description = "S3 prefix for processed Parquet data"
  value       = "processed/"
}

output "exports_prefix" {
  description = "S3 prefix for user exports"
  value       = "exports/"
}

output "metadata_prefix" {
  description = "S3 prefix for metadata and schema cache"
  value       = "metadata/"
}
