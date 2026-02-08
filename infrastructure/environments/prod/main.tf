# Production Environment - Main Configuration
# --------------------------------------------
# Provisions networking and S3 for prod environment

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0, < 6.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Data Sources
data "aws_caller_identity" "current" {}

# =============================================================================
# Variables
# =============================================================================

variable "project_name" {
  type        = string
  description = "Project identifier"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

# VPC Variables
variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
  default     = "10.0.0.0/16"
}

variable "availability_zones_count" {
  type        = number
  description = "Number of AZs"
  default     = 3
}

variable "single_nat_gateway" {
  type        = bool
  description = "Use single NAT gateway"
  default     = false
}

variable "enable_vpc_endpoints" {
  type        = bool
  description = "Enable VPC endpoints"
  default     = true
}

variable "enable_vpc_flow_logs" {
  type        = bool
  description = "Enable VPC flow logs"
  default     = true
}

variable "flow_log_retention_days" {
  type        = number
  description = "Flow log retention days"
  default     = 90
}

# S3 Variables
variable "enable_versioning" {
  type        = bool
  description = "Enable S3 versioning"
  default     = false
}

variable "enable_intelligent_tiering" {
  type        = bool
  description = "Enable intelligent tiering"
  default     = true
}

variable "enable_access_logging" {
  type        = bool
  description = "Enable S3 access logging"
  default     = true
}

variable "use_customer_managed_key" {
  type        = bool
  description = "Use CMK for S3"
  default     = true
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}

# =============================================================================
# Networking Module
# =============================================================================

module "networking" {
  source = "../../modules/networking"

  project_name             = var.project_name
  environment              = var.environment
  aws_region               = var.aws_region
  vpc_cidr                 = var.vpc_cidr
  availability_zones_count = var.availability_zones_count
  single_nat_gateway       = var.single_nat_gateway
  enable_vpc_endpoints     = var.enable_vpc_endpoints
  enable_vpc_flow_logs     = var.enable_vpc_flow_logs
  flow_log_retention_days  = var.flow_log_retention_days
  tags                     = var.tags
}

# =============================================================================
# S3 Module
# =============================================================================

module "s3" {
  source = "../../modules/s3"

  project_name               = var.project_name
  environment                = var.environment
  aws_region                 = var.aws_region
  aws_account_id             = data.aws_caller_identity.current.account_id
  enable_versioning          = var.enable_versioning
  enable_intelligent_tiering = var.enable_intelligent_tiering
  enable_access_logging      = var.enable_access_logging
  use_customer_managed_key   = var.use_customer_managed_key
  vpc_endpoint_id            = module.networking.s3_vpc_endpoint_id
  restrict_to_vpc_endpoint   = true
  force_destroy              = false
  tags                       = var.tags
}

# =============================================================================
# Outputs
# =============================================================================

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.networking.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "database_subnet_group_name" {
  description = "Database subnet group name"
  value       = module.networking.database_subnet_group_name
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = module.networking.alb_security_group_id
}

output "ecs_tasks_security_group_id" {
  description = "ECS tasks security group ID"
  value       = module.networking.ecs_tasks_security_group_id
}

output "aurora_security_group_id" {
  description = "Aurora security group ID"
  value       = module.networking.aurora_security_group_id
}

output "data_lake_bucket_name" {
  description = "S3 data lake bucket name"
  value       = module.s3.data_lake_bucket_name
}

output "data_lake_bucket_arn" {
  description = "S3 data lake bucket ARN"
  value       = module.s3.data_lake_bucket_arn
}

output "kms_key_arn" {
  description = "S3 KMS key ARN"
  value       = module.s3.kms_key_arn
}
