# Production Environment Variables
# ----------------------------------
# Override defaults for prod environment

project_name = "nlsql"
environment  = "prod"
aws_region   = "us-east-1"

# VPC Configuration - High Availability
vpc_cidr                 = "10.0.0.0/16"
availability_zones_count = 3
single_nat_gateway       = false

# Security and Compliance
enable_vpc_endpoints    = true
enable_vpc_flow_logs    = true
flow_log_retention_days = 90

# S3 Configuration - Full Features
enable_versioning          = false
enable_intelligent_tiering = true
enable_access_logging      = true
use_customer_managed_key   = true

# ECS Configuration
enable_ecs             = true
ecs_log_retention_days = 90
enable_execute_command = false  # Disable in prod for security
enable_https           = true
# certificate_arn      = "arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT-ID"

# Aurora Configuration
enable_aurora        = true
aurora_min_capacity  = 2
aurora_max_capacity  = 32
aurora_reader_count  = 1

# Common Tags
tags = {
  CostCenter  = "production"
  Owner       = "platform-team"
  Application = "nlsql-mas"
  Compliance  = "soc2"
}
