variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.project_name))
    error_message = "Project name must be 3-25 lowercase alphanumeric characters or hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "Environment name"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,9}$", var.environment))
    error_message = "Environment must be 1-10 lowercase alphanumeric characters or hyphens."
  }
}

variable "vpc_id" {
  description = "VPC ID for Aurora cluster"
  type        = string
}

variable "database_subnet_ids" {
  description = "List of database subnet IDs for Aurora"
  type        = list(string)
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group ID for ECS tasks (allowed to connect)"
  type        = string
}

variable "aurora_security_group_id" {
  description = "Security group ID for Aurora cluster"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for encryption (storage, secrets)"
  type        = string
  default     = null
}

variable "database_name" {
  description = "Name of the default database"
  type        = string
  default     = "retail_insights"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.database_name))
    error_message = "Database name must be 1-63 lowercase alphanumeric characters or underscores, starting with a letter."
  }
}

variable "master_username" {
  description = "Master username for the database"
  type        = string
  default     = "postgres_admin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.master_username))
    error_message = "Master username must be 1-63 lowercase alphanumeric characters or underscores, starting with a letter."
  }
}

variable "engine_version" {
  description = "Aurora PostgreSQL engine version"
  type        = string
  default     = "16.4"
}

variable "port" {
  description = "Database port"
  type        = number
  default     = 5432
}

variable "min_capacity" {
  description = "Minimum ACU capacity (0.5 = scales to near-zero)"
  type        = number
  default     = 0.5

  validation {
    condition     = var.min_capacity >= 0.5 && var.min_capacity <= 128
    error_message = "Minimum capacity must be between 0.5 and 128 ACUs."
  }
}

variable "max_capacity" {
  description = "Maximum ACU capacity"
  type        = number
  default     = 4

  validation {
    condition     = var.max_capacity >= 1 && var.max_capacity <= 128
    error_message = "Maximum capacity must be between 1 and 128 ACUs."
  }
}

variable "storage_type" {
  description = "Storage type (aurora for standard, aurora-iopt1 for I/O optimized)"
  type        = string
  default     = "aurora"

  validation {
    condition     = contains(["aurora", "aurora-iopt1"], var.storage_type)
    error_message = "Storage type must be aurora or aurora-iopt1."
  }
}

variable "backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_period >= 1 && var.backup_retention_period <= 35
    error_message = "Backup retention must be between 1 and 35 days."
  }
}

variable "preferred_backup_window" {
  description = "Preferred backup window (UTC)"
  type        = string
  default     = "02:00-04:00"
}

variable "preferred_maintenance_window" {
  description = "Preferred maintenance window (UTC)"
  type        = string
  default     = "sun:04:00-sun:05:00"
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on deletion"
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = false
}

variable "reader_count" {
  description = "Number of read replicas (additional instances)"
  type        = number
  default     = 0

  validation {
    condition     = var.reader_count >= 0 && var.reader_count <= 15
    error_message = "Reader count must be between 0 and 15."
  }
}

variable "performance_insights_enabled" {
  description = "Enable Performance Insights"
  type        = bool
  default     = true
}

variable "performance_insights_retention" {
  description = "Performance Insights retention period (7 for free tier, 731 for 2 years)"
  type        = number
  default     = 7

  validation {
    condition     = contains([7, 31, 62, 93, 124, 155, 186, 217, 248, 279, 310, 341, 372, 403, 434, 465, 496, 527, 558, 589, 620, 651, 682, 713, 731], var.performance_insights_retention)
    error_message = "Performance Insights retention must be 7 days (free) or up to 731 days (paid)."
  }
}

variable "enhanced_monitoring_interval" {
  description = "Enhanced monitoring interval in seconds (0 to disable)"
  type        = number
  default     = 60

  validation {
    condition     = contains([0, 1, 5, 10, 15, 30, 60], var.enhanced_monitoring_interval)
    error_message = "Enhanced monitoring interval must be 0, 1, 5, 10, 15, 30, or 60 seconds."
  }
}

variable "iam_database_authentication_enabled" {
  description = "Enable IAM database authentication"
  type        = bool
  default     = true
}

variable "create_app_user_secret" {
  description = "Create application user credentials in Secrets Manager"
  type        = bool
  default     = true
}

variable "app_username" {
  description = "Application database username"
  type        = string
  default     = "app_user"
}

variable "enable_pgvector" {
  description = "Enable pgvector extension configuration in parameter group"
  type        = bool
  default     = true
}

variable "enabled_cloudwatch_logs_exports" {
  description = "List of log types to export to CloudWatch"
  type        = list(string)
  default     = ["postgresql"]
}

variable "log_min_duration_statement" {
  description = "Minimum duration (ms) for logging slow queries (-1 to disable)"
  type        = number
  default     = 1000
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}

variable "apply_immediately" {
  description = "Apply changes immediately (use with caution in prod)"
  type        = bool
  default     = false
}
