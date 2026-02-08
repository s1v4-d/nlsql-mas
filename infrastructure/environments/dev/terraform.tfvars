# Development Environment Variables
# -----------------------------------
# Override defaults for dev environment

project_name = "nlsql"
environment  = "dev"
aws_region   = "us-east-1"

# VPC Configuration
vpc_cidr                 = "10.2.0.0/16"
availability_zones_count = 2
single_nat_gateway       = true

# Cost Optimization
enable_vpc_endpoints = false
enable_vpc_flow_logs = true
flow_log_retention_days = 7

# S3 Configuration
enable_versioning          = false
enable_intelligent_tiering = false
enable_access_logging      = false
use_customer_managed_key   = false

# ECS Configuration (set to true to enable)
enable_ecs             = false
ecs_log_retention_days = 7
enable_execute_command = true

# Aurora Configuration (set to true to enable)
enable_aurora        = false
aurora_min_capacity  = 0.5
aurora_max_capacity  = 4

# Common Tags
tags = {
  CostCenter  = "engineering"
  Owner       = "dev-team"
  Application = "nlsql-mas"
}
