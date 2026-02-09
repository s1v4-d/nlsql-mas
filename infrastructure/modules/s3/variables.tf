# S3 Data Lake Module Variables

# Input variables for S3 bucket configuration

variable "project_name" {
  type        = string
  description = "Project identifier used in resource naming"
}

variable "environment" {
  type        = string
  description = "Environment name"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,9}$", var.environment))
    error_message = "Environment must be 1-10 lowercase alphanumeric characters or hyphens."
  }
}

variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-east-1"
}

variable "aws_account_id" {
  type        = string
  description = "AWS Account ID for globally unique bucket naming"
}

variable "enable_versioning" {
  type        = bool
  description = "Enable S3 versioning (false recommended for Parquet analytics)"
  default     = false
}

variable "enable_intelligent_tiering" {
  type        = bool
  description = "Use Intelligent Tiering instead of manual lifecycle transitions"
  default     = true
}

variable "archive_access_days" {
  type        = number
  description = "Days until data moves to Archive Access tier (Intelligent Tiering)"
  default     = 90
}

variable "deep_archive_access_days" {
  type        = number
  description = "Days until data moves to Deep Archive Access tier"
  default     = 180
}

variable "export_expiration_days" {
  type        = number
  description = "Days until export files expire"
  default     = 7
}

variable "log_retention_days" {
  type        = number
  description = "Days to retain access logs before archiving"
  default     = 365
}

variable "use_customer_managed_key" {
  type        = bool
  description = "Use CMK instead of AWS-managed key for encryption"
  default     = true
}

variable "kms_key_deletion_window" {
  type        = number
  description = "KMS key deletion waiting period in days (7-30)"
  default     = 30

  validation {
    condition     = var.kms_key_deletion_window >= 7 && var.kms_key_deletion_window <= 30
    error_message = "KMS key deletion window must be between 7 and 30 days"
  }
}

variable "ecs_task_role_arn" {
  type        = string
  description = "ARN of ECS task role that needs S3 access"
  default     = null
}

variable "vpc_endpoint_id" {
  type        = string
  description = "S3 VPC Gateway Endpoint ID for bucket policy restrictions"
  default     = null
}

variable "restrict_to_vpc_endpoint" {
  type        = bool
  description = "Only allow access via VPC endpoint (enhanced security)"
  default     = false
}

variable "enable_access_logging" {
  type        = bool
  description = "Enable S3 access logging to separate bucket"
  default     = true
}

variable "force_destroy" {
  type        = bool
  description = "Allow bucket deletion even with objects (dev only)"
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Common tags for all resources"
  default     = {}
}
