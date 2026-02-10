variable "project_name" {
  type        = string
  description = "Project identifier"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, prod)"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for all resources"
  default     = {}
}

# KMS

variable "create_kms_key" {
  type        = bool
  description = "Create a dedicated KMS key for compliance resources"
  default     = true
}

variable "kms_key_arn" {
  type        = string
  description = "ARN of existing KMS key (if create_kms_key is false)"
  default     = null
}

# CloudTrail

variable "enable_cloudtrail" {
  type        = bool
  description = "Enable CloudTrail"
  default     = true
}

variable "enable_multi_region_trail" {
  type        = bool
  description = "Enable multi-region CloudTrail"
  default     = true
}

variable "enable_cloudwatch_logs" {
  type        = bool
  description = "Enable CloudWatch Logs integration for CloudTrail"
  default     = true
}

variable "cloudtrail_log_retention_days" {
  type        = number
  description = "Number of days to retain CloudTrail logs in S3"
  default     = 365
}

variable "cloudwatch_log_retention_days" {
  type        = number
  description = "Number of days to retain CloudWatch logs"
  default     = 90
}

variable "s3_data_event_bucket_arns" {
  type        = list(string)
  description = "List of S3 bucket ARNs to log data events for"
  default     = []
}

variable "enable_insights" {
  type        = bool
  description = "Enable CloudTrail Insights for anomaly detection"
  default     = true
}

# GuardDuty

variable "enable_guardduty" {
  type        = bool
  description = "Enable GuardDuty threat detection"
  default     = true
}

variable "guardduty_finding_frequency" {
  type        = string
  description = "GuardDuty finding publishing frequency"
  default     = "FIFTEEN_MINUTES"

  validation {
    condition     = contains(["FIFTEEN_MINUTES", "ONE_HOUR", "SIX_HOURS"], var.guardduty_finding_frequency)
    error_message = "Valid values: FIFTEEN_MINUTES, ONE_HOUR, SIX_HOURS"
  }
}

variable "guardduty_severity_threshold" {
  type        = number
  description = "Minimum severity level for GuardDuty alerts (1-10)"
  default     = 7

  validation {
    condition     = var.guardduty_severity_threshold >= 1 && var.guardduty_severity_threshold <= 10
    error_message = "Severity threshold must be between 1 and 10"
  }
}

variable "enable_eks_guardduty" {
  type        = bool
  description = "Enable GuardDuty EKS audit log monitoring"
  default     = false
}

# AWS Config

variable "enable_config" {
  type        = bool
  description = "Enable AWS Config for compliance monitoring"
  default     = true
}
