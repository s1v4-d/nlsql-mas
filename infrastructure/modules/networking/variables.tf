# Networking Module Variables

# Input variables for VPC, subnets, NAT Gateway, and VPC endpoints

variable "project_name" {
  type        = string
  description = "Project identifier used in resource naming"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.project_name))
    error_message = "Project name must be lowercase alphanumeric with hyphens, 3-21 chars"
  }
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

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for VPC"
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid IPv4 CIDR block"
  }
}

variable "availability_zones_count" {
  type        = number
  description = "Number of AZs to deploy across (2 or 3)"
  default     = 3

  validation {
    condition     = var.availability_zones_count >= 2 && var.availability_zones_count <= 3
    error_message = "AZ count must be 2 or 3"
  }
}

variable "single_nat_gateway" {
  type        = bool
  description = "Use single NAT Gateway (cost savings for non-prod)"
  default     = true
}

variable "enable_vpc_flow_logs" {
  type        = bool
  description = "Enable VPC Flow Logs"
  default     = true
}

variable "flow_log_retention_days" {
  type        = number
  description = "CloudWatch Log retention for VPC Flow Logs"
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.flow_log_retention_days)
    error_message = "Retention must be a valid CloudWatch Logs retention value"
  }
}

variable "enable_vpc_endpoints" {
  type        = bool
  description = "Create VPC endpoints for AWS services (ECR, Secrets Manager, S3)"
  default     = true
}

variable "enable_dns_hostnames" {
  type        = bool
  description = "Enable DNS hostnames in VPC"
  default     = true
}

variable "enable_dns_support" {
  type        = bool
  description = "Enable DNS support in VPC"
  default     = true
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources"
  default     = {}
}
