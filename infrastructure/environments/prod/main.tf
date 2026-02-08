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

# ECS Variables
variable "enable_ecs" {
  type        = bool
  description = "Enable ECS cluster"
  default     = true
}

variable "ecs_log_retention_days" {
  type        = number
  description = "ECS log retention days"
  default     = 90
}

variable "enable_execute_command" {
  type        = bool
  description = "Enable ECS Exec (disable in prod for security)"
  default     = false
}

variable "enable_https" {
  type        = bool
  description = "Enable HTTPS"
  default     = true
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN"
  default     = null
}

# Aurora Variables
variable "enable_aurora" {
  type        = bool
  description = "Enable Aurora PostgreSQL"
  default     = true
}

variable "aurora_min_capacity" {
  type        = number
  description = "Aurora min ACU"
  default     = 2
}

variable "aurora_max_capacity" {
  type        = number
  description = "Aurora max ACU"
  default     = 32
}

variable "aurora_reader_count" {
  type        = number
  description = "Aurora reader count"
  default     = 1
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
# ECS Module
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
  kms_key_arn                 = module.s3.kms_key_arn
  s3_data_bucket_arn          = module.s3.data_lake_bucket_arn
  log_retention_days          = var.ecs_log_retention_days
  enable_execute_command      = var.enable_execute_command

  # HTTPS configuration
  enable_https    = var.enable_https
  certificate_arn = var.certificate_arn

  # Prod-specific: Favor FARGATE over Spot for stability
  use_fargate_spot    = true
  fargate_weight      = 70
  fargate_spot_weight = 30
  fargate_base        = 1

  # Prod-specific: Higher capacity
  services = {
    api = {
      cpu               = 1024
      memory            = 2048
      container_port    = 8000
      health_check_path = "/health"
      min_capacity      = 2
      max_capacity      = 10
      desired_count     = 2
    }
    streamlit = {
      cpu               = 512
      memory            = 1024
      container_port    = 8501
      health_check_path = "/_stcore/health"
      min_capacity      = 1
      max_capacity      = 4
      desired_count     = 1
    }
  }

  tags = var.tags
}

# =============================================================================
# Aurora Module
# =============================================================================

module "aurora" {
  source = "../../modules/aurora"
  count  = var.enable_aurora ? 1 : 0

  project_name             = var.project_name
  environment              = var.environment
  aws_region               = var.aws_region
  vpc_id                   = module.networking.vpc_id
  database_subnet_ids      = module.networking.database_subnet_ids
  ecs_security_group_id    = module.networking.ecs_tasks_security_group_id
  aurora_security_group_id = module.networking.aurora_security_group_id
  kms_key_arn              = module.s3.kms_key_arn

  # Prod-specific: Higher capacity and redundancy
  min_capacity                   = var.aurora_min_capacity
  max_capacity                   = var.aurora_max_capacity
  storage_type                   = "aurora-iopt1"
  backup_retention_period        = 30
  skip_final_snapshot            = false
  deletion_protection            = true
  reader_count                   = var.aurora_reader_count
  performance_insights_enabled   = true
  performance_insights_retention = 731
  enhanced_monitoring_interval   = 15
  apply_immediately              = false

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

output "kms_key_arn" {
  description = "S3 KMS key ARN"
  value       = module.s3.kms_key_arn
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

output "ecs_alb_url" {
  description = "ECS ALB URL"
  value       = var.enable_ecs ? module.ecs[0].alb_url : null
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
