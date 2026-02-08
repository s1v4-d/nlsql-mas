variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.project_name))
    error_message = "Project name must be 3-25 lowercase alphanumeric characters or hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster to monitor"
  type        = string
}

variable "ecs_service_name" {
  description = "Name of the ECS service to monitor"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch retention value."
  }
}

variable "kms_key_arn" {
  description = "KMS key ARN for encrypting logs and metrics"
  type        = string
  default     = null
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  type        = string
  default     = null
}

variable "enable_xray" {
  description = "Enable X-Ray tracing integration"
  type        = bool
  default     = true
}

variable "api_latency_threshold_ms" {
  description = "Threshold for API latency alarm in milliseconds"
  type        = number
  default     = 3000
}

variable "error_rate_threshold_percent" {
  description = "Threshold for error rate alarm as percentage"
  type        = number
  default     = 5
}

variable "cpu_utilization_threshold" {
  description = "Threshold for CPU utilization alarm as percentage"
  type        = number
  default     = 80
}

variable "memory_utilization_threshold" {
  description = "Threshold for memory utilization alarm as percentage"
  type        = number
  default     = 80
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
