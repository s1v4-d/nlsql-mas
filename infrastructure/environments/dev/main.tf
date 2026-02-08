# Environment Configuration
# --------------------------
# Single environment setup - use tfvars to configure for dev/staging/prod

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
  default     = "10.2.0.0/16"
}

variable "availability_zones_count" {
  type        = number
  description = "Number of AZs"
  default     = 2
}

variable "single_nat_gateway" {
  type        = bool
  description = "Use single NAT gateway"
  default     = true
}

variable "enable_vpc_endpoints" {
  type        = bool
  description = "Enable VPC endpoints"
  default     = false
}

variable "enable_vpc_flow_logs" {
  type        = bool
  description = "Enable VPC flow logs"
  default     = true
}

variable "flow_log_retention_days" {
  type        = number
  description = "Flow log retention days"
  default     = 7
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
  default     = false
}

variable "enable_access_logging" {
  type        = bool
  description = "Enable S3 access logging"
  default     = false
}

variable "use_customer_managed_key" {
  type        = bool
  description = "Use CMK for S3"
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}

# ECS Variables
variable "enable_ecs" {
  type        = bool
  description = "Enable ECS cluster"
  default     = false
}

variable "ecs_log_retention_days" {
  type        = number
  description = "ECS log retention days"
  default     = 7
}

variable "enable_execute_command" {
  type        = bool
  description = "Enable ECS Exec"
  default     = true
}

# Aurora Variables
variable "enable_aurora" {
  type        = bool
  description = "Enable Aurora PostgreSQL"
  default     = false
}

variable "aurora_min_capacity" {
  type        = number
  description = "Aurora min ACU"
  default     = 0.5
}

variable "aurora_max_capacity" {
  type        = number
  description = "Aurora max ACU"
  default     = 4
}

# =============================================================================
# GitHub OIDC Module
# =============================================================================

variable "github_org" {
  type        = string
  description = "GitHub organization or user name"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository name"
}

variable "terraform_state_bucket" {
  type        = string
  description = "S3 bucket for Terraform state"
}

module "github_oidc" {
  source = "../../modules/github-oidc"

  project_name           = var.project_name
  environment            = var.environment
  github_org             = var.github_org
  github_repo            = var.github_repo
  terraform_state_bucket = var.terraform_state_bucket
  terraform_lock_table   = "terraform-locks"
  ecr_repository_arns    = var.enable_ecs ? values(module.ecs[0].ecr_repository_arns) : []
  ecs_cluster_arns       = var.enable_ecs ? [module.ecs[0].cluster_arn] : []
  s3_data_bucket_arn     = module.s3.data_lake_bucket_arn

  tags = var.tags
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
  force_destroy              = true
  tags                       = var.tags
}

# =============================================================================
# ECS Module (Optional)
# =============================================================================

module "ecs" {
  source = "../../modules/ecs"
  count  = var.enable_ecs ? 1 : 0

  project_name                = var.project_name
  environment                 = var.environment
  aws_region                  = var.aws_region
  vpc_id                      = module.networking.vpc_id
  private_subnet_ids          = module.networking.private_subnet_ids
  public_subnet_ids           = module.networking.public_subnet_ids
  alb_security_group_id       = module.networking.alb_security_group_id
  ecs_tasks_security_group_id = module.networking.ecs_tasks_security_group_id
  s3_data_bucket_arn          = module.s3.data_lake_bucket_arn
  log_retention_days          = var.ecs_log_retention_days
  enable_execute_command      = var.enable_execute_command

  # Dev-specific: Use Fargate Spot heavily
  use_fargate_spot    = true
  fargate_weight      = 20
  fargate_spot_weight = 80
  fargate_base        = 1

  # Dev-specific: Smaller capacity
  services = {
    api = {
      cpu               = 512
      memory            = 1024
      container_port    = 8000
      health_check_path = "/health"
      min_capacity      = 1
      max_capacity      = 2
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

  tags = var.tags
}

# =============================================================================
# Aurora Module (Optional)
# =============================================================================

module "aurora" {
  source = "../../modules/aurora"
  count  = var.enable_aurora ? 1 : 0

  project_name              = var.project_name
  environment               = var.environment
  aws_region                = var.aws_region
  vpc_id                    = module.networking.vpc_id
  database_subnet_ids       = module.networking.database_subnet_ids
  ecs_security_group_id     = module.networking.ecs_tasks_security_group_id
  aurora_security_group_id  = module.networking.aurora_security_group_id

  # Dev-specific: Cost optimization
  min_capacity                 = var.aurora_min_capacity
  max_capacity                 = var.aurora_max_capacity
  storage_type                 = "aurora"
  backup_retention_period      = 7
  skip_final_snapshot          = true
  deletion_protection          = false
  reader_count                 = 0
  performance_insights_enabled = true
  performance_insights_retention = 7
  enhanced_monitoring_interval = 60
  apply_immediately            = true

  tags = var.tags
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

# ECS Outputs (conditional)
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = var.enable_ecs ? module.ecs[0].cluster_name : null
}

output "ecs_alb_dns_name" {
  description = "ECS ALB DNS name"
  value       = var.enable_ecs ? module.ecs[0].alb_dns_name : null
}

output "ecr_repository_urls" {
  description = "ECR repository URLs"
  value       = var.enable_ecs ? module.ecs[0].ecr_repository_urls : null
}

# Aurora Outputs (conditional)
output "aurora_cluster_endpoint" {
  description = "Aurora cluster endpoint"
  value       = var.enable_aurora ? module.aurora[0].cluster_endpoint : null
}

output "aurora_reader_endpoint" {
  description = "Aurora reader endpoint"
  value       = var.enable_aurora ? module.aurora[0].cluster_reader_endpoint : null
}

output "aurora_app_credentials_secret_arn" {
  description = "Aurora app credentials secret ARN"
  value       = var.enable_aurora ? module.aurora[0].app_credentials_secret_arn : null
}

# GitHub OIDC Outputs
output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions"
  value       = module.github_oidc.github_actions_role_arn
}

output "terraform_role_arn" {
  description = "IAM role ARN for Terraform"
  value       = module.github_oidc.terraform_role_arn
}
