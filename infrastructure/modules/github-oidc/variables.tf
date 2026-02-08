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

variable "github_org" {
  description = "GitHub organization or user name"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "allowed_branches" {
  description = "List of branch patterns allowed to assume the role (e.g., ['main', 'refs/heads/main'])"
  type        = list(string)
  default     = ["*"]
}

variable "terraform_state_bucket" {
  description = "S3 bucket for Terraform state"
  type        = string
}

variable "terraform_lock_table" {
  description = "DynamoDB table for Terraform state locking"
  type        = string
  default     = "terraform-locks"
}

variable "ecr_repository_arns" {
  description = "List of ECR repository ARNs to grant push access"
  type        = list(string)
  default     = []
}

variable "ecs_cluster_arns" {
  description = "List of ECS cluster ARNs to grant deployment access"
  type        = list(string)
  default     = []
}

variable "s3_data_bucket_arn" {
  description = "S3 data bucket ARN for read access"
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
