# KMS
output "kms_key_arn" {
  description = "ARN of the compliance KMS key"
  value       = var.create_kms_key ? aws_kms_key.compliance[0].arn : var.kms_key_arn
}

output "kms_key_id" {
  description = "ID of the compliance KMS key"
  value       = var.create_kms_key ? aws_kms_key.compliance[0].id : null
}

# CloudTrail
output "cloudtrail_arn" {
  description = "ARN of the CloudTrail"
  value       = var.enable_cloudtrail ? aws_cloudtrail.main[0].arn : null
}

output "cloudtrail_s3_bucket_name" {
  description = "S3 bucket name for CloudTrail logs"
  value       = var.enable_cloudtrail ? aws_s3_bucket.cloudtrail[0].id : null
}

output "cloudtrail_cloudwatch_log_group_arn" {
  description = "CloudWatch log group ARN for CloudTrail"
  value       = var.enable_cloudtrail && var.enable_cloudwatch_logs ? aws_cloudwatch_log_group.cloudtrail[0].arn : null
}

# GuardDuty
output "guardduty_detector_id" {
  description = "GuardDuty detector ID"
  value       = var.enable_guardduty ? aws_guardduty_detector.main[0].id : null
}

output "security_alerts_sns_topic_arn" {
  description = "SNS topic ARN for security alerts"
  value       = var.enable_guardduty ? aws_sns_topic.security_alerts[0].arn : null
}

# AWS Config
output "config_recorder_id" {
  description = "AWS Config recorder ID"
  value       = var.enable_config ? aws_config_configuration_recorder.main[0].id : null
}

output "config_s3_bucket_name" {
  description = "S3 bucket name for AWS Config"
  value       = var.enable_config ? aws_s3_bucket.config[0].id : null
}
