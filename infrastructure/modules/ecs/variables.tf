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
  description = "VPC ID for ECS resources"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ALB"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for ALB"
  type        = string
}

variable "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for encryption (ECR, logs, secrets)"
  type        = string
  default     = null
}

variable "services" {
  description = "Map of ECS services to create"
  type = map(object({
    cpu                   = number
    memory                = number
    container_port        = number
    health_check_path     = string
    min_capacity          = number
    max_capacity          = number
    desired_count         = number
    environment_variables = optional(map(string), {})
    secrets               = optional(map(string), {})
  }))

  default = {
    api = {
      cpu               = 512
      memory            = 1024
      container_port    = 8000
      health_check_path = "/health"
      min_capacity      = 1
      max_capacity      = 4
      desired_count     = 1
    }
    streamlit = {
      cpu               = 512
      memory            = 1024
      container_port    = 8501
      health_check_path = "/_stcore/health"
      min_capacity      = 1
      max_capacity      = 2
      desired_count     = 1
    }
  }
}

variable "container_images" {
  description = "Container image URIs for each service (defaults to ECR repos)"
  type        = map(string)
  default     = {}
}

variable "enable_https" {
  description = "Enable HTTPS listener (requires certificate_arn)"
  type        = bool
  default     = false
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
  default     = null
}

variable "alb_idle_timeout" {
  description = "ALB idle timeout in seconds (increase for LLM streaming)"
  type        = number
  default     = 120
}

variable "enable_alb_access_logs" {
  description = "Enable ALB access logging to S3"
  type        = bool
  default     = false
}

variable "alb_access_logs_bucket" {
  description = "S3 bucket for ALB access logs"
  type        = string
  default     = null
}

variable "cpu_target_value" {
  description = "Target CPU utilization percentage for auto-scaling"
  type        = number
  default     = 70
}

variable "memory_target_value" {
  description = "Target memory utilization percentage for auto-scaling"
  type        = number
  default     = 80
}

variable "scale_in_cooldown" {
  description = "Scale-in cooldown period in seconds"
  type        = number
  default     = 300
}

variable "scale_out_cooldown" {
  description = "Scale-out cooldown period in seconds"
  type        = number
  default     = 60
}

variable "use_fargate_spot" {
  description = "Use Fargate Spot for cost savings"
  type        = bool
  default     = true
}

variable "fargate_weight" {
  description = "Weight for FARGATE capacity provider"
  type        = number
  default     = 70
}

variable "fargate_spot_weight" {
  description = "Weight for FARGATE_SPOT capacity provider"
  type        = number
  default     = 30
}

variable "fargate_base" {
  description = "Minimum number of tasks on FARGATE (not Spot)"
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch Logs retention period."
  }
}

variable "s3_data_bucket_arn" {
  description = "S3 bucket ARN for data access (DuckDB + Parquet)"
  type        = string
  default     = null
}

variable "enable_execute_command" {
  description = "Enable ECS Exec for container debugging"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "create_app_secrets" {
  description = "Create application secrets in Secrets Manager"
  type        = bool
  default     = true
}

variable "openai_api_key" {
  description = "OpenAI API key (store in tfvars or TF_VAR_openai_api_key)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "api_key" {
  description = "API key for user authentication"
  type        = string
  default     = ""
  sensitive   = true
}

variable "admin_api_key" {
  description = "API key for admin endpoints"
  type        = string
  default     = ""
  sensitive   = true
}
